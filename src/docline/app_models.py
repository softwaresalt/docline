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
            Resolved relative to ``workspace_root`` (or ``Path.cwd()``
            when ``workspace_root`` is unset).
        output_dir: Directory where processed output files are written.
            Resolved relative to ``workspace_root`` (or ``Path.cwd()``
            when ``workspace_root`` is unset).
        workspace_root: Optional absolute path used as the containment
            root for ``staging_dir`` and ``output_dir`` resolution. When
            unset (default), ``Path.cwd()`` is used — the legacy MCP
            and ``docline process`` behavior. The CLI ``ingest local-dir``
            flow sets this so the operator can run docline from any cwd
            and still write outputs to absolute paths (e.g.
            ``E:\\out\\powerbi`` while sitting in
            ``D:\\Source\\GitHub\\docline``).
        allow_heading_disorder: When ``True``, bypass the H1->H2->H3 heading
            hierarchy validation during Markdown assembly. Default ``False``.
        pdf_engine: PDF layout extractor selection. Four choices:

            * ``"auto"`` (default) prefers ``"azure_di"`` when the
              ``AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`` env var is set
              AND the ``docline[adi]`` extra is installed (027-F /
              029-S spike), falls back to ``"docling"`` when the
              ``docline[pdf]`` extras are installed, and falls back to
              ``"heuristic"`` otherwise. The ``"auto"`` path also
              transparently catches docling / ADI failures and
              degrades to the heuristic engine so a single hostile PDF
              cannot abort the batch.
            * ``"docling"`` opts in to the local docling layout model
              explicitly (raises when not installed).
            * ``"azure_di"`` opts in to Azure Document Intelligence via
              the optional ``docline[adi]`` extra (raises when the SDK
              is missing or when ``AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT``
              + ``AZURE_DOCUMENT_INTELLIGENCE_KEY`` env vars are not set).
            * ``"heuristic"`` uses the built-in extractor.
    """

    model_config = ConfigDict(extra="forbid")

    staging_dir: str = ".cache/staging"
    output_dir: str = "output"
    workspace_root: str | None = None
    allow_heading_disorder: bool = False
    pdf_engine: Literal["auto", "docling", "azure_di", "heuristic"] = "auto"
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
