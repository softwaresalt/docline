"""Tests for package metadata and the module entrypoint."""

import json
import subprocess
import sys
import tomllib
from pathlib import Path

from docline.app import get_manifest


def test_pyproject_declares_distribution_metadata() -> None:
    """pyproject.toml should declare richer distribution metadata."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]

    assert project["readme"] == "README.md"
    assert project["authors"]
    assert project["urls"]["Homepage"]
    assert project["urls"]["Repository"]


def test_python_m_docline_manifest_matches_shared_manifest() -> None:
    """python -m docline should expose the shared manifest entrypoint."""
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "docline", "--manifest"],
        capture_output=True,
        check=False,
        cwd=repo_root,
        text=True,
    )

    assert result.returncode == 0

    manifest = json.loads(result.stdout)

    assert manifest == get_manifest().model_dump()
