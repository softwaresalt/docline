"""Extended document schemas for wiki, ADR, transcript, and web document types.

Subclass-specific fields are kept as typed pydantic attributes for validation
and Python ergonomics, but they serialize under the ``docline:`` namespace
rather than at the top level so the persisted frontmatter conforms to the
graphtor-docs ingestion contract.
"""

from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import Field, field_validator, model_serializer

from docline.schema.models import BaseDocument, BaseFrontmatter

_ADR_STATUSES = {"proposed", "accepted", "deprecated", "superseded"}


class _DoclineNamespacedFrontmatter(BaseFrontmatter):
    """Mixin base that relocates subclass-specific fields under ``docline:``.

    Subclasses declare which of their own fields are docline-only via the
    ``DOCLINE_FIELDS`` ClassVar. ``model_dump`` then emits those values inside
    the ``docline`` mapping instead of as top-level frontmatter keys.
    """

    DOCLINE_FIELDS: ClassVar[tuple[str, ...]] = ()

    @model_serializer(mode="wrap")
    def _namespace_docline_fields(self, handler: Any) -> dict[str, Any]:
        dumped: dict[str, Any] = handler(self)
        namespace: dict[str, Any] = {}
        existing = dumped.get("docline")
        if isinstance(existing, dict):
            namespace.update(existing)
        for name in self.DOCLINE_FIELDS:
            if name in dumped:
                value = dumped.pop(name)
                # Drop None-valued optional fields so consumers only see
                # populated staging metadata (PA-1 / 010-S F7.T2).
                if value is None:
                    continue
                namespace[name] = value
        dumped["docline"] = namespace
        return dumped


class WikiFrontmatter(_DoclineNamespacedFrontmatter):
    """Frontmatter for wiki-style documents.

    Attributes:
        doc_type: Always ``"wiki"``.
        tags: Optional list of categorisation tags (docline-only namespace).
        section: Optional wiki section or category name (docline-only namespace).
    """

    doc_type: Literal["wiki"] = "wiki"  # type: ignore[override]
    tags: list[str] = []
    section: str = ""

    DOCLINE_FIELDS: ClassVar[tuple[str, ...]] = ("tags", "section")


class WikiDocument(BaseDocument):
    """A wiki document with WikiFrontmatter.

    Attributes:
        frontmatter: Wiki-specific metadata.
        body: Markdown body content.
    """

    frontmatter: WikiFrontmatter  # type: ignore[assignment]


class AdrFrontmatter(_DoclineNamespacedFrontmatter):
    """Frontmatter for Architecture Decision Record documents.

    Attributes:
        doc_type: Always ``"adr"``.
        status: ADR lifecycle status (docline-only namespace). Must be one of
            ``proposed``, ``accepted``, ``deprecated``, or ``superseded``.
        decision_date: ISO date string when the decision was made
            (docline-only namespace).
    """

    doc_type: Literal["adr"] = "adr"  # type: ignore[override]
    status: str
    decision_date: str = ""

    DOCLINE_FIELDS: ClassVar[tuple[str, ...]] = ("status", "decision_date")

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in _ADR_STATUSES:
            raise ValueError(f"status must be one of {sorted(_ADR_STATUSES)}, got {value!r}")
        return value


class AdrDocument(BaseDocument):
    """An Architecture Decision Record document with AdrFrontmatter.

    Attributes:
        frontmatter: ADR-specific metadata.
        body: Markdown body content.
    """

    frontmatter: AdrFrontmatter  # type: ignore[assignment]


class TranscriptFrontmatter(_DoclineNamespacedFrontmatter):
    """Frontmatter for transcript documents (.vtt, .srt).

    Attributes:
        doc_type: Always ``"transcript"``.
        speaker_count: Number of distinct speakers (docline-only namespace).
        duration_seconds: Total duration in seconds (docline-only namespace).
    """

    doc_type: Literal["transcript"] = "transcript"  # type: ignore[override]
    speaker_count: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0)

    DOCLINE_FIELDS: ClassVar[tuple[str, ...]] = ("speaker_count", "duration_seconds")


class TranscriptDocument(BaseDocument):
    """A transcript document with TranscriptFrontmatter.

    Attributes:
        frontmatter: Transcript-specific metadata.
        body: Markdown body content.
    """

    frontmatter: TranscriptFrontmatter  # type: ignore[assignment]


class WebFrontmatter(_DoclineNamespacedFrontmatter):
    """Frontmatter for web-crawled documents.

    Attributes:
        doc_type: Always ``"web"``.
        source_url: Source URL (docline-only namespace). Must start with
            ``http://`` or ``https://``.
        crawl_depth: Depth at which this page was discovered during crawling
            (docline-only namespace).
        http_status: Final HTTP status code observed on fetch (docline-only
            namespace). When set, must be a valid HTTP status code (``>= 100``).
        content_type: Final ``Content-Type`` header value reported by the
            origin (docline-only namespace).
        final_url: Post-redirect URL the response body was fetched from
            (docline-only namespace). When set, must use ``http://`` or
            ``https://``.
        fetched_at: Timestamp of the final fetch attempt (docline-only
            namespace).
    """

    doc_type: Literal["web"] = "web"  # type: ignore[override]
    source_url: str
    crawl_depth: int = Field(default=0, ge=0)
    http_status: int | None = Field(default=None, ge=100)
    content_type: str | None = None
    final_url: str | None = None
    fetched_at: datetime | None = None

    DOCLINE_FIELDS: ClassVar[tuple[str, ...]] = (
        "source_url",
        "crawl_depth",
        "http_status",
        "content_type",
        "final_url",
        "fetched_at",
    )

    @field_validator("source_url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        if not (value.lower().startswith("http://") or value.lower().startswith("https://")):
            raise ValueError("source_url must start with http:// or https://")
        return value

    @field_validator("final_url")
    @classmethod
    def _validate_final_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not (value.lower().startswith("http://") or value.lower().startswith("https://")):
            raise ValueError("final_url must start with http:// or https://")
        return value


class WebDocument(BaseDocument):
    """A web document with WebFrontmatter.

    Attributes:
        frontmatter: Web-specific metadata.
        body: Markdown body content.
    """

    frontmatter: WebFrontmatter  # type: ignore[assignment]
