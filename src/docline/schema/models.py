"""Schema core models for docline documents."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class DoclineError(Exception):
    """Base exception for all docline errors."""


class SchemaValidationError(DoclineError):
    """Raised when a document schema validation fails."""


class BaseFrontmatter(BaseModel):
    """Common frontmatter fields shared across all document types.

    The v1 schema extends the original fields with five additions required by
    the graphtor-docs ingestion contract plus a ``docline`` namespace for
    docline-only metadata that must not leak into the shared contract surface.

    Attributes:
        title: Human-readable document title. Must be non-empty.
        source: Origin URI or path of the document. Must be non-empty.
        ingested_at: Timestamp when the document was ingested.
        doc_type: Document type identifier. Must be non-empty.
        description: Short human-readable description. Defaults to "".
        content_sha256: SHA-256 hex digest over the assembled markdown body
            bytes. Populated by the assemble pipeline; defaults to "".
        source_path: Project-relative POSIX path of the source artifact.
            Populated by the assemble pipeline; defaults to "".
        chunk_strategy: Chunk-boundary strategy identifier. Defaults to
            ``"h1-h2-h3"``.
        schema_version: Semantic version of the frontmatter contract.
            Defaults to ``"1.0"``.
        docline: Optional namespace dict for docline-only metadata. Keys placed
            here are intentionally NOT promoted to top-level frontmatter fields
            so they cannot be mistaken for graphtor-contract fields.
    """

    title: str
    source: str
    ingested_at: datetime
    doc_type: str
    description: str = ""
    content_sha256: str = ""
    source_path: str = ""
    chunk_strategy: str = "h1-h2-h3"
    schema_version: str = "1.0"
    docline: dict[str, Any] | None = None

    @field_validator("title", "source", "doc_type")
    @classmethod
    def _must_be_non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("field must not be empty")
        return value


class BaseDocument(BaseModel):
    """A validated document with frontmatter and body.

    Attributes:
        frontmatter: Structured metadata for the document.
        body: Markdown body content of the document.
    """

    frontmatter: BaseFrontmatter
    body: str
