"""Probe docling's batch-size knobs and per-page invocation cost (030-F T4).

Runs a representative cosmos splice range through docling at varied batch
sizes (``layout_batch_size``, ``ocr_batch_size``, ``table_batch_size``)
and also compares the cost of a single multi-page invocation vs N
single-page invocations (informs whether per-page fidelity restoration
via ``page_range=(i,i)`` is performance-feasible).

Usage::

    python scripts/study/docling_batch_size_probe.py \\
        --splice-pdf .elt/output/cosmos-triage-022/study/dataset/range-0859-1056/_input.pdf \\
        --output-dir .elt/output/cosmos-triage-022/study/results/batch-probe

Output:
    A per-knob results table written to stdout and to
    ``docs/decisions/2026-06-14-docling-batch-size-probe.md``.

If docling extras are not installed, exits with a friendly message.

This is an operator-runnable artifact. The probe is not part of the
default test suite because it depends on real docling model loads and
representative PDF samples.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProbeResult:
    label: str
    wall_seconds: float
    page_count: int
    peak_rss_mb: float | None
    notes: str = ""

    def throughput_pp_per_min(self) -> float:
        if self.wall_seconds <= 0:
            return float("inf")
        return self.page_count / (self.wall_seconds / 60.0)


def _peak_rss_mb_current_process() -> float | None:
    """Return current process peak RSS in MB; None when unavailable."""

    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        info = psutil.Process(os.getpid()).memory_info()
        return float(info.rss) / (1024.0 * 1024.0)
    except Exception:  # noqa: BLE001 — best-effort
        return None


def _ensure_docling_or_exit() -> None:
    try:
        import docling  # noqa: F401
    except ImportError:
        print(
            "docling extras not installed; skipping probe.\n"
            "Install with: pip install 'docline[pdf]'",
            file=sys.stderr,
        )
        sys.exit(0)


def _run_one_probe(
    splice_pdf: Path,
    label: str,
    *,
    layout_batch_size: int = 4,
    ocr_batch_size: int = 4,
    table_batch_size: int = 4,
    page_range: tuple[int, int] | None = None,
) -> ProbeResult:
    """Run docling on a splice PDF with the given knobs; return timing."""

    from docling.datamodel.base_models import InputFormat  # type: ignore[import-untyped]
    from docling.datamodel.pipeline_options import (  # type: ignore[import-untyped]
        PdfPipelineOptions,
        TableStructureOptions,
    )
    from docling.document_converter import (  # type: ignore[import-untyped]
        DocumentConverter,
        PdfFormatOption,
    )

    options_kwargs: dict[str, Any] = {
        "do_table_structure": True,
        "table_structure_options": TableStructureOptions(do_cell_matching=True),
        "generate_picture_images": False,
        "images_scale": 2.0,
    }
    # Apply only the knobs the installed docling version actually accepts;
    # newer fields are gated to avoid TypeError on older releases.
    fields = set(getattr(PdfPipelineOptions, "model_fields", {}).keys())
    if "layout_batch_size" in fields:
        options_kwargs["layout_batch_size"] = layout_batch_size
    if "ocr_batch_size" in fields:
        options_kwargs["ocr_batch_size"] = ocr_batch_size
    if "table_batch_size" in fields:
        options_kwargs["table_batch_size"] = table_batch_size

    pipeline_options = PdfPipelineOptions(**options_kwargs)
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )

    convert_kwargs: dict[str, Any] = {}
    if page_range is not None:
        convert_kwargs["page_range"] = page_range

    start = time.perf_counter()
    result = converter.convert(str(splice_pdf), **convert_kwargs)
    markdown = result.document.export_to_markdown()
    wall = time.perf_counter() - start

    page_count: int
    try:
        page_count = len(getattr(result.document, "pages", []) or [])
    except Exception:  # noqa: BLE001
        page_count = -1
    if page_count <= 0 and page_range is not None:
        page_count = page_range[1] - page_range[0] + 1

    rss_mb = _peak_rss_mb_current_process()
    char_count = len(markdown.strip())
    return ProbeResult(
        label=label,
        wall_seconds=wall,
        page_count=page_count,
        peak_rss_mb=rss_mb,
        notes=f"chars={char_count}",
    )


def _run_per_page_loop(
    splice_pdf: Path, total_pages: int, *, label: str = "per-page-loop"
) -> ProbeResult:
    """Run docling once per page via page_range=(i,i); aggregate timing."""

    start = time.perf_counter()
    char_total = 0
    for page_no in range(1, total_pages + 1):
        sub = _run_one_probe(
            splice_pdf,
            label=f"per-page-{page_no}",
            page_range=(page_no, page_no),
        )
        # Each sub-run reports its own wall_seconds, but we want the
        # aggregate. Pull char count from notes for the total.
        if sub.notes.startswith("chars="):
            try:
                char_total += int(sub.notes.split("=", 1)[1])
            except ValueError:
                pass
    wall = time.perf_counter() - start
    return ProbeResult(
        label=label,
        wall_seconds=wall,
        page_count=total_pages,
        peak_rss_mb=_peak_rss_mb_current_process(),
        notes=f"chars={char_total}",
    )


def _format_table(results: list[ProbeResult]) -> str:
    header = (
        "| Probe | Pages | Wall (s) | Throughput (pp/min) | Peak RSS (MB) | Notes |\n"
        "|---|---:|---:|---:|---:|---|\n"
    )
    rows = []
    for r in results:
        rss = f"{r.peak_rss_mb:.0f}" if r.peak_rss_mb is not None else "-"
        rows.append(
            f"| {r.label} | {r.page_count} | {r.wall_seconds:.2f} | "
            f"{r.throughput_pp_per_min():.1f} | {rss} | {r.notes} |"
        )
    return header + "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--splice-pdf",
        type=Path,
        required=True,
        help="Path to a representative cosmos splice PDF (multi-page).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Where to write the results table + decision doc.",
    )
    parser.add_argument(
        "--batch-sizes",
        type=lambda s: [int(x) for x in s.split(",")],
        default=[1, 4, 8, 16, 32],
        help="Comma-separated batch sizes to probe (default: 1,4,8,16,32).",
    )
    parser.add_argument(
        "--skip-per-page",
        action="store_true",
        help="Skip the per-page loop (which can be slow on large splices).",
    )
    args = parser.parse_args(argv)

    _ensure_docling_or_exit()

    if not args.splice_pdf.exists():
        print(f"Splice PDF not found: {args.splice_pdf}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Discover total page count for the splice.
    try:
        import pypdf  # type: ignore[import-untyped]

        reader = pypdf.PdfReader(str(args.splice_pdf))
        total_pages = len(reader.pages)
    except Exception as err:  # noqa: BLE001
        print(f"Could not read splice PDF page count: {err}", file=sys.stderr)
        return 2

    print(f"Probing splice: {args.splice_pdf} ({total_pages} pages)")
    print(f"Batch sizes: {args.batch_sizes}")

    results: list[ProbeResult] = []

    # Probe layout_batch_size variations (full conversion each run).
    for bs in args.batch_sizes:
        label = f"layout_bs={bs}"
        print(f"  Running {label} ...", flush=True)
        try:
            r = _run_one_probe(args.splice_pdf, label=label, layout_batch_size=bs)
            results.append(r)
            print(f"    -> {r.wall_seconds:.2f}s ({r.throughput_pp_per_min():.1f} pp/min)")
        except Exception as err:  # noqa: BLE001
            print(f"    -> FAILED: {err!r}")
            results.append(
                ProbeResult(
                    label=label,
                    wall_seconds=0.0,
                    page_count=0,
                    peak_rss_mb=None,
                    notes=f"FAILED: {err!r}",
                )
            )

    # Compare single multi-page invocation vs per-page loop (informs the
    # per-page fidelity restoration spike).
    if not args.skip_per_page:
        print("  Running per-page-loop ...", flush=True)
        try:
            per_page = _run_per_page_loop(args.splice_pdf, total_pages)
            results.append(per_page)
            wall = per_page.wall_seconds
            tput = per_page.throughput_pp_per_min()
            print(f"    -> {wall:.2f}s ({tput:.1f} pp/min)")
        except Exception as err:  # noqa: BLE001
            print(f"    -> FAILED: {err!r}")

    table = _format_table(results)
    print()
    print(table)

    # Write decision doc.
    decision_path = (
        args.output_dir.parent / "decisions" / "2026-06-14-docling-batch-size-probe.md"
        if args.output_dir.name != "decisions"
        else args.output_dir / "2026-06-14-docling-batch-size-probe.md"
    )
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text(
        _decision_doc_body(args.splice_pdf, total_pages, results),
        encoding="utf-8",
    )
    print(f"\nDecision doc written: {decision_path}")
    return 0


def _decision_doc_body(splice_pdf: Path, total_pages: int, results: list[ProbeResult]) -> str:
    return f"""---
title: docling batch-size probe results
date: 2026-06-14
status: empirical
shipment: 032-S
feature: 030-F
task: 030.004-T
references:
  - scripts/study/docling_batch_size_probe.py
  - src/docline/readers/pdf.py
---

# docling batch-size probe — results

Probed splice: ``{splice_pdf}`` ({total_pages} pages)

## Results

{_format_table(results)}

## Knob availability

The probe applies ``layout_batch_size``, ``ocr_batch_size``, and
``table_batch_size`` only when the installed docling version's
``PdfPipelineOptions`` actually accepts each field. Newer fields are
gated to avoid ``TypeError`` on older releases. Check the probe stdout
for which knobs were active.

## Per-page invocation cost

The ``per-page-loop`` row times N invocations of
``DocumentConverter.convert(page_range=(i,i))`` against one invocation
covering all pages. This informs whether per-page fidelity restoration
(deferred from 030-F deliberation Option 2) is performance-feasible
under the batched worker (T3) which loads docling once.

## Conclusion

Fill in based on the results table:

- Chosen ``layout_batch_size``: TODO
- Chosen ``ocr_batch_size``: TODO
- Chosen ``table_batch_size``: TODO
- Per-page invocation overhead vs single-call: TODO (multiplier ratio)
- Recommended action: TODO (e.g., commit chosen values as constants in
  ``_read_pdf_docling_pages``; defer per-page fidelity restoration if
  overhead is unacceptable)
"""


if __name__ == "__main__":
    raise SystemExit(main())
