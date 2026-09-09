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
# (a) DNS rebinding — the initial hop has no intra-hop divergence to script
#
# 069-F/D5: before 069.003-T, the initial hop had a separate advisory
# "validation" resolution (in the preflight) followed by a distinct
# authoritative "connect" resolution, so a rebinding schedule could target
# the gap between them. After 069.003-T, ``_connect_validated_address``
# resolves ``host`` exactly ONCE and connects atomically — there is no
# intra-hop validate/connect divergence left to script for the initial hop.
# The only observable second resolution within a fetch is now on a
# **redirect** (``_ValidatingRedirectHandler.redirect_request``'s precheck,
# then the pinned connection), so the rebinding invariant is re-expressed
# there — see the parametrized
# ``test_rebinding_between_redirect_precheck_and_connect_is_rejected`` below,
# which is never deleted and never weakened, and now covers the same
# address classes (loopback, private, CGNAT, metadata) the retired
# initial-hop test covered.
# ---------------------------------------------------------------------------


def test_mixed_dns_answer_is_fully_screened_before_any_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every address in a single multi-answer resolution is screened before connect.

    The attacker controls DNS and returns one public address followed by one
    private address in the SAME ``getaddrinfo`` answer (not across separate
    calls). A naive implementation that only checked the first address
    would connect; ``resolve_and_validate`` screens the whole answer set
    before ``_connect_validated_address`` attempts any connection.
    """

    def _mixed_resolver(host: str, *args: object, **kwargs: object) -> list[tuple[object, ...]]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_IP, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", _mixed_resolver)
    log: list[tuple[str, int]] = []
    monkeypatch.setattr(socket, "create_connection", _scripted_transport([_OK_SITEMAP], log))

    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(sitemap_module.fetch_sitemap("http://mixed.example.com/sitemap.xml"))
    assert log == [], "no connection may be attempted when any resolved address is unsafe"


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


@pytest.mark.parametrize(
    "evil_ip",
    ["127.0.0.1", "10.0.0.5", "100.64.0.1", "169.254.169.254"],
    ids=["loopback", "private", "cgnat", "metadata"],
)
def test_rebinding_between_redirect_precheck_and_connect_is_rejected(
    monkeypatch: pytest.MonkeyPatch, evil_ip: str
) -> None:
    """A redirect host that answers public at precheck and unsafe at connect is rejected.

    069-F/D5: the primary rebinding formulation, now parametrized across the
    same address classes (loopback, private, CGNAT, metadata) the retired
    initial-hop rebinding test covered — see the note above (a).
    """
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _sequenced_getaddrinfo(
            {
                "start.example.com": [[_PUBLIC_IP]],
                "next.example.com": [[_PUBLIC_IP], [evil_ip]],
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
#
# 069-F/D3 retains this wrapper (loop.run_in_executor + asyncio.wait_for +
# time.monotonic deadline arithmetic) on SCOPE grounds even though the
# preflight itself no longer resolves after 069.003-T. 069-F/B.T4 renames
# and re-asserts these three tests to describe the contract they actually
# verify — that fetch_sitemap runs the preflight in the executor under
# asyncio.wait_for, that the wrapper bounds the call, and that elapsed
# preflight time is deducted from the deadline handed to fetch_page — with
# delay injected at the preflight EXECUTION SEAM (validate_sitemap_url
# itself, patched at module level so fetch_sitemap's global lookup picks up
# the stub), never into socket.getaddrinfo, which the preflight no longer
# calls.
# ---------------------------------------------------------------------------


def test_preflight_runs_in_the_executor_not_on_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``fetch_sitemap`` must offload the preflight call to the executor."""
    seen_threads: list[int] = []

    def _recording_validate(url: str) -> str:
        seen_threads.append(threading.get_ident())
        return url

    async def _stub_fetch_page(url: str, **kwargs: Any) -> sitemap_module.FetchResponse:
        return sitemap_module.FetchResponse(url=url, status=200, content_type=None, body="")

    monkeypatch.setattr(sitemap_module, "validate_sitemap_url", _recording_validate)
    monkeypatch.setattr(sitemap_module, "fetch_page", _stub_fetch_page)

    async def _run() -> int:
        loop_thread = threading.get_ident()
        await sitemap_module.fetch_sitemap("http://example.com/sitemap.xml")
        return loop_thread

    loop_thread = asyncio.run(_run())

    assert seen_threads, "the preflight must actually run"
    assert loop_thread not in seen_threads, (
        "the preflight must run in the executor, never on the event-loop thread"
    )


def test_preflight_is_bounded_by_the_request_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hanging preflight call is cut off by ``timeout_seconds``."""
    from docline.fetch.http import FetchTimeoutError

    def _hanging_validate(url: str) -> str:
        # Only needs to outlive the 0.5s deadline. Kept short because the
        # abandoned thread is joined at event-loop shutdown, so a long sleep
        # would be charged to every suite run.
        time.sleep(2)
        raise AssertionError("preflight should have been abandoned")

    monkeypatch.setattr(sitemap_module, "validate_sitemap_url", _hanging_validate)

    async def _run() -> float:
        started = time.monotonic()
        with pytest.raises(FetchTimeoutError):
            await sitemap_module.fetch_sitemap(
                "http://example.com/sitemap.xml", timeout_seconds=0.5
            )
        return time.monotonic() - started

    # The abandoned thread is not cancellable, so measure the awaited
    # deadline itself rather than event-loop shutdown, which joins that thread.
    elapsed = asyncio.run(_run())
    assert elapsed < 1.5, "the preflight must honor the request deadline"


def test_preflight_elapsed_time_is_deducted_from_the_fetch_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Time spent in the preflight shrinks the deadline handed to the pinned sink."""

    def _slow_validate(url: str) -> str:
        time.sleep(0.35)
        return url

    monkeypatch.setattr(sitemap_module, "validate_sitemap_url", _slow_validate)

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


def test_validate_sitemap_url_performs_zero_resolver_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deterministic preflight must never call ``socket.getaddrinfo``.

    Direct companion to the end-to-end isolation assertion in
    ``test_sitemap_resolution_count.py`` (069.001-T): here ``getaddrinfo`` is
    made to fail loudly if invoked at all, for both a hostname URL and a
    public IP-literal URL, so a regression cannot pass silently.
    """

    def _fail_if_called(*args: Any, **kwargs: Any) -> list[Any]:
        raise AssertionError("validate_sitemap_url must not resolve a hostname")

    monkeypatch.setattr(socket, "getaddrinfo", _fail_if_called)

    assert (
        sitemap_module.validate_sitemap_url("http://example.com/sitemap.xml")
        == "http://example.com/sitemap.xml"
    )
    assert (
        sitemap_module.validate_sitemap_url(f"http://{_PUBLIC_IP}/sitemap.xml")
        == f"http://{_PUBLIC_IP}/sitemap.xml"
    )
