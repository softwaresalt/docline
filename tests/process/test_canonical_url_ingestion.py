"""End-to-end test: canonical_url stamping during local-dir ingestion (044.002-T)."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from docline.app import execute_process
from docline.app_models import ProcessRequest
from docline.fetch.models import SourceMetadata, StagingJob
from docline.fetch.staging import build_cache_path, make_job_id, sanitize_source

_PUBLISH_CONFIG = {
    "docsets_to_publish": [
        {"docset_name": "fabric", "build_source_folder": "docs", "url_path_prefix": "/fabric"},
    ]
}

_MD = "# Foo\n\nBody paragraph.\n"

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _stage(staging_dir: Path, files: dict[str, bytes]) -> None:
    job_id = make_job_id("local_file:docs/repo")
    cache_rel = build_cache_path(str(staging_dir.name), job_id)
    cache_abs = staging_dir.parent / cache_rel
    files_dir = cache_abs / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    for relpath, content in files.items():
        target = files_dir / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    metadata = SourceMetadata(
        source=sanitize_source("local_file:docs/repo"),
        fetch_timestamp=datetime.now(UTC),
    )
    job = StagingJob(job_id=job_id, metadata=metadata, cache_path=cache_rel, complete=True)
    (cache_abs / "metadata.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")


def _run(tmp_path: Path) -> Path:
    output_dir = tmp_path / "output"
    request = ProcessRequest(
        staging_dir=str((tmp_path / "staging").relative_to(tmp_path)),
        output_dir=str(output_dir.relative_to(tmp_path)),
    )
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = execute_process(request)
    finally:
        os.chdir(original_cwd)
    assert result.success is True, result.error
    return output_dir


def _docline_ns(md_path: Path) -> dict:
    match = _FRONTMATTER_RE.match(md_path.read_text(encoding="utf-8"))
    assert match is not None, f"no frontmatter in {md_path}"
    parsed = yaml.safe_load(match.group(1))
    ns = parsed.get("docline")
    return ns if isinstance(ns, dict) else {}


def test_canonical_url_stamped_when_publish_config_present(tmp_path: Path) -> None:
    _stage(
        tmp_path / "staging",
        {
            ".openpublishing.publish.config.json": json.dumps(_PUBLISH_CONFIG).encode("utf-8"),
            "docs/admin/foo.md": _MD.encode("utf-8"),
        },
    )
    output_dir = _run(tmp_path)
    emitted = sorted(output_dir.rglob("*.md"))
    assert emitted, "expected an emitted markdown file"
    assert _docline_ns(emitted[0]).get("canonical_url") == "/fabric/admin/foo"


def test_no_canonical_url_without_publish_config(tmp_path: Path) -> None:
    _stage(tmp_path / "staging", {"docs/admin/foo.md": _MD.encode("utf-8")})
    output_dir = _run(tmp_path)
    emitted = sorted(output_dir.rglob("*.md"))
    assert emitted, "expected an emitted markdown file"
    assert "canonical_url" not in _docline_ns(emitted[0])


def test_canonical_url_stamped_from_docfx_breadcrumb(tmp_path: Path) -> None:
    # Config WITHOUT url_path_prefix (the real MS Learn case); prefix comes from docfx.
    config = {"docsets_to_publish": [{"docset_name": "fabric", "build_source_folder": "docs"}]}
    docfx = {"build": {"globalMetadata": {"breadcrumb_path": "/fabric/breadcrumb/toc.json"}}}
    _stage(
        tmp_path / "staging",
        {
            ".openpublishing.publish.config.json": json.dumps(config).encode("utf-8"),
            "docs/docfx.json": json.dumps(docfx).encode("utf-8"),
            "docs/admin/foo.md": _MD.encode("utf-8"),
        },
    )
    output_dir = _run(tmp_path)
    emitted = sorted(output_dir.rglob("*.md"))
    assert emitted, "expected an emitted markdown file"
    assert _docline_ns(emitted[0]).get("canonical_url") == "/fabric/admin/foo"


def test_build_docfx_prefixes_rejects_traversal(tmp_path: Path) -> None:
    """A build_source_folder with '..' must not read a docfx.json outside files_dir."""
    from docline.app import _build_docfx_prefixes

    files_dir = tmp_path / "files"
    (files_dir / "docs").mkdir(parents=True)
    (files_dir / "docs" / "docfx.json").write_text(
        json.dumps(
            {"build": {"globalMetadata": {"breadcrumb_path": "/fabric/breadcrumb/toc.json"}}}
        ),
        encoding="utf-8",
    )
    cfg = {
        "docsets_to_publish": [
            {"build_source_folder": "docs"},
            {"build_source_folder": "../"},  # traversal attempt
        ]
    }
    prefixes = _build_docfx_prefixes(files_dir, cfg)
    assert prefixes == {"docs": "/fabric"}  # valid docset resolved; traversal skipped
