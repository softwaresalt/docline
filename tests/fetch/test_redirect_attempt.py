"""Redirect-hop fetch-attempt-debit placement harness (064.029-T, red).

Proves the per-hop MAX_FETCH_ATTEMPTS debit lives INSIDE redirect_request — after
the stdlib build + §H6 revalidation, before the hop's outbound I/O — so a FOLLOWED
hop debits exactly one attempt while a REJECTED redirect (scheme/§H6) debits
nothing, and an attempt-breach raises before the crossing hop. Greened by 064.030-T.
"""

from __future__ import annotations

import socket
from http.client import HTTPMessage
from urllib.request import Request

import pytest


def _public_getaddrinfo(host_ip: dict[str, str]):
    def _resolver(host, *args, **kwargs):
        ip = host_ip.get(host, "93.184.216.34")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _resolver


def _make_handler(budget, max_redirects: int = 5):
    from docline.fetch.http import _ValidatingRedirectHandler

    return _ValidatingRedirectHandler(max_redirects, budget=budget)


def _req() -> Request:
    return Request("http://start.example.com")


def test_followed_hop_debits_exactly_one_attempt(monkeypatch) -> None:
    """A followed redirect hop debits exactly one attempt inside redirect_request."""
    from docline.fetch.http import RemainingByteBudget

    monkeypatch.setattr(socket, "getaddrinfo", _public_getaddrinfo({}))
    budget = RemainingByteBudget(total_bytes=None, max_attempts=5)
    handler = _make_handler(budget)
    new = handler.redirect_request(
        _req(), None, 302, "Found", HTTPMessage(), "http://next.example.com/x"
    )
    assert new is not None
    assert budget.attempts_remaining == 4


def test_h6_rejected_redirect_debits_nothing(monkeypatch) -> None:
    """A redirect rejected by §H6 revalidation consumes NO attempt."""
    from docline.fetch.http import RemainingByteBudget
    from docline.fetch.url_policy import CrawlUrlRejectedError

    monkeypatch.setattr(
        socket, "getaddrinfo", _public_getaddrinfo({"evil.example.com": "127.0.0.1"})
    )
    budget = RemainingByteBudget(total_bytes=None, max_attempts=5)
    handler = _make_handler(budget)
    with pytest.raises(CrawlUrlRejectedError):
        handler.redirect_request(
            _req(), None, 302, "Found", HTTPMessage(), "http://evil.example.com/x"
        )
    assert budget.attempts_remaining == 5  # no debit on rejection


def test_scheme_rejected_redirect_debits_nothing(monkeypatch) -> None:
    """A redirect rejected by the scheme check consumes NO attempt."""
    from docline.fetch.http import RemainingByteBudget
    from docline.fetch.url_policy import CrawlUrlRejectedError

    monkeypatch.setattr(socket, "getaddrinfo", _public_getaddrinfo({}))
    budget = RemainingByteBudget(total_bytes=None, max_attempts=5)
    handler = _make_handler(budget)
    with pytest.raises(CrawlUrlRejectedError):
        handler.redirect_request(
            _req(), None, 302, "Found", HTTPMessage(), "ftp://next.example.com/x"
        )
    assert budget.attempts_remaining == 5


def test_attempt_breach_raises_before_returning_request(monkeypatch) -> None:
    """When the attempt budget is exhausted, the crossing hop raises before I/O."""
    from docline.fetch.http import (
        FetchAttemptBudgetExceededError,
        RemainingByteBudget,
    )

    monkeypatch.setattr(socket, "getaddrinfo", _public_getaddrinfo({}))
    budget = RemainingByteBudget(total_bytes=None, max_attempts=0)
    handler = _make_handler(budget)
    with pytest.raises(FetchAttemptBudgetExceededError):
        handler.redirect_request(
            _req(), None, 302, "Found", HTTPMessage(), "http://next.example.com/x"
        )
