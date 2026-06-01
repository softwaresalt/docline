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
from docline.schema.models import DoclineError


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
    """Execute a fetch operation and stage the source document.

    Creates a deterministic staging job record for the requested source without
    performing the actual fetch I/O.

    Args:
        request: Validated fetch parameters.

    Returns:
        A fetch result describing the staged cache path and outcome.
    """
    from docline.fetch.staging import create_staging_job

    try:
        job = create_staging_job(request.source, request.output_dir)
    except (DoclineError, ValueError) as err:
        return FetchResult(source=request.source, staged_path="", success=False, error=str(err))

    return FetchResult(source=request.source, staged_path=job.cache_path, success=True)


def execute_process(request: ProcessRequest) -> ProcessResult:
    """Execute a processing operation on staged documents.

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
        output_path=request.output_dir,
        success=True,
    )
