"""Intermediate-redirect-body drain + fp-closure harness (064.027-T, red).

Proves the extended _ValidatingRedirectHandler bounded-drains each intermediate
3xx body against the per-response MAX_RESPONSE_BYTES cap AND the request-scoped
aggregate budget, closes the intermediate fp on every cap-breach / redirect_request
raise path, and still follows a within-budget redirect. Greened by 064.028-T.
"""

from __future__ import annotations

import socket
from http.client import HTTPMessage
from urllib.request import Request

import pytest


class _InstrumentedFp:
    """Fake intermediate 3xx response fp recording read sizes and close() calls."""

    def __init__(self, total: int) -> None:
        self._remaining = total
        self.read_sizes: list[int] = []
        self.close_count = 0

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if self._remaining <= 0:
            return b""
        if size is None or size < 0:
            size = self._remaining
        n = min(size, self._remaining)
        self._remaining -= n
        return b"a" * n

    def close(self) -> None:
        self.close_count += 1


class _FakeParent:
    """Fake OpenerDirector: records the followed request and returns a sentinel."""

    def __init__(self) -> None:
        self.opened: list[object] = []

    def open(self, req: object, timeout: object = None) -> str:
        self.opened.append(req)
        return "FINAL"


def _headers(location: str) -> HTTPMessage:
    h = HTTPMessage()
    h["Location"] = location
    return h


def _public_getaddrinfo(host_ip: dict[str, str]):
    def _resolver(host, *args, **kwargs):
        ip = host_ip.get(host, "93.184.216.34")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _resolver


def _make_handler(budget=None, max_redirects: int = 5):
    from docline.fetch.http import _ValidatingRedirectHandler

    handler = _ValidatingRedirectHandler(max_redirects, budget=budget)
    handler.parent = _FakeParent()  # type: ignore[attr-defined]
    return handler


REDIRECT_METHODS = [
    "http_error_301",
    "http_error_302",
    "http_error_303",
    "http_error_307",
    "http_error_308",
]


@pytest.mark.parametrize("method_name", REDIRECT_METHODS)
def test_intermediate_body_over_per_response_cap_aborts_and_closes(
    monkeypatch, method_name: str
) -> None:
    """An intermediate 3xx body over MAX_RESPONSE_BYTES aborts and closes the fp."""
    from docline.fetch.http import (
        CHUNK_SIZE,
        MAX_RESPONSE_BYTES,
        ResponseByteLimitError,
        _ValidatingRedirectHandler,
    )

    monkeypatch.setattr(socket, "getaddrinfo", _public_getaddrinfo({}))
    handler: _ValidatingRedirectHandler = _make_handler()
    method = getattr(handler, method_name)
    fp = _InstrumentedFp(MAX_RESPONSE_BYTES + 3 * CHUNK_SIZE)
    req = Request("http://start.example.com")
    with pytest.raises(ResponseByteLimitError):
        method(req, fp, int(method_name[-3:]), "Redirect", _headers("http://next.example.com/x"))
    assert fp.close_count >= 1
    assert all(s <= CHUNK_SIZE for s in fp.read_sizes)


def test_intermediate_body_over_aggregate_budget_aborts_and_closes(monkeypatch) -> None:
    """An intermediate body crossing the aggregate budget aborts mid-drain, closes fp."""
    from docline.fetch.http import (
        CHUNK_SIZE,
        AggregateBudgetExceededError,
        RemainingByteBudget,
    )

    monkeypatch.setattr(socket, "getaddrinfo", _public_getaddrinfo({}))
    budget = RemainingByteBudget(total_bytes=2 * CHUNK_SIZE)
    handler = _make_handler(budget=budget)
    fp = _InstrumentedFp(10 * CHUNK_SIZE)
    req = Request("http://start.example.com")
    with pytest.raises(AggregateBudgetExceededError):
        handler.http_error_302(req, fp, 302, "Found", _headers("http://next.example.com/x"))
    assert fp.close_count >= 1


def test_within_budget_redirect_still_follows(monkeypatch) -> None:
    """A within-budget 3xx body is drained, revalidated, and followed to the final."""
    from docline.fetch.http import RemainingByteBudget

    calls: dict[str, int] = {"resolve": 0}

    def _resolver(host, *args, **kwargs):
        calls["resolve"] += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _resolver)
    budget = RemainingByteBudget(total_bytes=1_000_000)
    handler = _make_handler(budget=budget)
    fp = _InstrumentedFp(1000)
    req = Request("http://start.example.com")
    result = handler.http_error_302(req, fp, 302, "Found", _headers("http://next.example.com/x"))
    assert result == "FINAL"
    assert fp.close_count >= 1
    assert calls["resolve"] >= 1  # §H6 revalidation ran


def test_redirect_cap_exceeded_closes_fp(monkeypatch) -> None:
    """When the redirect cap is exceeded, the intermediate fp is closed."""
    from docline.fetch.http import FetchError

    monkeypatch.setattr(socket, "getaddrinfo", _public_getaddrinfo({}))
    handler = _make_handler(max_redirects=0)  # any redirect exceeds the cap
    fp = _InstrumentedFp(1000)
    req = Request("http://start.example.com")
    with pytest.raises(FetchError):
        handler.http_error_302(req, fp, 302, "Found", _headers("http://next.example.com/x"))
    assert fp.close_count >= 1


def test_h6_rejected_redirect_closes_fp(monkeypatch) -> None:
    """When §H6 revalidation rejects the target, the intermediate fp is closed."""
    from docline.fetch.url_policy import CrawlUrlRejectedError

    monkeypatch.setattr(
        socket, "getaddrinfo", _public_getaddrinfo({"evil.example.com": "127.0.0.1"})
    )
    handler = _make_handler()
    fp = _InstrumentedFp(1000)
    req = Request("http://start.example.com")
    with pytest.raises(CrawlUrlRejectedError):
        handler.http_error_302(req, fp, 302, "Found", _headers("http://evil.example.com/x"))
    assert fp.close_count >= 1
