"""Sitemap pinned-sink composition harness (066.005-T, red).

``validate_sitemap_url`` classifies the addresses a hostname resolves to and
then hands the caller back the *hostname*. Any HTTP client re-resolves that
hostname at fetch time, so a TTL-0 attacker can answer public during
validation and private/CGNAT at connect — every address check is bypassed.

These tests pin the fix: sitemap retrieval must go through one authoritative
entry point, ``sitemap.fetch_sitemap``, that delegates to the already-hardened
public sink ``http.fetch_page`` so resolution, validation, connect,
redirect revalidation, and proxy suppression happen as one atomic unit.

The whole invariant is exercised end to end against the real ``urllib`` stack:
DNS is scripted per call (so rebinding is expressible) and the transport is a
scripted in-memory socket, so the genuine pinned connection classes, the
validating redirect handler, and the proxy-suppressing opener all run.

Red before 066.006-T: ``sitemap.fetch_sitemap`` does not exist.
"""

from __future__ import annotations

import asyncio
import io
import socket
import ssl
import threading
import time
from typing import Any

import pytest

from docline.fetch import sitemap as sitemap_module
from docline.fetch.url_policy import CrawlUrlRejectedError

_PUBLIC_IP = "93.184.216.34"


def _sequenced_getaddrinfo(schedule: dict[str, list[list[str]]]):
    """Return a ``getaddrinfo`` replacement whose answers change per call.

    Args:
        schedule: Maps a hostname to the list of answers to return, one per
            successive lookup. The final entry is reused once exhausted, so a
            two-entry list expresses "public at validation, private at connect".

    Returns:
        A callable suitable for ``monkeypatch.setattr(socket, "getaddrinfo", ...)``.
    """
    counters: dict[str, int] = {}

    def _resolver(host: str, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        answers = schedule.get(host)
        if answers is None:
            raise socket.gaierror(f"no scripted mapping for {host!r}")
        index = min(counters.get(host, 0), len(answers) - 1)
        counters[host] = counters.get(host, 0) + 1
        infos: list[tuple[Any, ...]] = []
        for ip in answers[index]:
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            sockaddr = (ip, 0, 0, 0) if family == socket.AF_INET6 else (ip, 0)
            infos.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
        return infos

    return _resolver


class _ScriptedSocket:
    """An in-memory socket replaying one canned HTTP response."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.sent = bytearray()

    def makefile(self, mode: str = "rb", *args: Any, **kwargs: Any) -> io.BytesIO:
        return io.BytesIO(self._payload)

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def send(self, data: bytes) -> int:
        self.sent += data
        return len(data)

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


def _response(status_line: str, headers: dict[str, str], body: bytes = b"") -> bytes:
    head = status_line + "\r\n"
    merged = {"Content-Length": str(len(body)), "Connection": "close", **headers}
    for key, value in merged.items():
        head += f"{key}: {value}\r\n"
    return head.encode("ascii") + b"\r\n" + body


def _scripted_transport(responses: list[bytes], log: list[tuple[str, int]]):
    """Return a ``create_connection`` replacement replaying ``responses`` in order."""
    sockets: list[_ScriptedSocket] = []

    def _create(address: tuple[str, int], timeout: Any = None, source_address: Any = None):
        log.append((address[0], address[1]))
        payload = responses[min(len(sockets), len(responses) - 1)]
        sock = _ScriptedSocket(payload)
        sockets.append(sock)
        return sock

    _create.sockets = sockets  # type: ignore[attr-defined]
    return _create


_OK_SITEMAP = _response(
    "HTTP/1.1 200 OK",
    {"Content-Type": "application/xml"},
    b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>',
)


# ---------------------------------------------------------------------------
# Contract surface
# ---------------------------------------------------------------------------


def test_fetch_sitemap_is_the_exported_retrieval_entry_point() -> None:
    """``fetch_sitemap`` is the single public sitemap fetch path."""
    assert "fetch_sitemap" in sitemap_module.__all__
    assert callable(sitemap_module.fetch_sitemap)


def test_validate_sitemap_url_remains_a_synchronous_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The preflight still returns the URL unchanged and is not a coroutine."""
    monkeypatch.setattr(
        socket, "getaddrinfo", _sequenced_getaddrinfo({"example.com": [[_PUBLIC_IP]]})
    )
    assert not asyncio.iscoroutinefunction(sitemap_module.validate_sitemap_url)
    assert (
        sitemap_module.validate_sitemap_url("https://example.com/sitemap.xml")
        == "https://example.com/sitemap.xml"
    )


# ---------------------------------------------------------------------------
# Positive control — the scripted transport really drives the pinned sink
# ---------------------------------------------------------------------------


def test_fetch_sitemap_succeeds_and_pins_the_validated_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A safe host is fetched over a connection pinned to the validated IP."""
    monkeypatch.setattr(
        socket, "getaddrinfo", _sequenced_getaddrinfo({"example.com": [[_PUBLIC_IP]]})
    )
    log: list[tuple[str, int]] = []
    monkeypatch.setattr(socket, "create_connection", _scripted_transport([_OK_SITEMAP], log))

    result = asyncio.run(sitemap_module.fetch_sitemap("http://example.com/sitemap.xml"))

    assert result.status == 200
    assert "urlset" in result.body
    assert log == [(_PUBLIC_IP, 80)], "connect must target the validated IP, never the hostname"


# ---------------------------------------------------------------------------
# (a) DNS rebinding between validation and connect
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("connect_ip", ["127.0.0.1", "10.0.0.5", "100.64.0.1", "169.254.169.254"])
def test_rebinding_between_validation_and_connect_is_rejected(
    monkeypatch: pytest.MonkeyPatch, connect_ip: str
) -> None:
    """Public at validation, private/CGNAT/metadata at connect must be rejected."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _sequenced_getaddrinfo({"rebind.example.com": [[_PUBLIC_IP], [connect_ip]]}),
    )
    log: list[tuple[str, int]] = []
    monkeypatch.setattr(socket, "create_connection", _scripted_transport([_OK_SITEMAP], log))

    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(sitemap_module.fetch_sitemap("http://rebind.example.com/sitemap.xml"))
    assert log == [], "no connection may be opened to a rebound private address"


# ---------------------------------------------------------------------------
# (b) Redirect target resolving to a private/CGNAT address
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("evil_ip", ["127.0.0.1", "100.64.0.1"])
def test_redirect_target_resolving_to_private_is_rejected(
    monkeypatch: pytest.MonkeyPatch, evil_ip: str
) -> None:
    """A 302 to a host resolving private/CGNAT is rejected mid-chain."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _sequenced_getaddrinfo(
            {"start.example.com": [[_PUBLIC_IP]], "evil.example.com": [[evil_ip]]}
        ),
    )
    redirect = _response("HTTP/1.1 302 Found", {"Location": "http://evil.example.com/sitemap.xml"})
    log: list[tuple[str, int]] = []
    monkeypatch.setattr(
        socket, "create_connection", _scripted_transport([redirect, _OK_SITEMAP], log)
    )

    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(sitemap_module.fetch_sitemap("http://start.example.com/sitemap.xml"))
    assert log == [(_PUBLIC_IP, 80)], "only the validated first hop may be connected"


# ---------------------------------------------------------------------------
# (c) Rebinding between the redirect precheck and the redirect connect
# ---------------------------------------------------------------------------


def test_rebinding_between_redirect_precheck_and_connect_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redirect host that answers public at precheck and private at connect is rejected."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _sequenced_getaddrinfo(
            {
                "start.example.com": [[_PUBLIC_IP]],
                "next.example.com": [[_PUBLIC_IP], ["10.0.0.5"]],
            }
        ),
    )
    redirect = _response("HTTP/1.1 302 Found", {"Location": "http://next.example.com/sitemap.xml"})
    log: list[tuple[str, int]] = []
    monkeypatch.setattr(
        socket, "create_connection", _scripted_transport([redirect, _OK_SITEMAP], log)
    )

    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(sitemap_module.fetch_sitemap("http://start.example.com/sitemap.xml"))
    assert log == [(_PUBLIC_IP, 80)], "the rebound redirect hop must never be connected"


# ---------------------------------------------------------------------------
# (d) Inherited proxy environment is ignored
# ---------------------------------------------------------------------------


def test_fetch_sitemap_ignores_inherited_proxy_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``HTTP(S)_PROXY`` must not re-resolve or re-route the sitemap fetch."""
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _sequenced_getaddrinfo({"example.com": [[_PUBLIC_IP]]}),
    )
    log: list[tuple[str, int]] = []
    transport = _scripted_transport([_OK_SITEMAP], log)
    monkeypatch.setattr(socket, "create_connection", transport)

    asyncio.run(sitemap_module.fetch_sitemap("http://example.com/sitemap.xml"))

    assert log == [(_PUBLIC_IP, 80)], "the fetch must reach the origin, never the proxy"
    request_line = bytes(transport.sockets[0].sent).split(b"\r\n", 1)[0]  # type: ignore[attr-defined]
    assert request_line == b"GET /sitemap.xml HTTP/1.1", (
        "origin-form request line proves no proxy absolute-form rewrite occurred"
    )


# ---------------------------------------------------------------------------
# (e) TLS SNI and certificate verification target the hostname, not the IP
# ---------------------------------------------------------------------------


def test_https_sni_and_verification_use_the_hostname_not_the_pinned_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The TLS handshake targets the DNS name while the socket connects to the pinned IP."""
    monkeypatch.setattr(
        socket, "getaddrinfo", _sequenced_getaddrinfo({"example.com": [[_PUBLIC_IP]]})
    )
    log: list[tuple[str, int]] = []
    monkeypatch.setattr(socket, "create_connection", _scripted_transport([_OK_SITEMAP], log))

    captured: dict[str, Any] = {}

    def _recording_wrap_socket(
        self: ssl.SSLContext, sock: Any, server_hostname: str | None = None, **kwargs: Any
    ) -> Any:
        captured["server_hostname"] = server_hostname
        captured["check_hostname"] = self.check_hostname
        captured["verify_mode"] = self.verify_mode
        return sock

    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", _recording_wrap_socket)

    result = asyncio.run(sitemap_module.fetch_sitemap("https://example.com/sitemap.xml"))

    assert result.status == 200
    assert log == [(_PUBLIC_IP, 443)], "the socket must be pinned to the validated IP"
    assert captured["server_hostname"] == "example.com", (
        "SNI and certificate verification must target the hostname, never the pinned IP"
    )
    assert captured["check_hostname"] is True, "hostname verification must stay enabled"
    assert captured["verify_mode"] == ssl.CERT_REQUIRED, "certificate verification must stay on"


# ---------------------------------------------------------------------------
# Preflight must not block the event loop and must share the request deadline
# ---------------------------------------------------------------------------


def test_preflight_resolution_runs_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """The blocking preflight DNS lookup must not run on the event-loop thread."""
    resolver_threads: list[int] = []
    base_resolver = _sequenced_getaddrinfo({"example.com": [[_PUBLIC_IP]]})

    def _recording_resolver(host: str, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        resolver_threads.append(threading.get_ident())
        return base_resolver(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _recording_resolver)
    log: list[tuple[str, int]] = []
    monkeypatch.setattr(socket, "create_connection", _scripted_transport([_OK_SITEMAP], log))

    async def _run() -> int:
        loop_thread = threading.get_ident()
        await sitemap_module.fetch_sitemap("http://example.com/sitemap.xml")
        return loop_thread

    loop_thread = asyncio.run(_run())

    assert resolver_threads, "the preflight must actually resolve"
    assert loop_thread not in resolver_threads, (
        "a slow resolver must never block the event loop during the preflight"
    )


def test_preflight_is_bounded_by_the_request_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hanging resolver in the preflight is cut off by ``timeout_seconds``."""
    from docline.fetch.http import FetchTimeoutError

    def _hanging_resolver(host: str, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        time.sleep(30)
        raise AssertionError("resolver should have been abandoned")

    monkeypatch.setattr(socket, "getaddrinfo", _hanging_resolver)

    started = time.monotonic()
    with pytest.raises(FetchTimeoutError):
        asyncio.run(
            sitemap_module.fetch_sitemap("http://example.com/sitemap.xml", timeout_seconds=0.5)
        )
    assert time.monotonic() - started < 10, "the preflight must honor the request deadline"


def test_preflight_elapsed_time_is_deducted_from_the_fetch_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Time spent in the preflight shrinks the deadline handed to the pinned sink."""
    base_resolver = _sequenced_getaddrinfo({"example.com": [[_PUBLIC_IP]]})

    def _slow_resolver(host: str, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        time.sleep(0.35)
        return base_resolver(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _slow_resolver)

    captured: dict[str, Any] = {}

    async def _recording_fetch_page(url: str, **kwargs: Any) -> object:
        captured.update(kwargs)
        captured["url"] = url
        return object()

    monkeypatch.setattr(sitemap_module, "fetch_page", _recording_fetch_page)

    asyncio.run(sitemap_module.fetch_sitemap("http://example.com/sitemap.xml", timeout_seconds=5.0))

    assert captured["url"] == "http://example.com/sitemap.xml"
    assert captured["max_redirects"] == 5
    assert captured["timeout_seconds"] < 5.0, "preflight time must be charged to the deadline"
    assert captured["timeout_seconds"] > 4.0, "the deadline must not collapse"
