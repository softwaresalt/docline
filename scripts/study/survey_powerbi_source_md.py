# ruff: noqa: E501
"""Spike: survey AST-aware quality metrics across the Power BI docs source MD corpus.

Reads every .md file under E:\\Source\\powerbi-docs\\powerbi-docs\\ and
computes QualityMetrics. Aggregates per-subdir + global statistics to
characterize what Microsoft Learn production source MD looks like
through docline's new (023-S) quality lens.

Goal: empirical evidence that informs 026-F (source-MD ingestion
pathway) design. Specifically:
- What is the structural density of production source MD?
- What is the typical section-chars distribution? (embedding-chunk fit?)
- Are there outliers that suggest DocFx extensions confuse the parser?
- How does it compare to the 2026-06-08 study's docling/markitdown averages?
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\Source\GitHub\docline\src")
from docline.process import compute_quality_metrics  # type: ignore  # noqa: E402

ROOT = Path(r"E:\Source\powerbi-docs\powerbi-docs")
OUT_DIR = Path(r"D:\Source\GitHub\docline\.elt\output\powerbi-source-survey")


def strip_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body) split on the YAML fence."""
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return "", text
    end = text.find("\n---", 4)
    if end < 0:
        return "", text
    fm = text[: end + 4]
    body = text[end + 4 :].lstrip("\n")
    return fm, body


def main() -> int:
    if not ROOT.exists():
        print(f"ERROR: {ROOT} not found", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    md_files = list(ROOT.rglob("*.md"))
    print(f"Found {len(md_files)} .md files under {ROOT}")

    start = time.perf_counter()
    rows: list[dict] = []
    for path in md_files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            rows.append({"path": str(path.relative_to(ROOT)), "error": str(exc)})
            continue
        fm, body = strip_frontmatter(text)
        m = compute_quality_metrics(body)
        rel = path.relative_to(ROOT)
        rows.append(
            {
                "path": str(rel),
                "subdir": rel.parts[0] if rel.parts else "",
                "raw_chars": len(text),
                "body_chars": len(body),
                "fm_chars": len(fm),
                "has_frontmatter": bool(fm),
                "parse_ok": m.parse_ok,
                "heading_count": m.heading_count,
                "heading_depth_max": m.heading_depth_max,
                "section_count": m.section_count,
                "median_section_chars": m.median_section_chars,
                "table_count": m.table_count,
                "table_cell_count": m.table_cell_count,
                "code_block_count": m.code_block_count,
                "list_item_count": m.list_item_count,
                "structural_density_per_1k": m.structural_density_per_1k,
            }
        )

    elapsed = time.perf_counter() - start
    print(
        f"Computed metrics for {len(rows)} files in {elapsed:.1f}s "
        f"({len(rows) / elapsed:.0f} files/sec)"
    )

    # Per-subdir summary
    subdirs: dict[str, list[dict]] = {}
    for r in rows:
        if "error" in r:
            continue
        subdirs.setdefault(r["subdir"], []).append(r)

    per_subdir: dict[str, dict] = {}
    for subdir, files in sorted(subdirs.items()):
        per_subdir[subdir] = {
            "n_files": len(files),
            "total_body_chars": sum(f["body_chars"] for f in files),
            "frontmatter_pct": round(
                sum(1 for f in files if f["has_frontmatter"]) / len(files) * 100, 1
            ),
            "mean_body_chars": round(statistics.mean(f["body_chars"] for f in files), 1),
            "median_body_chars": round(statistics.median(f["body_chars"] for f in files), 1),
            "mean_heading_count": round(statistics.mean(f["heading_count"] for f in files), 2),
            "mean_section_count": round(statistics.mean(f["section_count"] for f in files), 2),
            "mean_median_section_chars": round(
                statistics.mean(f["median_section_chars"] for f in files), 1
            ),
            "mean_table_count": round(statistics.mean(f["table_count"] for f in files), 3),
            "mean_table_cell_count": round(
                statistics.mean(f["table_cell_count"] for f in files), 2
            ),
            "mean_code_block_count": round(
                statistics.mean(f["code_block_count"] for f in files), 2
            ),
            "mean_list_item_count": round(statistics.mean(f["list_item_count"] for f in files), 2),
            "mean_structural_density_per_1k": round(
                statistics.mean(f["structural_density_per_1k"] for f in files), 3
            ),
        }

    # Global summary
    ok_rows = [r for r in rows if "error" not in r]
    global_summary = {
        "n_files_total": len(rows),
        "n_files_ok": len(ok_rows),
        "n_files_error": len(rows) - len(ok_rows),
        "total_body_chars": sum(r["body_chars"] for r in ok_rows),
        "frontmatter_pct": round(
            sum(1 for r in ok_rows if r["has_frontmatter"]) / len(ok_rows) * 100, 1
        ),
        "mean_body_chars": round(statistics.mean(r["body_chars"] for r in ok_rows), 1),
        "median_body_chars": round(statistics.median(r["body_chars"] for r in ok_rows), 1),
        "mean_heading_count": round(statistics.mean(r["heading_count"] for r in ok_rows), 2),
        "mean_section_count": round(statistics.mean(r["section_count"] for r in ok_rows), 2),
        "mean_median_section_chars": round(
            statistics.mean(r["median_section_chars"] for r in ok_rows), 1
        ),
        "mean_table_count": round(statistics.mean(r["table_count"] for r in ok_rows), 3),
        "mean_table_cell_count": round(statistics.mean(r["table_cell_count"] for r in ok_rows), 2),
        "mean_code_block_count": round(statistics.mean(r["code_block_count"] for r in ok_rows), 2),
        "mean_list_item_count": round(statistics.mean(r["list_item_count"] for r in ok_rows), 2),
        "mean_structural_density_per_1k": round(
            statistics.mean(r["structural_density_per_1k"] for r in ok_rows), 3
        ),
        "median_structural_density_per_1k": round(
            statistics.median(r["structural_density_per_1k"] for r in ok_rows), 3
        ),
    }

    # Write outputs
    (OUT_DIR / "per-file-metrics.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (OUT_DIR / "per-subdir-summary.json").write_text(
        json.dumps(per_subdir, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "global-summary.json").write_text(
        json.dumps(global_summary, indent=2), encoding="utf-8"
    )

    # TSV for spreadsheet inspection
    fieldnames = list(rows[0].keys())
    tsv_path = OUT_DIR / "per-file-metrics.tsv"
    with tsv_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("\t".join(fieldnames) + "\n")
        for r in rows:
            fh.write("\t".join(str(r.get(f, "")) for f in fieldnames) + "\n")

    # Console summary
    print()
    print("=== GLOBAL SUMMARY ===")
    for k, v in global_summary.items():
        print(f"  {k:35s} {v}")
    print()
    print("=== PER-SUBDIR SUMMARY ===")
    print(
        f"{'subdir':<22s} {'n':>5s} {'mean_ch':>8s} {'med_ch':>7s} "
        f"{'hdg':>5s} {'sec':>5s} {'med_sec':>8s} {'tbl':>5s} "
        f"{'code':>5s} {'list':>5s} {'dens':>6s}"
    )
    for subdir, stats in sorted(per_subdir.items(), key=lambda x: -x[1]["n_files"]):
        print(
            f"{subdir:<22s} {stats['n_files']:>5d} "
            f"{stats['mean_body_chars']:>8.0f} {stats['median_body_chars']:>7.0f} "
            f"{stats['mean_heading_count']:>5.1f} {stats['mean_section_count']:>5.1f} "
            f"{stats['mean_median_section_chars']:>8.0f} {stats['mean_table_count']:>5.2f} "
            f"{stats['mean_code_block_count']:>5.1f} {stats['mean_list_item_count']:>5.1f} "
            f"{stats['mean_structural_density_per_1k']:>6.2f}"
        )

    print()
    print("=== COMPARISON TO 2026-06-08 STUDY (cosmos PDF, per-engine averages) ===")
    print(f"{'engine':<22s} {'mean_dens':>10s} {'med_sec':>9s} {'note':<40s}")
    print(
        f"{'markitdown (PDF→md)':<22s} {2.62:>10.2f} {29161:>9d} {'one big blob, poor chunking':<40s}"
    )
    print(f"{'docling (PDF→md)':<22s} {6.80:>10.2f} {571:>9d} {'good chunking, slow':<40s}")
    print(
        f"{'source-md (cosmos proxy)':<22s} {9.14:>10.2f} {542:>9d} {'AzPostgreSQL public proxy':<40s}"
    )
    print(
        f"{'source-md (powerbi)':<22s} "
        f"{global_summary['mean_structural_density_per_1k']:>10.2f} "
        f"{int(global_summary['mean_median_section_chars']):>9d} "
        f"{'THIS RUN — large-corpus source MD':<40s}"
    )

    print()
    print(f"Outputs: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
