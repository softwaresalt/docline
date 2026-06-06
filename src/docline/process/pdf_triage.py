"""Triage-then-repair orchestrator for oversized PDFs.

The orchestrator runs five passes:

1. Heuristic baseline across the whole PDF via
   :func:`docline.readers.pdf.read_pdf_pages` with ``layout_engine="heuristic"``.
2. Score each page via :func:`docline.process.fidelity_scorer.score_page`.
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
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pypdf

from docline.process.fidelity_scorer import PageScore, score_page
from docline.process.page_range import coalesce_ranges
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
        metadata: Additional run metadata (flagged_ranges count,
            subprocess_fallback_count, total_pages, qa_disagreements,
            qa_random_seed_used, etc.).
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


def _default_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Default subprocess runner — captures stderr so diagnostics survive."""
    return subprocess.run(args, capture_output=True, text=True, check=False)


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
        budget: Optional resource budget snapshot. Currently informational —
            triage mode does not use the budget for chunking decisions
            (the scorer drives the split).
        runner: Injectable docling subprocess runner; defaults to
            :func:`subprocess.run`. Tests substitute a deterministic
            stand-in.
        scorer: Injectable page scorer; defaults to
            :func:`docline.process.fidelity_scorer.score_page`.
        buffer: Pages of context around each flagged page.
        merge_gap: Merge adjacent / near-adjacent ranges when their gap
            is at most this many pages.
        qa_sampling: Optional QA tripwire configuration (see
            :class:`QASampling`). When ``None``, only flagged ranges
            are sent to docling. U7 extends this path with actual
            sampling; this U3 implementation accepts the parameter and
            ignores it.

    Returns:
        :class:`TriageResult` with per-page outputs, engine attribution,
        flagged ranges, and run metadata.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    if runner is None:
        runner = _default_runner
    if scorer is None:
        scorer = score_page

    # Pass 1: Heuristic baseline across the whole PDF.
    # Iterate pypdf pages directly so the per-page mapping is preserved
    # even when individual pages have no extractable text (e.g. blank
    # pages, image-only pages). The public read_pdf_pages helper filters
    # out empty pages, which loses page-index alignment that this
    # orchestrator requires for splice-back.
    reader = pypdf.PdfReader(str(path), strict=False)
    total_pages = len(reader.pages)
    heuristic_pages: list[str] = []
    for page_idx in range(total_pages):
        try:
            text = reader.pages[page_idx].extract_text() or ""
        except Exception:  # noqa: BLE001 — keep batch alive on per-page extraction failure
            text = ""
        heuristic_pages.append(text)

    # Pass 2: Score each page.
    scores: list[PageScore] = []
    for idx, text in enumerate(heuristic_pages):
        page_metadata = reader.pages[idx] if idx < len(reader.pages) else None
        scores.append(scorer(idx, text, page_metadata))
    flagged_indices = [s.page_index for s in scores if s.needs_docling]

    # Pass 3: Coalesce flagged indices into ranges.
    flagged_ranges = coalesce_ranges(
        flagged_indices,
        total_pages=total_pages,
        buffer=buffer,
        merge_gap=merge_gap,
    )

    # Pass 4 + 5: Splice each range into a temp PDF, run docling, merge.
    final_pages: list[str] = list(heuristic_pages)
    engine_per_page: list[str] = ["heuristic"] * total_pages
    subprocess_fallback_count = 0

    splice_cache = output_dir / "splices"
    splice_cache.mkdir(parents=True, exist_ok=True)

    for start, end in flagged_ranges:
        splice_pdf = splice_cache / f"splice-{start:04d}-{end:04d}.pdf"
        splice_md = splice_cache / f"splice-{start:04d}-{end:04d}.md"

        writer = pypdf.PdfWriter()
        for page_idx in range(start, end + 1):
            if page_idx < len(reader.pages):
                writer.add_page(reader.pages[page_idx])
        with splice_pdf.open("wb") as fh:
            writer.write(fh)

        cmd = [
            sys.executable,
            "-m",
            "docline._tools.docling_worker",
            str(splice_pdf),
            str(splice_md),
        ]
        completed = runner(cmd)

        if completed.returncode == 0 and splice_md.exists():
            blob = splice_md.read_text(encoding="utf-8")
            # Attach the docling blob to the first page of the range; mark
            # all pages in the range as docling-sourced. Per-page splitting
            # of the blob is a known limitation of the docling_worker
            # contract (single output per subprocess invocation). Downstream
            # consumers can reconstruct page boundaries from the engine
            # attribution + the blob content.
            for page_idx in range(start, end + 1):
                if page_idx == start:
                    final_pages[page_idx] = blob
                else:
                    final_pages[page_idx] = ""
                engine_per_page[page_idx] = "docling"
        else:
            # Subprocess failed — keep heuristic output for this range and
            # record the fallback in metadata. Batch continues.
            subprocess_fallback_count += 1

    metadata: dict[str, object] = {
        "total_pages": total_pages,
        "flagged_pages_count": len(flagged_indices),
        "flagged_ranges_count": len(flagged_ranges),
        "subprocess_fallback_count": subprocess_fallback_count,
        "buffer": buffer,
        "merge_gap": merge_gap,
    }

    return TriageResult(
        source=path,
        pages=tuple(final_pages),
        engine_per_page=tuple(engine_per_page),
        flagged_ranges=tuple(flagged_ranges),
        metadata=metadata,
    )


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

    Stub — implementation lands in task 019.006-T (U6).
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
    ``"auto"`` mode (existing behavior) or :func:`process_pdf_triaged`
    for the ``"triage"`` mode.

    Args:
        mode: Mode name from ``--pdf-mode`` (``"auto"`` or ``"triage"``).
        path: Source PDF path.
        output_dir: Output directory for the chosen pipeline.
        **kwargs: Mode-specific keyword arguments forwarded to the
            chosen handler. The CLI is responsible for constructing
            and passing the resource ``budget``, ``runner``, etc. When
            no ``budget`` is provided for the ``"auto"`` mode, a
            docling-disabled budget is used so the dispatcher does not
            silently invoke a heavyweight ML pipeline (the production
            CLI always passes an explicit probed budget).

    Returns:
        Result object from the chosen handler (``BatchResult`` for
        ``"auto"`` or :class:`TriageResult` for ``"triage"``).

    Raises:
        ValueError: If ``mode`` is not a recognized value.
    """
    if mode == "triage":
        return process_pdf_triaged(path, output_dir=output_dir, **kwargs)  # type: ignore[arg-type]
    if mode == "auto":
        from docline.process.pdf_batch import process_pdf_in_chunks

        if "budget" not in kwargs:
            kwargs["budget"] = _no_docling_budget()
        return process_pdf_in_chunks(path, output_dir=output_dir, **kwargs)  # type: ignore[arg-type]
    raise ValueError(f"unknown pdf-mode: {mode!r}; supported: 'auto', 'triage'")


def _no_docling_budget() -> ResourceBudget:
    """Build a budget that forces process_pdf_in_chunks down the heuristic path.

    Used as the default by :func:`dispatch_pdf_mode` for the ``"auto"``
    mode when the caller did not supply a ``budget`` kwarg. Ensures the
    dispatcher never silently invokes a heavyweight ML pipeline; the
    production CLI must pass an explicit probed budget to enable docling.
    """
    return ResourceBudget(
        available_ram_gb=0.0,
        total_ram_gb=0.0,
        logical_cpus=1,
        pagefile_pressure=True,
        accelerator_device="cpu",
        gpu_name=None,
        gpu_vram_gb=None,
        gpu_compute_capability=None,
        recommended_concurrency=1,
        recommended_docling_max_pages=0,
        recommended_docling_max_mb=0,
        serialize_docling=True,
        omp_thread_count=1,
    )
