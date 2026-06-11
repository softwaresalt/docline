"""Empirical validation harness for the pre-triage scorer (028.004-T / 030-S).

Validates that the new pre-extraction triage classifications agree with
the docling-vs-heuristic winners from the 2026-06-08 extraction-strategy
study (``docs/decisions/2026-06-08-extraction-strategy-study.md``).

The study processed 15 page ranges from the cosmos technical reference
PDF, computing 25 AST-aware metrics for both the markitdown heuristic
and docling outputs. The ground truth for each range is "which engine
produced higher-fidelity output" based on structural density, heading
count, and section count.

This harness runs the new ``pre_triage_score`` against each page in each
range and aggregates per-range agreement against that ground truth. The
exit code is non-zero if aggregate agreement < 85%, gating production
rollout of ``--triage-pre-score``.

Usage::

    python scripts/study/validate_pre_triage.py \
        --pdf .elt/data/cosmosdb/azure-cosmos-db.pdf \
        --per-range-metrics .elt/output/cosmos-triage-022/study/results/per-range-metrics.json \
        --output .elt/output/cosmos-triage-022/study/results/pre-triage-validation.json

The script is idempotent: it re-runs scoring from scratch each invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pypdf

# Add src/ to sys.path so the script works without `pip install -e .`
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from docline.process.fidelity_scorer import (  # noqa: E402
    PreTriageDecision,
    pre_triage_score,
)

_AGREEMENT_GATE = 0.85
_PAGE_FLAG_FRACTION_THRESHOLD = 0.30


@dataclass(frozen=True)
class _GroundTruth:
    """Per-range ground-truth winner derived from the 2026-06-08 study."""

    range_start: int
    range_end: int
    docling_wins: bool
    reason: str


def _derive_ground_truth(range_metric: dict) -> _GroundTruth:
    """Decide which engine "wins" a range using AST-aware quality signals.

    A range counts as a docling win when docling produced meaningfully
    more structural fidelity. We use the 3-of-3 majority across the
    three AST-aware metrics used in the original study:

    * ``structural_density_per_1k`` — primary signal
    * ``heading_count`` — section structure
    * ``section_count`` — chunkability

    A 10% relative advantage on any single metric counts as a vote.
    Two or more votes → docling wins. Mirrors the decision rule from
    ``docs/decisions/2026-06-08-extraction-strategy-study.md``.
    """
    md_density = float(range_metric.get("md_structural_density_per_1k", 0.0))
    dl_density = float(range_metric.get("dl_structural_density_per_1k", 0.0))
    md_headings = int(range_metric.get("md_heading_count", 0))
    dl_headings = int(range_metric.get("dl_heading_count", 0))
    md_sections = int(range_metric.get("md_section_count", 0))
    dl_sections = int(range_metric.get("dl_section_count", 0))

    votes = 0
    reasons: list[str] = []
    if dl_density > md_density * 1.1:
        votes += 1
        reasons.append(f"density({dl_density:.2f}vs{md_density:.2f})")
    if dl_headings > md_headings * 1.1 or (md_headings == 0 and dl_headings > 0):
        votes += 1
        reasons.append(f"headings({dl_headings}vs{md_headings})")
    if dl_sections > md_sections * 1.1 or (md_sections <= 1 and dl_sections > 1):
        votes += 1
        reasons.append(f"sections({dl_sections}vs{md_sections})")

    return _GroundTruth(
        range_start=int(range_metric["range_start"]),
        range_end=int(range_metric["range_end"]),
        docling_wins=votes >= 2,
        reason=",".join(reasons) if reasons else "no_signal_advantage",
    )


def _score_range(
    reader: pypdf.PdfReader,
    range_start: int,
    range_end: int,
) -> list[PreTriageDecision]:
    """Pre-triage every page in ``[range_start, range_end]`` (inclusive)."""
    decisions: list[PreTriageDecision] = []
    end_exclusive = min(range_end + 1, len(reader.pages))
    for page_idx in range(range_start, end_exclusive):
        decisions.append(pre_triage_score(page_idx, reader.pages[page_idx]))
    return decisions


def _predict_docling_wins(decisions: Sequence[PreTriageDecision]) -> bool:
    """Predict range-level winner from per-page pre-triage classifications.

    A range is predicted as "docling wins" when at least
    ``_PAGE_FLAG_FRACTION_THRESHOLD`` of its pages classify as
    ``route_to_docling``. Otherwise predicted as heuristic wins.
    Uncertain pages contribute 0.5 weight (split decision).
    """
    if not decisions:
        return False
    docling_score = 0.0
    for d in decisions:
        if d.classification == "route_to_docling":
            docling_score += 1.0
        elif d.classification == "uncertain":
            docling_score += 0.5
    fraction = docling_score / len(decisions)
    return fraction >= _PAGE_FLAG_FRACTION_THRESHOLD


def validate(
    pdf_path: Path,
    metrics_path: Path,
    output_path: Path,
) -> dict[str, object]:
    """Run validation and return the report dict (also written to ``output_path``)."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"Source PDF not found: {pdf_path}")
    if not metrics_path.exists():
        raise FileNotFoundError(f"per-range-metrics.json not found: {metrics_path}")

    range_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    if not isinstance(range_metrics, list):
        raise ValueError(
            f"expected per-range-metrics.json to be a list, got {type(range_metrics).__name__}"
        )

    reader = pypdf.PdfReader(str(pdf_path), strict=False)
    per_range_rows: list[dict[str, object]] = []
    agree_count = 0

    for rm in range_metrics:
        gt = _derive_ground_truth(rm)
        decisions = _score_range(reader, gt.range_start, gt.range_end)
        predicted_docling = _predict_docling_wins(decisions)
        agrees = predicted_docling == gt.docling_wins
        if agrees:
            agree_count += 1
        per_range_rows.append(
            {
                "range_start": gt.range_start,
                "range_end": gt.range_end,
                "page_count": len(decisions),
                "ground_truth_docling_wins": gt.docling_wins,
                "ground_truth_reason": gt.reason,
                "predicted_docling_wins": predicted_docling,
                "agrees": agrees,
                "page_classifications": {
                    "route_to_docling": sum(
                        1 for d in decisions if d.classification == "route_to_docling"
                    ),
                    "route_to_heuristic": sum(
                        1 for d in decisions if d.classification == "route_to_heuristic"
                    ),
                    "uncertain": sum(1 for d in decisions if d.classification == "uncertain"),
                },
                "mean_aggregate": (
                    sum(d.aggregate for d in decisions) / len(decisions) if decisions else 0.0
                ),
            }
        )

    total = len(per_range_rows)
    agreement_pct = (agree_count / total) if total else 0.0
    gate_passed = agreement_pct >= _AGREEMENT_GATE

    report = {
        "agreement_pct": round(agreement_pct, 3),
        "agreement_count": agree_count,
        "total_ranges": total,
        "gate_threshold": _AGREEMENT_GATE,
        "gate_passed": gate_passed,
        "per_range": per_range_rows,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path(".elt/data/cosmosdb/azure-cosmos-db.pdf"),
        help="Source PDF path.",
    )
    parser.add_argument(
        "--per-range-metrics",
        type=Path,
        default=Path(".elt/output/cosmos-triage-022/study/results/per-range-metrics.json"),
        help="Ground-truth per-range AST metrics JSON from the 2026-06-08 study.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".elt/output/cosmos-triage-022/study/results/pre-triage-validation.json"),
        help="Output path for the validation report JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = validate(args.pdf, args.per_range_metrics, args.output)
    except FileNotFoundError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    print(
        f"agreement: {report['agreement_pct']:.1%} "
        f"({report['agreement_count']}/{report['total_ranges']} ranges)"
    )
    print(f"gate threshold: {report['gate_threshold']:.0%}")
    print(f"report: {args.output}")
    if not report["gate_passed"]:
        print(
            f"GATE FAILED — agreement below {_AGREEMENT_GATE:.0%}; "
            "pre-triage scorer needs calibration before rollout.",
            file=sys.stderr,
        )
        return 1
    print("gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
