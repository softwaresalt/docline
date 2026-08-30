"""Shared-fetch aggregate byte-accounting harness (064.016-T, red).

Proves the aggregate cap counts *entity-body* bytes (undecoded response-content
bytes), not decoded characters or a re-encode, and is enforced during-read via a
request-scoped remaining-byte budget threaded through fetch_page. crawl() must
RAISE (not swallow-as-skip) the typed AggregateBudgetExceededError.

Greened by 064.017-T (core: main-page + retry) and 064.024-T (ancillary robots/TOC).
"""

from __future__ import annotations

import asyncio

import pytest

from docline.fetch.crawl import CrawlConfig, crawl


class _ChunkedResponse:
    """Fake response whose read(n) yields up to n bytes from a fixed buffer."""

    def __init__(self, data: bytes) -> None:
        self._buf = bytearray(data)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if not self._buf:
            return b""
        if size is None or size < 0:
            size = len(self._buf)
        chunk = bytes(self._buf[:size])
        del self._buf[:size]
        return chunk


# ---------------------------------------------------------------------------
# Scenario (a)/(b): byte-accurate accounting (undecoded entity-body bytes)
# ---------------------------------------------------------------------------


def test_budget_counts_undecoded_nonascii_bytes() -> None:
    """A non-ASCII multibyte body accrues its BYTE length, not its char length."""
    from docline.fetch.http import (
        MAX_RESPONSE_BYTES,
        AggregateBudgetExceededError,
        RemainingByteBudget,
        read_body_capped,
    )

    payload = ("é" * 1000).encode("utf-8")  # 2000 bytes, 1000 chars
    assert len(payload) == 2000
    # A budget of exactly the byte count succeeds; one byte short raises.
    ok = RemainingByteBudget(total_bytes=2000)
    body = read_body_capped(_ChunkedResponse(payload), MAX_RESPONSE_BYTES, budget=ok)
    assert len(body) == 2000
    assert ok.remaining == 0
    short = RemainingByteBudget(total_bytes=1999)
    with pytest.raises(AggregateBudgetExceededError):
        read_body_capped(_ChunkedResponse(payload), MAX_RESPONSE_BYTES, budget=short)


def test_budget_counts_invalid_bytes_not_replacement_chars() -> None:
    """An invalid-byte body accrues its original byte length, not U+FFFD count."""
    from docline.fetch.http import (
        MAX_RESPONSE_BYTES,
        AggregateBudgetExceededError,
        RemainingByteBudget,
        read_body_capped,
    )

    payload = b"\xff" * 1000
    short = RemainingByteBudget(total_bytes=999)
    with pytest.raises(AggregateBudgetExceededError):
        read_body_capped(_ChunkedResponse(payload), MAX_RESPONSE_BYTES, budget=short)


# ---------------------------------------------------------------------------
# Scenario (c)(i)/(ii): during-read enforcement (mid-read abort + retry share)
# ---------------------------------------------------------------------------


def test_aggregate_abort_mid_read_bounded() -> None:
    """A body crossing the remaining aggregate allowance aborts mid-read, bounded."""
    from docline.fetch.http import (
        CHUNK_SIZE,
        MAX_RESPONSE_BYTES,
        AggregateBudgetExceededError,
        RemainingByteBudget,
        read_body_capped,
    )

    resp = _ChunkedResponse(b"a" * (10 * CHUNK_SIZE))
    budget = RemainingByteBudget(total_bytes=3 * CHUNK_SIZE)
    with pytest.raises(AggregateBudgetExceededError):
        read_body_capped(resp, MAX_RESPONSE_BYTES, budget=budget)
    assert all(s <= CHUNK_SIZE for s in resp.read_sizes)


def test_retried_attempt_decrements_shared_budget() -> None:
    """Bytes consumed by a first (over-cap) attempt still decrement a shared budget."""
    from docline.fetch.http import (
        MAX_RESPONSE_BYTES,
        AggregateBudgetExceededError,
        RemainingByteBudget,
        read_body_capped,
    )

    budget = RemainingByteBudget(total_bytes=1500)
    read_body_capped(_ChunkedResponse(b"a" * 1000), MAX_RESPONSE_BYTES, budget=budget)
    assert budget.remaining == 500
    with pytest.raises(AggregateBudgetExceededError):
        read_body_capped(_ChunkedResponse(b"a" * 1000), MAX_RESPONSE_BYTES, budget=budget)


def test_fetch_response_has_body_byte_count_defaulted_after_redirect_count() -> None:
    """FetchResponse gains body_byte_count (default 0), appended after redirect_count."""
    from docline.fetch.http import FetchResponse

    resp = FetchResponse(url="http://x", status=200, content_type=None, body="hi")
    assert resp.body_byte_count == 0
    resp2 = FetchResponse("http://x", 200, None, "hi", 1, 42)
    assert resp2.redirect_count == 1
    assert resp2.body_byte_count == 42


# ---------------------------------------------------------------------------
# Scenario (c): crawl() RAISES the aggregate error (main + ancillary vectors)
# ---------------------------------------------------------------------------


def _raise_budget(*_a, **_kw):
    from docline.fetch.http import AggregateBudgetExceededError

    async def _boom(*_ia, **_ikw):
        raise AggregateBudgetExceededError("aggregate crawl budget exceeded")

    return _boom()


def test_crawl_reraises_aggregate_on_main_page(monkeypatch) -> None:
    """A budget abort on a main-page fetch RAISES out of crawl() (not a skip)."""
    from docline.fetch.http import AggregateBudgetExceededError

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", _raise_budget)
    with pytest.raises(AggregateBudgetExceededError):
        asyncio.run(
            crawl("http://example.com", CrawlConfig(max_pages=5, respect_robots=False))
        ).results


def test_crawl_reraises_aggregate_on_robots(monkeypatch) -> None:
    """A budget abort on the ancillary robots.txt fetch RAISES out of crawl() (064.024-T)."""
    from docline.fetch.http import AggregateBudgetExceededError

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", _raise_budget)
    with pytest.raises(AggregateBudgetExceededError):
        asyncio.run(
            crawl("http://example.com", CrawlConfig(max_pages=5, respect_robots=True))
        ).results
