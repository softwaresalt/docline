"""Application-level functions shared between CLI and MCP server."""

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
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
from docline.fetch.html_normalize import extract_headings, normalize_heading_hierarchy
from docline.fetch.models import StagingJob
from docline.paths import PathContainmentError, posixify_path, safe_workspace_path
from docline.process.assemble import assemble_markdown
from docline.process.hashing import compute_content_sha256
from docline.process.manifest import update_manifest_index, write_manifest_index
from docline.process.metadata import assemble_frontmatter_payload, resolve_document_type
from docline.process.output import write_markdown_output
from docline.process.output_contract import build_output_document_parts
from docline.schema.library import WebFrontmatter, WikiFrontmatter
from docline.schema.models import SchemaValidationError
from docline.types import SourceInput, SourceKind

_log = logging.getLogger(__name__)

_FETCH_NOT_IMPLEMENTED_ERROR = "Fetch execution is not implemented."
_CRAWL_MANIFEST_NAME = "crawl-manifest.json"
_HEADING_RE = re.compile(r"^(#{1,6})(\s+.+)$")

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
            url = source[idx:]
            return re.sub(
                r"(?::(?:depth|max_pages|domain_lock|rate_limit_ms)=[^:]+)+$",
                "",
                url,
            )
    return None


def _load_staged_page_metadata(file_path: Path) -> Mapping[str, object] | None:
    """Load optional per-page staging metadata for a processed file."""
    metadata_path = file_path.with_suffix(".meta.json")
    if not metadata_path.is_file():
        return None
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        _log.warning("Ignoring malformed staged page metadata at %s: %s", metadata_path, err)
        return None
    if not isinstance(payload, dict):
        _log.warning("Ignoring non-object staged page metadata at %s", metadata_path)
        return None
    return payload


def _load_crawl_manifest(job_dir: Path) -> list[Mapping[str, object]]:
    """Load ordered crawl entries for a staged web job when present."""
    manifest_path = job_dir / _CRAWL_MANIFEST_NAME
    if not manifest_path.is_file():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        _log.warning("Ignoring malformed crawl manifest at %s: %s", manifest_path, err)
        return []
    pages = payload.get("pages")
    if not isinstance(pages, list):
        _log.warning("Ignoring crawl manifest with non-list pages at %s", manifest_path)
        return []
    entries: list[Mapping[str, object]] = [entry for entry in pages if isinstance(entry, dict)]
    return sorted(entries, key=_crawl_order_key)


def _crawl_order_key(entry: Mapping[str, object]) -> int:
    """Return the crawl-order sort key for a crawl manifest entry."""
    crawl_order = entry.get("crawl_order")
    return crawl_order if type(crawl_order) is int else 1_000_000


def _ordered_staged_files(files_dir: Path, crawl_entries: list[Mapping[str, object]]) -> list[Path]:
    """Return supported staged files in crawl order when available."""
    supported_files = [
        path
        for path in sorted(files_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in _SUPPORTED_EXTENSIONS
    ]
    if not crawl_entries:
        return supported_files

    supported_lookup = {path.resolve(): path for path in supported_files}
    ordered: list[Path] = []
    seen: set[Path] = set()
    for entry in crawl_entries:
        relative_path = entry.get("relative_path")
        if not isinstance(relative_path, str):
            continue
        try:
            candidate = safe_workspace_path(relative_path, files_dir)
        except PathContainmentError:
            continue
        supported_candidate = supported_lookup.get(candidate.resolve())
        if supported_candidate is not None:
            ordered.append(supported_candidate)
            seen.add(supported_candidate)

    ordered.extend(path for path in supported_files if path not in seen)
    return ordered


def _derive_document_title(file_path: Path, body: str, source: str) -> str:
    """Derive a stable title for frontmatter and web body normalization."""
    default_title = file_path.stem.replace("-", " ").replace("_", " ").title() or "Document"
    if not _is_web_source(source):
        return default_title

    headings = extract_headings(body)
    if headings and file_path.stem.lower() in {"index", "page"}:
        return headings[0][1]
    return default_title


def _shift_markdown_headings(markdown: str, delta: int) -> str:
    """Shift all ATX headings in *markdown* deeper by *delta* levels."""
    shifted_lines: list[str] = []
    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            new_level = min(len(match.group(1)) + delta, 6)
            shifted_lines.append(f"{'#' * new_level}{match.group(2)}")
        else:
            shifted_lines.append(line)
    return "\n".join(shifted_lines)


def _normalize_web_markdown_body(body: str, title: str) -> str:
    """Ensure web-derived Markdown always starts with a stable H1 root heading."""
    stripped = body.strip()
    if not stripped:
        return f"# {title}\n"

    normalized = normalize_heading_hierarchy(stripped).strip()
    headings = extract_headings(normalized)
    if not headings:
        return f"# {title}\n\n{normalized}\n"

    first_heading_text = headings[0][1].strip()
    if first_heading_text.casefold() == title.strip().casefold():
        return f"{normalized}\n" if not normalized.endswith("\n") else normalized

    shifted = _shift_markdown_headings(normalized, 1).strip()
    combined = f"# {title}\n\n{shifted}"
    return f"{combined}\n"


def _build_markdown_with_frontmatter(
    job: StagingJob,
    file_path: Path,
    body: str,
    page_metadata: Mapping[str, object] | None = None,
    title_override: str | None = None,
    relative_input_path: Path | str | None = None,
) -> str:
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
        page_metadata: Optional per-file staged metadata (URL/depth for crawls).
        title_override: Optional explicit title that bypasses derivation.
        relative_input_path: Path of the staged source artifact relative to the
            job's ``files/`` directory. When supplied, it is normalized through
            :func:`docline.paths.posixify_path` and emitted as the
            ``source_path`` frontmatter field so downstream graphtor-docs
            consumers always see forward-slash POSIX paths (PA-2 / 010-S F2.T3).

    Returns:
        Assembled Markdown string with YAML frontmatter.
    """
    source_str = job.metadata.source
    metadata = page_metadata or {}
    title = title_override or _derive_document_title(file_path, body, source_str)

    if _is_web_source(source_str):
        staged_page_url = metadata.get("page_url")
        source_url = (
            staged_page_url if isinstance(staged_page_url, str) else _extract_source_url(source_str)
        )
        source_input = SourceInput(kind=SourceKind.URL, raw=source_url or source_str)
        body = _normalize_web_markdown_body(body, title)
    else:
        source_url = None
        source_input = SourceInput(kind=SourceKind.FILE, raw=source_str)

    schema_family = resolve_document_type(source_input)

    base_data: dict[str, object] = {
        "title": title,
        "source": source_str,
        "ingested_at": datetime.now(UTC),
        "content_sha256": compute_content_sha256(body),
    }
    if relative_input_path is not None:
        base_data["source_path"] = posixify_path(relative_input_path)
    if schema_family is WebFrontmatter and source_url:
        base_data["source_url"] = source_url
        crawl_depth = metadata.get("crawl_depth")
        if type(crawl_depth) is int and crawl_depth >= 0:
            base_data["crawl_depth"] = crawl_depth

    try:
        payload = assemble_frontmatter_payload(schema_family, base_data)
    except SchemaValidationError:
        # Fallback: use WikiFrontmatter with minimal fields only
        payload = assemble_frontmatter_payload(WikiFrontmatter, base_data)

    return assemble_markdown(payload.model_dump(mode="json"), body)


def _build_document_id(job_id: str, input_path: str, ingest_order: int) -> str:
    """Build a deterministic document identifier for a processed output part."""
    normalized_input_path = input_path.replace("\\", "/")
    digest = sha256(f"{job_id}:{normalized_input_path}:{ingest_order}".encode()).hexdigest()
    return digest[:16]


def _resolve_ingest_order(
    next_ingest_order: int,
    page_metadata: Mapping[str, object] | None,
) -> int:
    """Resolve the ingest order for a processed output part."""
    if isinstance(page_metadata, Mapping):
        crawl_order = page_metadata.get("crawl_order")
        if type(crawl_order) is int and crawl_order >= 0:
            return crawl_order
    return next_ingest_order


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
            ManifestTool(
                name="export_schema",
                description=(
                    "Return the JSON Schema for the BaseFrontmatter v1 contract"
                    " as a deterministic sort_keys-normalized JSON string."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
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
    completed_job_found = False
    errors: list[str] = []

    for metadata_path in sorted(staging_dir.rglob("metadata.json")):
        try:
            job = StagingJob.model_validate_json(metadata_path.read_text(encoding="utf-8"))
        except Exception as err:  # noqa: BLE001
            _log.warning("Skipping malformed metadata.json at %s: %s", metadata_path, err)
            continue

        if not job.complete:
            continue

        completed_job_found = True
        files_dir = metadata_path.parent / "files"
        if not files_dir.is_dir():
            continue

        crawl_entries = _load_crawl_manifest(metadata_path.parent)
        job_output_root = output_dir / job.job_id
        job_manifest_entries: list[Mapping[str, object]] = []
        next_ingest_order = 0

        for file_path in _ordered_staged_files(files_dir, crawl_entries):
            rel_in_files = file_path.relative_to(files_dir)
            try:
                document_parts = build_output_document_parts(file_path, rel_in_files)
            except Exception as err:  # noqa: BLE001
                _log.warning("Failed to convert %s: %s", file_path, err)
                errors.append(str(err))
                continue

            page_metadata = _load_staged_page_metadata(file_path)
            base_title = _derive_document_title(
                file_path,
                document_parts[0].body,
                job.metadata.source,
            )
            current_ingest_order = _resolve_ingest_order(next_ingest_order, page_metadata)

            for part_index, document_part in enumerate(document_parts):
                part_ingest_order = current_ingest_order + part_index
                title_override = (
                    f"{base_title} {document_part.title_suffix}"
                    if document_part.title_suffix is not None
                    else None
                )
                try:
                    markdown_text = _build_markdown_with_frontmatter(
                        job,
                        file_path,
                        document_part.body,
                        page_metadata=page_metadata,
                        title_override=title_override,
                        relative_input_path=rel_in_files,
                    )
                except Exception as err:  # noqa: BLE001
                    _log.warning("Failed to build frontmatter for %s: %s", file_path, err)
                    markdown_text = document_part.body

                rel_output = str(Path(job.job_id) / document_part.relative_output_path)
                try:
                    out_path = write_markdown_output(output_dir, rel_output, markdown_text)
                    input_path = rel_in_files.as_posix()
                    manifest_entry: dict[str, object] = {
                        "document_id": _build_document_id(
                            job.job_id,
                            input_path,
                            part_ingest_order,
                        ),
                        "source": job.metadata.source,
                        "job_id": job.job_id,
                        "ingest_order": part_ingest_order,
                        "input_path": input_path,
                        "input_file": file_path.name,
                        "output_path": str(out_path.relative_to(root)),
                    }
                    if isinstance(page_metadata, Mapping):
                        source_url = page_metadata.get("page_url")
                        if isinstance(source_url, str):
                            manifest_entry["source_url"] = source_url
                        crawl_depth = page_metadata.get("crawl_depth")
                        if type(crawl_depth) is int and crawl_depth >= 0:
                            manifest_entry["crawl_depth"] = crawl_depth
                        crawl_order = page_metadata.get("crawl_order")
                        if type(crawl_order) is int and crawl_order >= 0:
                            manifest_entry["crawl_order"] = crawl_order
                    update_manifest_index(
                        output_dir,
                        "manifest.json",
                        manifest_entry,
                    )
                    job_manifest_entries.append(
                        {
                            **manifest_entry,
                            "output_path": str(out_path.relative_to(job_output_root)),
                        }
                    )
                    processed_count += 1
                except Exception as err:  # noqa: BLE001
                    _log.warning("Failed to write output for %s: %s", file_path, err)
                    errors.append(str(err))

            next_ingest_order = max(next_ingest_order, current_ingest_order + len(document_parts))

        if job_manifest_entries:
            write_manifest_index(job_output_root, "manifest.json", job_manifest_entries)

    if processed_count == 0:
        if errors:
            return ProcessResult(
                input_path=request.staging_dir,
                success=False,
                error="; ".join(errors[:3]),
            )
        if completed_job_found:
            return ProcessResult(
                input_path=request.staging_dir,
                success=False,
                error="Completed staging jobs produced no processed outputs.",
            )

    return ProcessResult(
        input_path=request.staging_dir,
        output_path=request.output_dir,
        success=True,
    )
