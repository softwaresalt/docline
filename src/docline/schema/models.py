"""Schema core models for docline documents."""

from datetime import datetime

from pydantic import BaseModel, field_validator


class DoclineError(Exception):
    """Base exception for all docline errors."""


class SchemaValidationError(DoclineError):
    """Raised when a document schema validation fails."""


class BaseFrontmatter(BaseModel):
    """Common frontmatter fields shared across all document types.

    Attributes:
        title: Human-readable document title. Must be non-empty.
        source: Origin URI or path of the document. Must be non-empty.
        ingested_at: Timestamp when the document was ingested.
        doc_type: Document type identifier. Must be non-empty.
    """

    title: str
    source: str
    ingested_at: datetime
    doc_type: str

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
