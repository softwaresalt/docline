"""Tests for pre-triage wiring through pdf_triage + CLI + ProcessRequest (028.003-T).

Covers four surfaces:

1. ``_heuristic_and_score_pass`` accepts an optional ``pre_scorer`` callable
   and short-circuits pages classified ``route_to_docling`` and
   ``route_to_heuristic`` per the pre-extraction routing decision.
2. ``triage_pre_score_report_only`` runs pre-scoring across all pages
   and emits a per-page TSV without invoking heuristic or docling.
3. ``ProcessRequest`` accepts the two new bool fields
   (``triage_pre_score`` and ``triage_pre_score_report_only``) with
   backward-compatible defaults of ``False``.
4. The CLI ``process`` subparser advertises the new flags via ``--help``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pypdf


def _make_blank_pdf(path: Path, page_count: int = 3) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def test_heuristic_and_score_pass_pre_scorer_route_to_docling_short_circuits(
    tmp_path: Path,
) -> None:
    """When pre_scorer returns route_to_docling, heuristic extraction MUST be skipped.

    Verified by passing a mock pre_scorer that always returns route_to_docling
    and a mock baseline that records its call count. The baseline MUST NOT
    be invoked because pre-triage already decided to route to docling.
    """
    from docline.process.fidelity_scorer import PreTriageDecision
    from docline.process.pdf_triage import _heuristic_and_score_pass

    pdf = _make_blank_pdf(tmp_path / "in.pdf", page_count=3)

    def always_docling(page_idx: int, _page_metadata: object | None) -> PreTriageDecision:
        return PreTriageDecision(
            page_index=page_idx,
            signals={"image_heavy": 1.0},
            aggregate=1.0,
            classification="route_to_docling",
            reason="image_heavy",
        )

    # Mock the baseline-extract so we can assert it isn't invoked
    with patch("docline.process.pdf_triage._heuristic_extract") as mock_extract:
        mock_extract.return_value = ("should-not-appear", False)
        result = _heuristic_and_score_pass(
            pdf,
            output_dir=tmp_path / "out",
            scorer=lambda *_: None,  # type: ignore[arg-type] — not called
            baseline_engine="pypdf",
            pre_scorer=always_docling,
        )

    assert mock_extract.call_count == 0, (
        f"heuristic extraction MUST NOT be invoked for route_to_docling pages; "
        f"got {mock_extract.call_count} calls"
    )
    assert len(result.heuristic_pages) == 3
    assert all(text == "" for text in result.heuristic_pages)
    assert all(s.needs_docling for s in result.scores)
    assert all("pre_triage" in s.reason for s in result.scores)


def test_heuristic_and_score_pass_pre_scorer_route_to_heuristic_skips_post_scoring(
    tmp_path: Path,
) -> None:
    """When pre_scorer returns route_to_heuristic, post-extraction scorer MUST NOT run."""
    from docline.process.fidelity_scorer import PreTriageDecision
    from docline.process.pdf_triage import _heuristic_and_score_pass

    pdf = _make_blank_pdf(tmp_path / "in.pdf", page_count=2)

    def always_heuristic(page_idx: int, _page_metadata: object | None) -> PreTriageDecision:
        return PreTriageDecision(
            page_index=page_idx,
            signals={},
            aggregate=0.0,
            classification="route_to_heuristic",
            reason="clean",
        )

    score_call_count = 0

    def counting_scorer(*_args, **_kwargs):
        nonlocal score_call_count
        score_call_count += 1
        from docline.process.fidelity_scorer import PageScore

        return PageScore(page_index=0)

    result = _heuristic_and_score_pass(
        pdf,
        output_dir=tmp_path / "out",
        scorer=counting_scorer,
        baseline_engine="pypdf",
        pre_scorer=always_heuristic,
    )

    assert score_call_count == 0, (
        "post-extraction scorer MUST NOT be invoked when pre_scorer routes to heuristic"
    )
    assert len(result.heuristic_pages) == 2
    assert all(not s.needs_docling for s in result.scores)


def test_heuristic_and_score_pass_pre_scorer_uncertain_falls_through(tmp_path: Path) -> None:
    """When pre_scorer returns uncertain, the existing heuristic + post-scoring path runs."""
    from docline.process.fidelity_scorer import PreTriageDecision
    from docline.process.pdf_triage import _heuristic_and_score_pass

    pdf = _make_blank_pdf(tmp_path / "in.pdf", page_count=2)

    def always_uncertain(page_idx: int, _page_metadata: object | None) -> PreTriageDecision:
        return PreTriageDecision(
            page_index=page_idx,
            signals={},
            aggregate=0.5,
            classification="uncertain",
            reason="borderline",
        )

    score_call_count = 0

    def counting_scorer(*_args, **_kwargs):
        nonlocal score_call_count
        score_call_count += 1
        from docline.process.fidelity_scorer import PageScore

        return PageScore(page_index=0)

    _heuristic_and_score_pass(
        pdf,
        output_dir=tmp_path / "out",
        scorer=counting_scorer,
        baseline_engine="pypdf",
        pre_scorer=always_uncertain,
    )

    assert score_call_count == 2, (
        f"post-extraction scorer MUST run for uncertain pages; got {score_call_count} calls"
    )


def test_heuristic_and_score_pass_default_pre_scorer_none_unchanged_behavior(
    tmp_path: Path,
) -> None:
    """pre_scorer=None (default) preserves existing scorer-runs-per-page behavior."""
    from docline.process.pdf_triage import _heuristic_and_score_pass

    pdf = _make_blank_pdf(tmp_path / "in.pdf", page_count=2)
    score_call_count = 0

    def counting_scorer(*_args, **_kwargs):
        nonlocal score_call_count
        score_call_count += 1
        from docline.process.fidelity_scorer import PageScore

        return PageScore(page_index=0)

    _heuristic_and_score_pass(
        pdf,
        output_dir=tmp_path / "out",
        scorer=counting_scorer,
        baseline_engine="pypdf",
    )

    assert score_call_count == 2, "scorer MUST run for every page when pre_scorer=None"


def test_triage_pre_score_report_only_emits_per_page_tsv(tmp_path: Path) -> None:
    """`triage_pre_score_report_only` MUST emit a TSV with the 5 signals + classification."""
    from docline.process.pdf_triage import triage_pre_score_report_only

    pdf = _make_blank_pdf(tmp_path / "in.pdf", page_count=2)
    report_path = tmp_path / "pre_triage_report.tsv"

    triage_pre_score_report_only(
        pdf,
        output_dir=tmp_path / "out",
        report_tsv_path=report_path,
    )

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    lines = content.strip().split("\n")
    assert len(lines) == 3, f"expected header + 2 data rows, got {len(lines)} lines"
    header = lines[0].split("\t")
    expected_columns = [
        "page_index",
        "image_heavy",
        "form_fields",
        "layout_complexity",
        "font_diversity",
        "text_flow_consistency",
        "aggregate",
        "classification",
        "reason",
    ]
    for col in expected_columns:
        assert col in header, f"expected column {col!r} in TSV header, got {header}"


def test_process_request_accepts_new_pre_score_flags() -> None:
    """ProcessRequest MUST accept triage_pre_score and triage_pre_score_report_only flags."""
    from docline.app_models import ProcessRequest

    request = ProcessRequest(
        staging_dir="staging",
        output_dir="output",
        triage_pre_score=True,
        triage_pre_score_report_only=False,
    )
    assert request.triage_pre_score is True
    assert request.triage_pre_score_report_only is False


def test_process_request_default_pre_score_flags_are_false() -> None:
    """Defaults MUST be False for backward compatibility with existing triage runs."""
    from docline.app_models import ProcessRequest

    request = ProcessRequest(staging_dir="staging", output_dir="output")
    assert request.triage_pre_score is False
    assert request.triage_pre_score_report_only is False


def test_cli_process_help_advertises_triage_pre_score(tmp_path: Path) -> None:
    """`docline process --help` MUST list --triage-pre-score and --triage-pre-score-report-only."""
    result = subprocess.run(
        [sys.executable, "-m", "docline", "process", "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "--triage-pre-score" in result.stdout
    assert "--triage-pre-score-report-only" in result.stdout


def test_manifest_includes_triage_pre_score_in_process_request(tmp_path: Path) -> None:
    """`docline --manifest` MUST advertise the new flags in the process tool schema."""
    import json

    result = subprocess.run(
        [sys.executable, "-m", "docline", "--manifest"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    manifest = json.loads(result.stdout)
    process_tool = next(t for t in manifest["tools"] if t["name"] == "process")
    props = process_tool["parameters"]["properties"]
    assert "triage_pre_score" in props
    assert "triage_pre_score_report_only" in props
