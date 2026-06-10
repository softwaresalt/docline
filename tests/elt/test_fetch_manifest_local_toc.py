"""Tests for TOC.yml-aware crawl-manifest emission in _fetch_manifest_local.

When the staged source contains DocFx-style TOC.yml files, the fetch path
MUST emit a `crawl-manifest.json` with the `pages` key in TOC-derived
order so the downstream process pipeline preserves authorial sequence
(graph parents before children, stable chunk IDs across re-runs).

Implements 025.003-T / T2 from docs/plans/2026-06-10-local-dir-ingest-plan.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docline.elt.execute import _fetch_manifest_local
from docline.elt.manifest_models import ManifestLocalSource


def _make_config(source_dir: Path) -> ManifestLocalSource:
    return ManifestLocalSource(
        type="local",
        id="test-source",
        path=str(source_dir),
        include=["**/*.md", "**/*.yml"],
    )


def _read_manifest(files_dir: Path) -> dict | None:
    """Return parsed crawl-manifest.json from the job dir, or None if absent."""
    manifest_path = files_dir.parent / "crawl-manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def test_toc_yml_ordering_applied_when_present(tmp_path: Path) -> None:
    """A TOC.yml referencing 3 of 5 files orders those 3 first."""
    src = tmp_path / "src"
    src.mkdir()
    # Create 5 .md files, one TOC.yml referencing 3 of them in non-alphabetical order
    (src / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (src / "beta.md").write_text("# Beta\n", encoding="utf-8")
    (src / "gamma.md").write_text("# Gamma\n", encoding="utf-8")
    (src / "delta.md").write_text("# Delta\n", encoding="utf-8")
    (src / "epsilon.md").write_text("# Epsilon\n", encoding="utf-8")
    (src / "TOC.yml").write_text(
        "- name: Gamma\n"
        "  href: gamma.md\n"
        "- name: Alpha\n"
        "  href: alpha.md\n"
        "- name: Delta\n"
        "  href: delta.md\n",
        encoding="utf-8",
    )

    files_dir = tmp_path / "stage" / "files"
    files_dir.mkdir(parents=True)
    _fetch_manifest_local(_make_config(src), tmp_path, files_dir)

    manifest = _read_manifest(files_dir)
    assert manifest is not None, "TOC.yml-aware path MUST emit crawl-manifest.json"
    pages = manifest["pages"]
    # First 3 entries must be in TOC order
    toc_paths = [p["path"] for p in pages[:3]]
    assert toc_paths == ["gamma.md", "alpha.md", "delta.md"], (
        f"first 3 entries should match TOC order; got {toc_paths}"
    )
    # All 3 should have toc_referenced=True
    for entry in pages[:3]:
        assert entry["toc_referenced"] is True
    # The remaining 2 are appended (alphabetically) with toc_referenced=False
    tail_paths = sorted(p["path"] for p in pages[3:] if p["path"].endswith(".md"))
    assert tail_paths == ["beta.md", "epsilon.md"]
    for entry in pages[3:]:
        if entry["path"].endswith(".md"):
            assert entry["toc_referenced"] is False


def test_no_toc_yml_alphabetical_fallback(tmp_path: Path) -> None:
    """With no TOC.yml present, fall back to alphabetical ordering."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "zeta.md").write_text("# Zeta\n", encoding="utf-8")
    (src / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (src / "mu.md").write_text("# Mu\n", encoding="utf-8")

    files_dir = tmp_path / "stage" / "files"
    files_dir.mkdir(parents=True)
    _fetch_manifest_local(_make_config(src), tmp_path, files_dir)

    manifest = _read_manifest(files_dir)
    assert manifest is not None
    md_paths = [p["path"] for p in manifest["pages"] if p["path"].endswith(".md")]
    assert md_paths == ["alpha.md", "mu.md", "zeta.md"]
    # All should have toc_referenced=False since no TOC.yml existed
    for entry in manifest["pages"]:
        assert entry["toc_referenced"] is False


def test_malformed_toc_yml_falls_back_alphabetically(tmp_path: Path) -> None:
    """A TOC.yml that fails to parse falls back to alphabetical ordering."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (src / "beta.md").write_text("# Beta\n", encoding="utf-8")
    (src / "TOC.yml").write_text("this: is: not: valid: yaml:::\n@@@\n", encoding="utf-8")

    files_dir = tmp_path / "stage" / "files"
    files_dir.mkdir(parents=True)
    _fetch_manifest_local(_make_config(src), tmp_path, files_dir)

    manifest = _read_manifest(files_dir)
    assert manifest is not None
    md_paths = [p["path"] for p in manifest["pages"] if p["path"].endswith(".md")]
    assert md_paths == ["alpha.md", "beta.md"]


def test_nested_subdir_tocs_merged(tmp_path: Path) -> None:
    """Multiple TOC.yml files at different depths get merged in subdir order."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "TOC.yml").write_text("- name: Root Intro\n  href: root-intro.md\n", encoding="utf-8")
    (src / "root-intro.md").write_text("# Root Intro\n", encoding="utf-8")
    (src / "guide").mkdir()
    (src / "guide" / "TOC.yml").write_text(
        "- name: Guide One\n  href: guide-one.md\n- name: Guide Two\n  href: guide-two.md\n",
        encoding="utf-8",
    )
    (src / "guide" / "guide-one.md").write_text("# Guide One\n", encoding="utf-8")
    (src / "guide" / "guide-two.md").write_text("# Guide Two\n", encoding="utf-8")

    files_dir = tmp_path / "stage" / "files"
    files_dir.mkdir(parents=True)
    _fetch_manifest_local(_make_config(src), tmp_path, files_dir)

    manifest = _read_manifest(files_dir)
    assert manifest is not None
    md_entries = [p for p in manifest["pages"] if p["path"].endswith(".md")]
    md_paths = [p["path"] for p in md_entries]
    # All 3 .md files referenced; root first then nested.
    assert "root-intro.md" in md_paths
    assert "guide/guide-one.md" in md_paths
    assert "guide/guide-two.md" in md_paths
    # All should be toc_referenced=True since each appears in a TOC.yml
    for entry in md_entries:
        assert entry["toc_referenced"] is True, f"{entry['path']} should be toc_referenced"


def test_manifest_has_pages_key_not_entries(tmp_path: Path) -> None:
    """docline.app._load_crawl_manifest requires key 'pages', NOT 'entries'."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.md").write_text("# Foo\n", encoding="utf-8")

    files_dir = tmp_path / "stage" / "files"
    files_dir.mkdir(parents=True)
    _fetch_manifest_local(_make_config(src), tmp_path, files_dir)

    manifest = _read_manifest(files_dir)
    assert manifest is not None
    assert "pages" in manifest, "manifest MUST use 'pages' key"
    assert "entries" not in manifest, "manifest MUST NOT use deprecated 'entries' key"


@pytest.mark.parametrize("required_field", ["path", "order", "crawl_order", "toc_referenced"])
def test_manifest_entries_have_required_fields(tmp_path: Path, required_field: str) -> None:
    """Each entry in pages[] MUST have path, order, crawl_order, toc_referenced."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.md").write_text("# Foo\n", encoding="utf-8")
    (src / "bar.md").write_text("# Bar\n", encoding="utf-8")

    files_dir = tmp_path / "stage" / "files"
    files_dir.mkdir(parents=True)
    _fetch_manifest_local(_make_config(src), tmp_path, files_dir)

    manifest = _read_manifest(files_dir)
    assert manifest is not None
    for entry in manifest["pages"]:
        assert required_field in entry, f"entry missing {required_field}: {entry}"
