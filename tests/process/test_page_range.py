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


# ---------------------------------------------------------------------------
# group_by_page_count — bounded sub-batching (032.003-T / 037-S)
# ---------------------------------------------------------------------------


def test_max_batched_pages_default_constant() -> None:
    """The calibrated cap constant exists and is 40 (per 2026-06-23 deliberation)."""
    from docline.process.page_range import MAX_BATCHED_PAGES

    assert MAX_BATCHED_PAGES == 40


def test_group_by_page_count_empty_input() -> None:
    from docline.process.page_range import group_by_page_count

    assert group_by_page_count([], max_pages=40) == []


def test_group_by_page_count_packs_within_cap_in_order() -> None:
    """Greedy bin-pack: items accumulate until adding the next would exceed cap."""
    from docline.process.page_range import group_by_page_count

    # 10+10+10=30 (next 10 would make 40, allowed)... use a cap of 25.
    groups = group_by_page_count([10, 10, 10, 5], max_pages=25)
    assert groups == [[0, 1], [2, 3]]


def test_group_by_page_count_boundary_sum_equal_to_cap_stays_together() -> None:
    """A cumulative sum exactly equal to the cap does not split."""
    from docline.process.page_range import group_by_page_count

    groups = group_by_page_count([20, 20, 1], max_pages=40)
    assert groups == [[0, 1], [2]]


def test_group_by_page_count_oversized_single_item_is_its_own_group() -> None:
    """An item larger than the cap forms its own group (cannot split further)."""
    from docline.process.page_range import group_by_page_count

    groups = group_by_page_count([50, 10, 10], max_pages=40)
    assert groups == [[0], [1, 2]]


def test_group_by_page_count_preserves_document_order() -> None:
    from docline.process.page_range import group_by_page_count

    groups = group_by_page_count([15, 15, 15, 15], max_pages=40)
    # 15+15=30 (next 15 -> 45 > 40), so [0,1] then [2,3].
    assert groups == [[0, 1], [2, 3]]
    flat = [i for g in groups for i in g]
    assert flat == [0, 1, 2, 3]


def test_group_by_page_count_invalid_cap_raises() -> None:
    from docline.process.page_range import group_by_page_count

    with pytest.raises(ValueError):
        group_by_page_count([10], max_pages=0)
