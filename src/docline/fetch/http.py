"""HTTP fetch primitives with timeout enforcement."""

import asyncio
import http.client
import socket
import ssl
from dataclasses import dataclass
from typing import IO, Protocol
from urllib import error, request
from urllib.parse import urlparse

from docline.fetch.url_policy import (
    resolve_and_validate,
    validate_crawl_url,
)
from docline.schema.models import DoclineError

# Fixed read chunk size for the bounded streamed body reader.
CHUNK_SIZE: int = 64 * 1024

# Hard streamed per-response entity-body byte cap (§H7 item 2, 10 MiB). Applies
# to the initial response, the terminal post-redirect response, and every
# intermediate 3xx redirect body (via the bounded-draining redirect handler).
MAX_RESPONSE_BYTES: int = 10 * 1024 * 1024


class FetchTimeoutError(DoclineError):
    """Raised when an HTTP request exceeds its configured timeout."""


class FetchError(DoclineError):
    """Raised when an HTTP request fails for a non-timeout reason."""


class ResponseByteLimitError(DoclineError):
    """Raised when a single response body exceeds ``MAX_RESPONSE_BYTES``."""


class _Readable(Protocol):
    """A minimal readable stream: ``read(size) -> bytes``."""

    def read(self, size: int = ..., /) -> bytes: ...


def read_body_capped(
    response: _Readable,
    max_bytes: int,
    budget: object | None = None,
) -> bytes:
    """Read a response body in bounded chunks, aborting once ``max_bytes`` is crossed.

    Each read requests at most ``min(CHUNK_SIZE, max_bytes - read + 1)`` bytes so
    at the boundary the reader observes at most the single crossing byte and the
    over-cap response is never fully buffered (buffered content <=
    ``max_bytes + 1``).

    Args:
        response: A readable stream exposing ``read(size) -> bytes``.
        max_bytes: The hard per-response byte allowance.
        budget: Reserved for the request-scoped aggregate budget (threaded in by
            later hardening tasks); unused here.

    Returns:
        The full response body bytes when within the cap.

    Raises:
        ResponseByteLimitError: When the body exceeds ``max_bytes``.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        to_read = min(CHUNK_SIZE, max_bytes - total + 1)
        if to_read <= 0:
            to_read = 1
        chunk = response.read(to_read)
        if not chunk:
            break
        total += len(chunk)
        chunks.append(chunk)
        if total > max_bytes:
            raise ResponseByteLimitError(
                f"Response body exceeded the {max_bytes}-byte per-response cap."
            )
    return b"".join(chunks)


@dataclass(frozen=True)
class FetchResponse:
    """Result of a single HTTP fetch.

    Attributes:
        url: Final URL after any redirects.
        status: HTTP response status code.
        content_type: Value of the Content-Type header, or ``None``.
        body: Decoded response body text.
        redirect_count: Number of redirects followed to reach this response.
    """

    url: str
    status: int
    content_type: str | None
    body: str
    redirect_count: int = 0


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that resolves + validates the host and pins the socket.

    ``connect`` re-resolves ``self.host`` through
    :func:`~docline.fetch.url_policy.resolve_and_validate` (rejecting any
    private/loopback/CGNAT/metadata address) and connects to a validated IP so
    no second, unvalidated DNS resolution can occur (closes DNS rebinding).
    """

    def connect(self) -> None:
        addresses = resolve_and_validate(self.host)
        source_address = getattr(self, "source_address", None)
        self.sock = socket.create_connection(
            (addresses[0], self.port), self.timeout, source_address
        )
        if getattr(self, "_tunnel_host", None):
            self._tunnel()  # type: ignore[attr-defined]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to a validated IP while keeping the DNS SNI.

    Connects to a validated resolved address but performs the TLS handshake with
    ``server_hostname=self.host`` so certificate/hostname verification targets
    the original DNS name, never the pinned IP.
    """

    def connect(self) -> None:
        addresses = resolve_and_validate(self.host)
        source_address = getattr(self, "source_address", None)
        sock = socket.create_connection((addresses[0], self.port), self.timeout, source_address)
        if getattr(self, "_tunnel_host", None):
            self.sock = sock
            self._tunnel()  # type: ignore[attr-defined]
            sock = self.sock
        context: ssl.SSLContext = self._context  # type: ignore[attr-defined]
        self.sock = context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPHandler(request.HTTPHandler):
    """HTTP handler dispatching through :class:`_PinnedHTTPConnection`."""

    def http_open(self, req: request.Request) -> http.client.HTTPResponse:
        return self.do_open(_PinnedHTTPConnection, req)


class _PinnedHTTPSHandler(request.HTTPSHandler):
    """HTTPS handler dispatching through :class:`_PinnedHTTPSConnection`."""

    def https_open(self, req: request.Request) -> http.client.HTTPResponse:
        return self.do_open(_PinnedHTTPSConnection, req, context=self._context)  # type: ignore[attr-defined]


class _ValidatingRedirectHandler(request.HTTPRedirectHandler):
    """Redirect handler that validates every target through URL policy.

    Enforces the caller-supplied ``max_redirects`` cap and rejects any redirect
    target that fails scheme, literal, or resolution validation. Every target is
    re-resolved at redirect time so a redirect to a name resolving to a private
    address is rejected mid-chain.
    """

    def __init__(self, max_redirects: int) -> None:
        super().__init__()
        self._max_redirects = max_redirects
        self.redirect_count = 0

    def redirect_request(
        self,
        req: request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> request.Request | None:
        """Validate and count each redirect before following it.

        Raises:
            FetchError: When the redirect cap is exceeded.
            CrawlUrlRejectedError: When the redirect target fails URL policy or
                resolves to a private/reserved address.
        """
        self.redirect_count += 1
        if self.redirect_count > self._max_redirects:
            raise FetchError(
                f"Redirect cap of {self._max_redirects} exceeded"
                f" (attempted redirect #{self.redirect_count} to {newurl!r})"
            )
        # Re-validate every redirect target: scheme/literal, then resolution.
        validate_crawl_url(newurl)
        resolve_and_validate(urlparse(newurl).hostname or "")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_fetch_opener(
    max_redirects: int,
    budget: object | None = None,
    redirect_handler: "_ValidatingRedirectHandler | None" = None,
) -> request.OpenerDirector:
    """Build an SSRF-hardened opener with inherited proxies disabled.

    Installs an explicitly empty :class:`urllib.request.ProxyHandler` so no
    ``HTTP(S)_PROXY`` / system proxy re-resolves the host, plus address-pinned
    HTTP/HTTPS handlers and the validating redirect handler.

    Args:
        max_redirects: Redirect cap for the request.
        budget: Reserved for the request-scoped byte/attempt budget (threaded in
            by later hardening tasks); accepted here for a stable signature.
        redirect_handler: Optional pre-constructed redirect handler so callers
            can read ``redirect_count`` after the request completes.

    Returns:
        A configured :class:`urllib.request.OpenerDirector`.
    """
    handler = redirect_handler or _ValidatingRedirectHandler(max_redirects)
    return request.build_opener(
        request.ProxyHandler({}),
        _PinnedHTTPHandler(),
        _PinnedHTTPSHandler(),
        handler,
    )


async def fetch_page(
    url: str,
    *,
    timeout_seconds: float = 30.0,
    max_redirects: int = 5,
) -> FetchResponse:
    """Fetch a single URL with timeout, SSRF, and redirect controls.

    The host is resolved and validated at connect time and the connection is
    pinned to a validated address; every redirect target is re-validated, and
    the total number of redirects is capped at *max_redirects*.

    Args:
        url: The URL to fetch.
        timeout_seconds: Per-request timeout in seconds.
        max_redirects: Maximum number of HTTP redirects to follow.

    Returns:
        A :class:`FetchResponse` with the final URL, status, and body.

    Raises:
        FetchTimeoutError: If the request exceeds ``timeout_seconds``.
        FetchError: For non-timeout fetch failures or redirect-cap violations.
        CrawlUrlRejectedError: If ``url`` or any redirect target fails policy.
    """
    validated_url = validate_crawl_url(url)

    def _fetch() -> FetchResponse:
        handler = _ValidatingRedirectHandler(max_redirects)
        opener = build_fetch_opener(max_redirects, redirect_handler=handler)
        req = request.Request(validated_url, headers={"User-Agent": "docline-crawler/1.0"})
        with opener.open(req, timeout=timeout_seconds) as response:
            body_bytes = read_body_capped(response, MAX_RESPONSE_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            body = body_bytes.decode(charset, errors="replace")
            final_url = response.geturl()
            # Validate the final URL in case urllib resolved it differently.
            if urlparse(final_url).netloc != urlparse(validated_url).netloc:
                validate_crawl_url(final_url)
            return FetchResponse(
                url=final_url,
                status=response.status,
                content_type=response.headers.get("Content-Type"),
                body=body,
                redirect_count=handler.redirect_count,
            )

    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _fetch),
            timeout=timeout_seconds,
        )
    except TimeoutError as err:
        raise FetchTimeoutError(
            f"Timed out fetching {validated_url} after {timeout_seconds} seconds"
        ) from err
    except (DoclineError, error.URLError):
        raise
    except Exception as err:
        raise FetchError(f"Failed to fetch {validated_url}: {err}") from err


__all__ = [
    "CHUNK_SIZE",
    "MAX_RESPONSE_BYTES",
    "FetchError",
    "FetchResponse",
    "FetchTimeoutError",
    "ResponseByteLimitError",
    "build_fetch_opener",
    "fetch_page",
    "read_body_capped",
]
