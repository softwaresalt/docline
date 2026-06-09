"""Triage-then-repair orchestrator for oversized PDFs.

The orchestrator runs five passes:

1. Heuristic baseline across the whole PDF via direct pypdf per-page
   extraction (preserves per-page index alignment for splice-back).
2. Score each page via :func:`docline.process.fidelity_scorer.score_page`.
3. Coalesce flagged page indices into ranges via
   :func:`docline.process.page_range.coalesce_ranges`.
4. Splice each range into a temp PDF using ``pypdf.PdfWriter`` and run
   the existing ``docling_worker`` subprocess on each splice.
5. Merge per-page outputs into a final list where flagged pages come
   from docling and the rest from heuristic.

Sibling entry points:

* :func:`triage_report_only` — runs passes 1-2 only and emits a
  per-page TSV without invoking docling (calibration mode, U6).
* :func:`dispatch_pdf_mode` — routing entry for the CLI ``--pdf-mode``
  flag (U4).

QA tripwire (U7): when a :class:`QASampling` configuration is passed,
:func:`process_pdf_triaged` randomly re-runs that fraction of
*unflagged* pages through docling and records the disagreement count
in :attr:`TriageResult.metadata` as ``"qa_disagreements"``.

Plan: ``docs/plans/2026-06-06-triage-then-repair-plan.md`` § U3, U6, U7.
"""

from __future__ import annotations

import csv
import logging
import random
import re
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pypdf
from markdown_it import MarkdownIt

from docline.process.fidelity_scorer import PageScore, score_page
from docline.process.page_range import coalesce_ranges
from docline.process.quality_metrics import compute_quality_metrics
from docline.runtime.resource_probe import ResourceBudget

_log = logging.getLogger(__name__)

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
        similarity_threshold: Jaccard-similarity threshold (020.003-T / U2).
            Disagreements are counted only when content similarity falls
            BELOW this threshold. Default 0.7 chosen empirically from
            the 2026-06-07 PA4 inspection: page 107 (code-fence /
            no-fence, same content) ~0.9 similarity; page 470
            (heuristic broken text vs docling table) <0.3.
    """

    sample_rate: float
    random_seed: int | None = None
    max_sampled_pages: int = 50
    similarity_threshold: float = 0.7


def _default_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Default subprocess runner — captures stderr so diagnostics survive."""
    return subprocess.run(args, capture_output=True, text=True, check=False)


_TOKEN_RE = re.compile(r"\w+")
_MARKITDOWN_INSTANCE: object | None = None


def _get_markitdown() -> object:
    """Return a process-wide MarkItDown instance, constructing once on first call.

    The MarkItDown constructor initializes the pdfminer.six backend and
    its plugins; doing this on every page would multiply the per-page
    overhead by 3,000+ on a cosmos-class document. Hoist to a module-
    level singleton instead.

    Also silences two noisy pdfminer loggers that fire per-page on PDFs
    with malformed font descriptors or CMaps. The warnings are
    informational only — pdfminer recovers and produces correct text —
    but on a 3,426-page corpus they produce thousands of spurious lines
    that drown out real diagnostics. Suppressed loggers:

    * ``pdfminer.pdffont`` (FontBBox / CMap parse failures)
    * ``pdfminer.pdfinterp`` (uncommon operator warnings)
    """
    global _MARKITDOWN_INSTANCE
    if _MARKITDOWN_INSTANCE is None:
        for _name in ("pdfminer.pdffont", "pdfminer.pdfinterp"):
            logging.getLogger(_name).setLevel(logging.ERROR)

        from markitdown import MarkItDown

        _MARKITDOWN_INSTANCE = MarkItDown(enable_plugins=False)
    return _MARKITDOWN_INSTANCE


def _content_similarity(a: str, b: str) -> float:
    """Jaccard similarity of lowercased + tokenized content (020.003-T / U2).

    Tokenization uses ``re.findall(r"\\w+", text.lower())`` — Unicode-aware,
    case-insensitive, handles whitespace + punctuation in one pass.

    Args:
        a: First text.
        b: Second text.

    Returns:
        Float in ``[0.0, 1.0]``. ``1.0`` means substantially identical
        token sets; ``0.0`` means no token overlap. Both empty returns
        ``1.0`` (vacuously identical); exactly one empty returns ``0.0``.
    """
    tokens_a = set(_TOKEN_RE.findall(a.lower()))
    tokens_b = set(_TOKEN_RE.findall(b.lower()))
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union


def _heuristic_extract(
    reader: object,
    page_idx: int,
    engine: str,
    splice_cache: Path,
) -> tuple[str, bool]:
    """Extract heuristic baseline text for one page via the chosen engine.

    Args:
        reader: ``pypdf.PdfReader`` instance for the source PDF.
        page_idx: Zero-based page index.
        engine: ``"markitdown"`` or ``"pypdf"``. When ``"markitdown"``,
            splices the page into ``splice_cache`` and invokes
            ``markitdown.MarkItDown(enable_plugins=False).convert(splice).text_content``.
            When ``"pypdf"``, uses ``reader.pages[page_idx].extract_text()``
            directly.
        splice_cache: Directory under ``output_dir`` for splice temp PDFs.

    Returns:
        Tuple of ``(extracted_text, fallback_triggered)``. ``fallback_triggered``
        is ``True`` when markitdown was requested but failed and the function
        fell back to pypdf for this page.
    """
    if engine == "pypdf":
        try:
            return reader.pages[page_idx].extract_text() or "", False  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 — keep batch alive on per-page failure
            return "", False

    if engine == "markitdown":
        splice_cache.mkdir(parents=True, exist_ok=True)
        splice_pdf = splice_cache / f"baseline-{page_idx:04d}.pdf"
        try:
            writer = pypdf.PdfWriter()
            writer.add_page(reader.pages[page_idx])  # type: ignore[attr-defined]
            with splice_pdf.open("wb") as fh:
                writer.write(fh)
            md = _get_markitdown()
            result = md.convert(str(splice_pdf))  # type: ignore[attr-defined]
            text = result.text_content or ""
            return text, False
        except Exception:  # noqa: BLE001 — defensive: markitdown can fail on weird PDFs
            _log.warning(
                "markitdown failed on page %d; falling back to pypdf", page_idx, exc_info=True
            )
            try:
                return reader.pages[page_idx].extract_text() or "", True  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                return "", True

    raise ValueError(f"unknown baseline_engine {engine!r}; expected 'markitdown' or 'pypdf'")


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
    baseline_engine: str = "markitdown",
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
        baseline_engine: Heuristic baseline extractor selection.
            ``"markitdown"`` (default, 020.002-T / U1) routes each
            page through :class:`markitdown.MarkItDown`, producing
            real markdown for numbered lists, code fences, and headings.
            ``"pypdf"`` uses ``reader.pages[i].extract_text()``
            directly — preserves the pre-020.002-T behavior, used for
            regression coverage and as the fallback when markitdown
            fails on a page.

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
    splice_cache = output_dir / "splices"
    splice_cache.mkdir(parents=True, exist_ok=True)
    heuristic_pages: list[str] = []
    baseline_engine_fallback = 0
    for page_idx in range(total_pages):
        text, fallback = _heuristic_extract(reader, page_idx, baseline_engine, splice_cache)
        heuristic_pages.append(text)
        if fallback:
            baseline_engine_fallback += 1

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
        "baseline_engine": baseline_engine,
        "baseline_engine_fallback": baseline_engine_fallback,
    }

    # QA tripwire: sample unflagged pages, run docling on each, count
    # disagreements with heuristic output.
    if qa_sampling is not None and qa_sampling.sample_rate > 0:
        unflagged_indices = [i for i in range(total_pages) if engine_per_page[i] == "heuristic"]
        if qa_sampling.random_seed is None:
            seed_used = int(time.time() * 1000) & 0xFFFFFFFF
        else:
            seed_used = qa_sampling.random_seed
        rng = random.Random(seed_used)
        target_count = min(
            int(len(unflagged_indices) * qa_sampling.sample_rate),
            qa_sampling.max_sampled_pages,
            len(unflagged_indices),
        )
        sampled = sorted(rng.sample(unflagged_indices, target_count)) if target_count > 0 else []

        qa_disagreements = 0
        bucket_counts: dict[str, int] = {">=0.9": 0, "0.7-0.9": 0, "0.5-0.7": 0, "<0.5": 0}
        for page_idx in sampled:
            qa_pdf = splice_cache / f"qa-{page_idx:04d}.pdf"
            qa_md = splice_cache / f"qa-{page_idx:04d}.md"

            qa_writer = pypdf.PdfWriter()
            qa_writer.add_page(reader.pages[page_idx])
            with qa_pdf.open("wb") as fh:
                qa_writer.write(fh)

            qa_cmd = [
                sys.executable,
                "-m",
                "docline._tools.docling_worker",
                str(qa_pdf),
                str(qa_md),
            ]
            qa_completed = runner(qa_cmd)
            if qa_completed.returncode == 0 and qa_md.exists():
                docling_text = qa_md.read_text(encoding="utf-8")
                heuristic_text = heuristic_pages[page_idx]
                similarity = _content_similarity(docling_text, heuristic_text)
                if similarity >= 0.9:
                    bucket_counts[">=0.9"] += 1
                elif similarity >= 0.7:
                    bucket_counts["0.7-0.9"] += 1
                elif similarity >= 0.5:
                    bucket_counts["0.5-0.7"] += 1
                else:
                    bucket_counts["<0.5"] += 1
                if similarity < qa_sampling.similarity_threshold:
                    qa_disagreements += 1

        metadata["qa_sampled_count"] = len(sampled)
        metadata["qa_disagreements"] = qa_disagreements
        metadata["qa_random_seed_used"] = seed_used
        metadata["qa_similarity_histogram"] = bucket_counts

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
    baseline_engine: str = "markitdown",
) -> TriageResult:
    """Run heuristic + score only; emit per-page TSV; never call docling.

    Used for empirical calibration of signal weights and thresholds
    before triage mode is recommended for production use.

    Args:
        path: Source PDF path.
        output_dir: Directory for any heuristic outputs (no docling
            splices written).
        report_tsv_path: Path where the per-page TSV is written.
            Columns:
            ``page_index, <signal_name>..., aggregate, needs_docling,
            reason, qm_parse_ok, qm_heading_count, qm_section_count,
            qm_table_count, qm_table_cell_count,
            qm_structural_density_per_1k, qm_median_section_chars``.
            The ``qm_*`` columns are appended after the existing columns
            for backward compatibility with positional TSV consumers
            (021.003-T / 023-S T3).
        scorer: Injectable page scorer; defaults to
            :func:`docline.process.fidelity_scorer.score_page`.
        buffer: Pages of context (recorded only — no docling invocation).
        merge_gap: Merge gap (recorded only — no docling invocation).
        baseline_engine: Heuristic baseline extractor selection.
            ``"markitdown"`` (default, 020.002-T / U1) routes each
            page through :class:`markitdown.MarkItDown`. ``"pypdf"``
            uses ``reader.pages[i].extract_text()`` directly — used
            for regression coverage of the pre-020.002-T behavior.

    Returns:
        :class:`TriageResult` with ``engine_per_page`` all-heuristic and
        ``flagged_ranges`` populated for downstream review.
        :attr:`TriageResult.metadata` contains a ``quality_metrics_summary``
        block with mean+median of ``structural_density_per_1k``,
        ``heading_count``, ``section_count``, and ``table_cell_count``
        across all pages (021.003-T / 023-S T3).
    """
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    if scorer is None:
        scorer = score_page

    reader = pypdf.PdfReader(str(path), strict=False)
    total_pages = len(reader.pages)
    splice_cache = output_dir / "splices"
    splice_cache.mkdir(parents=True, exist_ok=True)

    scores: list[PageScore] = []
    heuristic_pages: list[str] = []
    baseline_engine_fallback = 0
    for page_idx in range(total_pages):
        text, fallback = _heuristic_extract(reader, page_idx, baseline_engine, splice_cache)
        heuristic_pages.append(text)
        if fallback:
            baseline_engine_fallback += 1
        scores.append(scorer(page_idx, text, reader.pages[page_idx]))

    flagged_indices = [s.page_index for s in scores if s.needs_docling]
    flagged_ranges = coalesce_ranges(
        flagged_indices,
        total_pages=total_pages,
        buffer=buffer,
        merge_gap=merge_gap,
    )

    # Emit TSV with both fidelity-signal columns and AST-aware quality
    # metric columns (qm_*). qm_* columns are appended AFTER the existing
    # signal/aggregate/needs_docling/reason columns for backward compat
    # with positional-read consumers (021.003-T / 023-S T3).
    signal_names: list[str] = list(scores[0].signals.keys()) if scores else []
    qm_columns = [
        "qm_parse_ok",
        "qm_heading_count",
        "qm_section_count",
        "qm_table_count",
        "qm_table_cell_count",
        "qm_structural_density_per_1k",
        "qm_median_section_chars",
    ]
    fieldnames = [
        "page_index",
        *signal_names,
        "aggregate",
        "needs_docling",
        "reason",
        *qm_columns,
    ]

    # Construct a single markdown parser and reuse across all pages.
    # Avoids per-page MarkdownIt construction overhead which would
    # multiply by total_pages (3000+ for cosmos-class corpora).
    _qm_parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    per_page_quality = [
        compute_quality_metrics(text, md_parser=_qm_parser) for text in heuristic_pages
    ]

    report_tsv_path.parent.mkdir(parents=True, exist_ok=True)
    with report_tsv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for score, qm in zip(scores, per_page_quality, strict=True):
            row: dict[str, object] = {
                "page_index": score.page_index,
                "aggregate": f"{score.aggregate:.4f}",
                "needs_docling": int(score.needs_docling),
                "reason": score.reason,
                "qm_parse_ok": int(qm.parse_ok),
                "qm_heading_count": qm.heading_count,
                "qm_section_count": qm.section_count,
                "qm_table_count": qm.table_count,
                "qm_table_cell_count": qm.table_cell_count,
                "qm_structural_density_per_1k": f"{qm.structural_density_per_1k:.3f}",
                "qm_median_section_chars": qm.median_section_chars,
            }
            for name in signal_names:
                row[name] = f"{score.signals.get(name, 0.0):.4f}"
            writer.writerow(row)

    # Build per-engine aggregate summary block (mean + median across pages)
    # for the 4 most operationally relevant metrics (021.003-T / 023-S T3).
    quality_metrics_summary: dict[str, dict[str, float]] = {}
    for metric in (
        "structural_density_per_1k",
        "heading_count",
        "section_count",
        "table_cell_count",
    ):
        values = [float(getattr(qm, metric)) for qm in per_page_quality]
        if values:
            quality_metrics_summary[metric] = {
                "mean": round(statistics.mean(values), 3),
                "median": round(statistics.median(values), 3),
            }
        else:
            quality_metrics_summary[metric] = {"mean": 0.0, "median": 0.0}

    return TriageResult(
        source=path,
        pages=tuple(heuristic_pages),
        engine_per_page=tuple("heuristic" for _ in range(total_pages)),
        flagged_ranges=tuple(flagged_ranges),
        metadata={
            "total_pages": total_pages,
            "flagged_pages_count": len(flagged_indices),
            "flagged_ranges_count": len(flagged_ranges),
            "report_only": True,
            "baseline_engine": baseline_engine,
            "baseline_engine_fallback": baseline_engine_fallback,
            "quality_metrics_summary": quality_metrics_summary,
        },
    )


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
