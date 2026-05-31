"""Crawl URL policy enforcement — scheme allow-list and SSRF rejection."""

import ipaddress
from urllib.parse import urlparse

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
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise CrawlUrlRejectedError(
            f"Scheme '{parsed.scheme}' is not allowed; only http and https are permitted."
        )
    host = parsed.hostname or ""
    if not host:
        raise CrawlUrlRejectedError("URL has no host component.")
    if is_private_host(host):
        raise CrawlUrlRejectedError(f"Host '{host}' resolves to a reserved or private address.")
    return url


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
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_loopback or addr.is_private or addr.is_link_local
    except ValueError:
        return host.lower() == "localhost"


def assert_redirect_count(count: int) -> None:
    """Raise if a redirect chain exceeds the allowed cap.

    Args:
        count: Number of redirects followed so far.

    Raises:
        CrawlUrlRejectedError: When ``count`` exceeds :data:`MAX_REDIRECTS`.
    """
    if count > MAX_REDIRECTS:
        raise CrawlUrlRejectedError(
            f"Redirect chain length {count} exceeds the maximum of {MAX_REDIRECTS}."
        )


__all__ = [
    "CrawlUrlRejectedError",
    "MAX_REDIRECTS",
    "assert_redirect_count",
    "is_private_host",
    "validate_crawl_url",
]
