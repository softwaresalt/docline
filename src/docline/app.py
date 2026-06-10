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
from docline.readers.picture_sink import CountingPictureSink
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
    allow_heading_disorder: bool = False,
    docline_namespace: Mapping[str, object] | None = None,
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
        allow_heading_disorder: When ``True``, bypass the H1->H2->H3 heading
            hierarchy validation enforced by :func:`assemble_markdown`.
        docline_namespace: Optional pre-built ``docline:`` namespace map
            (referentiality fields for graphtor reconstruction). When
            provided, it is **merged** into ``payload_dict["docline"]``
            after the Pydantic payload is built — existing keys from
            ``WebFrontmatter`` auto-routing (``source_url``,
            ``crawl_depth``, ``http_status``, ``content_type``,
            ``final_url``, ``fetched_at``) are preserved and the
            referentiality keys are layered on top. Overwriting the
            namespace destroys web-crawl metadata; always merge.

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
        http_status = metadata.get("http_status")
        if type(http_status) is int and http_status >= 100:
            base_data["http_status"] = http_status
        content_type = metadata.get("content_type")
        if isinstance(content_type, str) and content_type:
            base_data["content_type"] = content_type
        final_url = metadata.get("final_url")
        if isinstance(final_url, str) and final_url:
            base_data["final_url"] = final_url
        fetched_at = metadata.get("fetched_at")
        if isinstance(fetched_at, str) and fetched_at:
            base_data["fetched_at"] = fetched_at

    try:
        payload = assemble_frontmatter_payload(schema_family, base_data)
    except SchemaValidationError:
        # Fallback: use WikiFrontmatter with minimal fields only
        payload = assemble_frontmatter_payload(WikiFrontmatter, base_data)

    payload_dict = payload.model_dump(mode="json")
    if docline_namespace is not None:
        existing_docline = payload_dict.get("docline")
        merged: dict[str, object] = {}
        if isinstance(existing_docline, dict):
            merged.update(existing_docline)
        merged.update(docline_namespace)
        payload_dict["docline"] = merged

    return assemble_markdown(
        payload_dict,
        body,
        allow_heading_disorder=allow_heading_disorder,
        emit_chunk_anchors=True,
    )


def _build_document_id(job_id: str, input_path: str, ingest_order: int) -> str:
    """Build a deterministic document identifier for a processed output part."""
    normalized_input_path = input_path.replace("\\", "/")
    digest = sha256(f"{job_id}:{normalized_input_path}:{ingest_order}".encode()).hexdigest()
    return digest[:16]


def _build_parent_document_id(job_id: str, input_path: str) -> str:
    """Build the SHA-derived id shared by every part of a single source.

    Reuses the :func:`_build_document_id` algorithm with ``ingest_order=0``
    so every part of the same source collapses to the same value, producing
    a stable ``parent_document_id`` for the ``docline.parent_document_id``
    referentiality field consumed by graphtor reconstruction.
    """
    return _build_document_id(job_id, input_path, ingest_order=0)


def _relative_sibling_basename(current: Path, all_paths: list[Path], *, offset: int) -> str | None:
    """Return the basename of the sibling part at ``offset`` or ``None`` at boundaries."""
    try:
        idx = all_paths.index(current)
    except ValueError:
        return None
    target = idx + offset
    if target < 0 or target >= len(all_paths):
        return None
    return all_paths[target].name


def _build_docline_namespace(
    *,
    parent_document_id: str,
    part_index: int,
    total_parts: int,
    current_output_path: Path,
    all_output_paths: list[Path],
    section_title: str | None,
) -> dict[str, object]:
    """Build the ``docline:`` namespace dict for a single processed output part.

    Used to populate the ``docline.{parent_document_id, part_index,
    total_parts, prev_part, next_part, section_title}`` referentiality
    fields consumed by graphtor reconstruction (G3b).
    """
    return {
        "parent_document_id": parent_document_id,
        "part_index": part_index,
        "total_parts": total_parts,
        "prev_part": _relative_sibling_basename(current_output_path, all_output_paths, offset=-1),
        "next_part": _relative_sibling_basename(current_output_path, all_output_paths, offset=+1),
        "section_title": section_title,
    }


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
            ManifestTool(
                name="ingest_local_dir",
                description=(
                    "One-shot fetch+process for an already-cloned local source. "
                    "Mirrors a `type: local` ManifestLocalSource YAML entry "
                    "behind a CLI command. Source path is staged, then "
                    "execute_process runs against the staging dir."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "source_path": {
                            "type": "string",
                            "description": "Path to the source directory.",
                        },
                        "output": {
                            "type": "string",
                            "description": "Output directory for processed Markdown.",
                        },
                        "include": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": ["**/*.md"],
                        },
                        "exclude": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                        "staging_dir": {"type": "string"},
                        "keep_staging": {"type": "boolean", "default": False},
                        "allow_heading_disorder": {"type": "boolean", "default": False},
                        "pdf_engine": {
                            "type": "string",
                            "enum": ["auto", "docling", "heuristic"],
                            "default": "auto",
                        },
                        "pdf_mode": {
                            "type": "string",
                            "enum": ["auto", "triage"],
                            "default": "auto",
                        },
                    },
                    "required": ["source_path", "output"],
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
            source_basename = rel_in_files.with_suffix("")
            picture_sink = CountingPictureSink(job_output_root / source_basename / "media")
            triage_cache = job_output_root / source_basename / "triage-cache"
            try:
                document_parts = build_output_document_parts(
                    file_path,
                    rel_in_files,
                    layout_engine=request.pdf_engine,
                    picture_sink=picture_sink,
                    pdf_mode=request.pdf_mode,
                    triage_output_dir=triage_cache,
                )
            except Exception as err:  # noqa: BLE001
                _log.warning("Failed to convert %s: %s", file_path, err)
                errors.append(str(err))
                continue

            page_metadata = _load_staged_page_metadata(file_path)
            # Prefer source MD's frontmatter title when present (023.001-T / 025-S):
            # authorial title is more reliable than H1 derivation, especially for
            # Microsoft Learn / DocFx / Hugo / Jekyll content that uses ``title:``
            # for short doc titles distinct from longer H1 headings.
            source_fm = document_parts[0].source_frontmatter
            source_title: str | None = None
            if isinstance(source_fm, Mapping):
                raw_title = source_fm.get("title")
                if isinstance(raw_title, str) and raw_title.strip():
                    source_title = raw_title.strip()
            base_title = source_title or _derive_document_title(
                file_path,
                document_parts[0].body,
                job.metadata.source,
            )
            current_ingest_order = _resolve_ingest_order(next_ingest_order, page_metadata)

            input_path_posix = rel_in_files.as_posix()
            parent_document_id = _build_parent_document_id(job.job_id, input_path_posix)
            all_part_output_paths = [part.relative_output_path for part in document_parts]
            total_parts = len(document_parts)

            for part_index, document_part in enumerate(document_parts):
                part_ingest_order = current_ingest_order + part_index
                # title_override resolution (priority order):
                #   1. base_title + part suffix when multi-part (e.g. "Doc Title Part 2")
                #   2. base_title when source frontmatter provided an authoritative
                #      title (023.001-T / 025-S) — overrides body-H1 derivation
                #   3. None — defer to _build_markdown_with_frontmatter's internal
                #      _derive_document_title (existing pre-025-S behavior)
                if document_part.title_suffix is not None:
                    title_override = f"{base_title} {document_part.title_suffix}"
                elif source_title is not None and part_index == 0:
                    title_override = base_title
                else:
                    title_override = None
                docline_namespace = _build_docline_namespace(
                    parent_document_id=parent_document_id,
                    part_index=part_index + 1,
                    total_parts=total_parts,
                    current_output_path=document_part.relative_output_path,
                    all_output_paths=all_part_output_paths,
                    section_title=document_part.section_title,
                )
                # Preserve authorial frontmatter under docline:source_frontmatter
                # so downstream consumers see ms.author / ms.topic / ms.date / etc.
                # (023.001-T / 025-S). Attached only to the first part to avoid
                # duplication across multi-part outputs.
                if part_index == 0 and isinstance(document_part.source_frontmatter, Mapping):
                    docline_namespace = dict(docline_namespace)
                    docline_namespace["source_frontmatter"] = dict(document_part.source_frontmatter)
                # Preserve cross-doc link metadata under docline:cross_doc_links
                # so downstream graph extraction can treat each as an edge
                # (024.003-T / 026-S T3). Attached only to first part.
                if part_index == 0 and document_part.cross_doc_links:
                    if not isinstance(docline_namespace, dict):
                        docline_namespace = dict(docline_namespace)
                    docline_namespace["cross_doc_links"] = [
                        dict(link) for link in document_part.cross_doc_links
                    ]
                try:
                    markdown_text = _build_markdown_with_frontmatter(
                        job,
                        file_path,
                        document_part.body,
                        page_metadata=page_metadata,
                        title_override=title_override,
                        relative_input_path=rel_in_files,
                        allow_heading_disorder=request.allow_heading_disorder,
                        docline_namespace=docline_namespace,
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
                        "media_files": list(document_part.media_files),
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
