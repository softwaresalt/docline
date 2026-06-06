"""Tests for per-page engine attribution in the output contract (task 019.005-T).

See compound learning ``docs/compound/2026-06-04-pydantic-namespace-merge-vs-overwrite.md``:
the ``engine`` field must MERGE into the ``docline:`` namespace, never overwrite.
"""

from __future__ import annotations

from pathlib import Path


def test_engine_field_merges_into_docline_namespace_without_destroying_existing_keys() -> None:
    """The new engine field must merge with existing docline: namespace keys."""
    from docline.process.output_contract import apply_triage_attribution

    seed = {
        "docline": {
            "source_url": "https://example.com/doc.pdf",
            "crawl_depth": 2,
        }
    }
    apply_triage_attribution(seed, engine="docling")

    assert seed["docline"]["source_url"] == "https://example.com/doc.pdf"
    assert seed["docline"]["crawl_depth"] == 2
    assert seed["docline"]["engine"] == "docling"


def test_round_trip_engine_attribution_for_mixed_triage_result() -> None:
    """A TriageResult with mixed engines produces per-part frontmatter with the right engine."""
    from docline.process.output_contract import build_triage_part_payloads
    from docline.process.pdf_triage import TriageResult

    triage = TriageResult(
        source=Path("doc.pdf"),
        pages=("p0", "p1", "p2"),
        engine_per_page=("heuristic", "docling", "heuristic"),
        flagged_ranges=((1, 1),),
        metadata={},
    )
    payloads = build_triage_part_payloads(triage)
    assert payloads[0]["docline"]["engine"] == "heuristic"
    assert payloads[1]["docline"]["engine"] == "docling"
    assert payloads[2]["docline"]["engine"] == "heuristic"


def test_manifest_triage_stats_matches_per_page_counts() -> None:
    """Manifest summary triage_stats block reflects actual per-page distribution."""
    from docline.process.output_contract import build_triage_manifest_stats
    from docline.process.pdf_triage import TriageResult

    triage = TriageResult(
        source=Path("doc.pdf"),
        pages=("a", "b", "c", "d", "e"),
        engine_per_page=("heuristic", "docling", "docling", "heuristic", "docling"),
        flagged_ranges=((1, 2), (4, 4)),
        metadata={},
    )
    stats = build_triage_manifest_stats(triage)
    assert stats["pages_total"] == 5
    assert stats["pages_docling"] == 3
    assert stats["pages_heuristic"] == 2
    assert stats["flagged_ranges"] == 2


def test_non_triage_runs_do_not_emit_engine_field() -> None:
    """Output for non-triage runs is byte-identical to today — no engine field appears."""
    from docline.process.output_contract import apply_triage_attribution

    seed = {"docline": {"source_url": "x"}}
    apply_triage_attribution(seed, engine=None)

    assert "engine" not in seed["docline"]
    assert seed["docline"]["source_url"] == "x"
