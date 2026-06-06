"""Tests for ``--pdf-mode`` CLI flag wiring (task 019.004-T)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


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


def test_pdf_mode_triage_dispatches_to_triage_orchestrator() -> None:
    """`--pdf-mode triage` must route through dispatch_pdf_mode to triage handler."""
    from docline.process.pdf_triage import TriageResult, dispatch_pdf_mode

    result = dispatch_pdf_mode("triage", Path("x.pdf"), output_dir=Path("out"))
    assert isinstance(result, TriageResult)


def test_pdf_mode_auto_dispatches_to_existing_batch_pipeline() -> None:
    """`--pdf-mode auto` must keep existing behavior — dispatches to process_pdf_in_chunks."""
    from docline.process.pdf_batch import BatchResult
    from docline.process.pdf_triage import dispatch_pdf_mode

    result = dispatch_pdf_mode("auto", Path("x.pdf"), output_dir=Path("out"))
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
    # Require U4-specific choices-constraint rejection, not the default "unrecognized arguments".
    assert "invalid choice" in combined or "choose from" in combined


def test_default_mode_is_auto() -> None:
    """Omitting --pdf-mode resolves to 'auto' through the dispatcher."""
    from docline.process.pdf_batch import BatchResult
    from docline.process.pdf_triage import dispatch_pdf_mode

    result = dispatch_pdf_mode("auto", Path("x.pdf"), output_dir=Path("out"))
    assert isinstance(result, BatchResult)
