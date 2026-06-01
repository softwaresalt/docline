"""Tests for CLI and MCP output equivalence."""

import json

from docline.app import get_manifest
from docline.app_models import FetchRequest, FetchResult, ProcessRequest, ProcessResult
from docline.cli import main
from docline.mcp.server import SERVER


def test_fetch_equivalent_via_cli_and_mcp(capsys) -> None:
    """CLI and MCP fetch surfaces return identical results."""
    request = FetchRequest(source="http://example.com")

    main(["fetch", "http://example.com"])
    cli_result = FetchResult(**json.loads(capsys.readouterr().out))

    assert cli_result == SERVER.fetch(request)


def test_process_equivalent_via_cli_and_mcp(capsys, monkeypatch, tmp_path) -> None:
    """CLI and MCP process surfaces return identical results."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    request = ProcessRequest(staging_dir="staging", output_dir="output")

    main(["process", "--staging-dir", "staging", "--output-dir", "output"])
    cli_result = ProcessResult(**json.loads(capsys.readouterr().out))

    assert cli_result == SERVER.process(request)


def test_fetch_staged_path_deterministic(capsys) -> None:
    """Fetch staged paths stay deterministic across interfaces."""
    request = FetchRequest(source="http://example.com")

    main(["fetch", "http://example.com"])
    cli_result = FetchResult(**json.loads(capsys.readouterr().out))
    mcp_result = SERVER.fetch(request)

    assert cli_result.staged_path == mcp_result.staged_path


def test_cli_and_mcp_fetch_source_preserved(capsys) -> None:
    """Both interfaces preserve the fetch source field."""
    request = FetchRequest(source="http://example.com")

    main(["fetch", "http://example.com"])
    cli_result = FetchResult(**json.loads(capsys.readouterr().out))

    assert cli_result.source == SERVER.fetch(request).source


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
    """CLI fetch JSON deserializes back into the FetchResult model."""
    main(["fetch", "http://example.com"])
    result = FetchResult(**json.loads(capsys.readouterr().out))

    assert result.success is False
    assert result.staged_path == ""


def test_cli_json_deserializes_to_process_result_model(capsys, monkeypatch, tmp_path) -> None:
    """CLI process JSON deserializes back into the ProcessResult model."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()

    main(["process", "--staging-dir", "staging"])
    result = ProcessResult(**json.loads(capsys.readouterr().out))

    assert result.success is False
    assert result.output_path is None


def test_manifest_tool_names_match_operation_names() -> None:
    """Manifest tool names match the CLI and MCP operation names."""
    manifest = get_manifest()

    assert [tool.name for tool in manifest.tools] == ["fetch", "process"]
