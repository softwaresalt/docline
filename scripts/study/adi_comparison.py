"""ADI vs docling empirical comparison study (027-F T4 / 027.004-T).

Runs Azure Document Intelligence (ADI) against the same cosmos PDF page
ranges already evaluated against docling + markitdown by the 022-S
extraction-strategy study. Computes the same AST-aware metrics as
``scripts/study/evaluate_markdown.py`` so the new ADI column slots
into the existing decision matrix.

Prerequisites:

* ``docline[adi]`` extra installed: ``pip install -e .[adi]``
* Azure Document Intelligence credentials in environment::

    setx AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT "https://<resource>.cognitiveservices.azure.com/"
    setx AZURE_DOCUMENT_INTELLIGENCE_KEY "<primary-or-secondary-key>"

* Source cosmos PDF present at ``.elt/data/cosmosdb/azure-cosmos-db.pdf``
  (or override via ``--source-pdf``)
* Range dataset already built under
  ``.elt/output/cosmos-triage-022/study/dataset/range-NNNN-NNNN/``
  (this script SKIPS ranges whose ``adi.md`` already exists)

Output:

* One ``adi.md`` per range directory (alongside existing ``docling.md``
  and ``markitdown.md``)
* Aggregate ``adi-findings.json`` and ``adi-findings.md`` in
  ``.elt/output/cosmos-triage-022/study/results/``
* Console summary with per-range cost, wall time, and structural-density
  comparison vs docling

Cost: ~$0.0015 per page at the prebuilt-layout list price. Full study
of 5 ranges totaling ~250 pages costs ~$0.40.

Usage::

    python scripts/study/adi_comparison.py                 # all ranges
    python scripts/study/adi_comparison.py --range 0213-0233  # one range
    python scripts/study/adi_comparison.py --dry-run       # print plan, no API calls
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
# Both ``src`` and the repo root must be on sys.path:
# - ``src`` so ``import docline`` resolves to the source-tree package
# - repo root so ``from scripts.study.evaluate_markdown import ...`` resolves
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT))

_STUDY_ROOT = _REPO_ROOT / ".elt" / "output" / "cosmos-triage-022" / "study"
_DATASET_ROOT = _STUDY_ROOT / "dataset"
_RESULTS_ROOT = _STUDY_ROOT / "results"
_DEFAULT_SOURCE_PDF = _REPO_ROOT / ".elt" / "data" / "cosmosdb" / "azure-cosmos-db.pdf"

# Cost per page at the prebuilt-layout list price (USD).
_ADI_COST_PER_PAGE = 0.0015


def _list_ranges(dataset_root: Path) -> list[Path]:
    """Return sorted range directories (e.g. range-0213-0233)."""
    return sorted(p for p in dataset_root.iterdir() if p.is_dir() and p.name.startswith("range-"))


def _slice_pdf(source_pdf: Path, start_page: int, end_page: int) -> bytes:
    """Slice ``source_pdf`` to the [start_page, end_page] inclusive range.

    Page numbers are 1-indexed (matching the existing range-NNNN-NNNN naming).
    Returns the sliced PDF as bytes (suitable for direct ADI upload).
    """
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(source_pdf)
    writer = PdfWriter()
    # PdfReader.pages is 0-indexed; range names are 1-indexed.
    for page_idx in range(start_page - 1, min(end_page, len(reader.pages))):
        writer.add_page(reader.pages[page_idx])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _run_adi_on_range(
    source_pdf: Path,
    range_dir: Path,
    *,
    dry_run: bool,
) -> dict[str, object]:
    """Run ADI on one range's slice of the source PDF and write adi.md.

    Returns a metrics dict for the aggregate findings file.
    """
    meta = json.loads((range_dir / "meta.json").read_text(encoding="utf-8"))
    start, end = meta["range_start"], meta["range_end"]
    page_count = meta["page_count"]
    adi_md_path = range_dir / "adi.md"

    if adi_md_path.exists():
        existing_content = adi_md_path.read_text(encoding="utf-8")
        return {
            "range": range_dir.name,
            "page_count": page_count,
            "status": "cached",
            "adi_chars": len(existing_content),
            "wall_seconds": None,
            "projected_cost_usd": None,
        }

    if dry_run:
        return {
            "range": range_dir.name,
            "page_count": page_count,
            "status": "dry-run",
            "adi_chars": None,
            "wall_seconds": None,
            "projected_cost_usd": page_count * _ADI_COST_PER_PAGE,
        }

    # Slice and write a temp PDF, then run through the ADI reader.
    sliced_pdf_path = range_dir / "_adi_slice.pdf"
    pdf_bytes = _slice_pdf(source_pdf, start, end)
    sliced_pdf_path.write_bytes(pdf_bytes)

    from docline.readers.adi import read_pdf_adi

    start_ts = time.monotonic()
    try:
        content = read_pdf_adi(sliced_pdf_path)
    finally:
        sliced_pdf_path.unlink(missing_ok=True)
    elapsed = time.monotonic() - start_ts

    adi_md_path.write_text(content, encoding="utf-8")

    return {
        "range": range_dir.name,
        "page_count": page_count,
        "status": "ran",
        "adi_chars": len(content),
        "wall_seconds": round(elapsed, 2),
        "projected_cost_usd": round(page_count * _ADI_COST_PER_PAGE, 4),
    }


def _compute_metrics(range_dir: Path) -> dict[str, object]:
    """Compute the same AST metrics as evaluate_markdown.py for ADI vs docling."""
    from scripts.study.evaluate_markdown import compute_metrics  # type: ignore[import-not-found]

    docling_md = (range_dir / "docling.md").read_text(encoding="utf-8")
    adi_path = range_dir / "adi.md"
    if not adi_path.exists():
        return {
            "range": range_dir.name,
            "status": "missing-adi",
        }
    adi_md = adi_path.read_text(encoding="utf-8")

    docling_metrics = compute_metrics(docling_md)
    adi_metrics = compute_metrics(adi_md)

    return {
        "range": range_dir.name,
        "status": "compared",
        "docling": docling_metrics,
        "adi": adi_metrics,
        "deltas": {
            "structural_density_per_1k": (
                adi_metrics["structural_density_per_1k"]
                - docling_metrics["structural_density_per_1k"]
            ),
            "heading_count_pct": _pct_delta(
                adi_metrics["heading_count"], docling_metrics["heading_count"]
            ),
            "table_count_pct": _pct_delta(
                adi_metrics["table_count"], docling_metrics["table_count"]
            ),
            "list_item_count_pct": _pct_delta(
                adi_metrics["list_item_count"], docling_metrics["list_item_count"]
            ),
            "char_count_pct": _pct_delta(adi_metrics["char_count"], docling_metrics["char_count"]),
        },
    }


def _pct_delta(adi_val: float, docling_val: float) -> float | None:
    """Percent delta of ADI vs docling (negative = ADI is lower).

    Returns ``None`` when docling's value is 0 and ADI's is positive
    (the divide-by-zero case). Using ``None`` rather than
    ``float("inf")`` keeps the aggregate ``adi-findings.json``
    parseable by strict (RFC 8259) JSON consumers, which reject the
    bare ``Infinity`` token. The Markdown formatter renders ``None``
    as ``"n/a (docling=0)"``.
    """
    if docling_val == 0:
        return None if adi_val > 0 else 0.0
    return round(100.0 * (adi_val - docling_val) / docling_val, 1)


def _fmt_pct(value: object) -> str:
    """Format a percent-delta value for the Markdown table.

    Renders ``None`` (the docling=0 divide-by-zero sentinel) as
    ``"n/a (docling=0)"`` and numeric values with a leading sign.
    """
    if value is None:
        return "n/a (docling=0)"
    return f"{value:+.1f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-pdf",
        type=Path,
        default=_DEFAULT_SOURCE_PDF,
        help=f"Source PDF to slice (default: {_DEFAULT_SOURCE_PDF})",
    )
    parser.add_argument(
        "--range",
        type=str,
        default=None,
        help="Single range name to process (e.g. 'range-0213-0233'). Default: all.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan + projected costs, do not call ADI",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=_RESULTS_ROOT,
        help=f"Where to write aggregate findings (default: {_RESULTS_ROOT})",
    )
    args = parser.parse_args()

    if not _DATASET_ROOT.exists():
        print(f"ERROR: dataset not found at {_DATASET_ROOT}", file=sys.stderr)
        return 1

    if not args.dry_run and not args.source_pdf.exists():
        print(f"ERROR: source PDF not found at {args.source_pdf}", file=sys.stderr)
        return 1

    ranges = _list_ranges(_DATASET_ROOT)
    if args.range:
        ranges = [r for r in ranges if r.name == args.range]
        if not ranges:
            print(f"ERROR: no range matches {args.range!r}", file=sys.stderr)
            return 1

    print(f"Found {len(ranges)} range(s):")
    for r in ranges:
        print(f"  {r.name}")

    run_results: list[dict[str, object]] = []
    metric_results: list[dict[str, object]] = []
    total_cost = 0.0
    for r in ranges:
        result = _run_adi_on_range(args.source_pdf, r, dry_run=args.dry_run)
        run_results.append(result)
        cost = result.get("projected_cost_usd") or 0.0
        if isinstance(cost, (int, float)):
            total_cost += float(cost)
        print(f"  {r.name}: status={result['status']}, cost~${cost}")

        if result["status"] in ("ran", "cached"):
            metric_results.append(_compute_metrics(r))

    args.results_dir.mkdir(parents=True, exist_ok=True)
    aggregate = {
        "run_results": run_results,
        "metric_results": metric_results,
        "total_projected_cost_usd": round(total_cost, 4),
    }
    json_path = args.results_dir / "adi-findings.json"
    json_path.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    print(f"\nWrote {json_path}")
    print(f"Total projected ADI cost: ${total_cost:.4f}")

    # Markdown summary
    md_lines: list[str] = ["# ADI vs docling — per-range comparison", ""]
    md_lines.append("| Range | Pages | ADI chars | Wall (s) | Cost (USD) | Status |")
    md_lines.append("|---|---:|---:|---:|---:|---|")
    for r in run_results:
        md_lines.append(
            f"| {r['range']} | {r.get('page_count', '?')} | {r.get('adi_chars', '?')} | "
            f"{r.get('wall_seconds', '?')} | {r.get('projected_cost_usd', '?')} | {r['status']} |"
        )
    md_lines.append("")
    md_lines.append(f"**Total projected cost**: ${total_cost:.4f}")
    md_lines.append("")
    if metric_results:
        md_lines.append("## ADI vs docling deltas (positive = ADI > docling)")
        md_lines.append("")
        md_lines.append(
            "| Range | "
            "Δ structural density / 1k | "
            "Δ headings % | Δ tables % | Δ lists % | Δ chars % |"
        )
        md_lines.append("|---|---:|---:|---:|---:|---:|")
        for m in metric_results:
            if m.get("status") != "compared":
                continue
            d = m["deltas"]
            md_lines.append(
                f"| {m['range']} | {d['structural_density_per_1k']:+.2f} | "
                f"{_fmt_pct(d['heading_count_pct'])} | "
                f"{_fmt_pct(d['table_count_pct'])} | "
                f"{_fmt_pct(d['list_item_count_pct'])} | "
                f"{_fmt_pct(d['char_count_pct'])} |"
            )
    md_path = args.results_dir / "adi-findings.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"Wrote {md_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
