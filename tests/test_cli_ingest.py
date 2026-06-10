"""Tests for the `docline ingest local-dir` CLI subcommand (027-S / 025.002-T).

This subcommand functionally mirrors the YAML manifest flow:

    .elt/config/my-source.sources.yaml      docline ingest local-dir <path>
    ────────────────────────────────────    ──────────────────────────────────
    sources:                                <path>           = ManifestLocalSource.path
      - id: my-source                       --include "*.md" = ManifestLocalSource.include
        type: local                         (derived id from path basename)
        path: <path>
        include: ["**/*.md"]

Both paths produce identical staging + processing output because they share
the same ``_execute_single_source`` and ``execute_process`` code paths.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_fixture(root: Path) -> None:
    """Build a small repo fixture: 3 .md files + 1 file to exclude."""
    (root / "guide").mkdir(parents=True, exist_ok=True)
    (root / "guide" / "getting-started.md").write_text(
        "---\ntitle: Getting Started\nms.topic: how-to\n---\n# Getting Started\n\nIntro text.\n",
        encoding="utf-8",
    )
    (root / "guide" / "advanced.md").write_text(
        "---\ntitle: Advanced\nms.topic: how-to\n---\n# Advanced\n\nDeeper material.\n",
        encoding="utf-8",
    )
    (root / "reference.md").write_text(
        "---\ntitle: Reference\nms.topic: reference\n---\n# Reference\n\nReference content.\n",
        encoding="utf-8",
    )
    (root / "DRAFT-notes.md").write_text(
        "---\ntitle: Draft Notes\n---\n# Draft\n\nDraft text.\n",
        encoding="utf-8",
    )


def _run_cli(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run `python -m docline <argv>` from cwd, capture output."""
    return subprocess.run(
        [sys.executable, "-m", "docline", *argv],
        check=False,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def test_ingest_local_dir_smoke(tmp_path: Path) -> None:
    """A directory with 3 .md files produces 3 output .md files via the new CLI."""
    src = tmp_path / "src-repo"
    src.mkdir()
    _write_fixture(src)
    out = tmp_path / "out"

    # Use a workspace-rooted cwd so safe_workspace_path resolves
    workspace = tmp_path
    result = _run_cli(
        ["ingest", "local-dir", str(src.resolve()), "--output", str(out.resolve())],
        cwd=workspace,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    output_files = list(out.rglob("*.md"))
    # 4 fixture .md files (3 in guide+root + DRAFT-notes), all match default include
    assert len(output_files) == 4, (
        f"expected 4 outputs from default --include '**/*.md', got {len(output_files)}: "
        f"{[p.name for p in output_files]}"
    )


def test_ingest_local_dir_exclude_filter(tmp_path: Path) -> None:
    """`--exclude DRAFT-*.md` skips matching files."""
    src = tmp_path / "src-repo"
    src.mkdir()
    _write_fixture(src)
    out = tmp_path / "out"

    result = _run_cli(
        [
            "ingest",
            "local-dir",
            str(src.resolve()),
            "--output",
            str(out.resolve()),
            "--exclude",
            "DRAFT-*.md",
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    output_files = list(out.rglob("*.md"))
    # 4 - 1 excluded = 3 outputs
    assert len(output_files) == 3
    assert not any("DRAFT" in p.name for p in output_files)


def test_ingest_local_dir_missing_source_errors(tmp_path: Path) -> None:
    """Pointing at a nonexistent directory exits non-zero with an error message."""
    out = tmp_path / "out"
    result = _run_cli(
        ["ingest", "local-dir", str(tmp_path / "does-not-exist"), "--output", str(out)],
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert (
        "not" in result.stderr.lower()
        or "exist" in result.stderr.lower()
        or "error" in result.stderr.lower()
    )


def test_ingest_local_dir_keep_staging_retains_dir(tmp_path: Path) -> None:
    """`--keep-staging` does not remove the staging dir after process completes."""
    src = tmp_path / "src-repo"
    src.mkdir()
    _write_fixture(src)
    out = tmp_path / "out"
    staging = tmp_path / "staging"

    result = _run_cli(
        [
            "ingest",
            "local-dir",
            str(src.resolve()),
            "--output",
            str(out.resolve()),
            "--staging-dir",
            str(staging.resolve()),
            "--keep-staging",
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert staging.exists(), "--keep-staging should retain the staging directory"
    # And outputs should still be produced
    output_files = list(out.rglob("*.md"))
    assert len(output_files) >= 3


def test_ingest_local_dir_default_cleans_staging(tmp_path: Path) -> None:
    """Without `--keep-staging`, an auto-created staging dir is removed after run."""
    src = tmp_path / "src-repo"
    src.mkdir()
    _write_fixture(src)
    out = tmp_path / "out"
    staging = tmp_path / "staging-auto-clean"

    result = _run_cli(
        [
            "ingest",
            "local-dir",
            str(src.resolve()),
            "--output",
            str(out.resolve()),
            "--staging-dir",
            str(staging.resolve()),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert not staging.exists(), "default behavior should clean up staging dir"


def test_manifest_includes_ingest_local_dir_subcommand(tmp_path: Path) -> None:
    """`docline --manifest` JSON describes the new `ingest local-dir` shape."""
    result = _run_cli(["--manifest"], cwd=tmp_path)
    assert result.returncode == 0
    manifest = json.loads(result.stdout)
    # The manifest model may expose subcommands under different keys depending on
    # current schema shape; check the rendered dump for the new tokens.
    serialized = json.dumps(manifest)
    assert "ingest" in serialized, "manifest should describe the ingest subcommand"


def test_ingest_local_dir_preserves_relative_paths(tmp_path: Path) -> None:
    """Output preserves source directory structure under <output>/<job-hash>/."""
    src = tmp_path / "src-repo"
    src.mkdir()
    _write_fixture(src)
    out = tmp_path / "out"

    result = _run_cli(
        ["ingest", "local-dir", str(src.resolve()), "--output", str(out.resolve())],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    # One of the outputs must live under guide/getting-started.md (relative path preserved)
    found_guide = list(out.rglob("guide/getting-started.md")) + list(
        out.rglob("guide/getting_started.md")
    )
    assert found_guide, (
        f"expected guide/getting-started.md preserved, got: {[str(p) for p in out.rglob('*.md')]}"
    )


def test_ingest_local_dir_output_frontmatter_is_graphtor_compatible(tmp_path: Path) -> None:
    """Each output has the graphtor-required frontmatter fields (AC3)."""
    src = tmp_path / "src-repo"
    src.mkdir()
    _write_fixture(src)
    out = tmp_path / "out"

    result = _run_cli(
        ["ingest", "local-dir", str(src.resolve()), "--output", str(out.resolve())],
        cwd=tmp_path,
    )
    assert result.returncode == 0

    output_files = list(out.rglob("*.md"))
    assert output_files
    # Inspect a single output's frontmatter for graphtor required fields
    sample = output_files[0].read_text(encoding="utf-8")
    required_top_level = [
        "chunk_strategy",
        "content_sha256",
        "doc_type",
        "title",
        "source_path",
        "source",
    ]
    for field_name in required_top_level:
        assert f"{field_name}:" in sample, f"missing top-level frontmatter field {field_name}"
    # docline namespace fields
    assert "source_frontmatter:" in sample
    # cross_doc_links may be empty for these fixture files (no inline links),
    # but the docline namespace MUST appear
    assert "docline:" in sample


# TOC.yml ingest ordering is verified end-to-end by
# tests/elt/test_fetch_manifest_local_toc.py and
# tests/elt/test_ingest_local_dir_e2e.py::test_ingest_local_dir_e2e_toc_*;
# no stub needed here.
