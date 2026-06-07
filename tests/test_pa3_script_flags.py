"""Tests for new flags in ``scripts/pa3_triage_cosmos.py`` (task 020.005-T / U5)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "pa3_triage_cosmos.py"


def test_script_help_includes_baseline_engine_flag() -> None:
    """`scripts/pa3_triage_cosmos.py --help` MUST list `--baseline-engine`."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--baseline-engine" in result.stdout, (
        f"--baseline-engine not in --help output; got:\n{result.stdout}"
    )


def test_script_help_lists_markitdown_as_default_baseline() -> None:
    """`--help` MUST document markitdown as the default baseline engine."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    # The help text should say markitdown is the default for --baseline-engine.
    lowered = result.stdout.lower()
    assert "markitdown" in lowered, (
        f"--help must mention markitdown as the default baseline; got:\n{result.stdout}"
    )


def test_script_help_includes_similarity_threshold_flag() -> None:
    """`--help` MUST surface the new Jaccard similarity threshold control."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--similarity-threshold" in result.stdout, (
        f"--similarity-threshold not in --help output; got:\n{result.stdout}"
    )
