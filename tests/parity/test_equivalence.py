"""Tests for CLI, app, and MCP output equivalence."""

import json

from docline.app import get_manifest
from docline.app_models import FetchRequest, FetchResult, ProcessRequest, ProcessResult
from docline.cli import main
from docline.elt.orchestrate import orchestrate_fetch
from docline.mcp.server import SERVER


def test_fetch_equivalent_via_cli_and_orchestrator(capsys, monkeypatch, tmp_path) -> None:
    """CLI fetch matches the orchestrator output for the same configs."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".elt" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "source.yaml").write_text(
        "type: web_crawl\nurl: https://example.com\n",
        encoding="utf-8",
    )

    main(["fetch"])
    cli_result = json.loads(capsys.readouterr().out)
    expected = [
        job.model_dump(mode="json") for job in orchestrate_fetch(config_dir, ".elt/staging")
    ]

    assert [job["job_id"] for job in cli_result] == [job["job_id"] for job in expected]
    assert [job["cache_path"] for job in cli_result] == [job["cache_path"] for job in expected]
    assert [job["metadata"]["source"] for job in cli_result] == [
        job["metadata"]["source"] for job in expected
    ]


def test_process_equivalent_via_cli_and_mcp(capsys, monkeypatch, tmp_path) -> None:
    """CLI and MCP process surfaces return identical results."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    request = ProcessRequest(staging_dir="staging", output_dir="output")

    main(["process", "--staging-dir", "staging", "--output-dir", "output"])
    cli_result = ProcessResult(**json.loads(capsys.readouterr().out))

    assert cli_result == SERVER.process(request)


def test_fetch_job_id_deterministic_between_cli_and_orchestrator(
    capsys, monkeypatch, tmp_path
) -> None:
    """CLI fetch job identifiers match the orchestrator deterministically."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".elt" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "source.yaml").write_text(
        "type: web_crawl\nurl: https://example.com\n",
        encoding="utf-8",
    )

    main(["fetch"])
    cli_result = json.loads(capsys.readouterr().out)
    expected = orchestrate_fetch(config_dir, ".elt/staging")

    assert cli_result[0]["job_id"] == expected[0].job_id


def test_cli_fetch_metadata_source_preserved(capsys, monkeypatch, tmp_path) -> None:
    """CLI fetch preserves the staged source metadata."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".elt" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "source.yaml").write_text(
        "type: web_crawl\nurl: https://example.com\n",
        encoding="utf-8",
    )

    main(["fetch"])
    cli_result = json.loads(capsys.readouterr().out)

    assert cli_result[0]["metadata"]["source"] == "web_crawl:https://example.com"


def test_cli_and_mcp_process_input_path_preserved(capsys, monkeypatch, tmp_path) -> None:
    """Both interfaces preserve the process input path field."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    request = ProcessRequest(staging_dir="staging", output_dir="output")

    main(["process", "--staging-dir", "staging", "--output-dir", "output"])
    cli_result = ProcessResult(**json.loads(capsys.readouterr().out))

    assert cli_result.input_path == SERVER.process(request).input_path


def test_fetch_result_model_fields_complete() -> None:
    """FetchResult exposes the full expected field set."""
    assert set(FetchResult.model_fields) == {"source", "staged_path", "success", "error"}


def test_process_result_model_fields_complete() -> None:
    """ProcessResult exposes the full expected field set."""
    assert set(ProcessResult.model_fields) == {"input_path", "output_path", "success", "error"}


def test_cli_json_deserializes_to_fetch_result_model(capsys) -> None:
    """MCP fetch JSON model remains stable for fetch results."""
    result = FetchResult(**SERVER.fetch(FetchRequest(source="http://example.com")).model_dump())

    assert result.success is False
    assert result.staged_path == ""


def test_cli_json_deserializes_to_process_result_model(capsys, monkeypatch, tmp_path) -> None:
    """CLI process JSON deserializes back into the ProcessResult model."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()

    main(["process", "--staging-dir", "staging"])
    result = ProcessResult(**json.loads(capsys.readouterr().out))

    assert result.success is True
    assert result.output_path == "output"


def test_manifest_tool_names_match_operation_names() -> None:
    """Manifest tool names match the CLI and MCP operation names."""
    manifest = get_manifest()

    assert [tool.name for tool in manifest.tools] == ["fetch", "process"]
