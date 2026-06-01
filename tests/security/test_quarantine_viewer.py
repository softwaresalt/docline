"""Tests for quarantine viewer workspace containment."""

import json
from pathlib import Path

import pytest

import docline.quarantine_viewer as quarantine_viewer
from docline.cli import main
from docline.quarantine_viewer import QuarantineViewerError, render_local_quarantine_viewer


def test_render_local_quarantine_viewer_renders_workspace_artifact(tmp_path, monkeypatch) -> None:
    """render_local_quarantine_viewer accepts workspace-relative artifact paths."""
    monkeypatch.chdir(tmp_path)
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(
        json.dumps({"document_id": "doc-123", "status": "quarantined"}),
        encoding="utf-8",
    )

    viewer_path = render_local_quarantine_viewer("artifact.json", "viewer")

    assert viewer_path == tmp_path / "viewer" / "index.html"
    assert viewer_path.read_text(encoding="utf-8")


def test_validate_local_artifact_path_allows_http_prefixed_workspace_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Workspace-local artifact names may include an ``http:`` prefix."""
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(json.dumps({"document_id": "doc-http"}), encoding="utf-8")

    def fake_safe_workspace_path(path_value: Path | str, workspace_root: Path) -> Path:
        assert path_value == "http:artifact.json"
        assert workspace_root == tmp_path
        return artifact_path

    monkeypatch.setattr(quarantine_viewer, "safe_workspace_path", fake_safe_workspace_path)

    resolved_path = quarantine_viewer._validate_local_artifact_path(
        "http:artifact.json",
        tmp_path,
    )

    assert resolved_path == artifact_path


def test_render_local_quarantine_viewer_rejects_artifact_outside_workspace(
    tmp_path, monkeypatch
) -> None:
    """render_local_quarantine_viewer rejects artifact traversal outside the workspace."""
    monkeypatch.chdir(tmp_path)
    outside_artifact = tmp_path.parent / "outside-artifact.json"
    outside_artifact.write_text(json.dumps({"document_id": "doc-456"}), encoding="utf-8")

    with pytest.raises(QuarantineViewerError, match="parent-directory traversal"):
        render_local_quarantine_viewer("../outside-artifact.json", "viewer")


def test_cli_quarantine_viewer_rejects_artifact_outside_workspace(
    tmp_path, monkeypatch, capsys
) -> None:
    """CLI quarantine-viewer keeps reporting contained-path failures via stderr."""
    monkeypatch.chdir(tmp_path)
    outside_artifact = tmp_path.parent / "outside-artifact.json"
    outside_artifact.write_text(json.dumps({"document_id": "doc-789"}), encoding="utf-8")

    exit_code = main(["quarantine-viewer", "../outside-artifact.json"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "parent-directory traversal" in captured.err
