"""Triage-then-repair orchestrator for oversized PDFs.

Stub module — implementations land in tasks 019.003-T (U3 main
orchestrator), 019.006-T (U6 report-only path), and 019.007-T (U7 QA
tripwire mode).

The orchestrator runs five passes:

1. Heuristic baseline across the whole PDF via
   :func:`docline.readers.pdf.read_pdf_pages` with
   ``layout_engine="heuristic"``.
2. Score each page via
   :func:`docline.process.fidelity_scorer.score_page`.
3. Coalesce flagged page indices into ranges via
   :func:`docline.process.page_range.coalesce_ranges`.
4. Splice each range into a temp PDF using ``pypdf.PdfWriter`` and run
   the existing ``docling_worker`` subprocess on each splice.
5. Merge per-page outputs into a final list where flagged pages come
   from docling and the rest from heuristic.

Plan: ``docs/plans/2026-06-06-triage-then-repair-plan.md`` § U3, U6, U7.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from docline.process.fidelity_scorer import PageScore
from docline.runtime.resource_probe import ResourceBudget

ChunkRunner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]
PageScorer = Callable[[int, str, object | None], PageScore]


@dataclass(frozen=True)
class TriageResult:
    """Aggregated outcome of :func:`process_pdf_triaged`.

    Attributes:
        source: Source PDF path.
        pages: Per-page final markdown (one entry per source page).
        engine_per_page: Engine that produced each page
            (``"heuristic"`` or ``"docling"``).
        flagged_ranges: Page ranges that were routed through docling.
        metadata: Additional run metadata (split chunks, fallback
            counts, QA disagreements, weights file, etc.).
    """

    source: Path
    pages: tuple[str, ...]
    engine_per_page: tuple[str, ...]
    flagged_ranges: tuple[tuple[int, int], ...]
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class QASampling:
    """Configuration for the U7 QA tripwire mode.

    When passed to :func:`process_pdf_triaged`, that fraction of
    unflagged ('clean') pages is randomly re-run through docling and
    diffed against the heuristic output. Disagreement count is recorded
    in :attr:`TriageResult.metadata` as ``"qa_disagreements"``.

    Attributes:
        sample_rate: Fraction of unflagged pages to re-run (0.0–1.0).
        random_seed: Optional integer seed for deterministic sampling.
            ``None`` uses a system-clock seed. The resolved seed is
            recorded in metadata as ``"qa_random_seed_used"``.
        max_sampled_pages: Cap on the number of unflagged pages sampled
            per run. Bounds runtime on long documents.
    """

    sample_rate: float
    random_seed: int | None = None
    max_sampled_pages: int = 50


def process_pdf_triaged(
    path: Path,
    *,
    output_dir: Path,
    budget: ResourceBudget | None = None,
    runner: ChunkRunner | None = None,
    scorer: PageScorer | None = None,
    buffer: int = 1,
    merge_gap: int = 2,
    qa_sampling: QASampling | None = None,
) -> TriageResult:
    """Process a PDF via heuristic baseline + selective docling repair.

    Args:
        path: Source PDF path.
        output_dir: Directory for splice temp files and per-page outputs.
            Must be inside the workspace per Constitution IV.
        budget: Optional resource budget snapshot. Defaults to a fresh
            :func:`docline.runtime.resource_probe.probe` call.
        runner: Injectable docling subprocess runner; defaults to the
            production subprocess invocation. Tests substitute a
            deterministic stand-in.
        scorer: Injectable page scorer; defaults to
            :func:`docline.process.fidelity_scorer.score_page`.
        buffer: Pages of context around each flagged page.
        merge_gap: Merge adjacent / near-adjacent ranges when their gap
            is at most this many pages.
        qa_sampling: Optional QA tripwire configuration (see
            :class:`QASampling`). When ``None``, only flagged ranges
            are sent to docling.

    Returns:
        :class:`TriageResult` with per-page outputs, engine attribution,
        flagged ranges, and run metadata.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    raise NotImplementedError("019.003-T: process_pdf_triaged")


def triage_report_only(
    path: Path,
    *,
    output_dir: Path,
    report_tsv_path: Path,
    scorer: PageScorer | None = None,
    buffer: int = 1,
    merge_gap: int = 2,
) -> TriageResult:
    """Run heuristic + score only; emit per-page TSV; never call docling.

    Used for empirical calibration of signal weights and thresholds
    before triage mode is recommended for production use.

    Args:
        path: Source PDF path.
        output_dir: Directory for any heuristic outputs (no docling
            splices written).
        report_tsv_path: Path where the per-page TSV is written. Columns:
            ``timestamp, page_index, signals..., aggregate,
            needs_docling, reason``.
        scorer: Injectable page scorer; defaults to
            :func:`docline.process.fidelity_scorer.score_page`.
        buffer: Pages of context (recorded only — no docling invocation).
        merge_gap: Merge gap (recorded only — no docling invocation).

    Returns:
        :class:`TriageResult` with ``engine_per_page`` all-heuristic and
        ``flagged_ranges`` populated for downstream review.
    """
    raise NotImplementedError("019.006-T: triage_report_only")


def dispatch_pdf_mode(
    mode: str,
    path: Path,
    *,
    output_dir: Path,
    **kwargs: object,
) -> object:
    """Route a PDF process invocation to the correct mode handler.

    Called by the CLI when ``--pdf-mode`` is set. Dispatches to
    :func:`docline.process.pdf_batch.process_pdf_in_chunks` for the
    ``"auto"`` mode (existing behavior) or
    :func:`process_pdf_triaged` for the ``"triage"`` mode.

    Args:
        mode: Mode name from ``--pdf-mode`` (``"auto"`` or ``"triage"``).
        path: Source PDF path.
        output_dir: Output directory for the chosen pipeline.
        **kwargs: Mode-specific keyword arguments forwarded to the
            chosen handler.

    Returns:
        Result object from the chosen handler (``BatchResult`` or
        :class:`TriageResult`).

    Raises:
        ValueError: If ``mode`` is not a recognized value.
    """
    raise NotImplementedError("019.004-T: dispatch_pdf_mode")
