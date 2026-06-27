"""Compare pa3 triage summaries across merge_gap values and emit a verdict.

Ingests two or more ``pa3-summary.json`` files (one per ``merge_gap`` setting),
prints a comparison table, and recommends whether to lower the triage
``merge_gap`` default. The decision is driven by **wall-clock** (the actual
goal) guarded by the QA tripwire; the docling routing stats (from the 038-S
``docling_attribution`` section) are reported for explanation.

This script does **not** run docling — it only reads already-produced summaries,
so it is safe to run inside any environment (the cosmos sweep that produces the
summaries is the operator-run 036.002-T task).

Usage::

    python scripts/study/compare_merge_gap.py \\
        --summaries .elt/output/cosmos-mg2/pa3-summary.json \\
                    .elt/output/cosmos-mg1/pa3-summary.json \\
                    .elt/output/cosmos-mg0/pa3-summary.json \\
        --win-threshold 0.05 --qa-tolerance 0

Verdicts:

* ``LOWER-DEFAULT`` — a lower ``merge_gap`` is faster by at least
  ``--win-threshold`` (relative wall-clock) without a QA-disagreement
  regression beyond ``--qa-tolerance``. Reports the winning ``merge_gap``.
* ``KEEP-DEFAULT`` — no lower ``merge_gap`` delivered a meaningful wall-clock
  win.
* ``INCONCLUSIVE`` — a lower ``merge_gap`` was faster but regressed QA beyond
  tolerance, so the trade-off needs a human call.

Exit codes: ``0`` success; ``2`` bad arguments (fewer than two summaries or a
summary missing the 038-S ``docling_attribution`` section).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _extract_row(summary: dict[str, Any]) -> dict[str, Any]:
    """Pull the comparison fields from one pa3 summary.

    Args:
        summary: Parsed ``pa3-summary.json`` content.

    Returns:
        A flat row with ``merge_gap``, ``wall_clock_seconds``, docling routing
        stats, and QA counts.

    Raises:
        ValueError: If the summary predates the 038-S ``docling_attribution``
            section.
    """
    attribution = summary.get("docling_attribution")
    if not isinstance(attribution, dict):
        raise ValueError(
            "summary is missing the 'docling_attribution' section (predates "
            "038-S); re-run pa3_triage_cosmos.py to produce comparable output"
        )
    metadata = summary.get("metadata", {})
    content_pages = int(attribution["content_pages"])
    collapsed = int(attribution["collapsed_placeholder_pages"])
    return {
        "merge_gap": int(summary["merge_gap"]),
        "wall_clock_seconds": float(summary["wall_clock_seconds"]),
        "docling_ranges": int(attribution["ranges"]),
        "docling_content_pages": content_pages,
        "docling_collapsed_pages": collapsed,
        "docling_source_pages": content_pages + collapsed,
        "total_docling_chars": int(attribution["total_docling_chars"]),
        "qa_disagreements": int(metadata.get("qa_disagreements", 0)),
        "qa_sampled_count": int(metadata.get("qa_sampled_count", 0)),
        "flagged_pages_count": int(metadata.get("flagged_pages_count", 0)),
    }


def _verdict(
    rows: list[dict[str, Any]],
    *,
    win_threshold: float,
    qa_tolerance: int,
) -> dict[str, Any]:
    """Decide whether a lower ``merge_gap`` should become the default.

    Args:
        rows: Extracted rows (one per summary).
        win_threshold: Minimum relative wall-clock reduction vs. the
            highest-``merge_gap`` baseline for a candidate to win.
        qa_tolerance: Maximum allowed increase in ``qa_disagreements`` over the
            baseline for a candidate to remain eligible.

    Returns:
        A dict with ``verdict`` (``LOWER-DEFAULT`` / ``KEEP-DEFAULT`` /
        ``INCONCLUSIVE``), ``baseline_merge_gap``, ``winner_merge_gap`` (or
        ``None``), and the winning ``wall_clock_reduction_pct``.
    """
    baseline = max(rows, key=lambda r: r["merge_gap"])
    candidates = [r for r in rows if r["merge_gap"] < baseline["merge_gap"]]

    eligible: list[tuple[dict[str, Any], float]] = []
    qa_blocked = False
    for cand in candidates:
        reduction = (
            (baseline["wall_clock_seconds"] - cand["wall_clock_seconds"])
            / baseline["wall_clock_seconds"]
            if baseline["wall_clock_seconds"]
            else 0.0
        )
        if reduction < win_threshold:
            continue
        if cand["qa_disagreements"] > baseline["qa_disagreements"] + qa_tolerance:
            qa_blocked = True
            continue
        eligible.append((cand, reduction))

    if eligible:
        winner, reduction = min(eligible, key=lambda pair: pair[0]["wall_clock_seconds"])
        return {
            "verdict": "LOWER-DEFAULT",
            "baseline_merge_gap": baseline["merge_gap"],
            "winner_merge_gap": winner["merge_gap"],
            "wall_clock_reduction_pct": round(reduction * 100, 2),
        }
    return {
        "verdict": "INCONCLUSIVE" if qa_blocked else "KEEP-DEFAULT",
        "baseline_merge_gap": baseline["merge_gap"],
        "winner_merge_gap": None,
        "wall_clock_reduction_pct": 0.0,
    }


def _format_table(rows: list[dict[str, Any]]) -> str:
    """Render the comparison rows as a fixed-width text table."""
    header = (
        f"{'merge_gap':>9}  {'wall_s':>9}  {'ranges':>7}  "
        f"{'docling_pages':>13}  {'docling_chars':>13}  {'qa_disagree':>11}"
    )
    lines = [header, "-" * len(header)]
    for r in sorted(rows, key=lambda x: x["merge_gap"], reverse=True):
        lines.append(
            f"{r['merge_gap']:>9}  {r['wall_clock_seconds']:>9.1f}  "
            f"{r['docling_ranges']:>7}  {r['docling_source_pages']:>13}  "
            f"{r['total_docling_chars']:>13}  {r['qa_disagreements']:>11}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python scripts/study/compare_merge_gap.py``."""
    parser = argparse.ArgumentParser(
        description=(
            "Compare pa3 triage summaries across merge_gap values and recommend "
            "whether to lower the merge_gap default."
        ),
    )
    parser.add_argument(
        "--summaries",
        type=Path,
        nargs="+",
        required=True,
        help="Two or more pa3-summary.json files (one per merge_gap value).",
    )
    parser.add_argument(
        "--win-threshold",
        type=float,
        default=0.05,
        help="Minimum relative wall-clock reduction vs. baseline for a win (default 0.05).",
    )
    parser.add_argument(
        "--qa-tolerance",
        type=int,
        default=0,
        help="Max allowed increase in qa_disagreements over baseline (default 0).",
    )
    args = parser.parse_args(argv)

    if len(args.summaries) < 2:
        print("ERROR: --summaries requires at least two files (one per merge_gap value)")
        return 2

    rows: list[dict[str, Any]] = []
    for path in args.summaries:
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            print(f"ERROR: could not read {path}: {err}")
            return 2
        try:
            rows.append(_extract_row(summary))
        except (ValueError, KeyError) as err:
            print(f"ERROR: {path}: {err}")
            return 2

    verdict = _verdict(rows, win_threshold=args.win_threshold, qa_tolerance=args.qa_tolerance)

    print(_format_table(rows))
    print()
    if verdict["verdict"] == "LOWER-DEFAULT":
        print(
            f"VERDICT: LOWER-DEFAULT to merge_gap={verdict['winner_merge_gap']} "
            f"({verdict['wall_clock_reduction_pct']}% faster than "
            f"merge_gap={verdict['baseline_merge_gap']}, no QA regression)"
        )
    elif verdict["verdict"] == "INCONCLUSIVE":
        print(
            "VERDICT: INCONCLUSIVE — a lower merge_gap was faster but regressed "
            "QA beyond tolerance; needs a human call"
        )
    else:
        print(
            f"VERDICT: KEEP-DEFAULT (merge_gap={verdict['baseline_merge_gap']}) — "
            "no lower merge_gap delivered a meaningful wall-clock win"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
