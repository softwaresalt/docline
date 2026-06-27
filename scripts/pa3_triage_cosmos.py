"""PA3 runtime verification — run process_pdf_triaged on a single PDF and report.

Runs the triage-then-repair PDF pipeline (021-S) against a single PDF and
writes a JSON summary + per-page TSV alongside the output. Intended for the
PA3 acceptance criterion in ``docs/closure/021-S-triage-then-repair.md``:
empirical wall-clock verification of triage mode on the ~3,426-page
``azure-cosmos-db.pdf`` corpus.

**Operator constraint** (per RCA
``docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md``):
this script MUST be run from a plain PowerShell / shell session, NOT
inside an AI agent's tool calls. The Copilot CLI process co-hosted
with docling triggered the 2026-06-04 paging spiral / hard reboot.

Usage::

    .\\.venv\\Scripts\\python.exe scripts\\pa3_triage_cosmos.py

    # or with a different PDF / output dir:
    .\\.venv\\Scripts\\python.exe scripts\\pa3_triage_cosmos.py \\
        --pdf .\\.elt\\data\\cosmosdb\\azure-cosmos-db.pdf \\
        --output-dir .\\.elt\\output\\cosmos-triage \\
        --log-path logs\\pa3-cosmos-triage.log

    # to exercise 037-S bounded sub-batching (opt-in batched mode):
    .\\.venv\\Scripts\\python.exe scripts\\pa3_triage_cosmos.py \\
        --use-batched-worker

Outputs (under ``--output-dir``):

* ``pa3-summary.json`` — wall-clock, per-page engine distribution,
  ``TriageResult.metadata``, and the list of flagged ranges
* ``pa3-engine-attribution.tsv`` — one row per source page
  (``page_index, engine, page_body_len_chars``) for downstream analysis
* ``splices/`` — splice cache (per-range PDFs + docling outputs); safe
  to delete after the run

Plus the run log at ``--log-path`` (mirrors all stdout/stderr).

Exit codes:

* 0 — success
* 1 — input PDF not found or other configuration error
* 2 — process_pdf_triaged raised an unhandled exception (run log has
  the full traceback)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import time
import traceback
from collections import Counter
from pathlib import Path

from docline.process.pdf_triage import QASampling, process_pdf_triaged

_DEFAULT_PDF = Path(".elt") / "data" / "cosmosdb" / "azure-cosmos-db.pdf"
_DEFAULT_OUTPUT_DIR = Path(".elt") / "output" / "cosmos-triage"
_DEFAULT_LOG_PATH = Path("logs") / "pa3-cosmos-triage.log"


def _human_duration(seconds: float) -> str:
    """Format ``seconds`` as ``HhMMmSSs``."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}h{minutes:02d}m{secs:02d}s"


def _docling_attribution(
    pages: tuple[str, ...],
    engines: tuple[str, ...],
    flagged_ranges: tuple[tuple[int, int], ...],
) -> dict[str, int]:
    """Range-level docling stats so collapsed placeholders don't mislead.

    A multi-page docling range concatenates its markdown onto the range's
    first page, leaving the rest as empty ``docling-collapsed`` placeholders
    (030-F T2). The per-page ``engine_distribution`` therefore overstates
    docling coverage. This reports the honest picture: one blob per range,
    how many docling pages actually carry content vs. are empty placeholders,
    and the total docling character volume.

    Args:
        pages: Per-page final markdown.
        engines: Per-page engine attribution.
        flagged_ranges: Page ranges routed through docling.

    Returns:
        Dict with ``ranges``, ``content_pages``, ``collapsed_placeholder_pages``,
        and ``total_docling_chars``.
    """
    content_pages = 0
    collapsed_placeholder_pages = 0
    total_docling_chars = 0
    for engine, body in zip(engines, pages, strict=True):
        if not engine.startswith("docling"):
            continue
        if body:
            content_pages += 1
            total_docling_chars += len(body)
        else:
            collapsed_placeholder_pages += 1
    return {
        "ranges": len(flagged_ranges),
        "content_pages": content_pages,
        "collapsed_placeholder_pages": collapsed_placeholder_pages,
        "total_docling_chars": total_docling_chars,
    }


def _write_engine_attribution_tsv(
    tsv_path: Path, pages: tuple[str, ...], engines: tuple[str, ...]
) -> None:
    """Emit per-page engine attribution + body length to ``tsv_path``."""
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    with tsv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=("page_index", "engine", "page_body_len_chars"),
            delimiter="\t",
        )
        writer.writeheader()
        for idx, (engine, body) in enumerate(zip(engines, pages, strict=True)):
            writer.writerow({"page_index": idx, "engine": engine, "page_body_len_chars": len(body)})


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python scripts/pa3_triage_cosmos.py``."""
    parser = argparse.ArgumentParser(
        description=(
            "PA3 runtime verification: run process_pdf_triaged on a PDF and "
            "report wall-clock + per-page engine distribution. Must be run "
            "from a plain shell, NOT inside an AI agent process."
        ),
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=_DEFAULT_PDF,
        help=f"Source PDF (default: {_DEFAULT_PDF})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory for splice cache + summary (default: {_DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=_DEFAULT_LOG_PATH,
        help=f"Run log path (default: {_DEFAULT_LOG_PATH})",
    )
    parser.add_argument(
        "--buffer",
        type=int,
        default=1,
        help="Context-buffer pages around each flagged page (default: 1)",
    )
    parser.add_argument(
        "--merge-gap",
        type=int,
        default=2,
        help="Merge flagged ranges separated by at most this many pages (default: 2)",
    )
    parser.add_argument(
        "--baseline-engine",
        choices=("markitdown", "pypdf"),
        default="markitdown",
        help=(
            "Heuristic baseline extractor for triage mode (default: markitdown). "
            "'markitdown' produces real markdown for numbered lists, code "
            "fences, and headings; 'pypdf' is the legacy fallback that "
            "reproduces 021-S PA3 wall-clock baseline (~50 min on cosmos vs "
            "~75 min with markitdown — markitdown is ~250ms/page heavier but "
            "produces materially richer output)."
        ),
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.7,
        help=(
            "QA tripwire Jaccard-similarity threshold (default: 0.7). "
            "When --sample-rate > 0, a sampled page counts as a disagreement "
            "only when content similarity falls below this threshold. Lower "
            "values are more permissive (fewer disagreements); higher values "
            "are stricter."
        ),
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=0.0,
        help=(
            "QA tripwire: fraction (0.0-1.0) of unflagged pages to randomly "
            "re-run through docling and diff against heuristic output. "
            "Disagreement count is recorded as qa_disagreements in the "
            "summary. Defaults to 0.0 (no tripwire sampling). Use --sample-rate "
            "0.01 for a ~1%% sample (cheap false-negative check); 0.05 for "
            "a heavier check. Capped at --qa-max-pages."
        ),
    )
    parser.add_argument(
        "--qa-random-seed",
        type=int,
        default=None,
        help=(
            "Seed for the QA tripwire sampler (deterministic). When omitted, "
            "a system-clock seed is used and recorded in the summary as "
            "qa_random_seed_used."
        ),
    )
    parser.add_argument(
        "--qa-max-pages",
        type=int,
        default=50,
        help=(
            "Cap on the number of unflagged pages sampled by --sample-rate "
            "(default: 50). Bounds wall-clock impact of the tripwire on "
            "long documents."
        ),
    )
    parser.add_argument(
        "--use-batched-worker",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Force bounded sub-batching of the docling worker on/off (037-S). "
            "When omitted, the library default applies (batched since the "
            "037-S cosmos runtime verification). Pass --use-batched-worker to "
            "force bounded-batched groups (one --batch worker per "
            "MAX_BATCHED_PAGES-capped group), or --no-use-batched-worker to "
            "force the per-range subprocess loop (one process per range)."
        ),
    )
    args = parser.parse_args(argv)

    args.log_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(args.log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    log = logging.getLogger("docline.pa3")

    if not args.pdf.exists():
        log.error("Input PDF not found: %s", args.pdf)
        return 1

    pdf_mb = args.pdf.stat().st_size / 1_000_000
    log.info("PA3 runtime verification starting")
    log.info("PDF: %s (%.2f MB)", args.pdf, pdf_mb)
    log.info("Output: %s", args.output_dir)
    log.info("Buffer: %d, merge_gap: %d", args.buffer, args.merge_gap)
    log.info("Reminder: must run from plain shell per 2026-06-04 RCA")

    start = time.monotonic()
    qa_sampling: QASampling | None = None
    if args.sample_rate > 0.0:
        qa_sampling = QASampling(
            sample_rate=args.sample_rate,
            random_seed=args.qa_random_seed,
            max_sampled_pages=args.qa_max_pages,
            similarity_threshold=args.similarity_threshold,
        )
        log.info(
            "QA tripwire enabled: rate=%.3f, max=%d, seed=%s, similarity_threshold=%.2f",
            qa_sampling.sample_rate,
            qa_sampling.max_sampled_pages,
            qa_sampling.random_seed,
            qa_sampling.similarity_threshold,
        )
    log.info("Baseline engine: %s", args.baseline_engine)
    log.info(
        "Batched worker (037-S): %s",
        "library default" if args.use_batched_worker is None else args.use_batched_worker,
    )
    # Only override the library default when the operator set the flag.
    try:
        if args.use_batched_worker is None:
            result = process_pdf_triaged(
                args.pdf,
                output_dir=args.output_dir,
                buffer=args.buffer,
                merge_gap=args.merge_gap,
                qa_sampling=qa_sampling,
                baseline_engine=args.baseline_engine,
            )
        else:
            result = process_pdf_triaged(
                args.pdf,
                output_dir=args.output_dir,
                buffer=args.buffer,
                merge_gap=args.merge_gap,
                qa_sampling=qa_sampling,
                baseline_engine=args.baseline_engine,
                use_batched_worker=args.use_batched_worker,
            )
    except Exception as err:  # noqa: BLE001 — surface full traceback for diagnosis
        elapsed = time.monotonic() - start
        log.error("process_pdf_triaged raised after %s: %s", _human_duration(elapsed), err)
        log.error("Traceback:\n%s", traceback.format_exc())
        return 2

    elapsed = time.monotonic() - start
    engine_distribution = dict(Counter(result.engine_per_page))

    summary = {
        "pdf": str(args.pdf),
        "pdf_size_mb": round(pdf_mb, 2),
        "output_dir": str(args.output_dir),
        "wall_clock_seconds": round(elapsed, 1),
        "wall_clock_human": _human_duration(elapsed),
        "buffer": args.buffer,
        "merge_gap": args.merge_gap,
        "use_batched_worker": result.metadata.get("batched_worker"),
        "qa_sampling": (
            {
                "sample_rate": qa_sampling.sample_rate,
                "max_sampled_pages": qa_sampling.max_sampled_pages,
                "random_seed_supplied": qa_sampling.random_seed,
            }
            if qa_sampling is not None
            else None
        ),
        "engine_distribution": engine_distribution,
        "docling_attribution": _docling_attribution(
            result.pages, result.engine_per_page, result.flagged_ranges
        ),
        "flagged_ranges": [list(r) for r in result.flagged_ranges],
        "metadata": result.metadata,
    }

    summary_path = args.output_dir / "pa3-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    tsv_path = args.output_dir / "pa3-engine-attribution.tsv"
    _write_engine_attribution_tsv(tsv_path, result.pages, result.engine_per_page)

    log.info("PA3 complete in %s", _human_duration(elapsed))
    log.info("Engine distribution: %s", engine_distribution)
    log.info("Flagged ranges: %d", len(result.flagged_ranges))
    log.info("Summary: %s", summary_path)
    log.info("Per-page attribution TSV: %s", tsv_path)
    log.info("Log: %s", args.log_path)

    print("\n=== PA3 summary ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
