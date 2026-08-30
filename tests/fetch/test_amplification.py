"""Shared-fetch request-amplification harness (064.025-T, red).

Proves the request-COUNT bound (§H7 item 4): a per-request outbound fetch-attempt
budget (MAX_FETCH_ATTEMPTS) debited at the common fetch_page boundary (pre-I/O)
across main-page, robots, TOC, and retry traffic, plus a FetchRequest.depth
upper bound. Greened by 064.026-T.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from docline.app_models import FetchRequest
from docline.fetch import crawl as crawl_mod
from docline.fetch.crawl import CrawlConfig, crawl
from docline.fetch.http import FetchResponse


class _Headers:
    def get_content_charset(self) -> str | None:
        return "utf-8"

    def get(self, _key: str, _default: object = None) -> object:
        return "text/html"


# ---------------------------------------------------------------------------
# Scenario 1: boundary fetch-attempt debit (pre-I/O) + auxiliary coverage
# ---------------------------------------------------------------------------


def test_fetch_page_debits_attempt_before_io() -> None:
    """fetch_page debits one attempt BEFORE outbound I/O; an exhausted budget
    raises FetchAttemptBudgetExceededError without any network resolution."""
    from docline.fetch.http import (
        FetchAttemptBudgetExceededError,
        RemainingByteBudget,
        fetch_page,
    )

    budget = RemainingByteBudget(total_bytes=None, max_attempts=0)
    with pytest.raises(FetchAttemptBudgetExceededError):
        asyncio.run(fetch_page("http://public.example.com", budget=budget))


def test_crawl_attempt_budget_counts_auxiliary_robots(monkeypatch) -> None:
    """robots.txt (auxiliary) traffic debits the SAME request-scoped attempt budget,
    so a crawl whose emitted page_count stays low still trips MAX_FETCH_ATTEMPTS."""
    from docline.fetch.http import FetchAttemptBudgetExceededError

    # Tighten the cap so the single allowed attempt is consumed by robots.txt.
    monkeypatch.setattr(crawl_mod, "MAX_FETCH_ATTEMPTS", 1)

    async def _fake_fetch_page(url, *, timeout_seconds=30.0, max_redirects=5, budget=None):
        if budget is not None:
            budget.debit_attempt()  # boundary debit (pre-I/O)
        return FetchResponse(
            url=url, status=200, content_type="text/html", body="<html></html>", body_byte_count=13
        )

    monkeypatch.setattr(crawl_mod, "fetch_page", _fake_fetch_page)
    with pytest.raises(FetchAttemptBudgetExceededError):
        asyncio.run(
            crawl("http://example.com", CrawlConfig(max_pages=5, respect_robots=True))
        ).results


# ---------------------------------------------------------------------------
# Scenario 2: depth upper bound
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 1, 64])
def test_depth_within_cap_accepted(value: int) -> None:
    """depth within 0..MAX_DEPTH_LIMIT is accepted."""
    req = FetchRequest(source="http://example.com", depth=value)
    assert req.depth == value


@pytest.mark.parametrize("value", [65, 100, 1000])
def test_depth_above_cap_rejected(value: int) -> None:
    """depth above MAX_DEPTH_LIMIT (64) is rejected at model validation."""
    with pytest.raises(ValidationError):
        FetchRequest(source="http://example.com", depth=value)


def test_depth_omitted_defaults_to_zero() -> None:
    """A request omitting depth still validates and defaults to 0."""
    req = FetchRequest(source="http://example.com")
    assert req.depth == 0
