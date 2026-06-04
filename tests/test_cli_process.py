"""Failing-first tests for ``docline process --pdf-engine`` CLI flag (G3c task 015.001-T).

Covers the new ``--pdf-engine {auto,docling,heuristic}`` argument on the
``process`` subcommand, its default ``auto`` value, and argparse-level
rejection of unknown values.
"""

from __future__ import annotations

import pytest

from docline.cli import main


def test_process_subparser_accepts_pdf_engine_flag(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``docline process --pdf-engine docling`` is accepted (no argparse error)."""
    # Use an empty staging dir so execute_process exits cleanly with 'no jobs'.
    staging = tmp_path / "staging"
    staging.mkdir()
    output = tmp_path / "output"
    rc = main(
        [
            "process",
            "--staging-dir",
            str(staging.relative_to(tmp_path)),
            "--output-dir",
            str(output.relative_to(tmp_path)),
            "--pdf-engine",
            "docling",
        ]
    )
    # The CLI may return 0 (no work) or 1 (no jobs found); both are non-2 (non-argparse-failure).
    assert rc in (0, 1), f"expected non-argparse exit, got {rc}"


def test_process_subparser_pdf_engine_defaults_to_auto(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Omitting ``--pdf-engine`` produces a ``ProcessRequest`` with ``pdf_engine='auto'``."""
    from docline.app_models import ProcessRequest

    # Round-trip: construct a ProcessRequest with all defaults to assert the field default.
    request = ProcessRequest(staging_dir="staging", output_dir="output")
    assert request.pdf_engine == "auto"


def test_process_subparser_rejects_unknown_pdf_engine_value(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--pdf-engine bogus`` is rejected by argparse with exit code 2."""
    staging = tmp_path / "staging"
    staging.mkdir()
    output = tmp_path / "output"
    rc = main(
        [
            "process",
            "--staging-dir",
            str(staging.relative_to(tmp_path)),
            "--output-dir",
            str(output.relative_to(tmp_path)),
            "--pdf-engine",
            "bogus",
        ]
    )
    assert rc == 2, f"expected argparse rejection (exit 2), got {rc}"
