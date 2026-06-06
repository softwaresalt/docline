"""Tests for ``docline.process.pdf_triage`` orchestrator (task 019.003-T)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pypdf
import pytest


def _make_pdf(path: Path, page_count: int) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def _runner_factory(markdown: str = "# Heading\nbody") -> Any:
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        output_path = Path(args[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def _failing_runner() -> Any:
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args, returncode=5, stdout="", stderr="docling failed"
        )

    return runner


def _make_scorer(flagged: set[int]) -> Any:
    """Build a deterministic scorer that flags only the given page indices."""

    from docline.process.fidelity_scorer import PageScore

    def scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
        return PageScore(
            page_index=page_index,
            signals={},
            aggregate=1.0 if page_index in flagged else 0.0,
            needs_docling=page_index in flagged,
            reason="forced" if page_index in flagged else "ok",
        )

    return scorer


def test_no_flagged_pages_skips_docling_runner(tmp_path: Path) -> None:
    """When the scorer flags no pages, the docling runner must not be invoked."""
    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "small.pdf", page_count=10)
    runner = MagicMock(side_effect=_runner_factory())
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_make_scorer(flagged=set()),
    )

    assert runner.call_count == 0
    assert all(eng == "heuristic" for eng in result.engine_per_page)
    assert result.flagged_ranges == ()


def test_flagged_pages_route_to_docling_and_splice_back(tmp_path: Path) -> None:
    """Flagged page indices are coalesced and docling outputs splice into the right slots."""
    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    runner = MagicMock(side_effect=_runner_factory("# Docling page\nrich content"))
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_make_scorer(flagged={3, 4, 5}),
        buffer=0,
        merge_gap=2,
    )

    assert runner.call_count == 1
    assert (3, 5) in result.flagged_ranges
    for idx in (3, 4, 5):
        assert result.engine_per_page[idx] == "docling"
    for idx in (0, 1, 2, 6, 7, 8, 9):
        assert result.engine_per_page[idx] == "heuristic"


def test_docling_failure_falls_back_to_heuristic_per_range(tmp_path: Path) -> None:
    """Docling subprocess non-zero exit must fall back to heuristic for that range only."""
    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=_failing_runner(),
        scorer=_make_scorer(flagged={4, 5}),
        buffer=0,
    )

    for idx in (4, 5):
        assert result.engine_per_page[idx] == "heuristic"
    assert result.metadata.get("subprocess_fallback_count", 0) >= 1


def test_triage_result_is_frozen(tmp_path: Path) -> None:
    """TriageResult returned by the orchestrator must be a frozen dataclass."""
    import dataclasses

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=3)
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=_runner_factory(),
        scorer=_make_scorer(flagged=set()),
    )
    assert dataclasses.is_dataclass(result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.pages = ("changed",)  # type: ignore[misc]
