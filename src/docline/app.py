"""Application-level functions shared between CLI and MCP server."""

import logging
from datetime import UTC, datetime
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
from docline.fetch.models import StagingJob
from docline.paths import PathContainmentError, safe_workspace_path
from docline.process.assemble import assemble_markdown
from docline.process.manifest import update_manifest_index
from docline.process.metadata import assemble_frontmatter_payload, resolve_document_type
from docline.process.output import write_markdown_output
from docline.schema.library import WebFrontmatter, WikiFrontmatter
from docline.schema.models import SchemaValidationError
from docline.types import SourceInput, SourceKind

_log = logging.getLogger(__name__)

_FETCH_NOT_IMPLEMENTED_ERROR = "Fetch execution is not implemented."

# Supported file extension → reader function name
_SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".html", ".htm", ".md", ".txt"}


def _is_web_source(source: str) -> bool:
    """Return True when the source key represents a web crawl or URL source.

    Args:
        source: Sanitized source key from :class:`~docline.fetch.models.SourceMetadata`.

    Returns:
        ``True`` for ``web_crawl:`` and ``manifest_url:`` prefixes.
    """
    return source.startswith(("web_crawl:", "manifest_url:"))


def _extract_source_url(source: str) -> str | None:
    """Extract the first ``http://`` or ``https://`` URL from a source key.

    Args:
        source: Sanitized source key string.

    Returns:
        The URL substring if found, otherwise ``None``.
    """
    for prefix in ("https://", "http://"):
        idx = source.find(prefix)
        if idx != -1:
            return source[idx:]
    return None


def _build_markdown_with_frontmatter(job: StagingJob, file_path: Path, body: str) -> str:
    """Wrap a document body in YAML frontmatter and return an assembled Markdown string.

    Resolves the appropriate frontmatter schema (``WikiFrontmatter`` for
    local/git sources, ``WebFrontmatter`` for URL sources) from the job's
    source metadata, builds a minimal valid payload, and assembles the final
    Markdown document.  Falls back to ``WikiFrontmatter`` if the resolved
    schema fails validation.

    Args:
        job: Staging job whose metadata describes the document origin.
        file_path: Absolute path to the staged file (used for title derivation).
        body: Extracted Markdown body text.

    Returns:
        Assembled Markdown string with YAML frontmatter.
    """
    source_str = job.metadata.source
    title = file_path.stem.replace("-", " ").replace("_", " ").title() or "Document"

    if _is_web_source(source_str):
        source_url = _extract_source_url(source_str)
        source_input = SourceInput(kind=SourceKind.URL, raw=source_url or source_str)
    else:
        source_url = None
        source_input = SourceInput(kind=SourceKind.FILE, raw=source_str)

    schema_family = resolve_document_type(source_input)

    base_data: dict[str, object] = {
        "title": title,
        "source": source_str,
        "ingested_at": datetime.now(UTC),
    }
    if schema_family is WebFrontmatter and source_url:
        base_data["source_url"] = source_url

    try:
        payload = assemble_frontmatter_payload(schema_family, base_data)
    except SchemaValidationError:
        # Fallback: use WikiFrontmatter with minimal fields only
        payload = assemble_frontmatter_payload(WikiFrontmatter, base_data)

    return assemble_markdown(payload.model_dump(mode="json"), body)


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
    """Process staged documents into Markdown output files.

    Walks the staging directory for completed staging jobs, reads each staged
    file using the appropriate reader, and writes Markdown output files.  A
    ``manifest.json`` index is maintained in the output directory.

    Args:
        request: Validated process parameters.

    Returns:
        A process result describing the outcome.
    """
    root = Path.cwd()
    try:
        staging_dir = safe_workspace_path(request.staging_dir, root)
    except PathContainmentError as err:
        return ProcessResult(
            input_path=request.staging_dir,
            success=False,
            error=str(err),
        )

    if not staging_dir.is_dir():
        return ProcessResult(
            input_path=request.staging_dir,
            success=False,
            error=f"Staging directory not found or is not a directory: {request.staging_dir}",
        )

    try:
        output_dir = safe_workspace_path(request.output_dir, root)
    except PathContainmentError as err:
        return ProcessResult(
            input_path=request.staging_dir,
            success=False,
            error=str(err),
        )

    processed_count = 0
    errors: list[str] = []

    for metadata_path in sorted(staging_dir.rglob("metadata.json")):
        try:
            job = StagingJob.model_validate_json(metadata_path.read_text(encoding="utf-8"))
        except Exception as err:  # noqa: BLE001
            _log.warning("Skipping malformed metadata.json at %s: %s", metadata_path, err)
            continue

        if not job.complete:
            continue

        files_dir = metadata_path.parent / "files"
        if not files_dir.is_dir():
            continue

        for file_path in sorted(files_dir.rglob("*")):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix not in _SUPPORTED_EXTENSIONS:
                continue

            try:
                body = _convert_to_markdown(file_path, suffix)
            except Exception as err:  # noqa: BLE001
                _log.warning("Failed to convert %s: %s", file_path, err)
                errors.append(str(err))
                continue

            try:
                markdown_text = _build_markdown_with_frontmatter(job, file_path, body)
            except Exception as err:  # noqa: BLE001
                _log.warning("Failed to build frontmatter for %s: %s", file_path, err)
                markdown_text = body

            # Unique output path: {job_id}/{relative-path-within-files}.md
            rel_in_files = file_path.relative_to(files_dir)
            rel_output = str(Path(job.job_id) / rel_in_files.with_suffix(".md"))
            try:
                out_path = write_markdown_output(output_dir, rel_output, markdown_text)
                update_manifest_index(
                    output_dir,
                    "manifest.json",
                    {
                        "source": job.metadata.source,
                        "job_id": job.job_id,
                        "output_path": str(out_path.relative_to(root)),
                        "input_file": file_path.name,
                    },
                )
                processed_count += 1
            except Exception as err:  # noqa: BLE001
                _log.warning("Failed to write output for %s: %s", file_path, err)
                errors.append(str(err))

    if errors and processed_count == 0:
        return ProcessResult(
            input_path=request.staging_dir,
            output_path=request.output_dir,
            success=False,
            error="; ".join(errors[:3]),
        )

    return ProcessResult(
        input_path=request.staging_dir,
        output_path=request.output_dir,
        success=True,
    )


def _convert_to_markdown(file_path: Path, suffix: str) -> str:
    """Convert a staged file to Markdown text.

    Args:
        file_path: Absolute path to the staged file.
        suffix: Lowercased file extension (e.g. ``".docx"``).

    Returns:
        Markdown text extracted from the file.

    Raises:
        Exception: If reading or extraction fails.
    """
    if suffix == ".docx":
        from docline.readers.docx import read_docx

        return read_docx(file_path)

    if suffix == ".pdf":
        from docline.readers.pdf import read_pdf

        return read_pdf(file_path)

    if suffix in {".html", ".htm"}:
        from docline.fetch.html_extract import HtmlExtractionError, extract_main_content

        html = file_path.read_text(encoding="utf-8", errors="replace")
        try:
            return extract_main_content(html)
        except HtmlExtractionError:
            return html  # Return raw HTML body on extraction failure

    if suffix in {".md", ".txt"}:
        return file_path.read_text(encoding="utf-8", errors="replace")

    return file_path.read_text(encoding="utf-8", errors="replace")
