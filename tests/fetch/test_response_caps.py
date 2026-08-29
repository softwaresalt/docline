"""Shared-fetch per-dimension resource-cap harness (064.012-T, red).

(a) FetchRequest.max_pages above the hard cap is rejected at model validation.
(b) A response body exceeding MAX_RESPONSE_BYTES is aborted without full
    buffering (streamed bounded read, not a single response.read()).
Greened by 064.013-T.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from docline.app_models import FetchRequest


class _ChunkedResponse:
    """Fake response whose read(n) yields up to n bytes and records read sizes."""

    def __init__(self, total: int) -> None:
        self._remaining = total
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if self._remaining <= 0:
            return b""
        if size is None or size < 0:
            size = self._remaining
        n = min(size, self._remaining)
        self._remaining -= n
        return b"a" * n


# ---------------------------------------------------------------------------
# Scenario (a): max_pages upper bound
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [1, 50, 1000])
def test_max_pages_within_cap_accepted(value: int) -> None:
    """max_pages within 1..MAX_PAGES_LIMIT is accepted."""
    req = FetchRequest(source="http://example.com", max_pages=value)
    assert req.max_pages == value


@pytest.mark.parametrize("value", [1001, 5000, 10_000])
def test_max_pages_above_cap_rejected(value: int) -> None:
    """max_pages above MAX_PAGES_LIMIT (1000) is rejected at model validation."""
    with pytest.raises(ValidationError):
        FetchRequest(source="http://example.com", max_pages=value)


def test_max_pages_none_still_allowed() -> None:
    """max_pages None is still allowed (uses the crawler default)."""
    req = FetchRequest(source="http://example.com")
    assert req.max_pages is None


# ---------------------------------------------------------------------------
# Scenario (b): per-response streamed byte cap
# ---------------------------------------------------------------------------


def test_response_within_cap_read_fully() -> None:
    """A response at exactly MAX_RESPONSE_BYTES is read fully."""
    from docline.fetch.http import MAX_RESPONSE_BYTES, read_body_capped

    resp = _ChunkedResponse(MAX_RESPONSE_BYTES)
    body = read_body_capped(resp, MAX_RESPONSE_BYTES)
    assert len(body) == MAX_RESPONSE_BYTES


def test_oversized_response_aborted_without_full_buffering() -> None:
    """A response exceeding MAX_RESPONSE_BYTES aborts mid-stream (bounded over-read)."""
    from docline.fetch.http import (
        CHUNK_SIZE,
        MAX_RESPONSE_BYTES,
        ResponseByteLimitError,
        read_body_capped,
    )

    # Far more than the cap; the reader must abort near the boundary.
    resp = _ChunkedResponse(MAX_RESPONSE_BYTES + 5 * CHUNK_SIZE)
    with pytest.raises(ResponseByteLimitError):
        read_body_capped(resp, MAX_RESPONSE_BYTES)
    # Bounded over-read: never requested more than CHUNK_SIZE per read, and the
    # crossing read observed at most one byte beyond the allowance.
    assert all(s <= CHUNK_SIZE for s in resp.read_sizes)
