"""Red-first sitemap discovery, parsing, and SSRF tests (010-S F6.T5).

These tests pin the contract that F6.T6 (010.030-T) must satisfy when
implementing ``src/docline/fetch/sitemap.py``:

* expose ``SitemapError(DoclineError)``, ``SitemapEntry``,
  ``parse_sitemap_urlset``, ``parse_sitemap_index``,
  ``discover_sitemaps_from_robots``, and ``validate_sitemap_url``
* parse the ``<urlset>`` and ``<sitemapindex>`` XML grammars from
  ``sitemaps.org/protocol``
* extract ``Sitemap:`` directives from ``robots.txt``
* enforce SSRF defense-in-depth on ``validate_sitemap_url`` per the
  OWASP SSRF Prevention Cheat Sheet:
    - reject non-``http``/``https`` schemes
    - reject empty host
    - resolve the hostname via ``socket.getaddrinfo`` and check **every**
      resolved address against the private/loopback/link-local/multicast/
      reserved sets (defense against DNS rebinding)
    - reject explicit cloud-metadata endpoints
      (``169.254.169.254``, ``169.254.170.2``, ``fd00:ec2::254``,
      ``metadata.google.internal``)

These assertions are expected to **fail today** because
``src/docline/fetch/sitemap.py`` raises ``NotImplementedError`` from every
public callable. F6.T6 lands the real implementation and turns these red
tests green.
"""

from __future__ import annotations

from typing import Any

import pytest

from docline.fetch.sitemap import (
    SitemapEntry,
    SitemapError,
    discover_sitemaps_from_robots,
    parse_sitemap_index,
    parse_sitemap_urlset,
    validate_sitemap_url,
)
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _addrinfo(family: int, ip: str) -> tuple[int, int, int, str, tuple[Any, ...]]:
    """Build a ``getaddrinfo`` tuple shaped result for a single IP."""
    if family == 10:  # AF_INET6
        return (family, 1, 6, "", (ip, 0, 0, 0))
    return (family, 1, 6, "", (ip, 0))


def _mock_resolver(*results: tuple[int, str]) -> Any:
    """Return a ``getaddrinfo`` replacement that yields the given (family, ip) tuples."""

    def _fake_getaddrinfo(host: str, *_args: Any, **_kwargs: Any) -> list[Any]:
        return [_addrinfo(family, ip) for family, ip in results]

    return _fake_getaddrinfo


# ---------------------------------------------------------------------------
# Structural: types and error hierarchy
# ---------------------------------------------------------------------------


def test_sitemap_error_is_docline_error() -> None:
    """``SitemapError`` must subclass ``DoclineError``."""
    err = SitemapError("sitemap parse failed")
    assert isinstance(err, DoclineError)


def test_sitemap_entry_has_loc_and_lastmod_fields() -> None:
    """``SitemapEntry`` must carry ``loc`` and optional ``lastmod``."""
    entry = SitemapEntry(loc="https://example.com/page", lastmod="2026-01-01")
    assert entry.loc == "https://example.com/page"
    assert entry.lastmod == "2026-01-01"

    entry_no_lastmod = SitemapEntry(loc="https://example.com/other")
    assert entry_no_lastmod.lastmod is None


# ---------------------------------------------------------------------------
# Behavioral: urlset parsing
# ---------------------------------------------------------------------------


_URLSET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/a</loc>
    <lastmod>2026-01-01</lastmod>
  </url>
  <url>
    <loc>https://example.com/b</loc>
  </url>
</urlset>
"""


def test_parse_sitemap_urlset_yields_entries() -> None:
    entries = parse_sitemap_urlset(_URLSET_XML)
    assert len(entries) == 2
    assert entries[0].loc == "https://example.com/a"
    assert entries[0].lastmod == "2026-01-01"
    assert entries[1].loc == "https://example.com/b"
    assert entries[1].lastmod is None


def test_parse_sitemap_urlset_returns_tuple() -> None:
    """Result must be a tuple for hashability and immutability."""
    entries = parse_sitemap_urlset(_URLSET_XML)
    assert isinstance(entries, tuple)


def test_parse_sitemap_urlset_rejects_malformed_xml() -> None:
    with pytest.raises(SitemapError):
        parse_sitemap_urlset("not-xml<<")


# ---------------------------------------------------------------------------
# Behavioral: sitemap index parsing
# ---------------------------------------------------------------------------


_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>https://example.com/sitemap-1.xml</loc>
  </sitemap>
  <sitemap>
    <loc>https://example.com/sitemap-2.xml</loc>
  </sitemap>
</sitemapindex>
"""


def test_parse_sitemap_index_yields_child_urls() -> None:
    children = parse_sitemap_index(_INDEX_XML)
    assert children == (
        "https://example.com/sitemap-1.xml",
        "https://example.com/sitemap-2.xml",
    )


def test_parse_sitemap_index_rejects_urlset_content() -> None:
    """A ``<urlset>`` document is not a valid sitemap index."""
    with pytest.raises(SitemapError):
        parse_sitemap_index(_URLSET_XML)


# ---------------------------------------------------------------------------
# Behavioral: robots.txt discovery
# ---------------------------------------------------------------------------


def test_discover_sitemaps_from_robots_extracts_sitemap_directives() -> None:
    robots = (
        "User-agent: *\n"
        "Disallow: /admin\n"
        "Sitemap: https://example.com/sitemap.xml\n"
        "Sitemap: https://example.com/news-sitemap.xml\n"
    )
    sitemaps = discover_sitemaps_from_robots(robots)
    assert sitemaps == (
        "https://example.com/sitemap.xml",
        "https://example.com/news-sitemap.xml",
    )


def test_discover_sitemaps_from_robots_is_case_insensitive() -> None:
    """``Sitemap:`` directive matching must be case-insensitive."""
    robots = "sitemap: https://example.com/sitemap.xml\nSITEMAP: https://example.com/other.xml\n"
    sitemaps = discover_sitemaps_from_robots(robots)
    assert "https://example.com/sitemap.xml" in sitemaps
    assert "https://example.com/other.xml" in sitemaps


def test_discover_sitemaps_from_robots_returns_empty_when_absent() -> None:
    robots = "User-agent: *\nDisallow: /\n"
    assert discover_sitemaps_from_robots(robots) == ()


# ---------------------------------------------------------------------------
# Behavioral: SSRF — scheme and structural rejection
# ---------------------------------------------------------------------------


def test_validate_sitemap_url_rejects_empty_input() -> None:
    with pytest.raises(SitemapError):
        validate_sitemap_url("")


def test_validate_sitemap_url_rejects_non_http_scheme() -> None:
    for url in ("ftp://example.com/sitemap.xml", "file:///etc/passwd", "gopher://x"):
        with pytest.raises(SitemapError):
            validate_sitemap_url(url)


def test_validate_sitemap_url_rejects_missing_host() -> None:
    with pytest.raises(SitemapError):
        validate_sitemap_url("http:///sitemap.xml")


# ---------------------------------------------------------------------------
# Behavioral: SSRF — IP-literal rejection (no DNS needed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/sitemap.xml",  # loopback
        "http://10.0.0.1/sitemap.xml",  # RFC 1918 private
        "http://192.168.1.1/sitemap.xml",  # RFC 1918 private
        "http://172.16.0.1/sitemap.xml",  # RFC 1918 private
        "http://169.254.1.1/sitemap.xml",  # link-local
        "http://169.254.169.254/latest/meta-data/",  # AWS metadata
        "http://[::1]/sitemap.xml",  # IPv6 loopback
        "http://[fc00::1]/sitemap.xml",  # IPv6 unique-local
        "http://[fe80::1]/sitemap.xml",  # IPv6 link-local
    ],
)
def test_validate_sitemap_url_rejects_reserved_ip_literals(url: str) -> None:
    with pytest.raises(SitemapError):
        validate_sitemap_url(url)


# ---------------------------------------------------------------------------
# Behavioral: SSRF — DNS-based defense
# ---------------------------------------------------------------------------


def test_validate_sitemap_url_accepts_public_resolved_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hostname that resolves to only public IPs must pass."""
    monkeypatch.setattr(
        "socket.getaddrinfo",
        _mock_resolver((2, "93.184.216.34")),  # AF_INET, example.com public IP
    )
    result = validate_sitemap_url("https://example.com/sitemap.xml")
    assert result == "https://example.com/sitemap.xml"


def test_validate_sitemap_url_rejects_host_resolving_to_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("socket.getaddrinfo", _mock_resolver((2, "127.0.0.1")))
    with pytest.raises(SitemapError):
        validate_sitemap_url("https://evil.example/sitemap.xml")


def test_validate_sitemap_url_rejects_host_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("socket.getaddrinfo", _mock_resolver((2, "10.1.2.3")))
    with pytest.raises(SitemapError):
        validate_sitemap_url("https://intranet.example/sitemap.xml")


def test_validate_sitemap_url_rejects_host_resolving_to_metadata_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("socket.getaddrinfo", _mock_resolver((2, "169.254.169.254")))
    with pytest.raises(SitemapError):
        validate_sitemap_url("https://meta.example/latest/meta-data/")


def test_validate_sitemap_url_rejects_dns_rebinding_mixed_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense against DNS rebinding: if ANY resolved IP is unsafe, reject.

    The attacker controls DNS and returns one public IP plus one private IP.
    A naive implementation that checks only the first result would be bypassed.
    """
    monkeypatch.setattr(
        "socket.getaddrinfo",
        _mock_resolver((2, "8.8.8.8"), (2, "10.0.0.1")),
    )
    with pytest.raises(SitemapError):
        validate_sitemap_url("https://rebind.example/sitemap.xml")


def test_validate_sitemap_url_rejects_metadata_internal_hostnames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloud metadata hostnames must be rejected even before DNS resolution."""
    # Pretend resolver would return a public IP to prove name-based rejection runs first.
    monkeypatch.setattr("socket.getaddrinfo", _mock_resolver((2, "8.8.8.8")))
    for url in (
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://METADATA.GOOGLE.INTERNAL/x",
    ):
        with pytest.raises(SitemapError):
            validate_sitemap_url(url)


def test_validate_sitemap_url_rejects_when_dns_resolution_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DNS failure must raise ``SitemapError`` — do not silently fall through."""
    import socket

    def _raise(*_args: Any, **_kwargs: Any) -> list[Any]:
        raise socket.gaierror("no such host")

    monkeypatch.setattr("socket.getaddrinfo", _raise)
    with pytest.raises(SitemapError):
        validate_sitemap_url("https://nonexistent.invalid/sitemap.xml")
