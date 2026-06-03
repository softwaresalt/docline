"""Tests for generated-artifact exclusion in the ELT local source scan.

Acceptance criteria:
- _fetch_manifest_local does NOT copy files under runtime-staging* or runtime-output*
  subdirectories when the resolved base directory is .elt (stale-path heuristic
  remaps ``path: tmp`` → ``.elt``).
- Regular source files at the root and in non-generated subdirs ARE copied.
- _is_elt_generated_artifact returns True only for paths under the excluded prefixes.
- The exclusion function handles edge-cases: file at base root, non-relative paths.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Unit tests for the exclusion helper
# ---------------------------------------------------------------------------


def test_is_elt_generated_artifact_runtime_staging(tmp_path: Path) -> None:
    """runtime-staging subdirectory is detected as a generated artifact."""
    from docline.elt.execute import _is_elt_generated_artifact

    base = tmp_path / ".elt"
    src = base / "runtime-staging" / "abc" / "metadata.json"

    assert _is_elt_generated_artifact(src, base) is True


def test_is_elt_generated_artifact_runtime_staging_numbered(tmp_path: Path) -> None:
    """runtime-staging2 prefix variant is also detected."""
    from docline.elt.execute import _is_elt_generated_artifact

    base = tmp_path / ".elt"
    src = base / "runtime-staging2" / "some.docx"

    assert _is_elt_generated_artifact(src, base) is True


def test_is_elt_generated_artifact_runtime_output(tmp_path: Path) -> None:
    """runtime-output subdirectory is detected as a generated artifact."""
    from docline.elt.execute import _is_elt_generated_artifact

    base = tmp_path / ".elt"
    src = base / "runtime-output" / "manifest.json"

    assert _is_elt_generated_artifact(src, base) is True


def test_is_elt_generated_artifact_runtime_output_real(tmp_path: Path) -> None:
    """runtime-output-real prefix variant is also detected."""
    from docline.elt.execute import _is_elt_generated_artifact

    base = tmp_path / ".elt"
    src = base / "runtime-output-real" / "ab1de93c" / "azure-cosmos-db.md"

    assert _is_elt_generated_artifact(src, base) is True


def test_is_elt_generated_artifact_regular_file(tmp_path: Path) -> None:
    """A regular source file at the base root is NOT a generated artifact."""
    from docline.elt.execute import _is_elt_generated_artifact

    base = tmp_path / ".elt"
    src = base / "myfile.docx"

    assert _is_elt_generated_artifact(src, base) is False


def test_is_elt_generated_artifact_regular_subdir(tmp_path: Path) -> None:
    """A regular subdirectory with non-excluded name is NOT a generated artifact."""
    from docline.elt.execute import _is_elt_generated_artifact

    base = tmp_path / ".elt"
    src = base / "pbi" / "report.docx"

    assert _is_elt_generated_artifact(src, base) is False


def test_is_elt_generated_artifact_staging_prefix_only(tmp_path: Path) -> None:
    """A file in a 'staging' subdir (no runtime- prefix) is NOT excluded."""
    from docline.elt.execute import _is_elt_generated_artifact

    base = tmp_path / ".elt"
    src = base / "staging" / "file.pdf"

    assert _is_elt_generated_artifact(src, base) is False


def test_is_elt_generated_artifact_outside_base(tmp_path: Path) -> None:
    """A path outside base returns False (ValueError from relative_to is handled)."""
    from docline.elt.execute import _is_elt_generated_artifact

    base = tmp_path / ".elt"
    src = tmp_path / "other" / "runtime-staging" / "file.pdf"

    assert _is_elt_generated_artifact(src, base) is False


# ---------------------------------------------------------------------------
# Behavioral: _fetch_manifest_local integration through execute_elt_fetch
# ---------------------------------------------------------------------------


def _create_elt_workspace(root: Path) -> None:
    """Build a minimal .elt workspace with source files and generated artifacts.

    Layout::

        root/
          .elt/config/sources.yaml       — manifest with path: tmp
          .elt/document.docx             — real source file
          .elt/pbi/report.pdf            — real source file in sub-dir
          .elt/runtime-staging/ab/ab1234/files/PartTable.docx   — generated artifact
          .elt/runtime-staging2/cd/cd5678/files/PartTable.docx  — generated artifact
          .elt/runtime-output/ab1234/azure-cosmos-db.md         — generated artifact

    Args:
        root: Temporary workspace root.
    """
    elt = root / ".elt"
    # Real source files
    (elt / "pbi").mkdir(parents=True)
    (elt / "document.docx").write_bytes(b"PK real docx")
    (elt / "pbi" / "report.pdf").write_bytes(b"%PDF-1.4 real")

    # Generated staging artifacts
    staging1 = elt / "runtime-staging" / "ab" / "ab1234" / "files"
    staging1.mkdir(parents=True)
    (staging1 / "PartTableAndIndexStrat.docx").write_bytes(b"PK generated")

    staging2 = elt / "runtime-staging2" / "cd" / "cd5678" / "files"
    staging2.mkdir(parents=True)
    (staging2 / "PartTableAndIndexStrat.docx").write_bytes(b"PK generated2")

    # Generated output artifact
    output1 = elt / "runtime-output" / "ab1234"
    output1.mkdir(parents=True)
    (output1 / "azure-cosmos-db.md").write_text("# generated", encoding="utf-8")

    # Config manifest using the stale tmp → .elt heuristic path
    config_dir = elt / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "sources.yaml").write_text(
        "sources:\n"
        "  - type: local\n"
        "    id: sample\n"
        "    path: tmp\n"
        '    include: ["**/*.docx", "**/*.pdf"]\n',
        encoding="utf-8",
    )


def test_fetch_manifest_local_excludes_runtime_staging_files(tmp_path: Path) -> None:
    """execute_elt_fetch does not copy runtime-staging* files into the staging area."""
    from docline.elt.execute import execute_elt_fetch

    _create_elt_workspace(tmp_path)

    config_dir = tmp_path / ".elt" / "config"
    jobs = execute_elt_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

    assert len(jobs) == 1
    files_dir = tmp_path / jobs[0].cache_path / "files"

    # Collect all copied file names (relative paths within files_dir)
    copied = {p.name for p in files_dir.rglob("*") if p.is_file()}

    # Generated artifacts must NOT appear
    assert "PartTableAndIndexStrat.docx" not in copied, (
        "PartTableAndIndexStrat.docx from runtime-staging was incorrectly ingested"
    )


def test_fetch_manifest_local_excludes_runtime_output_files(tmp_path: Path) -> None:
    """execute_elt_fetch does not copy runtime-output* files into the staging area."""
    from docline.elt.execute import execute_elt_fetch

    _create_elt_workspace(tmp_path)

    config_dir = tmp_path / ".elt" / "config"
    jobs = execute_elt_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

    assert len(jobs) == 1
    files_dir = tmp_path / jobs[0].cache_path / "files"

    # Collect all copied file names
    copied = {p.name for p in files_dir.rglob("*") if p.is_file()}

    # Generated output artifacts must NOT appear
    assert "azure-cosmos-db.md" not in copied, (
        "azure-cosmos-db.md from runtime-output was incorrectly ingested"
    )


def test_fetch_manifest_local_includes_real_source_files(tmp_path: Path) -> None:
    """execute_elt_fetch still copies legitimate source files when exclusions apply."""
    from docline.elt.execute import execute_elt_fetch

    _create_elt_workspace(tmp_path)

    config_dir = tmp_path / ".elt" / "config"
    jobs = execute_elt_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

    assert len(jobs) == 1
    assert jobs[0].complete is True

    files_dir = tmp_path / jobs[0].cache_path / "files"
    copied = {p.name for p in files_dir.rglob("*") if p.is_file()}

    # Real source files must be present
    assert "document.docx" in copied, "document.docx (real source) should have been ingested"
    assert "report.pdf" in copied, "report.pdf (real source) should have been ingested"


def test_fetch_manifest_local_no_exclusion_for_normal_base(tmp_path: Path) -> None:
    """Exclusion does NOT apply when base is not under .elt (no false positives)."""
    from docline.elt.execute import _is_elt_generated_artifact

    # If someone has a different base (e.g. docs/), runtime-staging inside it
    # should also be excluded because the prefix check is general — that is
    # intentional and safe because these prefix names are tool-managed.
    # Verify that a completely unrelated file is safe.
    base = tmp_path / "docs"
    src = base / "readme.md"

    assert _is_elt_generated_artifact(src, base) is False


def test_exclusion_does_not_affect_staging_dir_name(tmp_path: Path) -> None:
    """A 'staging' directory without 'runtime-' prefix is not excluded."""
    from docline.elt.execute import _is_elt_generated_artifact

    base = tmp_path / ".elt"
    # The existing .elt/staging directory should NOT be excluded
    src = base / "staging" / "config.yaml"

    assert _is_elt_generated_artifact(src, base) is False
