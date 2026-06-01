"""Tests for shared app-layer services used by CLI and MCP surfaces."""

from pathlib import Path

from docline.app import execute_process
from docline.app_models import ProcessRequest
from docline.paths import PathContainmentError


def test_execute_process_returns_failure_envelope_for_containment_error(monkeypatch) -> None:
    """execute_process converts containment failures into a normal result envelope."""

    def _raise_containment_error(path: str, workspace_root: str) -> None:
        raise PathContainmentError(f"Path {path!r} is outside {workspace_root!r}")

    monkeypatch.setattr("docline.app.safe_workspace_path", _raise_containment_error)

    result = execute_process(ProcessRequest(staging_dir="staging"))

    assert result.input_path == "staging"
    assert result.success is False
    assert result.output_path is None
    assert result.error == f"Path 'staging' is outside {Path.cwd()!r}"
