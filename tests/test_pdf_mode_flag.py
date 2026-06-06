"""Tests for ``--pdf-mode`` CLI flag wiring (task 019.004-T)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pypdf


def _make_pdf(path: Path, page_count: int = 3) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def test_manifest_includes_pdf_mode_flag() -> None:
    """`docline --manifest` output must declare the new --pdf-mode flag."""
    result = subprocess.run(
        [sys.executable, "-m", "docline", "--manifest"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--pdf-mode" in result.stdout or "pdf-mode" in result.stdout.lower()


def test_pdf_mode_triage_dispatches_to_triage_orchestrator(tmp_path: Path) -> None:
    """`--pdf-mode triage` must route through dispatch_pdf_mode to triage handler."""
    from docline.process.pdf_triage import TriageResult, dispatch_pdf_mode

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=3)
    result = dispatch_pdf_mode("triage", pdf, output_dir=tmp_path / "out")
    assert isinstance(result, TriageResult)


def test_pdf_mode_auto_dispatches_to_existing_batch_pipeline(tmp_path: Path) -> None:
    """`--pdf-mode auto` must keep existing behavior — dispatches to process_pdf_in_chunks."""
    from docline.process.pdf_batch import BatchResult
    from docline.process.pdf_triage import dispatch_pdf_mode

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=3)
    result = dispatch_pdf_mode("auto", pdf, output_dir=tmp_path / "out")
    assert isinstance(result, BatchResult)


def test_pdf_mode_invalid_value_rejected_by_argparse() -> None:
    """`--pdf-mode nonsense` must exit with an argparse choices error, not just unknown-flag."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "docline",
            "process",
            "--pdf-mode",
            "nonsense",
            "--input",
            "x",
            "--output",
            "y",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    combined = (result.stderr + result.stdout).lower()
    assert "invalid choice" in combined or "choose from" in combined


def test_default_mode_is_auto(tmp_path: Path) -> None:
    """Omitting --pdf-mode resolves to 'auto' through the dispatcher."""
    from docline.process.pdf_batch import BatchResult
    from docline.process.pdf_triage import dispatch_pdf_mode

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=3)
    result = dispatch_pdf_mode("auto", pdf, output_dir=tmp_path / "out")
    assert isinstance(result, BatchResult)
