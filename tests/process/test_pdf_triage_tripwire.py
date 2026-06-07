"""Tests for the QA tripwire mode in ``pdf_triage`` (task 019.007-T)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pypdf


def _make_pdf(path: Path, page_count: int) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def _ok_runner(markdown: str = "# docling output") -> Any:
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        out = Path(args[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def _no_flag_scorer() -> Any:
    from docline.process.fidelity_scorer import PageScore

    def scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
        return PageScore(
            page_index=page_index,
            signals={},
            aggregate=0.0,
            needs_docling=False,
            reason="ok",
        )

    return scorer


def test_sample_rate_zero_invokes_runner_only_for_flagged_ranges(tmp_path: Path) -> None:
    """qa_sampling=None or sample_rate=0 must not trigger any tripwire docling calls."""
    from docline.process.pdf_triage import QASampling, process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    runner = MagicMock(side_effect=_ok_runner())
    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_no_flag_scorer(),
        qa_sampling=QASampling(sample_rate=0.0, random_seed=42),
    )
    assert runner.call_count == 0


def test_sample_rate_one_samples_every_unflagged_page_subject_to_cap(tmp_path: Path) -> None:
    """sample_rate=1.0 samples every unflagged page (up to max_sampled_pages cap)."""
    from docline.process.pdf_triage import QASampling, process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    runner = MagicMock(side_effect=_ok_runner())
    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_no_flag_scorer(),
        qa_sampling=QASampling(sample_rate=1.0, random_seed=42, max_sampled_pages=50),
    )
    assert runner.call_count == 10


def test_disagreement_counter_increments_when_outputs_differ(tmp_path: Path) -> None:
    """When sampled docling output differs from heuristic, qa_disagreements increments."""
    from docline.process.pdf_triage import QASampling, process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=5)
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=_ok_runner("# This is wildly different from heuristic output"),
        scorer=_no_flag_scorer(),
        qa_sampling=QASampling(sample_rate=1.0, random_seed=42),
    )
    assert result.metadata.get("qa_disagreements", 0) >= 1


def test_random_seed_makes_sampling_deterministic(tmp_path: Path) -> None:
    """Two runs with the same seed select the same set of sampled pages."""
    from docline.process.pdf_triage import QASampling, process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=20)
    sampling = QASampling(sample_rate=0.3, random_seed=99)
    runner_a = MagicMock(side_effect=_ok_runner())
    runner_b = MagicMock(side_effect=_ok_runner())

    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "a",
        runner=runner_a,
        scorer=_no_flag_scorer(),
        qa_sampling=sampling,
    )
    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "b",
        runner=runner_b,
        scorer=_no_flag_scorer(),
        qa_sampling=sampling,
    )

    assert runner_a.call_count == runner_b.call_count
    pages_a = sorted(Path(call.args[0][-2]).stem for call in runner_a.call_args_list)
    pages_b = sorted(Path(call.args[0][-2]).stem for call in runner_b.call_args_list)
    assert pages_a == pages_b
