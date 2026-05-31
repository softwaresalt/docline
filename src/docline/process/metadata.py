"""Metadata processing stubs for type resolution and frontmatter assembly."""

from collections.abc import Mapping

from pydantic import ValidationError

from docline.schema.library import (
    AdrFrontmatter,
    TranscriptFrontmatter,
    WebFrontmatter,
    WikiFrontmatter,
)
from docline.schema.models import BaseFrontmatter, DoclineError, SchemaValidationError
from docline.types import SourceInput, SourceKind


def resolve_document_type(
    source_input: SourceInput, staged_metadata: Mapping[str, object] | None = None
) -> type[BaseFrontmatter]:
    """Resolve a staged source into a schema family.

    Args:
        source_input: Classified staged source input.
        staged_metadata: Optional staged metadata used for schema-family resolution.

    Returns:
        The resolved frontmatter model type.

    Raises:
        DoclineError: If the source kind cannot be resolved.
    """
    del staged_metadata
    normalized_raw = source_input.raw.replace("\\", "/")

    if source_input.kind is SourceKind.UNKNOWN:
        raise DoclineError("Cannot resolve document type for unknown source kind")

    if source_input.kind is SourceKind.TRANSCRIPT:
        return TranscriptFrontmatter

    if source_input.kind is SourceKind.URL:
        if "/wiki/" in normalized_raw:
            return WikiFrontmatter
        return WebFrontmatter

    if source_input.kind is SourceKind.FILE:
        if "/adr/" in normalized_raw:
            return AdrFrontmatter
        return WikiFrontmatter

    raise DoclineError(f"Cannot resolve document type for source kind {source_input.kind.value!r}")


def assemble_frontmatter_payload(
    schema_family: type[BaseFrontmatter], staged_metadata: Mapping[str, object]
) -> BaseFrontmatter:
    """Build a validated frontmatter payload for a resolved schema family.

    Args:
        schema_family: Target frontmatter schema family.
        staged_metadata: Normalized staged metadata values.

    Returns:
        Validated frontmatter payload.

    Raises:
        SchemaValidationError: If the payload does not satisfy the schema.
    """
    try:
        return schema_family(**staged_metadata)
    except ValidationError as exc:
        raise SchemaValidationError(str(exc)) from exc


__all__ = ["assemble_frontmatter_payload", "resolve_document_type"]
