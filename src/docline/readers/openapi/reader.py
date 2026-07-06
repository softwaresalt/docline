"""Assemble OpenAPI operations and schemas into BaseDocument objects (050.005-T / T5).

Binds the pure renderers (T3/T4) to docline's output contract. Each operation
and each named component schema becomes a fully-populated
:class:`~docline.schema.models.BaseDocument`:

* ``doc_type`` is ``openapi_operation`` or ``openapi_schema``;
* ``source`` is the spec URI plus a fragment identifying the operation
  (``#{operationId}``) or schema (``#/components/schemas/{name}``);
* ``content_sha256`` is computed the same way as every other reader;
* cross-doc links harvested from the rendered body are surfaced under the
  ``docline`` namespace so downstream graph extraction sees typed edges.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docline.process.cross_doc_links import resolve_cross_doc_links
from docline.process.hashing import compute_content_sha256
from docline.readers.openapi.errors import OpenApiError
from docline.readers.openapi.loader import load_spec
from docline.readers.openapi.render import (
    default_schema_href,
    render_operation,
    render_schema,
    sibling_schema_href,
)
from docline.schema.models import BaseDocument, BaseFrontmatter

# HTTP methods recognized under a path item, in stable render order.
_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")

OPERATION_DOC_TYPE = "openapi_operation"
SCHEMA_DOC_TYPE = "openapi_schema"


@dataclass(frozen=True)
class OpenApiDocument:
    """A rendered OpenAPI document plus its intended relative output path.

    Attributes:
        relative_path: POSIX path of the emitted document relative to the spec's
            output root (e.g. ``operations/getWidget.md`` or
            ``schemas/Widget.md``).
        document: The assembled, schema-valid document.
    """

    relative_path: str
    document: BaseDocument


def _slug(text: str) -> str:
    """Return a filesystem/link-safe slug for *text*."""
    slug = _SLUG_RE.sub("-", text).strip("-")
    return slug or "operation"


def _derive_operation_id(method: str, path: str) -> str:
    """Derive a deterministic operation id when ``operationId`` is absent."""
    return _slug(f"{method.lower()} {path}")


def _unique(candidate: str, seen: set[str]) -> str:
    """Return *candidate* or a numbered variant that has not been used yet."""
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    stem, _, suffix = candidate.rpartition(".")
    index = 2
    while True:
        alternate = f"{stem}-{index}.{suffix}"
        if alternate not in seen:
            seen.add(alternate)
            return alternate
        index += 1


def _assemble_document(
    *,
    relative_path: str,
    title: str,
    source: str,
    doc_type: str,
    body: str,
    source_path: str,
    ingested_at: datetime,
    openapi_meta: dict[str, Any],
) -> BaseDocument:
    """Build a validated BaseDocument from a rendered body and its metadata."""
    _, links = resolve_cross_doc_links(body, current_rel_path=Path(relative_path), deduplicate=True)
    docline_namespace: dict[str, Any] = {"openapi": openapi_meta}
    if links:
        docline_namespace["cross_doc_links"] = [dict(link) for link in links]

    frontmatter = BaseFrontmatter(
        title=title or relative_path,
        source=source,
        ingested_at=ingested_at,
        doc_type=doc_type,
        content_sha256=compute_content_sha256(body),
        source_path=source_path,
        docline=docline_namespace,
    )
    return BaseDocument(frontmatter=frontmatter, body=body)


def read_openapi_spec(
    source: str | Path,
    *,
    source_uri: str | None = None,
    source_path: str = "",
) -> list[OpenApiDocument]:
    """Render an OpenAPI 3.x specification into assembled BaseDocuments.

    Args:
        source: Path to the specification file, given as a :class:`Path` or a
            path string. The file is loaded from disk and parsed as JSON or YAML.
        source_uri: Base URI recorded in each document's ``source`` field. When
            omitted, the spec path's POSIX form is used.
        source_path: Project-relative POSIX path of the spec artifact, recorded
            as ``source_path`` on every emitted document.

    Returns:
        One :class:`OpenApiDocument` per operation (``operations/{id}.md``) and
        per named component schema (``schemas/{name}.md``), in stable order.

    Raises:
        OpenApiError: If the spec root is not OpenAPI 3.x (Swagger 2.0 rendering
            is deferred beyond v1).
        OpenApiParseError: If the spec cannot be read or parsed.
        OpenApiRefError: If a local ``$ref`` is unresolvable or cyclic.
    """
    path = source if isinstance(source, Path) else Path(source)
    spec = load_spec(path)

    version = spec.get("openapi")
    if not (isinstance(version, str) and version.startswith("3.")):
        raise OpenApiError(
            "read_openapi_spec renders OpenAPI 3.x only; "
            f"got openapi={version!r} (Swagger 2.0 rendering is deferred beyond v1)"
        )

    base_uri = source_uri if source_uri is not None else path.as_posix()
    ingested_at = datetime.now(UTC)

    documents: list[OpenApiDocument] = []
    seen_paths: set[str] = set()

    paths_obj = spec.get("paths")
    if isinstance(paths_obj, Mapping):
        for path_str, path_item in paths_obj.items():
            if not isinstance(path_item, Mapping):
                continue
            for method in _HTTP_METHODS:
                operation = path_item.get(method)
                if not isinstance(operation, Mapping):
                    continue
                raw_id = operation.get("operationId")
                operation_id = (
                    raw_id.strip()
                    if isinstance(raw_id, str) and raw_id.strip()
                    else _derive_operation_id(method, path_str)
                )
                relative_path = _unique(f"operations/{_slug(operation_id)}.md", seen_paths)
                body = render_operation(
                    method, path_str, operation, root=spec, schema_href=default_schema_href
                )
                summary = operation.get("summary")
                title = (
                    summary.strip()
                    if isinstance(summary, str) and summary.strip()
                    else f"{method.upper()} {path_str}"
                )
                documents.append(
                    OpenApiDocument(
                        relative_path,
                        _assemble_document(
                            relative_path=relative_path,
                            title=title,
                            source=f"{base_uri}#{operation_id}",
                            doc_type=OPERATION_DOC_TYPE,
                            body=body,
                            source_path=source_path,
                            ingested_at=ingested_at,
                            openapi_meta={
                                "method": method.upper(),
                                "path": path_str,
                                "operation_id": operation_id,
                            },
                        ),
                    )
                )

    components = spec.get("components")
    schemas = components.get("schemas") if isinstance(components, Mapping) else None
    if isinstance(schemas, Mapping):
        for name, schema in schemas.items():
            if not isinstance(schema, Mapping):
                continue
            relative_path = _unique(f"schemas/{_slug(str(name))}.md", seen_paths)
            body = render_schema(str(name), schema, root=spec, schema_href=sibling_schema_href)
            documents.append(
                OpenApiDocument(
                    relative_path,
                    _assemble_document(
                        relative_path=relative_path,
                        title=str(name),
                        source=f"{base_uri}#/components/schemas/{name}",
                        doc_type=SCHEMA_DOC_TYPE,
                        body=body,
                        source_path=source_path,
                        ingested_at=ingested_at,
                        openapi_meta={"schema_name": str(name)},
                    ),
                )
            )

    return documents


__all__ = [
    "OPERATION_DOC_TYPE",
    "SCHEMA_DOC_TYPE",
    "OpenApiDocument",
    "read_openapi_spec",
]
