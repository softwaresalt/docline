"""Crawl URL policy enforcement — scheme allow-list and SSRF rejection."""

from docline.schema.models import DoclineError

_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Maximum number of HTTP redirects followed per crawl request.
MAX_REDIRECTS: int = 5


class CrawlUrlRejectedError(DoclineError):
    """Raised when a crawl URL is rejected by policy."""


def validate_crawl_url(url: str) -> str:
    """Validate a URL against the crawl policy and return it unchanged if safe.

    Enforcement order:

    1. Scheme must be ``http`` or ``https``.
    2. Host must not be empty.
    3. Host must not resolve to a loopback, link-local, or private address
       (RFC 1918 / RFC 4193 / metadata services).

    Args:
        url: The URL string to validate.

    Returns:
        The original URL string when all policy checks pass.

    Raises:
        CrawlUrlRejectedError: When the URL violates any policy rule.
    """
    raise NotImplementedError("stub: url_policy.validate_crawl_url not yet implemented")


def is_private_host(host: str) -> bool:
    """Return ``True`` if *host* is a loopback, private, or link-local address.

    Covers IPv4 and IPv6 literals.  Hostname strings (e.g. ``localhost``) are
    matched by name only; DNS resolution is intentionally **not** performed
    here — callers that need post-resolution checks must resolve first and
    then call this function on the resolved IP string.

    Args:
        host: A hostname or IP address string (no port, no brackets for IPv6).

    Returns:
        ``True`` when the host is a reserved address class.
    """
    raise NotImplementedError("stub: url_policy.is_private_host not yet implemented")


def assert_redirect_count(count: int) -> None:
    """Raise if a redirect chain exceeds the allowed cap.

    Args:
        count: Number of redirects followed so far.

    Raises:
        CrawlUrlRejectedError: When ``count`` exceeds :data:`MAX_REDIRECTS`.
    """
    raise NotImplementedError("stub: url_policy.assert_redirect_count not yet implemented")


__all__ = [
    "CrawlUrlRejectedError",
    "MAX_REDIRECTS",
    "assert_redirect_count",
    "is_private_host",
    "validate_crawl_url",
]
