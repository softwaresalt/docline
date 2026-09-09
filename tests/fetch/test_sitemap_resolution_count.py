"""Harness: exactly one hostname resolution per successful ``fetch_sitemap`` (069.001-T).

Pins 069-F/D4: ``fetch_sitemap`` must resolve the original hostname exactly
**once** per successful, non-redirected fetch — inside ``fetch_page``'s
authoritative ``resolve-validate-pin`` sequence (``_connect_validated_address``).
"One hostname lookup" is defined as one ``getaddrinfo`` call whose ``host``
argument equals the **original hostname string** — not a raw count of every
``getaddrinfo`` call, because ``socket.create_connection`` also resolves an
already-validated *numeric* address in production, and a naive global
counter would conflate the two.

Before 069.003-T, ``fetch_sitemap`` performed **two** hostname lookups: one
inside ``validate_sitemap_url``'s advisory preflight (the now-deleted
``_resolve_all_addresses``) and one inside ``fetch_page``'s connect. These
tests were written and verified red against that pre-change source (the
first test asserting exactly one lookup, which failed at a count of two;
the second isolating the preflight from ``fetch_page`` and asserting zero
preflight-only lookups, which failed for the hostname case because the
preflight still resolved). 069.003-T stripped the preflight's resolution
out, turning both green. They now stand as the permanent regression guard
for the single-resolution invariant.

No source change in this task.
"""

from __future__ import annotations

import asyncio
import io
import socket
from typing import Any

import pytest

from docline.fetch import sitemap as sitemap_module

_PUBLIC_IP = "93.184.216.34"
_HOSTNAME = "example.com"


def _counting_getaddrinfo(hostname: str) -> tuple[Any, dict[str, int]]:
    """Return a ``getaddrinfo`` replacement + call counter, keyed on ``hostname``.

    Counts only calls whose ``host`` argument equals ``hostname`` (D4
    accounting), so a downstream numeric-address resolution is never
    mistaken for a hostname lookup.
    """
    counts = {"hostname_lookups": 0}

    def _resolver(host: str, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        if host.lower() == hostname.lower():
            counts["hostname_lookups"] += 1
        family = socket.AF_INET6 if ":" in _PUBLIC_IP else socket.AF_INET
        sockaddr = (_PUBLIC_IP, 0, 0, 0) if family == socket.AF_INET6 else (_PUBLIC_IP, 0)
        return [(family, socket.SOCK_STREAM, 6, "", sockaddr)]

    return _resolver, counts


class _ScriptedSocket:
    """A minimal in-memory socket replaying one canned HTTP response."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def makefile(self, mode: str = "rb", *args: Any, **kwargs: Any) -> io.BytesIO:
        return io.BytesIO(self._payload)

    def sendall(self, data: bytes) -> None:
        return None

    def send(self, data: bytes) -> int:
        return 0

    def settimeout(self, value: float | None) -> None:
        return None

    def gettimeout(self) -> float | None:
        return None

    def setsockopt(self, *args: Any) -> None:
        return None

    def shutdown(self, *args: Any) -> None:
        return None

    def close(self) -> None:
        return None


def _http_response(status_line: str, headers: dict[str, str], body: bytes = b"") -> bytes:
    merged = {"Content-Length": str(len(body)), "Connection": "close", **headers}
    head = status_line + "\r\n" + "".join(f"{key}: {value}\r\n" for key, value in merged.items())
    return head.encode("ascii") + b"\r\n" + body


_OK_SITEMAP_BODY = (
    b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>'
)
_OK_SITEMAP_RESPONSE = _http_response(
    "HTTP/1.1 200 OK", {"Content-Type": "application/xml"}, _OK_SITEMAP_BODY
)


def _create_connection_stub(
    address: tuple[str, int], timeout: Any = None, source_address: Any = None
) -> _ScriptedSocket:
    return _ScriptedSocket(_OK_SITEMAP_RESPONSE)


def test_fetch_sitemap_performs_exactly_one_hostname_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``fetch_sitemap`` must resolve the original hostname exactly ONCE.

    D4 accounting: before 069.003-T this was 2 (the advisory preflight
    resolution plus fetch_page's authoritative connect-time resolution);
    069.003-T stopped the preflight from resolving at all, so the target
    (and now-enforced) count is 1.
    """
    resolver, counts = _counting_getaddrinfo(_HOSTNAME)
    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    monkeypatch.setattr(socket, "create_connection", _create_connection_stub)

    result = asyncio.run(sitemap_module.fetch_sitemap(f"http://{_HOSTNAME}/sitemap.xml"))

    assert result.status == 200
    assert counts["hostname_lookups"] == 1, (
        f"expected exactly one hostname lookup for {_HOSTNAME!r}, "
        f"got {counts['hostname_lookups']} (pre-change baseline: 2 — one advisory "
        "preflight resolve plus one authoritative fetch_page resolve)"
    )


@pytest.mark.parametrize(
    ("url", "host"),
    [
        (f"http://{_HOSTNAME}/sitemap.xml", _HOSTNAME),
        (f"http://{_PUBLIC_IP}/sitemap.xml", _PUBLIC_IP),  # IP-literal: no DNS needed either way
    ],
    ids=["hostname", "ip-literal"],
)
def test_preflight_alone_performs_zero_hostname_lookups(
    monkeypatch: pytest.MonkeyPatch, url: str, host: str
) -> None:
    """With ``fetch_page`` patched out, the preflight alone must resolve nothing.

    Isolates ``validate_sitemap_url`` from ``fetch_page``: a raw call count
    cannot express this because ``fetch_page`` legitimately resolves — the
    patch is the isolation seam. Before 069.003-T this was red for the
    hostname case (the preflight still called ``_resolve_all_addresses``);
    the IP-literal case already passed even then, because the IP-literal
    branch never resolves. Both cases are green now that 069.003-T removed
    the preflight's resolution entirely.
    """
    resolver, counts = _counting_getaddrinfo(host)
    monkeypatch.setattr(socket, "getaddrinfo", resolver)

    async def _stub_fetch_page(target_url: str, **kwargs: Any) -> sitemap_module.FetchResponse:
        return sitemap_module.FetchResponse(
            url=target_url, status=200, content_type=None, body="", redirect_count=0
        )

    monkeypatch.setattr(sitemap_module, "fetch_page", _stub_fetch_page)

    asyncio.run(sitemap_module.fetch_sitemap(url))

    assert counts["hostname_lookups"] == 0, (
        f"the preflight alone must perform zero hostname lookups for {url!r}, "
        f"got {counts['hostname_lookups']}"
    )
