"""Assemble OpenAPI operations and schemas into BaseDocument objects (050.005-T / T5).

Binds the pure renderers (T3/T4) to docline's output contract. Each operation
and each named component schema becomes a fully-populated
:class:`~docline.schema.models.BaseDocument`:

* ``doc_type`` is ``openapi_operation`` or ``openapi_schema``;
* ``source`` is the spec URI plus a fragment identifying the operation
  (``#{operationId}``) or schema (``#/components/schemas/{name}``);
* ``content_sha256`` is left empty here and finalized by the assemble
  pipeline (:func:`~docline.process.assemble.assemble_markdown`) over the
  emitted body, so the stored digest matches a re-hash of what is written;
* cross-doc links harvested from the rendered body are surfaced under the
  ``docline`` namespace so downstream graph extraction sees typed edges.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from docline.process.cross_doc_links import resolve_cross_doc_links
from docline.readers.openapi.convert import swagger2_to_openapi3
from docline.readers.openapi.errors import OpenApiError
from docline.readers.openapi.loader import component_name_from_ref, load_spec, slug
from docline.readers.openapi.render import (
    RefLink,
    render_operation,
    render_schema,
)
from docline.readers.openapi.resolve import CorpusRefLinker
from docline.schema.models import BaseDocument, BaseFrontmatter

# HTTP methods recognized under a path item, in stable render order.
_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

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


def _derive_operation_id(method: str, path: str) -> str:
    """Derive a deterministic operation id when ``operationId`` is absent."""
    return slug(f"{method.lower()} {path}")


_SCHEMAS_REF_PREFIX = "#/components/schemas/"


def _default_operation_ref_link(ref: str) -> str | None:
    """Local-only ref link for operation docs (pre-053-F single-file behavior)."""
    if ref.startswith(_SCHEMAS_REF_PREFIX):
        return f"../schemas/{slug(component_name_from_ref(ref))}.md"
    return None


def _default_schema_ref_link(ref: str) -> str | None:
    """Local-only ref link for schema docs (sibling within ``schemas/``)."""
    if ref.startswith(_SCHEMAS_REF_PREFIX):
        return f"{slug(component_name_from_ref(ref))}.md"
    return None


def _make_ref_link(linker: CorpusRefLinker | None, subdir: str) -> RefLink:
    """Build the ``$ref`` → href function for a doc kind (``operations``/``schemas``).

    When *linker* is ``None`` (single-file ingest), only local refs link. When a
    linker is present (corpus ingest), cross-file refs resolve to sibling files'
    schema docs.
    """
    if linker is None:
        return _default_operation_ref_link if subdir == "operations" else _default_schema_ref_link
    from_dir = f"{linker.referring_basename}/{subdir}"
    return lambda ref: linker.link_for(ref, from_dir=from_dir)


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
    cross_link_path: str | None = None,
) -> BaseDocument:
    """Build a validated BaseDocument from a rendered body and its metadata.

    ``cross_link_path`` is the document's path used to resolve cross-doc link
    hrefs into graph-edge targets. For single-file ingests it is the file-local
    ``relative_path``; for corpus ingests it is the corpus-relative path so
    cross-file (``../../other/...``) links resolve to the correct target.
    """
    link_path = cross_link_path if cross_link_path is not None else relative_path
    _, links = resolve_cross_doc_links(body, current_rel_path=Path(link_path), deduplicate=True)
    docline_namespace: dict[str, Any] = {"openapi": openapi_meta}
    if links:
        docline_namespace["cross_doc_links"] = [dict(link) for link in links]

    frontmatter = BaseFrontmatter(
        title=title or relative_path,
        source=source,
        ingested_at=ingested_at,
        doc_type=doc_type,
        source_path=source_path,
        docline=docline_namespace,
    )
    return BaseDocument(frontmatter=frontmatter, body=body)


def _doc_source_path(spec_source_path: str, relative_path: str) -> str:
    """Return a unique ``source_path`` for one doc emitted from a multi-doc spec.

    graphtor treats ``source_path`` as canonical identity and rejects
    duplicates, so every document produced from a single spec must carry a
    distinct value. Combines the spec path's stem with the document's
    spec-relative path (e.g. ``spark/definitions.json`` +
    ``operations/getFoo.md`` -> ``spark/definitions/operations/getFoo.md``).
    When no spec source_path is known (single-file ingest), the already-unique
    per-doc ``relative_path`` is used directly.
    """
    if not spec_source_path:
        return relative_path
    # Normalize any backslashes so a Windows-style spec path splits correctly;
    # ``with_suffix("")`` safely returns the path unchanged for extensionless
    # names, so this does not raise on specs without a file extension.
    stem = PurePosixPath(spec_source_path.replace("\\", "/")).with_suffix("")
    return f"{stem.as_posix()}/{relative_path}"


def read_openapi_spec(
    source: str | Path,
    *,
    source_uri: str | None = None,
    source_path: str = "",
    corpus_root: str | Path | None = None,
) -> list[OpenApiDocument]:
    """Render an OpenAPI 3.x specification into assembled BaseDocuments.

    Args:
        source: Path to the specification file, given as a :class:`Path` or a
            path string. The file is loaded from disk and parsed as JSON or YAML.
        source_uri: Base URI recorded in each document's ``source`` field. When
            omitted, the spec path's POSIX form is used.
        source_path: Project-relative POSIX path of the spec artifact, recorded
            as ``source_path`` on every emitted document.
        corpus_root: When provided, enables external/split-file ``$ref``
            cross-linking (053-F): refs to other spec files under this root are
            resolved (path-contained; URL refs denied) and emitted as relative
            Markdown links to the schema docs those files produce. When ``None``,
            only local (in-file) refs are linked.

    Returns:
        One :class:`OpenApiDocument` per operation (``operations/{id}.md``) and
        per named component schema (``schemas/{name}.md``), in stable order.

    Raises:
        OpenApiError: If the spec root is neither OpenAPI 3.x nor Swagger 2.0.
        OpenApiParseError: If the spec cannot be read or parsed.
        OpenApiRefError: If a local ``$ref`` is unresolvable or cyclic.
    """
    path = source if isinstance(source, Path) else Path(source)
    spec = load_spec(path)

    swagger = spec.get("swagger")
    if isinstance(swagger, str) and swagger.startswith("2."):
        # Pre-convert Swagger 2.0 to OpenAPI 3.x, then render via the same path
        # (051-F). External/split-file $ref resolution is layered on top (053-F).
        spec = swagger2_to_openapi3(spec)

    version = spec.get("openapi")
    if not (isinstance(version, str) and version.startswith("3.")):
        raise OpenApiError(
            "read_openapi_spec requires an OpenAPI 3.x or Swagger 2.0 root; "
            f"got openapi={version!r} swagger={swagger!r}"
        )

    linker = (
        CorpusRefLinker(referring_path=path.resolve(), corpus_root=Path(corpus_root))
        if corpus_root is not None
        else None
    )
    operation_ref_link = _make_ref_link(linker, "operations")
    schema_ref_link = _make_ref_link(linker, "schemas")

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
                relative_path = _unique(f"operations/{slug(operation_id)}.md", seen_paths)
                body = render_operation(
                    method, path_str, operation, root=spec, ref_link=operation_ref_link
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
                            source_path=_doc_source_path(source_path, relative_path),
                            ingested_at=ingested_at,
                            openapi_meta={
                                "method": method.upper(),
                                "path": path_str,
                                "operation_id": operation_id,
                            },
                            cross_link_path=(
                                f"{linker.referring_basename}/{relative_path}"
                                if linker is not None
                                else None
                            ),
                        ),
                    )
                )

    components = spec.get("components")
    schemas = components.get("schemas") if isinstance(components, Mapping) else None
    if isinstance(schemas, Mapping):
        for name, schema in schemas.items():
            if not isinstance(schema, Mapping):
                continue
            relative_path = _unique(f"schemas/{slug(str(name))}.md", seen_paths)
            body = render_schema(str(name), schema, root=spec, ref_link=schema_ref_link)
            documents.append(
                OpenApiDocument(
                    relative_path,
                    _assemble_document(
                        relative_path=relative_path,
                        title=str(name),
                        source=f"{base_uri}#/components/schemas/{name}",
                        doc_type=SCHEMA_DOC_TYPE,
                        body=body,
                        source_path=_doc_source_path(source_path, relative_path),
                        ingested_at=ingested_at,
                        openapi_meta={"schema_name": str(name)},
                        cross_link_path=(
                            f"{linker.referring_basename}/{relative_path}"
                            if linker is not None
                            else None
                        ),
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
