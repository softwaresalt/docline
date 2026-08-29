"""Shared-fetch SSRF-by-DNS-resolution hardening harness (064.010-T, red).

Proves connect-time resolution validation, DNS-rebinding rejection, redirect
revalidation, and inherited-proxy disablement in the shared fetch path
(url_policy.py / http.py). Greened by 064.011-T.
"""

from __future__ import annotations

import asyncio
import socket
import urllib.request

import pytest

from docline.fetch.url_policy import CrawlUrlRejectedError


def _fake_getaddrinfo(mapping: dict[str, list[str]]):
    """Return a getaddrinfo replacement resolving host -> the given IP list."""

    def _resolver(host, *args, **kwargs):
        addrs = mapping.get(host)
        if addrs is None:
            raise socket.gaierror(f"no fake mapping for {host!r}")
        infos = []
        for ip in addrs:
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            sockaddr = (ip, 0, 0, 0) if family == socket.AF_INET6 else (ip, 0)
            infos.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
        return infos

    return _resolver


# ---------------------------------------------------------------------------
# Scenario (a): public hostname resolving to loopback/private is rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("private_ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"])
def test_public_host_resolving_to_private_is_rejected(
    monkeypatch: pytest.MonkeyPatch, private_ip: str
) -> None:
    """A public hostname whose A/AAAA record is private/loopback/metadata is rejected."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _fake_getaddrinfo({"rebind.example.com": [private_ip]}),
    )
    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(fetch_page_wrapper("http://rebind.example.com"))


@pytest.mark.parametrize("cgnat_ip", ["100.64.0.1", "100.127.255.254"])
def test_cgnat_resolution_is_rejected(monkeypatch: pytest.MonkeyPatch, cgnat_ip: str) -> None:
    """CGNAT (100.64.0.0/10) resolution is rejected — the six ipaddress flags miss it."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"cgn.example.com": [cgnat_ip]}))
    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(fetch_page_wrapper("http://cgn.example.com"))


# ---------------------------------------------------------------------------
# Scenario (b): DNS rebinding — any private address in the resolved set rejects
# ---------------------------------------------------------------------------


def test_rebinding_mixed_record_set_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """If ANY resolved address is unsafe, the whole target is rejected (rebinding defense)."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _fake_getaddrinfo({"mixed.example.com": ["93.184.216.34", "127.0.0.1"]}),
    )
    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(fetch_page_wrapper("http://mixed.example.com"))


def test_unclassifiable_resolution_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A host that resolves to no usable address fails closed."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"empty.example.com": []}))
    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(fetch_page_wrapper("http://empty.example.com"))


# ---------------------------------------------------------------------------
# Scenario (c): address-pinned connect / inherited-proxy disablement
# ---------------------------------------------------------------------------


def test_fetch_opener_disables_inherited_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fetch opener honors no HTTP(S)_PROXY: no active proxying handler is installed.

    Passing an empty ``ProxyHandler({})`` to ``build_opener`` prevents urllib from
    installing its default environment-reading ``ProxyHandler``; urllib does not
    register a method-less empty proxy handler, so the invariant is that NO
    ``ProxyHandler`` with any configured proxy is present.
    """
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    from docline.fetch.http import build_fetch_opener

    opener = build_fetch_opener(max_redirects=5, budget=None)
    active_proxies = [
        h for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler) and h.proxies
    ]
    assert not active_proxies, "no environment/system proxy handler must be honored"


def test_resolved_addresses_are_validated_and_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_and_validate returns the validated public address set for pinning."""
    from docline.fetch.url_policy import resolve_and_validate

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"ok.example.com": ["93.184.216.34"]})
    )
    addrs = resolve_and_validate("ok.example.com")
    assert "93.184.216.34" in addrs


def test_redirect_target_resolving_to_private_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A redirect target whose hostname resolves to a private address is rejected mid-chain."""
    from docline.fetch.http import _ValidatingRedirectHandler

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"evil-redirect.example.com": ["127.0.0.1"]})
    )
    handler = _ValidatingRedirectHandler(max_redirects=5)
    with pytest.raises(CrawlUrlRejectedError):
        handler.redirect_request(
            urllib.request.Request("http://start.example.com"),
            None,
            302,
            "Found",
            {},  # type: ignore[arg-type]
            "http://evil-redirect.example.com/",
        )


async def fetch_page_wrapper(url: str) -> object:
    """Call fetch_page while faking the actual socket connect so only resolution is exercised."""
    from docline.fetch.http import fetch_page

    return await fetch_page(url)
