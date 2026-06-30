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

# Tighter cap for OCR-flagged groups (038-F). OCR rendering (RapidOCR) rasterizes
# each page to a bitmap and the onnxruntime graph allocates large intermediate
# tensors on top of docling's ~2 GB/30-page working set — the combination caused
# a hard 0xC0000005 / std::bad_alloc crash that killed an entire batched group
# (036.002-T cosmos sweep, 2026-06-27). OCR-flagged items are therefore isolated
# from OCR-free items AND bounded by this much smaller cap so that (a) an OCR OOM
# cannot drag OCR-free docling ranges down with it, and (b) far fewer page
# bitmaps are resident per OCR subprocess. 8 keeps docling's model-load cost
# amortized across a short run of scanned pages while staying well inside a
# conservative memory envelope; lower it further if OCR OOMs recur.
OCR_MAX_BATCHED_PAGES = 8


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


def group_by_page_count_ocr_aware(
    page_counts: Sequence[int],
    needs_ocr: Sequence[bool],
    *,
    max_pages: int = MAX_BATCHED_PAGES,
    ocr_max_pages: int = OCR_MAX_BATCHED_PAGES,
) -> list[list[int]]:
    """Bin-pack item indices into groups, isolating OCR items under a tighter cap.

    Extends :func:`group_by_page_count` with OCR awareness for the batched
    docling worker (038-F). A single greedy pass over the items in document
    order starts a new group whenever the next item's OCR-ness differs from the
    current group's, or whenever adding it would exceed that group's cap. As a
    result:

    * **No group mixes OCR and OCR-free items.** A hard OCR OOM crash kills the
      whole worker subprocess, so isolation guarantees only the OCR-flagged
      items in that one group fall back to heuristic — OCR-free docling work in
      neighbouring groups survives.
    * **OCR-flagged items bin under** ``ocr_max_pages`` (memory driven by page
      bitmaps), while **OCR-free items bin under** ``max_pages`` (unchanged
      behaviour). With ``needs_ocr`` all ``False`` the result is identical to
      :func:`group_by_page_count`.

    Document order is preserved within and across groups (groups are contiguous
    runs of ascending indices) so downstream splice-back stays aligned. A single
    item whose page count exceeds its cap forms its own group — it cannot be
    split below the existing range/chunk granularity.

    Args:
        page_counts: Per-item page counts in document order.
        needs_ocr: Per-item OCR flags, parallel to ``page_counts``.
        max_pages: Maximum cumulative pages per OCR-free group. Must be ``>= 1``.
        ocr_max_pages: Maximum cumulative pages per OCR group. Must be ``>= 1``.

    Returns:
        A list of groups, each a list of indices into ``page_counts``. The
        concatenation of all groups equals ``range(len(page_counts))``.

    Raises:
        ValueError: If ``max_pages < 1``, ``ocr_max_pages < 1``, or
            ``len(page_counts) != len(needs_ocr)``.
    """
    if max_pages < 1:
        raise ValueError(f"max_pages must be >= 1, got {max_pages}")
    if ocr_max_pages < 1:
        raise ValueError(f"ocr_max_pages must be >= 1, got {ocr_max_pages}")
    if len(page_counts) != len(needs_ocr):
        raise ValueError(
            "page_counts and needs_ocr must have equal length, "
            f"got {len(page_counts)} and {len(needs_ocr)}"
        )

    groups: list[list[int]] = []
    current: list[int] = []
    current_sum = 0
    current_ocr: bool | None = None
    for index, count in enumerate(page_counts):
        item_ocr = bool(needs_ocr[index])
        cap = ocr_max_pages if item_ocr else max_pages
        if current and (item_ocr != current_ocr or current_sum + count > cap):
            groups.append(current)
            current = []
            current_sum = 0
        current.append(index)
        current_sum += count
        current_ocr = item_ocr
    if current:
        groups.append(current)
    return groups
