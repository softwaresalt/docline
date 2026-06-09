"""Tests for _heuristic_and_score_pass helper (task 022.001-T / 024-S).

Verifies the refactor: the private Pass 1+2 helper produces identical
output to the prior inline implementations in process_pdf_triaged and
triage_report_only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pypdf
import pytest


def _make_pdf(path: Path, page_count: int) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def _no_flag_scorer() -> Any:
    from docline.process.fidelity_scorer import PageScore

    def scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
        return PageScore(
            page_index=page_index,
            signals={"density": 0.0},
            aggregate=0.0,
            needs_docling=False,
            reason="ok",
        )

    return scorer


def _flag_even_pages_scorer() -> Any:
    from docline.process.fidelity_scorer import PageScore

    def scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
        flag = page_index % 2 == 0
        return PageScore(
            page_index=page_index,
            signals={"density": 0.5 if flag else 0.0},
            aggregate=0.5 if flag else 0.0,
            needs_docling=flag,
            reason="even" if flag else "odd",
        )

    return scorer


def test_pass12_helper_returns_one_score_per_page(tmp_path: Path) -> None:
    from docline.process.pdf_triage import _heuristic_and_score_pass

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=5)
    result = _heuristic_and_score_pass(
        pdf,
        output_dir=tmp_path / "out",
        scorer=_no_flag_scorer(),
        baseline_engine="pypdf",
    )
    assert result.total_pages == 5
    assert len(result.heuristic_pages) == 5
    assert len(result.scores) == 5
    assert result.baseline_engine_fallback == 0


def test_pass12_helper_splice_cache_created(tmp_path: Path) -> None:
    from docline.process.pdf_triage import _heuristic_and_score_pass

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=2)
    out = tmp_path / "out"
    result = _heuristic_and_score_pass(
        pdf,
        output_dir=out,
        scorer=_no_flag_scorer(),
        baseline_engine="pypdf",
    )
    assert result.splice_cache.exists()
    assert result.splice_cache == out / "splices"


def test_pass12_helper_scorer_sees_correct_page_index(tmp_path: Path) -> None:
    from docline.process.pdf_triage import _heuristic_and_score_pass

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=4)
    result = _heuristic_and_score_pass(
        pdf,
        output_dir=tmp_path / "out",
        scorer=_flag_even_pages_scorer(),
        baseline_engine="pypdf",
    )
    # Pages 0 and 2 should be flagged (even); pages 1 and 3 not (odd)
    flagged = [s.page_index for s in result.scores if s.needs_docling]
    assert flagged == [0, 2]


def test_pass12_helper_raises_on_missing_pdf(tmp_path: Path) -> None:
    from docline.process.pdf_triage import _heuristic_and_score_pass

    missing = tmp_path / "nope.pdf"
    with pytest.raises(FileNotFoundError):
        _heuristic_and_score_pass(
            missing,
            output_dir=tmp_path / "out",
            scorer=_no_flag_scorer(),
            baseline_engine="pypdf",
        )


def test_pass12_result_heuristic_pages_is_immutable(tmp_path: Path) -> None:
    """The returned _Pass12Result.heuristic_pages MUST be a tuple (immutable),
    not a list. Prevents accidental mutation by downstream callers that share
    the same _Pass12Result.
    """
    from docline.process.pdf_triage import _heuristic_and_score_pass

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=2)
    result = _heuristic_and_score_pass(
        pdf,
        output_dir=tmp_path / "out",
        scorer=_no_flag_scorer(),
        baseline_engine="pypdf",
    )
    assert isinstance(result.heuristic_pages, tuple)
    assert isinstance(result.scores, tuple)
