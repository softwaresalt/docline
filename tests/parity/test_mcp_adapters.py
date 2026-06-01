"""Tests for MCP fetch and process adapters."""

from docline.app import execute_fetch
from docline.app_models import FetchRequest, FetchResult, ProcessRequest, ProcessResult
from docline.mcp.server import SERVER


def test_mcp_server_fetch_returns_fetch_result() -> None:
    """MCP fetch returns the shared fetch result model."""
    result = SERVER.fetch(FetchRequest(source="http://example.com"))
    assert isinstance(result, FetchResult)


def test_mcp_server_fetch_result_success() -> None:
    """MCP fetch succeeds for a valid source."""
    result = SERVER.fetch(FetchRequest(source="http://example.com"))
    assert result.success is True


def test_mcp_server_fetch_result_has_source() -> None:
    """MCP fetch preserves the source field."""
    result = SERVER.fetch(FetchRequest(source="http://example.com"))
    assert result.source == "http://example.com"


def test_mcp_server_fetch_result_has_staged_path() -> None:
    """MCP fetch returns a non-empty staged path."""
    result = SERVER.fetch(FetchRequest(source="http://example.com"))
    assert result.staged_path != ""


def test_mcp_server_process_returns_process_result() -> None:
    """MCP process returns the shared process result model."""
    result = SERVER.process(ProcessRequest())
    assert isinstance(result, ProcessResult)


def test_mcp_server_process_missing_staging_dir_fails() -> None:
    """MCP process fails when the default staging directory is missing."""
    result = SERVER.process(ProcessRequest())
    assert result.success is False


def test_mcp_server_process_with_existing_dir_succeeds(monkeypatch, tmp_path) -> None:
    """MCP process succeeds when the staging directory exists."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()

    result = SERVER.process(ProcessRequest(staging_dir="staging"))
    assert result.success is True


def test_mcp_server_fetch_process_same_contracts_as_app() -> None:
    """MCP fetch returns the same contract as the shared app layer."""
    request = FetchRequest(source="http://example.com")
    assert SERVER.fetch(request) == execute_fetch(request)
