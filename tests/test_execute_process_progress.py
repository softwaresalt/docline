"""Progress-callback tests for :func:`docline.app.execute_process` (056.012-T).

The callback reports a **global cumulative** file count summed across all
completed jobs up front, so ``files_done`` is monotonic across job boundaries
and ``detail`` carries the job identity. The ``progress`` parameter is kept
outside :class:`ProcessRequest` so the MCP schema is unchanged.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from docline.app import execute_process
from docline.app_models import ProcessRequest
from docline.fetch.models import SourceMetadata, StagingJob
from docline.fetch.staging import build_cache_path, make_job_id, sanitize_source


def _write_staging_job(staging_root: Path, source_key: str, files: dict[str, bytes]) -> None:
    job_id = make_job_id(source_key)
    cache_rel = build_cache_path(staging_root.name, job_id)
    cache_abs = staging_root.parent / cache_rel
    files_dir = cache_abs / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        dest = files_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    job = StagingJob(
        job_id=job_id,
        metadata=SourceMetadata(
            source=sanitize_source(source_key), fetch_timestamp=datetime.now(UTC)
        ),
        cache_path=cache_rel,
        complete=True,
    )
    (cache_abs / "metadata.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")


def _html(title: str) -> bytes:
    return f"<html><body><h1>{title}</h1></body></html>".encode()


def test_progress_reports_global_cumulative_monotonic_count(tmp_path: Path) -> None:
    staging_dir = tmp_path / "staging"
    _write_staging_job(
        staging_dir,
        "web_crawl:https://example.com/docs",
        {"page.html": _html("Docs"), "extra.html": _html("Extra")},
    )
    _write_staging_job(
        staging_dir,
        "web_crawl:https://example.com/api",
        {"page.html": _html("API")},
    )

    calls: list[tuple[int, int | None, str]] = []
    request = ProcessRequest(
        staging_dir=str(staging_dir.relative_to(tmp_path)),
        output_dir=str((tmp_path / "output").relative_to(tmp_path)),
    )

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = execute_process(request, progress=lambda d, t, det: calls.append((d, t, det)))
    finally:
        os.chdir(original_cwd)

    assert result.success is True
    # 3 files total across both jobs → one callback per file.
    assert len(calls) == 3
    dones = [c[0] for c in calls]
    assert dones == [1, 2, 3]  # cumulative + monotonic across the job boundary
    assert all(total == 3 for _, total, _ in calls)  # global total, not per-job
    # detail carries job identity/phase.
    assert any(det.startswith("job 1/2:") for _, _, det in calls)
    assert any(det.startswith("job 2/2:") for _, _, det in calls)


def test_progress_is_not_a_process_request_field() -> None:
    # Keeping progress out of the Pydantic model preserves the MCP schema.
    assert "progress" not in ProcessRequest.model_fields


def test_progress_none_preserves_behavior(tmp_path: Path) -> None:
    staging_dir = tmp_path / "staging"
    _write_staging_job(
        staging_dir,
        "web_crawl:https://example.com/docs",
        {"page.html": _html("Docs")},
    )
    request = ProcessRequest(
        staging_dir=str(staging_dir.relative_to(tmp_path)),
        output_dir=str((tmp_path / "output").relative_to(tmp_path)),
    )

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = execute_process(request)  # no progress callback
    finally:
        os.chdir(original_cwd)

    assert result.success is True


def test_progress_fires_once_on_conversion_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging_dir = tmp_path / "staging"
    _write_staging_job(
        staging_dir, "web_crawl:https://example.com/docs", {"page.html": _html("Docs")}
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("conversion failed")

    monkeypatch.setattr("docline.app.build_output_document_parts", boom)
    calls: list[tuple[int, int | None, str]] = []
    request = ProcessRequest(
        staging_dir=str(staging_dir.relative_to(tmp_path)),
        output_dir=str((tmp_path / "output").relative_to(tmp_path)),
    )
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = execute_process(request, progress=lambda d, t, det: calls.append((d, t, det)))
    finally:
        os.chdir(original_cwd)

    assert result.success is False  # conversion failed
    assert calls == [(1, 1, "job 1/1: page.html")]  # still one callback for the attempted file


def test_progress_fires_once_on_openapi_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging_dir = tmp_path / "staging"
    _write_staging_job(
        staging_dir, "web_crawl:https://example.com/api", {"spec.json": b'{"openapi": "3.0.0"}'}
    )

    monkeypatch.setattr("docline.app._is_openapi_staged", lambda _p: True)
    monkeypatch.setattr(
        "docline.app._emit_openapi_documents",
        lambda *_a, **kwargs: (kwargs.get("start_ingest_order", 0), 0, []),
    )
    calls: list[tuple[int, int | None, str]] = []
    request = ProcessRequest(
        staging_dir=str(staging_dir.relative_to(tmp_path)),
        output_dir=str((tmp_path / "output").relative_to(tmp_path)),
    )
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        execute_process(request, progress=lambda d, t, det: calls.append((d, t, det)))
    finally:
        os.chdir(original_cwd)

    assert calls == [(1, 1, "job 1/1: spec.json")]  # openapi branch still reports one callback
