"""Failing harness tests for the quarantine viewer CLI surface."""

import json
from pathlib import Path

import pytest

from docline.cli import main
from docline.quarantine_viewer import QuarantineViewerError, render_local_quarantine_viewer


def test_render_local_quarantine_viewer_writes_escaped_local_html(
    monkeypatch, tmp_path: Path
) -> None:
    """The shared renderer should escape hostile artifact content into local HTML."""
    artifact_name = "doc-001-quarantine.json"
    artifact_path = tmp_path / artifact_name
    artifact_path.write_text(
        json.dumps(
            {
                "document_id": "doc-001",
                "failure_payload": {"reason": "schema-validation"},
                "markdown_excerpt": "<script>alert('xss')</script>",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    viewer_path = render_local_quarantine_viewer(artifact_name, "viewer")

    assert viewer_path == tmp_path / "viewer" / "index.html"
    html = viewer_path.read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "&lt;script&gt;alert('xss')&lt;/script&gt;" in html


def test_cli_quarantine_viewer_renders_local_viewer_artifact(
    capsys, monkeypatch, tmp_path: Path
) -> None:
    """The CLI should route quarantine-viewer through the shared local renderer."""
    artifact_name = "doc-001-quarantine.json"
    artifact_path = tmp_path / artifact_name
    artifact_path.write_text(
        json.dumps(
            {
                "document_id": "doc-001",
                "failure_payload": {"reason": "schema-validation"},
                "markdown_excerpt": "Broken content",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(["quarantine-viewer", artifact_name, "--output-dir", "viewer"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["viewer_path"] == str(tmp_path / "viewer" / "index.html")


def test_render_local_quarantine_viewer_rejects_output_dir_outside_workspace(
    monkeypatch, tmp_path: Path
) -> None:
    """The shared renderer should reject output paths that escape the workspace."""
    artifact_name = "doc-001-quarantine.json"
    artifact_path = tmp_path / artifact_name
    artifact_path.write_text(json.dumps({"document_id": "doc-001"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(QuarantineViewerError, match="must not contain parent-directory traversal"):
        render_local_quarantine_viewer(artifact_name, "../viewer")


def test_cli_quarantine_viewer_rejects_unsafe_output_dir_with_handled_error(
    capsys, monkeypatch, tmp_path: Path
) -> None:
    """The CLI should handle quarantine viewer failures without bubbling a traceback."""
    artifact_name = "doc-001-quarantine.json"
    artifact_path = tmp_path / artifact_name
    artifact_path.write_text(json.dumps({"document_id": "doc-001"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = main(["quarantine-viewer", artifact_name, "--output-dir", "../viewer"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "error:" in captured.err
    assert "must not contain parent-directory traversal" in captured.err
