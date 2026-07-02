"""Adaptive batched docling-worker dispatch with OCR OOM downsizing (038.003-T).

The batched docling worker processes a *group* of chunks/ranges in one
subprocess to amortize docling's model-load cost. OCR rendering (RapidOCR)
rasterizes each page to a bitmap, and accumulating bitmaps across a group can
exhaust memory — a hard ``std::bad_alloc`` / ``0xC0000005`` crash that kills the
whole subprocess (observed in the 036.002-T cosmos sweep).

:func:`dispatch_batched_groups_with_retry` dispatches each group and, when a
group containing OCR work crashes, **re-splits that group at half the page cap
and retries recursively** (8 → 4 → 2 → 1) before conceding to heuristic
fallback. Successful smaller retries write their per-item envelopes, which the
caller's existing post-pass splices back as docling output, so recovery is
transparent. OCR-free groups never retry — their failure is a genuine docling
error, not a memory-pressure artifact.

The single public entry point is :func:`dispatch_batched_groups_with_retry`.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path

from docline.process.page_range import (
    MAX_BATCHED_PAGES,
    OCR_MAX_BATCHED_PAGES,
    group_by_page_count,
)
from docline.runtime import ocr_budget

_log = logging.getLogger(__name__)

ChunkRunner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]

_MB_PER_GB = 1000.0  # decimal MB per GB, matching ResourceBudget units


def _downsize_cap(
    cap: int,
    *,
    available_ram_gb: float,
    page_megapixels: float | None,
    budget_scale: float,
) -> int:
    """Next OCR group cap after an OOM crash.

    Memory-derived when the host budget and a representative page size are
    known: recompute the calibrated cost-model cap at a shrunk effective budget
    (``budget_scale`` of available memory), so the retry jumps toward a size the
    model expects to fit rather than blindly halving. Falls back to geometric
    halving otherwise. Always strictly less than ``cap`` and ``>= 1`` so the
    retry loop is guaranteed to terminate.

    Args:
        cap: The page cap that just crashed.
        available_ram_gb: Host available RAM in decimal GB (``0`` if unknown).
        page_megapixels: Representative page bitmap size, or ``None`` if unknown.
        budget_scale: Fraction of available memory to assume this retry level.

    Returns:
        The next cap, an integer in ``[1, cap - 1]``.
    """
    if available_ram_gb > 0 and page_megapixels is not None and page_megapixels > 0:
        derived = ocr_budget.max_ocr_pages_per_group(
            available_ram_gb * _MB_PER_GB * budget_scale, page_megapixels=page_megapixels
        )
    else:
        derived = cap // 2
    return max(1, min(cap - 1, derived))


def dispatch_batched_groups_with_retry(
    groups: Sequence[Sequence[int]],
    *,
    inputs: Sequence[str],
    outputs: Sequence[str],
    do_ocr: Sequence[bool],
    page_counts: Sequence[int],
    runner: ChunkRunner,
    manifest_dir: Path,
    ocr_max_pages: int = OCR_MAX_BATCHED_PAGES,
    available_ram_gb: float = 0.0,
    page_megapixels: float | None = None,
) -> list[int]:
    """Dispatch batched docling groups, adaptively shrinking crashed OCR groups.

    Each group is written to a ``--batch`` manifest and run via ``runner``. On a
    hard crash (non-zero exit) of a group that contains any OCR item, the group's
    items are re-split with :func:`group_by_page_count` at half the current cap
    and each subgroup retried — the 8 → 4 → 2 → 1 downsizing. A group with a
    single item, or one already at ``cap == 1``, is not retried; it is left
    without an envelope so the caller's post-pass falls back to heuristic. The
    loop always terminates: the cap halves at each retry level regardless of
    regrouping progress, and single-item groups never recurse.

    Args:
        groups: Initial item-index groups (e.g. from
            ``group_by_page_count_ocr_aware``).
        inputs: Per-item input PDF paths (as strings), indexed by item.
        outputs: Per-item output envelope paths (as strings), indexed by item.
        do_ocr: Per-item OCR flags, indexed by item.
        page_counts: Per-item page counts, indexed by item.
        runner: Callable that runs a worker command and returns the completed
            process (the same injection seam used by the single-chunk path).
        manifest_dir: Directory in which ``--batch`` manifest files are written.
        ocr_max_pages: Starting per-group cap for OCR groups. When
            ``available_ram_gb`` and ``page_megapixels`` are provided, an OOM
            retry recomputes the cap from the calibrated cost model at a shrunk
            budget (041-F); otherwise it halves (038.003-T).
        available_ram_gb: Host available RAM (decimal GB) for memory-derived
            downsizing. ``0`` disables it (falls back to halving).
        page_megapixels: Representative OCR page size for memory-derived
            downsizing. ``None`` disables it (falls back to halving).

    Returns:
        A per-item return code list parallel to ``inputs``: ``0`` when the
        item's last dispatch succeeded, otherwise the crashing exit code
        (signalling the caller to fall back to heuristic for that item).
    """
    returncodes = [0] * len(inputs)
    # Worklist of (item indices, cap, budget_scale). budget_scale shrinks each
    # OCR retry level so memory-derived downsizing re-derives against less RAM.
    work: deque[tuple[list[int], int, float]] = deque()
    for group in groups:
        is_ocr = any(do_ocr[i] for i in group)
        work.append((list(group), ocr_max_pages if is_ocr else MAX_BATCHED_PAGES, 1.0))

    attempt = 0
    while work:
        indices, cap, budget_scale = work.popleft()
        manifest_path = manifest_dir / f"_batch_manifest_{attempt:03d}.json"
        attempt += 1
        manifest_path.write_text(
            json.dumps(
                {
                    "chunks": [
                        {
                            "input": inputs[i],
                            "output": outputs[i],
                            "do_ocr": bool(do_ocr[i]),
                        }
                        for i in indices
                    ]
                }
            ),
            encoding="utf-8",
        )
        cmd = [
            sys.executable,
            "-m",
            "docline._tools.docling_worker",
            "--batch",
            str(manifest_path),
        ]
        completed = runner(cmd)
        if completed.returncode == 0:
            for i in indices:
                returncodes[i] = 0
            continue

        stderr = (getattr(completed, "stderr", "") or "").strip() or "<none captured>"
        is_ocr = any(do_ocr[i] for i in indices)
        if is_ocr and len(indices) > 1 and cap > 1:
            new_scale = budget_scale * 0.5
            new_cap = _downsize_cap(
                cap,
                available_ram_gb=available_ram_gb,
                page_megapixels=page_megapixels,
                budget_scale=new_scale,
            )
            sub_counts = [page_counts[i] for i in indices]
            for sub in group_by_page_count(sub_counts, max_pages=new_cap):
                work.append(([indices[j] for j in sub], new_cap, new_scale))
            _log.warning(
                "OCR batched group OOM (exit=%s) on %d item(s); retrying at cap %d. "
                "Worker stderr: %s",
                completed.returncode,
                len(indices),
                new_cap,
                stderr,
            )
            continue

        # Give up: single item or cap exhausted -> heuristic fallback in caller.
        for i in indices:
            returncodes[i] = completed.returncode
        _log.warning(
            "Batched docling worker group failed (exit=%s) for %d item(s); "
            "those items fall back to heuristic. Worker stderr: %s",
            completed.returncode,
            len(indices),
            stderr,
        )
    return returncodes
