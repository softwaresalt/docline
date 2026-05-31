"""HTTP fetch primitives with timeout enforcement."""

from dataclasses import dataclass

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
    raise NotImplementedError("stub: http.fetch_page not yet implemented")


__all__ = [
    "FetchError",
    "FetchResponse",
    "FetchTimeoutError",
    "fetch_page",
]
