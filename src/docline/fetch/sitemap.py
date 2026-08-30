"""Sitemap discovery, parsing, and SSRF-resistant URL validation.

Implements the contract pinned by ``tests/fetch/test_sitemap.py``
(F6.T5/T6, tasks 010.029-T and 010.030-T):

* ``<urlset>`` and ``<sitemapindex>`` XML parsing (sitemaps.org protocol)
* ``Sitemap:`` directive extraction from ``robots.txt``
* SSRF defense-in-depth on :func:`validate_sitemap_url` per the OWASP
  SSRF Prevention Cheat Sheet:

    1. parse with :func:`urllib.parse.urlparse`
    2. reject non-``http``/``https`` schemes
    3. reject explicit cloud-metadata hostnames before resolution
    4. resolve hostname with :func:`socket.getaddrinfo` to enumerate
       **all** addresses (defense against DNS rebinding)
    5. classify every resolved address with the single canonical predicate
       :func:`docline.fetch.url_policy.is_unsafe_resolved_address`, which
       normalizes IPv4-mapped IPv6 addresses and rejects private, loopback,
       link-local, multicast, reserved, unspecified, cloud-metadata, CGNAT
       (``100.64.0.0/10``), ULA (``fc00::/7``), and site-local
       (``fec0::/10``) addresses

This module deliberately owns **no** address classifier of its own: it
delegates to ``url_policy`` so the live crawl path and the sitemap path can
never diverge on a security-critical predicate.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from docline.fetch.http import FetchResponse, FetchTimeoutError, fetch_page
from docline.fetch.url_policy import is_unsafe_resolved_address
from docline.schema.models import DoclineError

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_SITEMAP_NS: str = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Hostnames that point at cloud-metadata endpoints. Rejected before DNS
# resolution so an attacker cannot bypass with a public-IP A record.
_METADATA_HOSTNAMES: frozenset[str] = frozenset(
    {
        "metadata.google.internal",
        "metadata.aws.amazon.com",
        "metadata",
    }
)


class SitemapError(DoclineError):
    """Raised when sitemap discovery, parsing, or SSRF validation fails."""


@dataclass(frozen=True)
class SitemapEntry:
    """A single ``<url>`` entry inside a ``<urlset>`` sitemap.

    Attributes:
        loc: The ``<loc>`` URL.
        lastmod: Optional ISO-8601 ``<lastmod>`` value.
    """

    loc: str
    lastmod: str | None = None


def _qname(tag: str) -> str:
    return f"{{{_SITEMAP_NS}}}{tag}"


def parse_sitemap_urlset(content: str) -> tuple[SitemapEntry, ...]:
    """Parse a ``<urlset>`` sitemap document.

    Args:
        content: Raw XML body of the sitemap.

    Returns:
        Tuple of :class:`SitemapEntry`, preserving document order.

    Raises:
        SitemapError: If ``content`` is malformed XML or not a ``<urlset>``.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise SitemapError(f"sitemap is not valid XML: {exc}") from exc

    if root.tag != _qname("urlset"):
        raise SitemapError(
            f"expected <urlset> root, got <{root.tag}>; use parse_sitemap_index for indexes"
        )

    entries: list[SitemapEntry] = []
    for url_el in root.findall(_qname("url")):
        loc_el = url_el.find(_qname("loc"))
        if loc_el is None or loc_el.text is None or not loc_el.text.strip():
            continue
        lastmod_el = url_el.find(_qname("lastmod"))
        lastmod = (
            lastmod_el.text.strip()
            if lastmod_el is not None and lastmod_el.text is not None
            else None
        )
        entries.append(SitemapEntry(loc=loc_el.text.strip(), lastmod=lastmod))
    return tuple(entries)


def parse_sitemap_index(content: str) -> tuple[str, ...]:
    """Parse a ``<sitemapindex>`` document and return child sitemap URLs.

    Args:
        content: Raw XML body of the sitemap index.

    Returns:
        Tuple of ``<loc>`` URLs for each child ``<sitemap>``.

    Raises:
        SitemapError: If ``content`` is malformed XML or is not a sitemap
            index (for example, a ``<urlset>`` document).
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise SitemapError(f"sitemap index is not valid XML: {exc}") from exc

    if root.tag != _qname("sitemapindex"):
        raise SitemapError(
            f"expected <sitemapindex> root, got <{root.tag}>; use parse_sitemap_urlset for url sets"
        )

    children: list[str] = []
    for sm_el in root.findall(_qname("sitemap")):
        loc_el = sm_el.find(_qname("loc"))
        if loc_el is None or loc_el.text is None or not loc_el.text.strip():
            continue
        children.append(loc_el.text.strip())
    return tuple(children)


def discover_sitemaps_from_robots(robots_txt: str) -> tuple[str, ...]:
    """Extract ``Sitemap:`` directive URLs from a ``robots.txt`` body.

    Args:
        robots_txt: The raw ``robots.txt`` content.

    Returns:
        Tuple of sitemap URLs in document order. Empty when no
        ``Sitemap:`` directive is present.
    """
    sitemaps: list[str] = []
    for raw_line in robots_txt.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        if key.strip().lower() != "sitemap":
            continue
        url = value.strip()
        if url:
            sitemaps.append(url)
    return tuple(sitemaps)


def _resolve_all_addresses(host: str) -> tuple[str, ...]:
    """Return every IP address the resolver yields for ``host``.

    Raises:
        SitemapError: On any DNS lookup failure.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, OSError) as exc:
        raise SitemapError(f"DNS resolution failed for {host!r}: {exc}") from exc
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if isinstance(sockaddr, tuple) and sockaddr:
            ip = sockaddr[0]
            if isinstance(ip, str) and ip not in addresses:
                addresses.append(ip)
    if not addresses:
        raise SitemapError(f"DNS returned no addresses for {host!r}")
    return tuple(addresses)


def validate_sitemap_url(url: str) -> str:
    """Run the synchronous SSRF preflight for ``url`` and return it unchanged.

    This is a **preflight only**. Its resolution is advisory and deliberately
    non-authoritative: the returned value is the original URL, not a resolved
    address, so callers must not treat a passing preflight as permission to
    connect. Use :func:`fetch_sitemap` to retrieve a sitemap — it performs the
    authoritative resolve-validate-pin sequence atomically.

    Args:
        url: Candidate sitemap URL.

    Returns:
        ``url`` unchanged when every check passes.

    Raises:
        SitemapError: When the URL has a disallowed scheme, missing host,
            targets a cloud-metadata endpoint, or resolves to one or more
            unsafe addresses.
    """
    if not url:
        raise SitemapError("url must be a non-empty string")

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise SitemapError(f"scheme {parsed.scheme!r} is not http or https")

    host = (parsed.hostname or "").lower()
    if not host:
        raise SitemapError(f"url is missing a host: {url!r}")

    if host in _METADATA_HOSTNAMES:
        raise SitemapError(f"host {host!r} is a cloud-metadata endpoint")

    # IPv6 literals from urlparse arrive without brackets but with the
    # raw IPv6 form. Try direct classification first to skip DNS for
    # IP-literal URLs (and to catch IPv6 link-local / unique-local).
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if is_unsafe_resolved_address(str(literal)):
            raise SitemapError(f"host {host!r} resolves to a reserved address")
        return url

    addresses = _resolve_all_addresses(host)
    for addr in addresses:
        if is_unsafe_resolved_address(addr):
            raise SitemapError(
                f"host {host!r} resolves to unsafe address {addr!r} "
                "(SSRF guard, defense against DNS rebinding)"
            )
    return url


async def fetch_sitemap(
    url: str,
    *,
    timeout_seconds: float = 30.0,
    max_redirects: int = 5,
) -> FetchResponse:
    """Fetch a sitemap through the SSRF-hardened, address-pinned HTTP sink.

    This is the single authoritative sitemap retrieval path. It runs the
    synchronous preflight and then delegates to
    :func:`docline.fetch.http.fetch_page`, so resolution, address validation,
    connect, redirect revalidation, and proxy suppression happen as one atomic
    unit. The validated address is pinned for the outbound TCP connection while
    the original hostname is preserved for the ``Host`` header, TLS SNI, and
    certificate verification, which closes the validate-then-re-resolve
    (DNS-rebinding) window without weakening HTTPS.

    Args:
        url: The sitemap URL to retrieve.
        timeout_seconds: Per-request timeout in seconds.
        max_redirects: Maximum number of HTTP redirects to follow.

    Returns:
        The :class:`~docline.fetch.http.FetchResponse` for the sitemap.

    ``timeout_seconds`` bounds the whole operation, not just the HTTP fetch:
    the preflight performs a blocking :func:`socket.getaddrinfo` lookup, so it
    runs in the default executor (never on the event loop) under the same
    deadline, and the time it consumes is deducted from the budget handed to
    :func:`~docline.fetch.http.fetch_page`.

    Args:
        url: The sitemap URL to retrieve.
        timeout_seconds: Deadline in seconds for the preflight and fetch combined.
        max_redirects: Maximum number of HTTP redirects to follow.

    Returns:
        The :class:`~docline.fetch.http.FetchResponse` for the sitemap.

    Raises:
        SitemapError: When the preflight rejects ``url``.
        CrawlUrlRejectedError: When the URL or any redirect target resolves to
            an address the canonical predicate rejects.
        FetchTimeoutError: When the preflight or the request exceeds
            ``timeout_seconds``.
        FetchError: For non-timeout fetch failures or redirect-cap violations.
    """
    loop = asyncio.get_running_loop()
    started = time.monotonic()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, validate_sitemap_url, url),
            timeout=timeout_seconds,
        )
    except TimeoutError as err:
        raise FetchTimeoutError(
            f"Timed out validating {url} after {timeout_seconds} seconds"
        ) from err
    remaining = timeout_seconds - (time.monotonic() - started)
    if remaining <= 0:
        raise FetchTimeoutError(f"Timed out validating {url} after {timeout_seconds} seconds")
    return await fetch_page(
        url,
        timeout_seconds=remaining,
        max_redirects=max_redirects,
    )


__all__ = [
    "SitemapEntry",
    "SitemapError",
    "discover_sitemaps_from_robots",
    "fetch_sitemap",
    "parse_sitemap_index",
    "parse_sitemap_urlset",
    "validate_sitemap_url",
]
