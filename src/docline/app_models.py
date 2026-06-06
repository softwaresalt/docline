"""Shared operation models used by both the CLI and MCP server interfaces."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from docline.paths import PathContainmentError, validate_workspace_relative_path


class FetchRequest(BaseModel):
    """Parameters for a document fetch operation.

    Attributes:
        source: URL or file path to fetch.
        depth: Crawl depth for web sources. 0 means single page only.
        output_dir: Directory where staged files are written.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    depth: int = Field(default=0, ge=0)
    output_dir: str = ".cache/staging"

    @field_validator("output_dir")
    @classmethod
    def _validate_output_dir(cls, value: str) -> str:
        try:
            return validate_workspace_relative_path(value)
        except PathContainmentError as err:
            raise ValueError(str(err)) from err


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
        allow_heading_disorder: When ``True``, bypass the H1->H2->H3 heading
            hierarchy validation during Markdown assembly. Default ``False``.
        pdf_engine: PDF layout extractor selection. ``"auto"`` (default,
            G3c / 014-S) resolves to ``"docling"`` when the optional
            ``docline[pdf]`` extras are installed and transparently falls
            back to ``"heuristic"`` when docling is unavailable or fails
            to load a particular PDF. ``"docling"`` opts in explicitly
            (and raises when not installed); ``"heuristic"`` uses the
            built-in extractor.
    """

    model_config = ConfigDict(extra="forbid")

    staging_dir: str = ".cache/staging"
    output_dir: str = "output"
    allow_heading_disorder: bool = False
    pdf_engine: Literal["auto", "docling", "heuristic"] = "auto"
    pdf_mode: Literal["auto", "triage"] = Field(
        default="auto",
        description=(
            "PDF processing pipeline mode (CLI: --pdf-mode). 'auto' "
            "(default) is the existing split-and-throttle batch pipeline. "
            "'triage' runs the heuristic engine across the whole document, "
            "scores each page for fidelity loss, and re-runs only flagged "
            "pages through docling — typically 6-8x faster on long technical "
            "PDFs with mostly clean prose. Orthogonal to --pdf-engine."
        ),
    )

    @field_validator("staging_dir", "output_dir")
    @classmethod
    def _validate_workspace_paths(cls, value: str) -> str:
        try:
            return validate_workspace_relative_path(value)
        except PathContainmentError as err:
            raise ValueError(str(err)) from err


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

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str
    parameters: dict[str, object] = Field(
        serialization_alias="inputSchema",
        validation_alias="inputSchema",
    )


class Manifest(BaseModel):
    """The full manifest of tools exposed by docline.

    Attributes:
        tools: Ordered list of tool definitions.
    """

    tools: list[ManifestTool]


class McpManifestResponse(BaseModel):
    """A minimal MCP-compatible tools/list response.

    Attributes:
        tools: Ordered list of shared manifest tools in MCP discovery format.
    """

    tools: list[ManifestTool]
