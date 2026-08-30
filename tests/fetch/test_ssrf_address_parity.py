"""Canonical unsafe-address predicate class-parity harness (066.001-T, red).

Pins the SSRF address classifier contract that 066.002-T greens:

* every rejected address class is asserted by concrete literal rather than by
  replaying the :mod:`ipaddress` flag table, so a future flag-table change
  cannot silently widen the accept set
* ``sitemap`` and ``url_policy`` consume **one** shared predicate (delegation
  identity), so an address-class fix can never land in one copy and be
  forgotten in the other
* an unparseable address is unsafe (fail closed)
* the documented globally-reachable exceptions inside the
  CVE-2024-4032-affected prefixes stay **accepted**, so the mitigation (the
  ``requires-python >= 3.12.4`` runtime floor from 066.007-T) never turns into
  a wholesale over-block of valid public-unicast destinations

Red against the pre-consolidation tree: ``url_policy`` misses IPv6 site-local
``fec0::/10`` and ``sitemap`` still carries its own divergent duplicate.
"""

from __future__ import annotations

import pytest

from docline.fetch import sitemap as sitemap_module
from docline.fetch import url_policy as url_policy_module
from docline.fetch.sitemap import SitemapError, validate_sitemap_url
from docline.fetch.url_policy import is_unsafe_resolved_address

# Every address class the canonical predicate must reject, pinned by concrete
# literal. ``id`` names the class so a parametrized failure reports which class
# regressed rather than only an opaque address.
_REJECTED: tuple[tuple[str, str], ...] = (
    ("private-rfc1918-10", "10.0.0.5"),
    ("private-rfc1918-172", "172.16.0.1"),
    ("private-rfc1918-192", "192.168.1.1"),
    ("private-ula-fc00-low", "fc00::1"),
    ("private-ula-fdff-high", "fdff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"),
    ("loopback-ipv4", "127.0.0.1"),
    ("loopback-ipv6", "::1"),
    ("link-local-ipv4", "169.254.1.1"),
    ("link-local-ipv6", "fe80::1"),
    ("multicast-ipv4", "224.0.0.1"),
    ("multicast-ipv6", "ff02::1"),
    ("reserved-ipv4", "240.0.0.1"),
    ("unspecified-ipv4", "0.0.0.0"),
    ("unspecified-ipv6", "::"),
    ("cgnat-rfc6598-low", "100.64.0.1"),
    ("cgnat-rfc6598-high", "100.127.255.254"),
    ("site-local-fec0-low", "fec0::1"),
    ("site-local-feff-high", "feff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"),
    ("metadata-imds-ipv4", "169.254.169.254"),
    ("metadata-ecs-task", "169.254.170.2"),
    ("metadata-imds-ipv6", "fd00:ec2::254"),
    ("ipv4-mapped-loopback", "::ffff:127.0.0.1"),
    ("ipv4-mapped-cgnat", "::ffff:100.64.0.1"),
)

# Documented globally-reachable exceptions inside the CVE-2024-4032-affected
# prefixes. These classify correctly only under the 066.007-T runtime floor
# (``requires-python >= 3.12.4``); rejecting them would break valid
# public-unicast destinations, so the predicate must NOT hand-roll a wholesale
# rejection of the affected prefixes.
_MUST_NOT_REJECT: tuple[str, ...] = (
    "192.0.0.9",
    "192.0.0.10",
    "2001:1::1",
    "2001:1::2",
    "2001:3::1",
    "2001:4:112::1",
    "2001:20::1",
    "2001:30::1",
)

# Ordinary public-unicast controls, so an over-tightened predicate that rejects
# everything cannot pass the guard above by accident.
_ORDINARY_PUBLIC: tuple[str, ...] = (
    "93.184.216.34",
    "2606:2800:220:1:248:1893:25c8:1946",
)


@pytest.mark.parametrize(
    "address",
    [pytest.param(addr, id=name) for name, addr in _REJECTED],
)
def test_canonical_predicate_rejects_every_unsafe_class(address: str) -> None:
    """Every pinned unsafe address class is rejected by the canonical predicate."""
    assert is_unsafe_resolved_address(address) is True


@pytest.mark.parametrize("address", _MUST_NOT_REJECT)
def test_cve_2024_4032_exceptions_are_not_over_blocked(address: str) -> None:
    """Globally-reachable CVE-2024-4032 exceptions stay accepted (over-block guard)."""
    assert is_unsafe_resolved_address(address) is False


@pytest.mark.parametrize("address", _ORDINARY_PUBLIC)
def test_ordinary_public_unicast_is_accepted(address: str) -> None:
    """Ordinary public-unicast addresses stay accepted."""
    assert is_unsafe_resolved_address(address) is False


@pytest.mark.parametrize(
    "value",
    [
        "not-an-ip",
        "",
        "example.com",
        "10.0.0.0/8",
        "fc00::/7",
        "999.1.1.1",
        "::ffff:999.1.1.1",
        "127.0.0.1:80",
        "[::1]",
    ],
)
def test_unparseable_address_fails_closed(value: str) -> None:
    """An address the predicate cannot classify is treated as unsafe."""
    assert is_unsafe_resolved_address(value) is True


def test_sitemap_delegates_to_the_canonical_predicate() -> None:
    """``sitemap`` consumes the same predicate object as ``url_policy``."""
    assert sitemap_module.is_unsafe_resolved_address is url_policy_module.is_unsafe_resolved_address


@pytest.mark.parametrize("attribute", ["_is_unsafe_address", "_METADATA_IPS", "_CGNAT_NETWORK"])
def test_sitemap_duplicate_classifier_state_is_removed(attribute: str) -> None:
    """The divergent duplicate predicate and its constants no longer exist in ``sitemap``."""
    assert not hasattr(sitemap_module, attribute)


@pytest.mark.parametrize(
    "address",
    [
        pytest.param(addr, id=name)
        for name, addr in _REJECTED
        if ":" in addr or addr.count(".") == 3
    ],
)
def test_sitemap_url_surface_rejects_every_unsafe_class(address: str) -> None:
    """The sitemap URL surface inherits every rejected class through the shared predicate."""
    host = f"[{address}]" if ":" in address else address
    with pytest.raises(SitemapError):
        validate_sitemap_url(f"http://{host}/sitemap.xml")
