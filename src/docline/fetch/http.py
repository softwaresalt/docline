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


class AggregateBudgetExceededError(DoclineError):
    """Raised when a request-scoped aggregate fetch budget is exhausted."""


# Byte-accurate aggregate per-request crawl budget (§H7 item 3, 512 MiB) over
# undecoded entity-body bytes; and the per-request outbound fetch-attempt cap
# (§H7 item 4, request COUNT not byte VOLUME).
MAX_TOTAL_FETCH_BYTES: int = 512 * 1024 * 1024
MAX_FETCH_ATTEMPTS: int = 4 * 1000


class FetchAttemptBudgetExceededError(AggregateBudgetExceededError):
    """Raised when the per-request outbound fetch-attempt budget is exhausted.

    Subclasses :class:`AggregateBudgetExceededError` so the existing
    ``crawl.py`` re-raise clauses propagate it out of ``crawl()``.
    """


class RemainingByteBudget:
    """A request-scoped remaining byte + fetch-attempt allowance.

    Threaded through every ``fetch_page`` call for a crawl request and
    decremented while entity-body bytes are read, so a crossing response aborts
    mid-read. ``None`` allowances mean unbounded (standalone single fetch).
    """

    def __init__(self, total_bytes: int | None, max_attempts: int | None = None) -> None:
        self.remaining = total_bytes
        self.attempts_remaining = max_attempts

    def read_cap(self, base_cap: int) -> int:
        """Return the per-read cap, bounded by the remaining aggregate allowance."""
        if self.remaining is None:
            return base_cap
        return min(base_cap, self.remaining + 1)

    def debit_bytes(self, count: int) -> None:
        """Debit ``count`` entity-body bytes, aborting if the allowance is crossed."""
        if self.remaining is None:
            return
        self.remaining -= count
        if self.remaining < 0:
            raise AggregateBudgetExceededError(
                "Aggregate crawl byte budget exceeded during response read."
            )

    def debit_attempt(self) -> None:
        """Debit one outbound fetch attempt, aborting if the attempt cap is crossed."""
        if self.attempts_remaining is None:
            return
        if self.attempts_remaining <= 0:
            raise FetchAttemptBudgetExceededError(
                "Aggregate outbound fetch-attempt budget exceeded."
            )
        self.attempts_remaining -= 1


class _Readable(Protocol):
    """A minimal readable stream: ``read(size) -> bytes``."""

    def read(self, size: int = ..., /) -> bytes: ...


def read_body_capped(
    response: _Readable,
    max_bytes: int,
    budget: "RemainingByteBudget | None" = None,
) -> bytes:
    """Read a response body in bounded chunks, aborting once a cap is crossed.

    Each read requests at most
    ``min(CHUNK_SIZE, max_bytes - read + 1, aggregate_remaining + 1)`` bytes so at
    either boundary the reader observes at most the single crossing byte and the
    over-cap response is never fully buffered.

    Args:
        response: A readable stream exposing ``read(size) -> bytes``.
        max_bytes: The hard per-response byte allowance.
        budget: Optional request-scoped aggregate byte budget, decremented per
            chunk while bytes are read.

    Returns:
        The full response body bytes when within both caps.

    Raises:
        ResponseByteLimitError: When the body exceeds ``max_bytes``.
        AggregateBudgetExceededError: When the request-scoped budget is crossed.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        to_read = min(CHUNK_SIZE, max_bytes - total + 1)
        if budget is not None:
            to_read = min(to_read, budget.read_cap(CHUNK_SIZE))
        if to_read <= 0:
            to_read = 1
        chunk = response.read(to_read)
        if not chunk:
            break
        total += len(chunk)
        chunks.append(chunk)
        if budget is not None:
            budget.debit_bytes(len(chunk))
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
        body_byte_count: Undecoded entity-body byte length (observability only).
    """

    url: str
    status: int
    content_type: str | None
    body: str
    redirect_count: int = 0
    body_byte_count: int = 0


def _connect_validated_address(
    host: str, port: int, timeout: float | None, source_address: tuple[str, int] | None
) -> socket.socket:
    """Connect to the first reachable validated address for ``host``.

    Resolves and validates ``host`` once (rejecting private/loopback/CGNAT/
    metadata addresses), then tries each validated address in order so a
    multi-address or dual-stack host is not defeated by a single unreachable —
    but validated — answer. No second, unvalidated DNS resolution occurs, so DNS
    rebinding stays closed.

    Args:
        host: The DNS hostname to resolve and validate.
        port: The destination port.
        timeout: The per-attempt connection timeout.
        source_address: Optional bind source address.

    Returns:
        A connected socket to a validated address.

    Raises:
        OSError: If every validated address is unreachable (last error re-raised).
        CrawlUrlRejectedError: If resolution/validation rejects the host.
    """
    addresses = resolve_and_validate(host)
    last_error: OSError | None = None
    for address in addresses:
        try:
            return socket.create_connection((address, port), timeout, source_address)
        except OSError as err:
            last_error = err
    # resolve_and_validate guarantees a non-empty list, so last_error is set.
    assert last_error is not None
    raise last_error


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that resolves + validates the host and pins the socket.

    ``connect`` re-resolves ``self.host`` through
    :func:`~docline.fetch.url_policy.resolve_and_validate` (rejecting any
    private/loopback/CGNAT/metadata address) and connects to a validated IP so
    no second, unvalidated DNS resolution can occur (closes DNS rebinding).
    """

    def connect(self) -> None:
        source_address = getattr(self, "source_address", None)
        self.sock = _connect_validated_address(self.host, self.port, self.timeout, source_address)
        if getattr(self, "_tunnel_host", None):
            self._tunnel()  # type: ignore[attr-defined]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to a validated IP while keeping the DNS SNI.

    Connects to a validated resolved address but performs the TLS handshake with
    ``server_hostname=self.host`` so certificate/hostname verification targets
    the original DNS name, never the pinned IP.
    """

    def connect(self) -> None:
        source_address = getattr(self, "source_address", None)
        sock = _connect_validated_address(self.host, self.port, self.timeout, source_address)
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


class _BoundedFpProxy:
    """Wraps an intermediate 3xx response fp so its body drain is bounded.

    ``read`` streams the wrapped fp through :func:`read_body_capped` (per-response
    cap + aggregate budget), so an intermediate redirect body cannot bypass the
    caps via urllib's in-handler unbounded ``fp.read()``.
    """

    def __init__(self, fp: IO[bytes], max_bytes: int, budget: "RemainingByteBudget | None") -> None:
        self._fp = fp
        self._max_bytes = max_bytes
        self._budget = budget

    def read(self, amt: int | None = None) -> bytes:
        return read_body_capped(self._fp, self._max_bytes, self._budget)

    def close(self) -> None:
        self._fp.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self._fp, name)


class _ValidatingRedirectHandler(request.HTTPRedirectHandler):
    """Redirect handler that validates every target and bounds intermediate bodies.

    Enforces the caller-supplied ``max_redirects`` cap, rejects any redirect
    target that fails scheme/literal/resolution validation (re-resolved at
    redirect time), AND bounded-drains every intermediate 3xx body through the
    per-response + aggregate caps, closing the intermediate connection on every
    cap-breach or ``redirect_request``-raised exit so no socket leaks.
    """

    def __init__(self, max_redirects: int, budget: "RemainingByteBudget | None" = None) -> None:
        super().__init__()
        self._max_redirects = max_redirects
        self._budget = budget
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
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and self._budget is not None:
            # Debit one attempt per FOLLOWED hop, after validation and before the
            # hop's outbound I/O (§H7 item 4a); a rejected redirect debits nothing.
            self._budget.debit_attempt()
        return new

    def http_error_302(
        self,
        req: request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
    ) -> object:
        """Bounded-drain the intermediate body and close its fp on any breach.

        Wraps ``fp`` in a bounded proxy and delegates to the stdlib handler so
        the existing §H6 revalidation, ``max_redirects`` count, and Location/
        loop/scheme logic are unchanged, while the intermediate body is read
        through the per-response + aggregate caps. On any cap-breach or
        ``redirect_request``-raised exit the real ``fp`` is closed before the
        typed error propagates (stdlib closes it only after a completed read).
        """
        proxy = _BoundedFpProxy(fp, MAX_RESPONSE_BYTES, self._budget)
        try:
            return super().http_error_302(req, proxy, code, msg, headers)  # type: ignore[arg-type]
        except Exception:
            # Close the real fp on ANY failure path (cap breach, revalidation
            # reject, redirect-loop/malformed-Location HTTPError/ValueError) so no
            # intermediate socket leaks; the stdlib closes it only after a
            # completed read. fp.close() is idempotent.
            fp.close()
            raise

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def build_fetch_opener(
    max_redirects: int,
    budget: "RemainingByteBudget | None" = None,
    redirect_handler: "_ValidatingRedirectHandler | None" = None,
) -> request.OpenerDirector:
    """Build an SSRF-hardened opener with inherited proxies disabled.

    Installs an explicitly empty :class:`urllib.request.ProxyHandler` so no
    ``HTTP(S)_PROXY`` / system proxy re-resolves the host, plus address-pinned
    HTTP/HTTPS handlers and the validating redirect handler.

    Args:
        max_redirects: Redirect cap for the request.
        budget: The request-scoped remaining byte/attempt budget threaded into the
            redirect handler, which enforces the aggregate-byte and redirect-attempt
            limits (§H7). ``None`` disables aggregate budgeting for this opener.
        redirect_handler: Optional pre-constructed redirect handler so callers
            can read ``redirect_count`` after the request completes.

    Returns:
        A configured :class:`urllib.request.OpenerDirector`.
    """
    handler = redirect_handler or _ValidatingRedirectHandler(max_redirects, budget=budget)
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
    budget: "RemainingByteBudget | None" = None,
) -> FetchResponse:
    """Fetch a single URL with timeout, SSRF, and redirect controls.

    The host is resolved and validated at connect time and the connection is
    pinned to a validated address; every redirect target is re-validated, and
    the total number of redirects is capped at *max_redirects*.

    Args:
        url: The URL to fetch.
        timeout_seconds: Per-request timeout in seconds.
        max_redirects: Maximum number of HTTP redirects to follow.
        budget: Optional request-scoped byte/attempt budget decremented while
            entity-body bytes are read and once per outbound attempt.

    Returns:
        A :class:`FetchResponse` with the final URL, status, and body.

    Raises:
        FetchTimeoutError: If the request exceeds ``timeout_seconds``.
        FetchError: For non-timeout fetch failures or redirect-cap violations.
        CrawlUrlRejectedError: If ``url`` or any redirect target fails policy.
        AggregateBudgetExceededError: If the request-scoped budget is exhausted.
    """
    validated_url = validate_crawl_url(url)
    if budget is not None:
        # Debit one outbound attempt at the common boundary BEFORE any I/O so
        # main-page, robots, TOC, and retry traffic all count (§H7 item 4a).
        budget.debit_attempt()

    def _fetch() -> FetchResponse:
        handler = _ValidatingRedirectHandler(max_redirects, budget=budget)
        opener = build_fetch_opener(max_redirects, budget=budget, redirect_handler=handler)
        req = request.Request(validated_url, headers={"User-Agent": "docline-crawler/1.0"})
        with opener.open(req, timeout=timeout_seconds) as response:
            body_bytes = read_body_capped(response, MAX_RESPONSE_BYTES, budget=budget)
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
                body_byte_count=len(body_bytes),
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
    "MAX_TOTAL_FETCH_BYTES",
    "MAX_FETCH_ATTEMPTS",
    "AggregateBudgetExceededError",
    "FetchAttemptBudgetExceededError",
    "FetchError",
    "FetchResponse",
    "FetchTimeoutError",
    "RemainingByteBudget",
    "ResponseByteLimitError",
    "build_fetch_opener",
    "fetch_page",
    "read_body_capped",
]
