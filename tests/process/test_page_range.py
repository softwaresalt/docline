"""Tests for ``docline.process.page_range`` (task 019.002-T)."""

from __future__ import annotations

import pytest


def test_empty_input_returns_empty_list() -> None:
    """No flagged pages should produce no ranges."""
    from docline.process.page_range import coalesce_ranges

    assert coalesce_ranges([], total_pages=100, buffer=1, merge_gap=2) == []


def test_single_flag_produces_single_range_with_buffer() -> None:
    """A lone flagged index produces a single range expanded by ±buffer."""
    from docline.process.page_range import coalesce_ranges

    assert coalesce_ranges([10], total_pages=100, buffer=1, merge_gap=2) == [(9, 11)]
    assert coalesce_ranges([10], total_pages=100, buffer=2, merge_gap=2) == [(8, 12)]


def test_adjacent_indices_merge_across_gap_threshold() -> None:
    """Adjacent/near-adjacent flagged indices merge into one range when gap <= merge_gap."""
    from docline.process.page_range import coalesce_ranges

    actual = coalesce_ranges(
        [3, 4, 5, 12, 47, 48, 100],
        total_pages=200,
        buffer=1,
        merge_gap=2,
    )
    assert actual == [(2, 6), (11, 13), (46, 49), (99, 101)]


def test_boundary_clamping_at_zero_and_total_pages_minus_one() -> None:
    """Flags at indices 0 and total_pages-1 clamp to valid range bounds."""
    from docline.process.page_range import coalesce_ranges

    assert coalesce_ranges([0], total_pages=10, buffer=2, merge_gap=2) == [(0, 2)]
    assert coalesce_ranges([9], total_pages=10, buffer=2, merge_gap=2) == [(7, 9)]


@pytest.mark.parametrize(
    "buffer,merge_gap,total_pages",
    [(-1, 2, 100), (1, -1, 100), (1, 2, -1)],
)
def test_invalid_inputs_raise_value_error(buffer: int, merge_gap: int, total_pages: int) -> None:
    """Negative numeric inputs must raise ValueError."""
    from docline.process.page_range import coalesce_ranges

    with pytest.raises(ValueError):
        coalesce_ranges([5], total_pages=total_pages, buffer=buffer, merge_gap=merge_gap)
