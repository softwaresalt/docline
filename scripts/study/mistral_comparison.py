"""Mistral OCR vs docling empirical comparison study (029.004-T / 031-S).

Runs Mistral OCR against the same cosmos PDF page ranges already evaluated
against docling + markitdown by the 022-S extraction-strategy study and
against ADI by the (now-removed) 029-S spike. Computes the same AST-aware
metrics as ``scripts/study/evaluate_markdown.py`` so the new Mistral
column slots into the existing decision matrix.

The previous adi_comparison.py was removed in T1 of 031-S; this script
is forked from its git-history shape and retargeted at Mistral OCR via
``src/docline/readers/mistral.py`` (raw httpx; works against Foundry
MaaS or direct Mistral API).

Prerequisites:

* ``docline[mistral]`` extra installed: ``pip install -e .[mistral]``
* Mistral OCR credentials in ``.env.local`` (auto-loaded):

    AZURE_AI_FOUNDRY_ENDPOINT=https://<resource>.services.ai.azure.com/providers/mistral/azure/ocr
    AZURE_AI_FOUNDRY_KEY=<foundry-api-key>

  Or for direct Mistral API::

    MISTRAL_API_KEY=<mistral-api-key>

* Source cosmos PDF present at ``.elt/data/cosmosdb/azure-cosmos-db.pdf``
  (or override via ``--source-pdf``)
* Range dataset already built under
  ``.elt/output/cosmos-triage-022/study/dataset/range-NNNN-NNNN/``
  (this script SKIPS ranges whose ``mistral.md`` already exists)

Output:

* One ``mistral.md`` per range directory
* Aggregate ``mistral-findings.json`` and ``mistral-findings.md`` in
  ``.elt/output/cosmos-triage-022/study/results/``
* Console summary with per-range cost, wall time, and structural-density
  comparison vs docling

Cost: ~$0.001 per page at Mistral OCR list price. Full study of 15
ranges totaling ~575 pages costs ~$0.55. Foundry MaaS billing may
differ from list price — confirm in your Azure billing dashboard.

Usage::

    python scripts/study/mistral_comparison.py                       # all ranges
    python scripts/study/mistral_comparison.py --range range-0213-0233  # one range
    python scripts/study/mistral_comparison.py --dry-run             # print plan
    python scripts/study/mistral_comparison.py --model mistral-ocr-2503  # compare older model
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


def _load_dotenv_local(env_path: Path) -> None:
    """Load ``KEY=VALUE`` lines from ``env_path`` into ``os.environ`` if not already set.

    Zero-dependency dotenv parser; existing env vars win so shell-set
    values override file values. Silently no-ops if file is missing.
    """
    if not env_path.is_file():
        return
    import os

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_local(_REPO_ROOT / ".env.local")

_STUDY_ROOT = _REPO_ROOT / ".elt" / "output" / "cosmos-triage-022" / "study"
_DATASET_ROOT = _STUDY_ROOT / "dataset"
_RESULTS_ROOT = _STUDY_ROOT / "results"
_DEFAULT_SOURCE_PDF = _REPO_ROOT / ".elt" / "data" / "cosmosdb" / "azure-cosmos-db.pdf"

# Cost per page at Mistral OCR list price (USD). Foundry MaaS billing may differ.
_MISTRAL_COST_PER_PAGE = 0.001


def _list_ranges(dataset_root: Path) -> list[Path]:
    """Return sorted range directories (e.g. range-0213-0233)."""
    return sorted(p for p in dataset_root.iterdir() if p.is_dir() and p.name.startswith("range-"))


def _import_docline_error() -> type:
    """Return the DoclineError class. Lazy to avoid eager package init."""
    from docline.schema.models import DoclineError

    return DoclineError


def _slice_pdf(source_pdf: Path, start_page: int, end_page: int) -> bytes:
    """Slice ``source_pdf`` to the [start_page, end_page] inclusive range.

    Page numbers are 1-indexed (matching the existing range-NNNN-NNNN naming).
    """
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(source_pdf)
    writer = PdfWriter()
    for page_idx in range(start_page - 1, min(end_page, len(reader.pages))):
        writer.add_page(reader.pages[page_idx])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _run_mistral_on_range(
    source_pdf: Path,
    range_dir: Path,
    *,
    dry_run: bool,
    model: str,
) -> dict[str, object]:
    """Run Mistral OCR on one range's slice of the source PDF and write mistral.md."""
    meta = json.loads((range_dir / "meta.json").read_text(encoding="utf-8"))
    start, end = meta["range_start"], meta["range_end"]
    page_count = meta["page_count"]
    mistral_md_path = range_dir / "mistral.md"

    if mistral_md_path.exists():
        existing_content = mistral_md_path.read_text(encoding="utf-8")
        return {
            "range": range_dir.name,
            "page_count": page_count,
            "status": "cached",
            "mistral_chars": len(existing_content),
            "wall_seconds": None,
            "projected_cost_usd": None,
        }

    if dry_run:
        return {
            "range": range_dir.name,
            "page_count": page_count,
            "status": "dry-run",
            "mistral_chars": None,
            "wall_seconds": None,
            "projected_cost_usd": page_count * _MISTRAL_COST_PER_PAGE,
        }

    start_ts = time.monotonic()
    try:
        content = _read_pdf_mistral_with_split(source_pdf, start, end, range_dir, model)
    except Exception as err:
        DoclineError = _import_docline_error()
        raise DoclineError(
            f"Mistral OCR failed for {range_dir.name} (pages {start}-{end}) even after "
            f"split-and-retry; underlying error: {err}"
        ) from err
    elapsed = time.monotonic() - start_ts

    mistral_md_path.write_text(content, encoding="utf-8")

    return {
        "range": range_dir.name,
        "page_count": page_count,
        "status": "ran",
        "mistral_chars": len(content),
        "wall_seconds": round(elapsed, 2),
        "projected_cost_usd": round(page_count * _MISTRAL_COST_PER_PAGE, 4),
    }


def _read_pdf_mistral_with_split(
    source_pdf: Path,
    start: int,
    end: int,
    workdir: Path,
    model: str,
) -> str:
    """Run Mistral OCR on [start, end]; recursively halve on size errors.

    Mistral OCR has a per-request page limit (30 pages as of 2026-06)
    AND its own size/timeout limits. If a request fails with an HTTP
    error suggesting any of these, halve the page range and try each
    half independently. Content from sub-ranges joined with double
    newline.

    A page-count-driven early split is also applied when the requested
    range exceeds 30 pages, to avoid wasting a guaranteed-fail API call.
    """
    from docline.readers.mistral import read_pdf_mistral

    DoclineError = _import_docline_error()

    # Early split for known too-many-pages ceiling (avoid wasting a 400-fail call)
    _MAX_PAGES_PER_REQUEST = 30
    if (end - start + 1) > _MAX_PAGES_PER_REQUEST and start < end:
        mid = start + (end - start) // 2
        left = _read_pdf_mistral_with_split(source_pdf, start, mid, workdir, model)
        right = _read_pdf_mistral_with_split(source_pdf, mid + 1, end, workdir, model)
        return f"{left}\n\n{right}"

    slice_name = f"_mistral_slice_{start:04d}_{end:04d}.pdf"
    slice_path = workdir / slice_name
    try:
        slice_path.write_bytes(_slice_pdf(source_pdf, start, end))
        return read_pdf_mistral(slice_path, model=model)
    except DoclineError as err:
        msg = str(err).lower()
        size_error_markers = (
            "content length",
            "payload too large",
            "request entity too large",
            "413",
            "timeout",
            "too_many_pages",
            "too many pages",
            "document_parser_too_many_pages",
        )
        if start == end or not any(marker in msg for marker in size_error_markers):
            raise
        mid = start + (end - start) // 2
        left = _read_pdf_mistral_with_split(source_pdf, start, mid, workdir, model)
        right = _read_pdf_mistral_with_split(source_pdf, mid + 1, end, workdir, model)
        return f"{left}\n\n{right}"
    finally:
        slice_path.unlink(missing_ok=True)


def _compute_metrics(range_dir: Path) -> dict[str, object]:
    """Compute the same AST metrics as evaluate_markdown.py for Mistral vs docling."""
    from scripts.study.evaluate_markdown import metrics_for

    docling_md = (range_dir / "docling.md").read_text(encoding="utf-8")
    mistral_path = range_dir / "mistral.md"
    if not mistral_path.exists():
        return {"range": range_dir.name, "status": "missing-mistral"}
    mistral_md = mistral_path.read_text(encoding="utf-8")

    docling_metrics = metrics_for(docling_md)
    mistral_metrics = metrics_for(mistral_md)

    return {
        "range": range_dir.name,
        "status": "compared",
        "docling": docling_metrics,
        "mistral": mistral_metrics,
        "deltas": {
            "structural_density_per_1k": (
                mistral_metrics["structural_density_per_1k"]
                - docling_metrics["structural_density_per_1k"]
            ),
            "heading_count_pct": _pct_delta(
                mistral_metrics["heading_count"], docling_metrics["heading_count"]
            ),
            "table_count_pct": _pct_delta(
                mistral_metrics["table_count"], docling_metrics["table_count"]
            ),
            "list_item_count_pct": _pct_delta(
                mistral_metrics["list_item_count"], docling_metrics["list_item_count"]
            ),
            "char_len_pct": _pct_delta(mistral_metrics["char_len"], docling_metrics["char_len"]),
        },
    }


def _pct_delta(mistral_val: float, docling_val: float) -> float | None:
    """Percent delta of Mistral vs docling. None when docling=0 and mistral>0."""
    if docling_val == 0:
        return None if mistral_val > 0 else 0.0
    return round(100.0 * (mistral_val - docling_val) / docling_val, 1)


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a (docling=0)"
    return f"{value:+.1f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
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
        help="Print the plan + projected costs, do not call Mistral",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="mistral-document-ai-2505",
        help="Mistral OCR model id (default: mistral-document-ai-2505)",
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
        result = _run_mistral_on_range(args.source_pdf, r, dry_run=args.dry_run, model=args.model)
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
        "model": args.model,
    }
    json_path = args.results_dir / "mistral-findings.json"
    json_path.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    print(f"\nWrote {json_path}")
    print(f"Total projected Mistral cost: ${total_cost:.4f}")

    md_lines: list[str] = [f"# Mistral OCR ({args.model}) vs docling — per-range comparison", ""]
    md_lines.append("| Range | Pages | Mistral chars | Wall (s) | Cost (USD) | Status |")
    md_lines.append("|---|---:|---:|---:|---:|---|")
    for r in run_results:
        md_lines.append(
            f"| {r['range']} | {r.get('page_count', '?')} | {r.get('mistral_chars', '?')} | "
            f"{r.get('wall_seconds', '?')} | {r.get('projected_cost_usd', '?')} | {r['status']} |"
        )
    md_lines.append("")
    md_lines.append(f"**Total projected cost**: ${total_cost:.4f}")
    md_lines.append("")
    if metric_results:
        md_lines.append("## Mistral vs docling deltas (positive = Mistral > docling)")
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
                f"| {m['range']} | {_fmt_delta(d['structural_density_per_1k'])} | "
                f"{_fmt_pct(d['heading_count_pct'])} | "
                f"{_fmt_pct(d['table_count_pct'])} | "
                f"{_fmt_pct(d['list_item_count_pct'])} | "
                f"{_fmt_pct(d['char_len_pct'])} |"
            )
    md_path = args.results_dir / "mistral-findings.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
