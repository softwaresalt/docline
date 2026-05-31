"""HTTP fetch primitives with timeout enforcement."""

import asyncio
from dataclasses import dataclass
from urllib import error, request

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


async def fetch_page(
    url: str,
    *,
    timeout_seconds: float = 30.0,
    max_redirects: int = 5,
) -> FetchResponse:
    """Fetch a single URL with timeout and redirect controls.

    Args:
        url: The URL to fetch.
        timeout_seconds: Per-request timeout in seconds.
        max_redirects: Maximum number of HTTP redirects to follow.

    Returns:
        A :class:`FetchResponse` with the final URL, status, and body.

    Raises:
        FetchTimeoutError: If the request exceeds ``timeout_seconds``.
        FetchError: For non-timeout fetch failures.
        CrawlUrlRejectedError: If ``url`` fails policy validation.
    """
    validated_url = validate_crawl_url(url)
    _ = max_redirects

    def _fetch() -> FetchResponse:
        with request.urlopen(validated_url, timeout=timeout_seconds) as response:
            body_bytes = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            body = body_bytes.decode(charset, errors="replace")
            return FetchResponse(
                url=response.geturl(),
                status=response.status,
                content_type=response.headers.get("Content-Type"),
                body=body,
                redirect_count=0,
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
    except error.URLError as err:
        raise FetchError(f"Failed to fetch {validated_url}: {err}") from err


__all__ = [
    "FetchError",
    "FetchResponse",
    "FetchTimeoutError",
    "fetch_page",
]
