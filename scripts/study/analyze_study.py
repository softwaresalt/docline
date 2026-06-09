# ruff: noqa: E501
"""Analyze the study results, derive findings, and emit a strategy report.

Reads ``study/results/per-range-metrics.json`` produced by
``evaluate_markdown.py`` and answers the following research questions:

RQ1. Across the dataset, does docling consistently produce stronger
     structural markdown than markitdown? (heading_count, table_count,
     list_item_count, structural_density_per_1k)

RQ2. Where does markitdown match or beat docling? (semantic density,
     wall-clock — proxied by per-page cost not captured here, but
     known: markitdown ≈ 1-2 s/page, docling ≈ 15-30 s/page).

RQ3. Which range characteristics predict "docling worth invoking"?
     (page count, table presence in markitdown output, structural
     density delta).

RQ4. What downstream metric best correlates with use-case effectiveness
     (LLM context, embedding chunking, graph extraction)?

Output:
    study/results/findings.json    (aggregates + per-RQ verdicts)
    study/results/findings.md      (human-readable report)
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-engine aggregate stats and per-row engine-delta."""
    md_keys = [k[3:] for k in rows[0] if k.startswith("md_")]

    engines = ["md", "dl"]
    agg: dict[str, dict[str, Any]] = {e: {} for e in engines}
    for engine in engines:
        for key in md_keys:
            vals = [
                r[f"{engine}_{key}"]
                for r in rows
                if isinstance(r.get(f"{engine}_{key}"), (int, float))
            ]
            if not vals:
                continue
            agg[engine][key] = {
                "n": len(vals),
                "sum": sum(vals),
                "mean": round(statistics.mean(vals), 3),
                "median": round(statistics.median(vals), 3),
                "min": min(vals),
                "max": max(vals),
            }
            if len(vals) >= 2:
                agg[engine][key]["stdev"] = round(statistics.stdev(vals), 3)

    # Per-row deltas (dl - md)
    deltas = []
    for r in rows:
        d = {
            "range": f"{r['range_start']}-{r['range_end']}",
            "page_count": r["page_count"],
            "bucket": r["bucket"],
        }
        for key in md_keys:
            mv = r.get(f"md_{key}")
            dv = r.get(f"dl_{key}")
            if isinstance(mv, (int, float)) and isinstance(dv, (int, float)):
                d[f"delta_{key}"] = round(dv - mv, 3)
                d[f"ratio_{key}"] = round(
                    _safe_div(dv, mv) if mv else float("inf") if dv else 1.0, 3
                )
        deltas.append(d)
    return {"per_engine": agg, "per_row_delta": deltas}


def classify_ranges(deltas: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Partition ranges into 'docling clearly wins' / 'tied' / 'markitdown wins'.

    Decision rule (favors graph/LLM/embedding goals):
      - 'docling wins' if delta_table_cell_count >= 5 OR
                          delta_structural_density_per_1k >= 1.0 OR
                          ratio_char_len >= 1.3 (≥30% more content)
      - 'markitdown wins' if delta_table_cell_count <= -2 OR
                              ratio_char_len <= 0.95 AND delta_heading_count >= 0
      - else 'tied'
    """
    docling_wins: list[dict[str, Any]] = []
    tied: list[dict[str, Any]] = []
    md_wins: list[dict[str, Any]] = []

    for d in deltas:
        dc = d.get("delta_table_cell_count", 0)
        ds = d.get("delta_structural_density_per_1k", 0)
        rc = d.get("ratio_char_len", 1.0)
        dh = d.get("delta_heading_count", 0)

        if dc >= 5 or ds >= 1.0 or rc >= 1.3:
            docling_wins.append(d)
        elif (dc <= -2) or (rc <= 0.95 and dh >= 0):
            md_wins.append(d)
        else:
            tied.append(d)

    return {"docling_wins": docling_wins, "tied": tied, "markitdown_wins": md_wins}


def correlate(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Per-bucket aggregate of key indicators."""
    buckets = ["small", "medium", "large"]
    out: dict[str, dict[str, float]] = {}
    for b in buckets:
        sub = [r for r in rows if r.get("bucket") == b]
        if not sub:
            out[b] = {}
            continue
        out[b] = {
            "n_ranges": len(sub),
            "total_pages": sum(r["page_count"] for r in sub),
            "mean_md_chars_per_page": round(
                statistics.mean(r["md_char_len"] / r["page_count"] for r in sub), 1
            ),
            "mean_dl_chars_per_page": round(
                statistics.mean(r["dl_char_len"] / r["page_count"] for r in sub), 1
            ),
            "mean_md_structural_density": round(
                statistics.mean(r["md_structural_density_per_1k"] for r in sub), 3
            ),
            "mean_dl_structural_density": round(
                statistics.mean(r["dl_structural_density_per_1k"] for r in sub), 3
            ),
            "mean_md_table_cells_per_page": round(
                statistics.mean(r["md_table_cell_count"] / r["page_count"] for r in sub), 3
            ),
            "mean_dl_table_cells_per_page": round(
                statistics.mean(r["dl_table_cell_count"] / r["page_count"] for r in sub), 3
            ),
            "mean_md_heading_count_per_page": round(
                statistics.mean(r["md_heading_count"] / r["page_count"] for r in sub), 3
            ),
            "mean_dl_heading_count_per_page": round(
                statistics.mean(r["dl_heading_count"] / r["page_count"] for r in sub), 3
            ),
            "mean_md_section_count": round(statistics.mean(r["md_section_count"] for r in sub), 2),
            "mean_dl_section_count": round(statistics.mean(r["dl_section_count"] for r in sub), 2),
        }
    return out


def write_report(findings: dict[str, Any], out_path: Path) -> None:
    cls = findings["classification"]
    agg = findings["aggregate"]["per_engine"]
    bb = findings["bucket_breakdown"]

    n_total = len(cls["docling_wins"]) + len(cls["tied"]) + len(cls["markitdown_wins"])

    lines: list[str] = []
    lines.append("# Extraction strategy study — findings")
    lines.append("")
    lines.append(f"Dataset: **{n_total} flagged-range samples** drawn from the cosmos PA3+PA4 run.")
    lines.append(
        "Each sample pairs regenerated **markitdown** per-page output against the existing **docling** range splice output (PA3 evidence)."
    )
    lines.append("")
    lines.append("## Headline result")
    lines.append("")
    lines.append("| Bucket | Count | % |")
    lines.append("|---|---|---|")
    lines.append(
        f"| docling clearly wins | {len(cls['docling_wins'])} | {len(cls['docling_wins']) * 100 // n_total}% |"
    )
    lines.append(
        f"| tied / negligible gain | {len(cls['tied'])} | {len(cls['tied']) * 100 // n_total}% |"
    )
    lines.append(
        f"| markitdown wins | {len(cls['markitdown_wins'])} | {len(cls['markitdown_wins']) * 100 // n_total}% |"
    )
    lines.append("")
    lines.append(
        "Decision rule: docling wins when it produces meaningfully more structural content (≥5 extra table cells, OR ≥1.0/1000-char structural density gain, OR ≥30% more total content). markitdown wins when it matches/beats on structure and is shorter (lower-cost equivalent). Else tied."
    )
    lines.append("")

    lines.append("## Per-engine aggregate (across all sampled ranges)")
    lines.append("")
    key_metrics = [
        "char_len",
        "heading_count",
        "list_item_count",
        "code_block_count",
        "table_count",
        "table_cell_count",
        "section_count",
        "structural_density_per_1k",
        "type_token_ratio",
        "median_section_chars",
    ]
    lines.append("| Metric | markitdown (mean) | docling (mean) | docling/markitdown ratio |")
    lines.append("|---|---|---|---|")
    for k in key_metrics:
        mv = agg["md"].get(k, {}).get("mean", 0)
        dv = agg["dl"].get(k, {}).get("mean", 0)
        ratio = round(_safe_div(dv, mv), 2) if mv else "—"
        lines.append(f"| {k} | {mv} | {dv} | {ratio} |")
    lines.append("")

    lines.append("## Per-bucket breakdown")
    lines.append("")
    for bucket, stats in bb.items():
        if not stats:
            continue
        lines.append(
            f"### {bucket} ranges ({stats['n_ranges']} ranges, {stats['total_pages']} pages total)"
        )
        lines.append("")
        lines.append("| Metric | markitdown | docling | ratio |")
        lines.append("|---|---|---|---|")
        for label, (mk, dk) in [
            ("chars/page", ("mean_md_chars_per_page", "mean_dl_chars_per_page")),
            (
                "structural density per 1k chars",
                ("mean_md_structural_density", "mean_dl_structural_density"),
            ),
            ("table cells/page", ("mean_md_table_cells_per_page", "mean_dl_table_cells_per_page")),
            ("headings/page", ("mean_md_heading_count_per_page", "mean_dl_heading_count_per_page")),
            ("section count", ("mean_md_section_count", "mean_dl_section_count")),
        ]:
            mv = stats.get(mk, 0)
            dv = stats.get(dk, 0)
            ratio = round(_safe_div(dv, mv), 2) if mv else "—"
            lines.append(f"| {label} | {mv} | {dv} | {ratio} |")
        lines.append("")

    lines.append("## Ranges where docling clearly wins")
    lines.append("")
    if cls["docling_wins"]:
        lines.append("| Range | pages | Δ table cells | Δ structural density | char ratio |")
        lines.append("|---|---|---|---|---|")
        for d in sorted(cls["docling_wins"], key=lambda x: -x.get("delta_table_cell_count", 0))[
            :10
        ]:
            lines.append(
                f"| {d['range']} | {d['page_count']} | {d.get('delta_table_cell_count', 0)} | {d.get('delta_structural_density_per_1k', 0)} | {d.get('ratio_char_len', 1.0)} |"
            )
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Ranges where markitdown wins or matches")
    lines.append("")
    if cls["markitdown_wins"]:
        lines.append("| Range | pages | Δ heading | char ratio |")
        lines.append("|---|---|---|---|")
        for d in sorted(cls["markitdown_wins"], key=lambda x: x.get("ratio_char_len", 1.0))[:10]:
            lines.append(
                f"| {d['range']} | {d['page_count']} | {d.get('delta_heading_count', 0)} | {d.get('ratio_char_len', 1.0)} |"
            )
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Tied / negligible-gain ranges (over-fire candidates)")
    lines.append("")
    if cls["tied"]:
        lines.append("| Range | pages | char ratio | Δ table cells | Δ heading |")
        lines.append("|---|---|---|---|---|")
        for d in sorted(cls["tied"], key=lambda x: -x["page_count"])[:10]:
            lines.append(
                f"| {d['range']} | {d['page_count']} | {d.get('ratio_char_len', 1.0)} | {d.get('delta_table_cell_count', 0)} | {d.get('delta_heading_count', 0)} |"
            )
        lines.append("")
        total_tied_pages = sum(d["page_count"] for d in cls["tied"])
        lines.append(
            f"**Total pages in tied ranges**: {total_tied_pages}. These are pages where docling was invoked at ~15-30 s/page but produced no meaningful improvement over markitdown's ~1-2 s/page baseline."
        )
        lines.append("")
    else:
        lines.append("(none)")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    in_path = Path(".elt/output/cosmos-triage-022/study/results/per-range-metrics.json")
    out_dir = in_path.parent
    if not in_path.exists():
        print(f"ERROR: {in_path} not found; run evaluate_markdown.py first", file=sys.stderr)
        return 1

    rows = json.loads(in_path.read_text(encoding="utf-8"))
    agg = aggregate(rows)
    cls = classify_ranges(agg["per_row_delta"])
    bb = correlate(rows)

    findings = {
        "n_ranges": len(rows),
        "aggregate": agg,
        "classification": cls,
        "bucket_breakdown": bb,
    }
    (out_dir / "findings.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")
    write_report(findings, out_dir / "findings.md")

    print(f"Findings: {out_dir / 'findings.md'}")
    print(f"  docling wins: {len(cls['docling_wins'])}")
    print(f"  tied:         {len(cls['tied'])}")
    print(f"  markitdown wins: {len(cls['markitdown_wins'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
