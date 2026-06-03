"""Corpus-scan test asserting all emitted ``source_path`` values are POSIX.

This test exercises the assemble pipeline end-to-end with a staged DOCX whose
relative path contains a subdirectory (so the path includes at least one
separator), and verifies that the YAML frontmatter ``source_path`` field
contains the project-relative POSIX path of the source artifact with no
backslashes.

PA-2 (010-S F2.T3): every ``source_path`` emission must route through
``docline.paths.posixify_path`` so docline-emitted frontmatter uses
forward-slash POSIX paths regardless of the host OS.
"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from docline.app import execute_process
from docline.app_models import ProcessRequest
from docline.fetch.models import SourceMetadata, StagingJob
from docline.fetch.staging import build_cache_path, make_job_id, sanitize_source


def _make_minimal_docx() -> bytes:
    """Build a minimal valid DOCX with literal body text."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (
        '<?xml version="1.0"?>'
        f'<w:document xmlns:w="{ns}">'
        "<w:body><w:p><w:r>"
        "<w:t>Source path POSIX corpus body</w:t>"
        "</w:r></w:p></w:body>"
        "</w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", xml)
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
    return buf.getvalue()


def _stage_files_with_subdir(staging_dir: Path, source_key: str, files: dict[str, bytes]) -> None:
    """Stage one or more files at relative paths that include subdirectories."""
    job_id = make_job_id(source_key)
    cache_rel = build_cache_path(str(staging_dir.name), job_id)
    cache_abs = staging_dir.parent / cache_rel
    files_dir = cache_abs / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    for relpath, content in files.items():
        target = files_dir / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    metadata = SourceMetadata(
        source=sanitize_source(source_key),
        fetch_timestamp=datetime.now(UTC),
    )
    job = StagingJob(
        job_id=job_id,
        metadata=metadata,
        cache_path=cache_rel,
        complete=True,
    )
    (cache_abs / "metadata.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _frontmatter_source_path(markdown_text: str) -> str | None:
    """Extract the ``source_path`` value from a YAML frontmatter block, if present."""
    match = _FRONTMATTER_RE.match(markdown_text)
    if not match:
        return None
    for line in match.group(1).splitlines():
        if line.startswith("source_path:"):
            _, _, value = line.partition(":")
            return json.loads(value.strip()) if value.strip().startswith('"') else value.strip()
    return None


def _all_emitted_markdown(output_dir: Path) -> Iterable[Path]:
    """Yield every emitted markdown file under the process output directory."""
    return sorted(output_dir.rglob("*.md"))


def test_emitted_source_path_uses_posix_forward_slashes(tmp_path: Path) -> None:
    """Every emitted ``source_path`` must be forward-slash POSIX with no backslashes."""
    staging_dir = tmp_path / "staging"
    _stage_files_with_subdir(
        staging_dir,
        "local_file:docs/sample.docx",
        {"subdir/nested/sample.docx": _make_minimal_docx()},
    )

    output_dir = tmp_path / "output"
    request = ProcessRequest(
        staging_dir=str(staging_dir.relative_to(tmp_path)),
        output_dir=str(output_dir.relative_to(tmp_path)),
    )

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = execute_process(request)
    finally:
        os.chdir(original_cwd)

    assert result.success is True, result.error

    emitted = list(_all_emitted_markdown(output_dir))
    assert emitted, "expected at least one emitted markdown file"

    saw_populated_source_path = False
    for md_path in emitted:
        text = md_path.read_text(encoding="utf-8")
        source_path = _frontmatter_source_path(text)
        assert source_path is not None, (
            f"emitted markdown {md_path} is missing a source_path frontmatter field"
        )
        assert "\\" not in source_path, (
            f"source_path in {md_path} contains a backslash: {source_path!r}"
        )
        if source_path:
            saw_populated_source_path = True

    assert saw_populated_source_path, (
        "expected at least one emitted document to populate source_path; "
        "found only empty strings, which means the assemble pipeline is not "
        "routing the staged relative path through posixify_path"
    )


def test_emitted_source_path_matches_posix_relative_input(tmp_path: Path) -> None:
    """``source_path`` must equal the staged relative input path in POSIX form."""
    staging_dir = tmp_path / "staging"
    relative_input = "deep/sub/folder/sample.docx"
    _stage_files_with_subdir(
        staging_dir,
        "local_file:docs/sample.docx",
        {relative_input: _make_minimal_docx()},
    )

    output_dir = tmp_path / "output"
    request = ProcessRequest(
        staging_dir=str(staging_dir.relative_to(tmp_path)),
        output_dir=str(output_dir.relative_to(tmp_path)),
    )

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = execute_process(request)
    finally:
        os.chdir(original_cwd)

    assert result.success is True, result.error

    emitted = list(_all_emitted_markdown(output_dir))
    assert emitted, "expected at least one emitted markdown file"

    md_path = emitted[0]
    text = md_path.read_text(encoding="utf-8")
    source_path = _frontmatter_source_path(text)

    assert source_path == relative_input, (
        f"expected source_path == {relative_input!r}, got {source_path!r}"
    )


@pytest.mark.parametrize(
    "relative_input",
    [
        "a/b/c/sample.docx",
        "WindowsLike/Sub/Dir/sample.docx",
        "single.docx",
    ],
)
def test_emitted_source_path_never_contains_backslash(tmp_path: Path, relative_input: str) -> None:
    """Across multiple staged inputs, ``source_path`` must never contain backslashes."""
    staging_dir = tmp_path / "staging"
    _stage_files_with_subdir(
        staging_dir,
        f"local_file:{relative_input}",
        {relative_input: _make_minimal_docx()},
    )

    output_dir = tmp_path / "output"
    request = ProcessRequest(
        staging_dir=str(staging_dir.relative_to(tmp_path)),
        output_dir=str(output_dir.relative_to(tmp_path)),
    )

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = execute_process(request)
    finally:
        os.chdir(original_cwd)

    assert result.success is True, result.error

    for md_path in _all_emitted_markdown(output_dir):
        text = md_path.read_text(encoding="utf-8")
        source_path = _frontmatter_source_path(text)
        assert source_path is not None
        assert "\\" not in source_path, (
            f"source_path in {md_path} contains a backslash: {source_path!r}"
        )
