"""HTTP fetch primitives with timeout enforcement."""

import asyncio
import http.client
from dataclasses import dataclass
from typing import IO
from urllib import error, request
from urllib.parse import urlparse

from docline.fetch.url_policy import validate_crawl_url
from docline.schema.models import DoclineError


class FetchTimeoutError(DoclineError):
    """Raised when an HTTP request exceeds its configured timeout."""


class FetchError(DoclineError):
    """Raised when an HTTP request fails for a non-timeout reason."""


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


class _ValidatingRedirectHandler(request.HTTPRedirectHandler):
    """Redirect handler that validates every target through URL policy.

    Enforces the caller-supplied ``max_redirects`` cap and rejects any
    redirect target that fails scheme or private-address validation.
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

        Args:
            req: The original request.
            fp: The response file object (unused).
            code: The HTTP status code.
            msg: The HTTP status message.
            headers: The response headers.
            newurl: The redirect target URL.

        Returns:
            A new :class:`~urllib.request.Request` for the redirect target,
            or ``None`` to abort the redirect.

        Raises:
            FetchError: When the redirect cap is exceeded.
            CrawlUrlRejectedError: When the redirect target fails URL policy.
        """
        self.redirect_count += 1
        if self.redirect_count > self._max_redirects:
            raise FetchError(
                f"Redirect cap of {self._max_redirects} exceeded"
                f" (attempted redirect #{self.redirect_count} to {newurl!r})"
            )
        # Re-validate every redirect target through URL policy to prevent
        # open-redirect SSRF (e.g. public URL → http://169.254.169.254/).
        validate_crawl_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


async def fetch_page(
    url: str,
    *,
    timeout_seconds: float = 30.0,
    max_redirects: int = 5,
) -> FetchResponse:
    """Fetch a single URL with timeout and redirect controls.

    Every redirect target is validated against the URL policy before being
    followed, and the total number of redirects is capped at *max_redirects*.

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
        opener = request.build_opener(handler)
        req = request.Request(validated_url, headers={"User-Agent": "docline-crawler/1.0"})
        with opener.open(req, timeout=timeout_seconds) as response:
            body_bytes = response.read()
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
    "FetchError",
    "FetchResponse",
    "FetchTimeoutError",
    "fetch_page",
]
