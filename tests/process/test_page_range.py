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


# ---------------------------------------------------------------------------
# group_by_page_count_ocr_aware — OCR-isolated bounded sub-batching (038-F)
# ---------------------------------------------------------------------------


def test_ocr_max_batched_pages_constant_is_tighter_than_default() -> None:
    """The OCR cap exists and is strictly tighter than the OCR-free cap."""
    from docline.process.page_range import MAX_BATCHED_PAGES, OCR_MAX_BATCHED_PAGES

    assert 1 <= OCR_MAX_BATCHED_PAGES < MAX_BATCHED_PAGES


def test_ocr_aware_empty_input() -> None:
    from docline.process.page_range import group_by_page_count_ocr_aware

    assert group_by_page_count_ocr_aware([], []) == []


def test_ocr_aware_all_ocr_free_matches_plain_grouping() -> None:
    """With no OCR items the OCR-aware result equals plain page-count grouping."""
    from docline.process.page_range import (
        group_by_page_count,
        group_by_page_count_ocr_aware,
    )

    page_counts = [15, 15, 15, 15]
    expected = group_by_page_count(page_counts, max_pages=40)
    actual = group_by_page_count_ocr_aware(page_counts, [False, False, False, False], max_pages=40)
    assert actual == expected == [[0, 1], [2, 3]]


def test_ocr_aware_never_mixes_ocr_and_ocr_free_in_a_group() -> None:
    """An OCR item sandwiched between OCR-free items is isolated to its own group."""
    from docline.process.page_range import group_by_page_count_ocr_aware

    groups = group_by_page_count_ocr_aware(
        [10, 10, 10],
        [False, True, False],
        max_pages=40,
        ocr_max_pages=8,
    )
    assert groups == [[0], [1], [2]]
    ocr = [False, True, False]
    for group in groups:
        assert len({ocr[i] for i in group}) == 1  # group is homogeneous


def test_ocr_aware_ocr_items_bin_under_tighter_cap() -> None:
    """Consecutive OCR items split at the tighter ocr_max_pages cap, not max_pages."""
    from docline.process.page_range import group_by_page_count_ocr_aware

    # Four 3-page OCR ranges: under max_pages=40 they would be one group, but
    # ocr_max_pages=8 forces 3+3=6 (next 3 -> 9 > 8) -> split.
    groups = group_by_page_count_ocr_aware(
        [3, 3, 3, 3],
        [True, True, True, True],
        max_pages=40,
        ocr_max_pages=8,
    )
    assert groups == [[0, 1], [2, 3]]


def test_ocr_aware_ocr_free_items_still_use_full_cap() -> None:
    """OCR-free runs continue to pack up to max_pages even with a small OCR cap."""
    from docline.process.page_range import group_by_page_count_ocr_aware

    groups = group_by_page_count_ocr_aware(
        [20, 20, 1],
        [False, False, False],
        max_pages=40,
        ocr_max_pages=8,
    )
    assert groups == [[0, 1], [2]]


def test_ocr_aware_preserves_document_order() -> None:
    """Flattened group indices remain ascending (splice-back alignment)."""
    from docline.process.page_range import group_by_page_count_ocr_aware

    groups = group_by_page_count_ocr_aware(
        [5, 5, 5, 5, 5],
        [False, True, True, False, False],
        max_pages=40,
        ocr_max_pages=8,
    )
    flat = [i for g in groups for i in g]
    assert flat == [0, 1, 2, 3, 4]
    # Each group is homogeneous in OCR-ness.
    ocr = [False, True, True, False, False]
    for group in groups:
        assert len({ocr[i] for i in group}) == 1


def test_ocr_aware_oversized_single_ocr_item_is_its_own_group() -> None:
    """An OCR item larger than ocr_max_pages still forms its own group."""
    from docline.process.page_range import group_by_page_count_ocr_aware

    groups = group_by_page_count_ocr_aware(
        [20, 5],
        [True, True],
        max_pages=40,
        ocr_max_pages=8,
    )
    assert groups == [[0], [1]]


def test_ocr_aware_length_mismatch_raises() -> None:
    from docline.process.page_range import group_by_page_count_ocr_aware

    with pytest.raises(ValueError):
        group_by_page_count_ocr_aware([10, 10], [True])


@pytest.mark.parametrize("max_pages,ocr_max_pages", [(0, 8), (40, 0)])
def test_ocr_aware_invalid_caps_raise(max_pages: int, ocr_max_pages: int) -> None:
    from docline.process.page_range import group_by_page_count_ocr_aware

    with pytest.raises(ValueError):
        group_by_page_count_ocr_aware(
            [10], [False], max_pages=max_pages, ocr_max_pages=ocr_max_pages
        )
