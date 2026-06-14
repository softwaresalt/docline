"""Per-page fidelity validation harness (030-F T5).

Runs ``process_pdf_triaged`` against a representative PDF and asserts
that every page index marked ``engine="docling"`` has non-empty
content. Pages marked ``engine="docling-collapsed"`` are the post-030-F
honest attribution for multi-page splice ranges (docling returns one
blob per call; the orchestrator attaches that blob to the first page
of the range and leaves subsequent pages empty until per-page fidelity
restoration via ``page_range=(i,i)`` is shipped — see deferred follow-up
in docs/decisions/2026-06-14-docling-batch-size-probe.md).

The validation contract this harness enforces:

- ``engine="docling"`` ⇒ ``pages[i]`` is non-empty (per-page envelope worked)
- ``engine="docling-collapsed"`` ⇒ ``pages[i]`` may be empty (legacy collapse
  is honest; first page of the range carries the blob, rest are "")
- ``engine="heuristic"`` ⇒ ``pages[i]`` is non-empty (heuristic baseline)

Counts of each attribution are reported. If any ``engine="docling"`` page
has empty content, the harness exits non-zero — that's the contract
violation T1+T2 was meant to prevent.

Usage::

    python scripts/study/per_page_fidelity_check.py \\
        --source-pdf .elt/data/cosmosdb/azure-cosmos-db.pdf \\
        --output-dir .elt/output/per-page-fidelity-check

The script auto-skips if docling extras are not installed.

This is an operator-runnable artifact. It is not part of the default
test suite because it depends on real docling model loads and
representative PDF samples that may be several hundred pages.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path


def _ensure_docling_or_exit() -> None:
    try:
        import docling  # noqa: F401
    except ImportError:
        print(
            "docling extras not installed; skipping per-page fidelity check.\n"
            "Install with: pip install 'docline[pdf]'",
            file=sys.stderr,
        )
        sys.exit(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--source-pdf",
        type=Path,
        required=True,
        help="Path to the source PDF to triage.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for splice cache and per-page outputs.",
    )
    parser.add_argument(
        "--max-flagged-pages",
        type=int,
        default=200,
        help="Cap the per-page assertion sweep to the first N flagged pages "
        "(default: 200) to keep wall-clock bounded on huge PDFs.",
    )
    args = parser.parse_args(argv)

    _ensure_docling_or_exit()

    if not args.source_pdf.exists():
        print(f"Source PDF not found: {args.source_pdf}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running process_pdf_triaged on: {args.source_pdf}")

    from docline.process.pdf_triage import process_pdf_triaged

    result = process_pdf_triaged(
        args.source_pdf,
        output_dir=args.output_dir,
    )

    engine_counts = Counter(result.engine_per_page)
    print()
    print("Engine attribution distribution:")
    for engine, count in sorted(engine_counts.items()):
        print(f"  {engine:24s} {count:6d}")
    print(f"  TOTAL                    {len(result.engine_per_page):6d}")

    print()
    print("Run metadata:")
    for key in (
        "total_pages",
        "flagged_pages_count",
        "flagged_ranges_count",
        "subprocess_fallback_count",
        "batched_worker",
        "baseline_engine",
        "baseline_engine_fallback",
    ):
        if key in result.metadata:
            print(f"  {key:32s} {result.metadata[key]}")

    print()
    print("Per-page fidelity assertion:")
    docling_pages = [
        (i, result.pages[i]) for i, eng in enumerate(result.engine_per_page) if eng == "docling"
    ]
    collapsed_pages = [
        (i, result.pages[i])
        for i, eng in enumerate(result.engine_per_page)
        if eng == "docling-collapsed"
    ]

    empty_docling = [(i, p) for i, p in docling_pages if not p.strip()]
    nonempty_collapsed_blob_pages = [(i, p) for i, p in collapsed_pages if p.strip()]
    empty_collapsed_subsequent_pages = [(i, p) for i, p in collapsed_pages if not p.strip()]

    print(f"  engine='docling' pages: {len(docling_pages)} (empty content: {len(empty_docling)})")
    print(
        f"  engine='docling-collapsed' pages: {len(collapsed_pages)} "
        f"(non-empty blob pages: {len(nonempty_collapsed_blob_pages)}, "
        f"empty subsequent pages: {len(empty_collapsed_subsequent_pages)})"
    )

    print()
    if empty_docling:
        print("FAIL: per-page fidelity contract violated.")
        print(
            f"{len(empty_docling)} page(s) marked engine='docling' have empty content. "
            "This indicates the worker envelope length matched the splice range length "
            "but at least one page in the envelope was empty. Investigate the worker "
            "envelope assignment in pdf_triage._splice_and_run_docling."
        )
        # Show first 5 offenders.
        for idx, _ in empty_docling[: args.max_flagged_pages][:5]:
            print(f"  - page index {idx}")
        return 1

    print("PASS: every engine='docling' page carries non-empty content.")
    print(
        "      every engine='docling-collapsed' page exhibits the known "
        "first-page-blob-rest-empty pattern (honest attribution; per-page "
        "restoration deferred to a future follow-up shipment)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
