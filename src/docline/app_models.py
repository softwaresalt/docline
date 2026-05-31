"""Shared operation models used by both the CLI and MCP server interfaces."""

import re

from pydantic import BaseModel, Field, field_validator

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:", re.ASCII)
_PATH_SEPARATOR_RE = re.compile(r"[\\/]+")


def _validate_workspace_relative_path(value: str) -> str:
    """Validate that a boundary path is relative and non-traversing."""
    if value.startswith(("/", "\\")) or _WINDOWS_DRIVE_RE.match(value):
        raise ValueError("path must be relative to the workspace")
    if ".." in _PATH_SEPARATOR_RE.split(value):
        raise ValueError("path must not contain parent-directory traversal")
    return value


class FetchRequest(BaseModel):
    """Parameters for a document fetch operation.

    Attributes:
        source: URL or file path to fetch.
        depth: Crawl depth for web sources. 0 means single page only.
        output_dir: Directory where staged files are written.
    """

    source: str = Field(min_length=1)
    depth: int = Field(default=0, ge=0)
    output_dir: str = ".cache/staging"

    @field_validator("output_dir")
    @classmethod
    def _validate_output_dir(cls, value: str) -> str:
        return _validate_workspace_relative_path(value)


class FetchResult(BaseModel):
    """Result of a document fetch operation.

    Attributes:
        source: The original source that was fetched.
        staged_path: Path to the staged file on disk.
        success: Whether the fetch completed without error.
        error: Error message if the fetch failed, otherwise ``None``.
    """

    source: str
    staged_path: str
    success: bool
    error: str | None = None


class ProcessRequest(BaseModel):
    """Parameters for a document processing operation.

    Attributes:
        staging_dir: Directory containing staged files to process.
        output_dir: Directory where processed output files are written.
    """

    staging_dir: str = ".cache/staging"
    output_dir: str = "output"

    @field_validator("staging_dir", "output_dir")
    @classmethod
    def _validate_workspace_paths(cls, value: str) -> str:
        return _validate_workspace_relative_path(value)


class ProcessResult(BaseModel):
    """Result of a document processing operation.

    Attributes:
        input_path: Path to the input staged file.
        output_path: Path to the processed output file, or ``None`` on failure.
        success: Whether processing completed without error.
        error: Error message if processing failed, otherwise ``None``.
    """

    input_path: str
    output_path: str | None = None
    success: bool
    error: str | None = None


class ManifestTool(BaseModel):
    """Describes a single tool exposed by the docline manifest.

    Attributes:
        name: Unique tool name in snake_case.
        description: Human-readable description of what the tool does.
        parameters: Full JSON Schema dict for the tool's parameters.
    """

    name: str
    description: str
    parameters: dict[str, object]


class Manifest(BaseModel):
    """The full manifest of tools exposed by docline.

    Attributes:
        tools: Ordered list of tool definitions.
    """

    tools: list[ManifestTool]
