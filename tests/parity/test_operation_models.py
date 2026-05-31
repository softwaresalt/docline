"""Tests for shared operation models used by CLI and MCP interfaces."""

import pytest
from pydantic import ValidationError

from docline.app_models import (
    FetchRequest,
    FetchResult,
    Manifest,
    ManifestTool,
    ProcessRequest,
    ProcessResult,
)


def test_fetch_request_defaults() -> None:
    """FetchRequest uses correct default values."""
    req = FetchRequest(source="http://example.com")
    assert req.depth == 0
    assert req.output_dir == ".cache/staging"


def test_fetch_request_custom_fields() -> None:
    """FetchRequest accepts custom depth and output_dir."""
    req = FetchRequest(source="http://example.com", depth=2, output_dir="/tmp/out")
    assert req.depth == 2
    assert req.output_dir == "/tmp/out"


def test_fetch_request_requires_source() -> None:
    """FetchRequest raises ValidationError when source is missing."""
    with pytest.raises(ValidationError):
        FetchRequest()  # type: ignore[call-arg]


def test_fetch_result_success() -> None:
    """FetchResult can represent a successful fetch."""
    result = FetchResult(source="http://example.com", staged_path="/cache/abc", success=True)
    assert result.success is True
    assert result.error is None


def test_fetch_result_failure() -> None:
    """FetchResult can represent a failed fetch with error message."""
    result = FetchResult(
        source="http://example.com", staged_path="", success=False, error="timeout"
    )
    assert result.success is False
    assert result.error == "timeout"


def test_process_request_defaults() -> None:
    """ProcessRequest uses correct default values."""
    req = ProcessRequest()
    assert req.staging_dir == ".cache/staging"
    assert req.output_dir == "output"


def test_process_result_success() -> None:
    """ProcessResult can represent a successful processing."""
    result = ProcessResult(input_path="staging/doc.md", output_path="output/doc.md", success=True)
    assert result.success is True
    assert result.output_path == "output/doc.md"


def test_process_result_failure() -> None:
    """ProcessResult can represent a failure with no output path."""
    result = ProcessResult(input_path="staging/doc.md", success=False, error="parse error")
    assert result.output_path is None
    assert result.error == "parse error"


def test_manifest_tool_construction() -> None:
    """ManifestTool accepts name, description, and parameters."""
    tool = ManifestTool(name="fetch", description="Fetch a document", parameters={"url": "str"})
    assert tool.name == "fetch"
    assert tool.parameters == {"url": "str"}


def test_manifest_construction() -> None:
    """Manifest accepts a list of ManifestTool objects."""
    tools = [
        ManifestTool(name="fetch", description="Fetch", parameters={}),
        ManifestTool(name="process", description="Process", parameters={}),
    ]
    manifest = Manifest(tools=tools)
    assert len(manifest.tools) == 2


def test_fetch_request_json_schema_generated() -> None:
    """FetchRequest.model_json_schema() returns a schema with required fields."""
    schema = FetchRequest.model_json_schema()
    assert "properties" in schema
    assert "source" in schema["properties"]


def test_process_request_json_schema_generated() -> None:
    """ProcessRequest.model_json_schema() returns a valid schema."""
    schema = ProcessRequest.model_json_schema()
    assert "properties" in schema
