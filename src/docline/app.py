"""Application-level functions shared between CLI and MCP server."""

from pathlib import Path

from docline.app_models import (
    FetchRequest,
    FetchResult,
    Manifest,
    ManifestTool,
    McpManifestResponse,
    ProcessRequest,
    ProcessResult,
)

_FETCH_NOT_IMPLEMENTED_ERROR = "Fetch execution is not implemented."
_PROCESS_NOT_IMPLEMENTED_ERROR = "Process execution is not implemented."


def get_manifest() -> Manifest:
    """Build and return the docline tool manifest.

    Derives tool parameter schemas from the Pydantic model JSON schemas for
    :class:`~docline.app_models.FetchRequest` and
    :class:`~docline.app_models.ProcessRequest`.

    Returns:
        A :class:`~docline.app_models.Manifest` containing ``fetch`` and
        ``process`` tool definitions.
    """
    fetch_schema = FetchRequest.model_json_schema()
    process_schema = ProcessRequest.model_json_schema()

    return Manifest(
        tools=[
            ManifestTool(
                name="fetch",
                description=(
                    "Fetch a document from a URL or file path and stage it for processing."
                ),
                parameters=fetch_schema,
            ),
            ManifestTool(
                name="process",
                description=("Process staged documents into schema-validated Markdown output."),
                parameters=process_schema,
            ),
        ]
    )


def get_mcp_manifest() -> McpManifestResponse:
    """Build and return the manifest through a minimal MCP tools/list envelope.

    Returns:
        A :class:`~docline.app_models.McpManifestResponse` containing the shared
        manifest payload converted into MCP ``tools/list`` entries.
    """
    return McpManifestResponse(tools=get_manifest().tools)


def execute_fetch(request: FetchRequest) -> FetchResult:
    """Execute a fetch operation.

    Until the real fetch pipeline exists, this returns an explicit failure
    result rather than claiming that a staged artifact was produced.

    Args:
        request: Validated fetch parameters.

    Returns:
        A fetch result describing the honest placeholder outcome.
    """
    return FetchResult(
        source=request.source,
        staged_path="",
        success=False,
        error=_FETCH_NOT_IMPLEMENTED_ERROR,
    )


def execute_process(request: ProcessRequest) -> ProcessResult:
    """Execute a processing operation on staged documents.

    Until the real processing pipeline exists, this returns an explicit failure
    result rather than claiming that an output artifact was produced.

    Args:
        request: Validated process parameters.

    Returns:
        A process result describing the input and output paths and outcome.
    """
    staging_dir = Path(request.staging_dir)
    if not staging_dir.is_dir():
        return ProcessResult(
            input_path=request.staging_dir,
            success=False,
            error=f"Staging directory not found or is not a directory: {request.staging_dir}",
        )

    return ProcessResult(
        input_path=request.staging_dir,
        success=False,
        error=_PROCESS_NOT_IMPLEMENTED_ERROR,
    )
