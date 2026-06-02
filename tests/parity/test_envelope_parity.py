"""Tests for result envelope parity across app, CLI, and MCP surfaces."""

import json

from docline.app import execute_fetch, get_manifest, get_mcp_manifest
from docline.app_models import FetchRequest, FetchResult, ProcessResult
from docline.cli import main
from docline.elt.orchestrate import orchestrate_fetch
from docline.mcp.server import SERVER


def test_cli_fetch_outputs_staging_job_contract(capsys, monkeypatch, tmp_path) -> None:
    """CLI fetch outputs serialized staging job records."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".elt" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "source.yaml").write_text(
        "type: web_crawl\nurl: https://example.com\n",
        encoding="utf-8",
    )

    main(["fetch"])
    payload = json.loads(capsys.readouterr().out)

    assert set(payload[0]) == {"job_id", "metadata", "cache_path", "complete"}


def test_cli_process_success_envelope_has_required_fields(capsys, monkeypatch, tmp_path) -> None:
    """CLI process success output contains the process result contract fields."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()

    main(["process", "--staging-dir", "staging"])
    payload = json.loads(capsys.readouterr().out)

    assert set(payload) == {"input_path", "output_path", "success", "error"}


def test_fetch_result_success_envelope() -> None:
    """FetchResult success envelopes carry the expected field values."""
    result = FetchResult(
        source="http://example.com",
        staged_path=".cache/staging/ab/job",
        success=True,
    )

    assert result.success is True
    assert result.source == "http://example.com"
    assert result.staged_path == ".cache/staging/ab/job"
    assert result.error is None


def test_fetch_result_error_envelope() -> None:
    """FetchResult error envelopes include an error message."""
    result = FetchResult(
        source="http://example.com",
        staged_path="",
        success=False,
        error="boom",
    )

    assert result.success is False
    assert result.error == "boom"


def test_process_result_success_envelope() -> None:
    """ProcessResult success envelopes carry the expected field values."""
    result = ProcessResult(input_path="staging", output_path="output", success=True)

    assert result.success is True
    assert result.input_path == "staging"
    assert result.output_path == "output"
    assert result.error is None


def test_process_result_error_envelope() -> None:
    """ProcessResult error envelopes include an error message."""
    result = ProcessResult(input_path="staging", success=False, error="missing")

    assert result.success is False
    assert result.error == "missing"


def test_cli_fetch_output_matches_orchestrator(capsys, monkeypatch, tmp_path) -> None:
    """CLI fetch output matches the ELT orchestrator job payload."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".elt" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "source.yaml").write_text(
        "type: web_crawl\nurl: https://example.com\n",
        encoding="utf-8",
    )

    main(["fetch"])
    cli_payload = json.loads(capsys.readouterr().out)

    expected = [
        job.model_dump(mode="json") for job in orchestrate_fetch(config_dir, ".elt/staging")
    ]

    assert [job["job_id"] for job in cli_payload] == [job["job_id"] for job in expected]
    assert [job["cache_path"] for job in cli_payload] == [job["cache_path"] for job in expected]
    assert [job["metadata"]["source"] for job in cli_payload] == [
        job["metadata"]["source"] for job in expected
    ]


def test_mcp_output_matches_app_layer_fetch_result() -> None:
    """MCP fetch output matches the shared app-layer fetch result model."""
    request = FetchRequest(source="http://example.com")

    assert SERVER.fetch(request) == execute_fetch(request)


def test_mcp_fetch_output_matches_app_layer_fetch_result() -> None:
    """MCP fetch output still matches the shared app-layer fetch result model."""
    request = FetchRequest(source="http://example.com")

    assert SERVER.fetch(request) == execute_fetch(request)


def test_manifest_field_names_consistent() -> None:
    """CLI and MCP manifests use their expected schema field names."""
    cli_manifest = get_manifest().model_dump()
    mcp_manifest = get_mcp_manifest().model_dump(by_alias=True)

    assert "parameters" in cli_manifest["tools"][0]
    assert "inputSchema" in mcp_manifest["tools"][0]
