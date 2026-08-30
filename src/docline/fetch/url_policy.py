"""Crawl URL policy enforcement — scheme allow-list and SSRF rejection."""

import ipaddress
import socket
from urllib.parse import urlparse

from docline.schema.models import DoclineError

_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Maximum number of HTTP redirects followed per crawl request.
MAX_REDIRECTS: int = 5

# Cloud-metadata endpoints rejected after parse and normalization. Stored as
# parsed ``ipaddress`` objects so alternate spellings of the same address
# (IPv4-mapped, expanded, uppercase) cannot bypass the membership check.
_METADATA_IPS: frozenset[ipaddress.IPv4Address | ipaddress.IPv6Address] = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),  # AWS, GCP, Azure IMDS
        ipaddress.ip_address("169.254.170.2"),  # ECS task metadata
        ipaddress.ip_address("fd00:ec2::254"),  # AWS IPv6 IMDS
    }
)

# Carrier-grade NAT (CGNAT) shared address space, RFC 6598 — not flagged by any
# ``ipaddress`` special-use property on Python 3.12.x; rejected explicitly.
_CGNAT_NETWORK: ipaddress.IPv4Network = ipaddress.IPv4Network("100.64.0.0/10")

# Unique-local IPv6 addresses (RFC 4193), fc00::/7 — rejected explicitly.
_ULA_NETWORK: ipaddress.IPv6Network = ipaddress.IPv6Network("fc00::/7")

# Site-local IPv6 addresses (deprecated by RFC 3879), fec0::/10. Reported by
# ``IPv6Address.is_site_local`` but by none of the six special-use flags the
# predicate relies on; rejected via explicit membership.
_SITE_LOCAL_NETWORK: ipaddress.IPv6Network = ipaddress.IPv6Network("fec0::/10")


class CrawlUrlRejectedError(DoclineError):
    """Raised when a crawl URL is rejected by policy."""


def is_unsafe_resolved_address(addr: str) -> bool:
    """Return ``True`` when a resolved IP is not a global public-unicast address.

    This is the single canonical unsafe-address classifier for the package;
    :mod:`docline.fetch.sitemap` and :mod:`docline.fetch.http` both consume it
    so an address-class fix can never land in one surface and be forgotten in
    another.

    Fails closed: an unclassifiable address is treated as unsafe. Classification
    combines the six :mod:`ipaddress` special-use flags with explicit network
    membership for the classes those flags miss — cloud metadata, CGNAT
    (``100.64.0.0/10``), ULA (``fc00::/7``), and site-local (``fec0::/10``).

    The CVE-2024-4032-affected prefixes are deliberately **not** rejected
    wholesale: they retain documented globally-reachable exceptions (for example
    ``192.0.0.9``, ``192.0.0.10``, and reachable ``2001::/23`` subranges) that a
    blanket reject would break. The mitigation is the ``requires-python >=
    3.12.4`` floor, which guarantees the corrected CPython classification tables
    back the flag checks below.

    Args:
        addr: A resolved IP address literal.

    Returns:
        ``True`` when the address must not be connected to.
    """
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return True
    # Normalize an IPv4-mapped IPv6 literal to its embedded IPv4 form before
    # classification so the flag checks, the metadata membership test, and
    # CGNAT membership all see the real class.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip in _METADATA_IPS:
        return True
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    if isinstance(ip, ipaddress.IPv4Address):
        return ip in _CGNAT_NETWORK
    return ip in _ULA_NETWORK or ip in _SITE_LOCAL_NETWORK


def resolve_and_validate(host: str) -> list[str]:
    """Resolve ``host`` and reject if any resolved address is unsafe.

    Enumerates every ``getaddrinfo`` answer (all A/AAAA records) so a
    DNS-rebinding record set with even one private address is rejected as a
    whole, then returns the validated address set for address-pinned connect.

    Args:
        host: A hostname or IP literal (no port, no brackets).

    Returns:
        The list of validated public-unicast IP addresses.

    Raises:
        CrawlUrlRejectedError: When resolution fails, returns no address, or any
            resolved address is not a global public-unicast address.
    """
    if not host:
        raise CrawlUrlRejectedError("URL has no host component.")
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror) as err:
        raise CrawlUrlRejectedError(f"DNS resolution failed for host {host!r}.") from err
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if isinstance(sockaddr, tuple) and sockaddr:
            ip = sockaddr[0]
            if isinstance(ip, str) and ip not in addresses:
                addresses.append(ip)
    if not addresses:
        raise CrawlUrlRejectedError(f"DNS returned no addresses for host {host!r}.")
    for addr in addresses:
        if is_unsafe_resolved_address(addr):
            raise CrawlUrlRejectedError(f"Host {host!r} resolves to a reserved or private address.")
    return addresses


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
    "is_unsafe_resolved_address",
    "resolve_and_validate",
    "validate_crawl_url",
]
