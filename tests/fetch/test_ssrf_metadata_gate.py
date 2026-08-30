"""Metadata-IP membership normalization harness (066.003-T, red).

The cloud-metadata membership check is defense-in-depth: the real metadata
addresses (``169.254.169.254``, ``169.254.170.2``, ``fd00:ec2::254``) are also
caught by ``is_link_local`` / ``is_private`` after normalization, so a
regression in the metadata gate itself is invisible when tested with those
literals.

These tests branch-isolate the gate by swapping the metadata set for
**globally routable** sentinels. Such an address is rejected by the metadata
membership check and by nothing else, so each assertion exercises exactly one
branch. The contract pinned here — and greened by 066.004-T — is that the
membership comparison happens *after* parse and IPv4-mapped normalization
against :mod:`ipaddress` objects, so alternate spellings of the same address
(IPv4-mapped, expanded, uppercase) cannot slip past a raw-string comparison.
"""

from __future__ import annotations

import ipaddress

import pytest

from docline.fetch import url_policy
from docline.fetch.url_policy import is_unsafe_resolved_address

# Globally routable sentinels. Chosen so that *only* the metadata membership
# check can reject them; every other branch of the predicate accepts them.
_IPV4_SENTINEL = "93.184.216.34"
_IPV6_SENTINEL = "2606:2800:220::1946"


@pytest.fixture
def routable_metadata_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the metadata set with globally routable sentinel addresses."""
    monkeypatch.setattr(
        url_policy,
        "_METADATA_IPS",
        frozenset(
            {
                ipaddress.ip_address(_IPV4_SENTINEL),
                ipaddress.ip_address(_IPV6_SENTINEL),
            }
        ),
    )


@pytest.mark.parametrize("address", [_IPV4_SENTINEL, _IPV6_SENTINEL])
def test_sentinels_are_branch_isolated(address: str) -> None:
    """Unpatched, the sentinels are accepted — only the metadata gate can reject them."""
    assert is_unsafe_resolved_address(address) is False


def test_metadata_ips_are_stored_as_parsed_address_objects() -> None:
    """The metadata set holds parsed ``ipaddress`` objects, not raw strings."""
    assert url_policy._METADATA_IPS
    assert all(
        isinstance(entry, ipaddress.IPv4Address | ipaddress.IPv6Address)
        for entry in url_policy._METADATA_IPS
    )


@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param(_IPV4_SENTINEL, id="exact"),
        pytest.param("::ffff:93.184.216.34", id="ipv4-mapped-dotted"),
        pytest.param("::ffff:5db8:d822", id="ipv4-mapped-hextet"),
        pytest.param("0000:0000:0000:0000:0000:ffff:5db8:d822", id="ipv4-mapped-expanded"),
    ],
)
def test_ipv4_metadata_membership_survives_normalization(
    routable_metadata_set: None, spelling: str
) -> None:
    """Every spelling of an IPv4 metadata address hits the gate after normalization."""
    assert is_unsafe_resolved_address(spelling) is True


@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param(_IPV6_SENTINEL, id="compressed"),
        pytest.param("2606:2800:0220:0000:0000:0000:0000:1946", id="expanded"),
        pytest.param("2606:2800:220:0:0:0:0:1946", id="partially-expanded"),
        pytest.param("2606:2800:220::1946".upper(), id="uppercase"),
    ],
)
def test_ipv6_metadata_membership_survives_normalization(
    routable_metadata_set: None, spelling: str
) -> None:
    """Expanded, compressed, and uppercase IPv6 spellings all hit the metadata gate."""
    assert is_unsafe_resolved_address(spelling) is True


def test_non_metadata_routable_address_still_accepted(routable_metadata_set: None) -> None:
    """The patched gate rejects only its members — it is not a blanket reject."""
    assert is_unsafe_resolved_address("93.184.216.35") is False


@pytest.mark.parametrize(
    "address",
    [
        "169.254.169.254",
        "169.254.170.2",
        "fd00:ec2::254",
        "::ffff:169.254.169.254",
        "FD00:EC2:0000:0000:0000:0000:0000:0254",
    ],
)
def test_real_metadata_literals_remain_rejected(address: str) -> None:
    """The shipped metadata literals and their alternate spellings stay rejected."""
    assert is_unsafe_resolved_address(address) is True
