"""Page-range coalescer for the triage-then-repair PDF pipeline.

Converts flagged page indices into ``(start, end)`` ranges with a
configurable context buffer and merges adjacent / near-adjacent ranges
per a merge-gap threshold.

POC reference: ``docs/scratch/2026-06-06-fidelity-scorer-poc.py``
(``coalesce_ranges``).
Plan: ``docs/plans/2026-06-06-triage-then-repair-plan.md`` § U2.
"""

from __future__ import annotations


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
