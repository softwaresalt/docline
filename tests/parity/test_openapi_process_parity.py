"""Dual-interface parity for OpenAPI ingestion via CLI and MCP surfaces (050.006-T / T6).

Both ``docline process`` (CLI) and the MCP ``process`` tool delegate to
:func:`docline.app.execute_process`. These tests exercise both entry points on
the same staged OpenAPI spec and assert the emitted documents are identical
(ignoring the per-run ``ingested_at`` timestamp), and that a spec is ingested
end-to-end into per-operation / per-schema Markdown.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from docline.app import execute_process
from docline.app_models import ProcessRequest
from docline.fetch.models import SourceMetadata, StagingJob
from docline.fetch.staging import build_cache_path, make_job_id, sanitize_source
from docline.mcp.server import DoclineMcpServer

_SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "Widget API", "version": "1.0.0"},
    "paths": {
        "/widgets/{id}": {
            "get": {
                "operationId": "getWidget",
                "summary": "Get a widget",
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Widget"}}
                        },
                    }
                },
            }
        }
    },
    "components": {
        "schemas": {"Widget": {"type": "object", "properties": {"id": {"type": "string"}}}}
    },
}
_SPEC_BYTES = json.dumps(_SPEC).encode("utf-8")


def _write_staging_job(root: Path, source_key: str, files: dict[str, bytes]) -> StagingJob:
    """Write a completed staging job with the supplied files on disk."""
    staging_dir = root / "staging"
    job_id = make_job_id(source_key)
    cache_rel = build_cache_path(staging_dir.name, job_id)
    cache_abs = staging_dir.parent / cache_rel
    files_dir = cache_abs / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        dest = files_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    metadata = SourceMetadata(source=sanitize_source(source_key), fetch_timestamp=datetime.now(UTC))
    job = StagingJob(job_id=job_id, metadata=metadata, cache_path=cache_rel, complete=True)
    (cache_abs / "metadata.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return job


def _collect_markdown(job_root: Path) -> dict[str, str]:
    """Return {relative_posix_path: content-without-ingested_at} for emitted docs."""
    outputs: dict[str, str] = {}
    for md_path in sorted(job_root.rglob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        stable = "\n".join(
            line for line in text.splitlines() if not line.startswith("ingested_at:")
        )
        outputs[md_path.relative_to(job_root).as_posix()] = stable
    return outputs


def test_cli_process_ingests_openapi_spec(tmp_path: Path) -> None:
    """docline process (execute_process) ingests a spec into per-operation/schema docs."""
    workspace = tmp_path / "cli"
    job = _write_staging_job(workspace, "widget-svc", {"api.json": _SPEC_BYTES})

    result = execute_process(
        ProcessRequest(workspace_root=str(workspace), staging_dir="staging", output_dir="output")
    )
    assert result.success is True, result.error

    job_root = workspace / "output" / job.job_id
    produced = {p.relative_to(job_root).as_posix() for p in job_root.rglob("*.md")}
    assert produced == {"api/operations/getWidget.md", "api/schemas/Widget.md"}

    operation = (job_root / "api/operations/getWidget.md").read_text(encoding="utf-8")
    assert 'doc_type: "openapi_operation"' in operation
    assert "# GET /widgets/{id}" in operation
    assert "[Widget](../schemas/Widget.md)" in operation


def test_cli_and_mcp_produce_identical_output(tmp_path: Path) -> None:
    """The CLI and MCP surfaces emit identical documents for the same spec."""
    cli_ws = tmp_path / "cli"
    cli_job = _write_staging_job(cli_ws, "widget-svc", {"api.json": _SPEC_BYTES})
    cli_result = execute_process(
        ProcessRequest(workspace_root=str(cli_ws), staging_dir="staging", output_dir="output")
    )
    assert cli_result.success is True, cli_result.error

    mcp_ws = tmp_path / "mcp"
    mcp_job = _write_staging_job(mcp_ws, "widget-svc", {"api.json": _SPEC_BYTES})
    mcp_result = DoclineMcpServer().process(
        {"workspace_root": str(mcp_ws), "staging_dir": "staging", "output_dir": "output"}
    )
    assert mcp_result.success is True, mcp_result.error

    cli_outputs = _collect_markdown(cli_ws / "output" / cli_job.job_id)
    mcp_outputs = _collect_markdown(mcp_ws / "output" / mcp_job.job_id)
    assert cli_outputs == mcp_outputs
    assert set(cli_outputs) == {"api/operations/getWidget.md", "api/schemas/Widget.md"}


def test_config_json_is_not_ingested_as_openapi(tmp_path: Path) -> None:
    """A plain config .json staged alongside is not misclassified as a spec."""
    workspace = tmp_path / "cfg"
    config = json.dumps({"build": {"content": []}, "docsets_to_publish": []}).encode("utf-8")
    job = _write_staging_job(workspace, "cfg-svc", {"docfx.json": config})

    execute_process(
        ProcessRequest(workspace_root=str(workspace), staging_dir="staging", output_dir="output")
    )
    # No supported inputs → process reports no outputs; crucially, no OpenAPI docs.
    job_root = workspace / "output" / job.job_id
    produced = list(job_root.rglob("*.md")) if job_root.exists() else []
    assert produced == []


def test_swagger_2_spec_is_not_ingested(tmp_path: Path) -> None:
    """A staged Swagger 2.0 spec is detected but NOT rendered (v1 is 3.x only)."""
    workspace = tmp_path / "v2"
    swagger = json.dumps(
        {
            "swagger": "2.0",
            "info": {"title": "Legacy", "version": "1.0"},
            "paths": {"/ping": {"get": {"responses": {"200": {"description": "OK"}}}}},
            "definitions": {"Widget": {"type": "object"}},
        }
    ).encode("utf-8")
    job = _write_staging_job(workspace, "legacy-svc", {"api.json": swagger})

    execute_process(
        ProcessRequest(workspace_root=str(workspace), staging_dir="staging", output_dir="output")
    )
    job_root = workspace / "output" / job.job_id
    produced = list(job_root.rglob("*.md")) if job_root.exists() else []
    assert produced == []
