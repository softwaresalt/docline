"""Tests for MCP fetch and process adapters."""

import pytest

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


def test_mcp_server_fetch_accepts_raw_dict() -> None:
    """MCP fetch validates and accepts a raw dict payload at the transport boundary."""
    result = SERVER.fetch({"source": "http://example.com"})
    assert isinstance(result, FetchResult)
    assert result.success is True


def test_mcp_server_fetch_dict_source_preserved() -> None:
    """MCP fetch from raw dict preserves the source field."""
    result = SERVER.fetch({"source": "http://example.com"})
    assert result.source == "http://example.com"


def test_mcp_server_fetch_invalid_dict_raises_validation_error() -> None:
    """MCP fetch rejects an empty-source raw dict with a validation error."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SERVER.fetch({"source": ""})


def test_mcp_server_process_accepts_raw_dict(monkeypatch, tmp_path) -> None:
    """MCP process validates and accepts a raw dict payload at the transport boundary."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()

    result = SERVER.process({"staging_dir": "staging", "output_dir": "output"})
    assert isinstance(result, ProcessResult)
    assert result.success is True


def test_mcp_server_process_invalid_dict_raises_validation_error() -> None:
    """MCP process rejects a traversal path in raw dict payload."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SERVER.process({"staging_dir": "../escape"})


def test_mcp_server_process_file_path_not_dir_fails(tmp_path) -> None:
    """MCP process fails when staging_dir points to a file rather than a directory."""
    file_path = tmp_path / "not_a_dir.txt"
    file_path.write_text("data")

    import os

    original = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = SERVER.process(ProcessRequest(staging_dir="not_a_dir.txt"))
        assert result.success is False
        assert "not a directory" in (result.error or "")
    finally:
        os.chdir(original)
