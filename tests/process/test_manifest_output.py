"""Failing harness tests for contained Markdown output and manifest updates."""

import json
from pathlib import Path

import pytest

from docline.paths import PathContainmentError
from docline.process.manifest import update_manifest_index
from docline.process.output import write_markdown_output


def test_write_markdown_output_writes_under_the_configured_root(tmp_path: Path) -> None:
    output_path = write_markdown_output(
        tmp_path,
        "ingested/wiki/architecture-overview.md",
        "# Architecture Overview\n",
    )
    assert output_path == tmp_path / "ingested" / "wiki" / "architecture-overview.md"


def test_write_markdown_output_enforces_path_containment(tmp_path: Path) -> None:
    with pytest.raises(PathContainmentError):
        write_markdown_output(tmp_path, "ingested/../escape.md", "# Escaped\n")


def test_write_markdown_output_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(PathContainmentError):
        write_markdown_output(tmp_path, "..\\..\\outside.md", "# Escaped\n")


def test_update_manifest_index_writes_atomically(tmp_path: Path) -> None:
    manifest_path = update_manifest_index(
        tmp_path,
        "manifest.json",
        {"document_id": "doc-001", "output_path": "ingested/wiki/architecture-overview.md"},
    )
    assert manifest_path == tmp_path / "manifest.json"


def test_update_manifest_index_omits_relationship_data(tmp_path: Path) -> None:
    manifest_path = update_manifest_index(
        tmp_path,
        "manifest.json",
        {
            "document_id": "doc-001",
            "output_path": "ingested/wiki/architecture-overview.md",
            "relationships": [{"kind": "supersedes", "target": "doc-000"}],
        },
    )
    assert "relationships" not in manifest_path.read_text(encoding="utf-8")


def test_update_manifest_index_uses_an_ingestion_index_structure(tmp_path: Path) -> None:
    manifest_path = update_manifest_index(
        tmp_path,
        "manifest.json",
        {"document_id": "doc-001", "output_path": "ingested/wiki/architecture-overview.md"},
    )
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert list(manifest_data) == ["documents"]


def test_update_manifest_index_enforces_path_containment(tmp_path: Path) -> None:
    with pytest.raises(PathContainmentError):
        update_manifest_index(
            tmp_path,
            "..\\manifest.json",
            {"document_id": "doc-001", "output_path": "ingested/wiki/architecture-overview.md"},
        )
