"""Page-range coalescer for the triage-then-repair PDF pipeline.

Converts flagged page indices into ``(start, end)`` ranges with a
configurable context buffer and merges adjacent / near-adjacent ranges
per a merge-gap threshold.

POC reference: ``docs/scratch/2026-06-06-fidelity-scorer-poc.py``
(``coalesce_ranges``).
Plan: ``docs/plans/2026-06-06-triage-then-repair-plan.md`` § U2.
"""

from __future__ import annotations

from collections.abc import Sequence

# Calibrated cap for bounded sub-batching of the docling batched worker
# (032.003-T / deliberation 2026-06-23). A single 30-page docling conversion
# peaks at ~2 GB RSS and batched mode accumulates working set across
# conversions in one process; capping a batched group at 40 cumulative pages
# keeps a fresh per-group subprocess within a conservative memory envelope
# while still amortizing docling's model-load cost across the group.
MAX_BATCHED_PAGES = 40


def coalesce_ranges(
    flagged_indices: list[int],
    *,
    total_pages: int,
    buffer: int = 1,
    merge_gap: int = 2,
) -> list[tuple[int, int]]:
    """Convert flagged page indices into ``(start, end)`` ranges for docling.

    Args:
        flagged_indices: Zero-based page indices the scorer triggered on.
            Order does not matter; duplicates are tolerated.
        total_pages: Total page count of the source PDF (used to clamp
            output ranges). Must be ``>= 0``.
        buffer: Pages of context to include on each side of every
            flagged index. Must be ``>= 0``.
        merge_gap: Two ranges are merged when their gap is ``<=`` this
            many pages. Must be ``>= 0``.

    Returns:
        Sorted list of ``(start_inclusive, end_inclusive)`` page-index
        tuples, clamped to ``[0, total_pages - 1]``.

    Raises:
        ValueError: If ``buffer < 0``, ``merge_gap < 0``, or
            ``total_pages < 0``.
    """
    if buffer < 0:
        raise ValueError(f"buffer must be >= 0, got {buffer}")
    if merge_gap < 0:
        raise ValueError(f"merge_gap must be >= 0, got {merge_gap}")
    if total_pages < 0:
        raise ValueError(f"total_pages must be >= 0, got {total_pages}")

    if not flagged_indices or total_pages == 0:
        return []

    expanded = sorted(
        {(max(0, idx - buffer), min(total_pages - 1, idx + buffer)) for idx in flagged_indices}
    )

    merged: list[tuple[int, int]] = []
    for start, end in expanded:
        if merged and start - merged[-1][1] <= merge_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def group_by_page_count(
    page_counts: Sequence[int],
    *,
    max_pages: int = MAX_BATCHED_PAGES,
) -> list[list[int]]:
    """Greedy bin-pack item indices into groups bounded by cumulative page count.

    Walks ``page_counts`` in order, accumulating item indices into the current
    group until adding the next item would exceed ``max_pages``; then starts a
    new group. Document order is preserved (groups and within-group indices are
    ascending) so downstream splice-back stays aligned. A single item whose page
    count exceeds ``max_pages`` forms its own group — it cannot be split below
    the existing range/chunk granularity.

    Args:
        page_counts: Per-item page counts in document order.
        max_pages: Maximum cumulative pages per group. Must be ``>= 1``.

    Returns:
        A list of groups, each a list of indices into ``page_counts``. The
        concatenation of all groups equals ``range(len(page_counts))``.

    Raises:
        ValueError: If ``max_pages < 1``.
    """
    if max_pages < 1:
        raise ValueError(f"max_pages must be >= 1, got {max_pages}")

    groups: list[list[int]] = []
    current: list[int] = []
    current_sum = 0
    for index, count in enumerate(page_counts):
        if current and current_sum + count > max_pages:
            groups.append(current)
            current = []
            current_sum = 0
        current.append(index)
        current_sum += count
    if current:
        groups.append(current)
    return groups
