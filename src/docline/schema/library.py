"""Extended document schemas for wiki, ADR, transcript, and web document types."""

from typing import Literal

from pydantic import field_validator

from docline.schema.models import BaseDocument, BaseFrontmatter

_ADR_STATUSES = {"proposed", "accepted", "deprecated", "superseded"}


class WikiFrontmatter(BaseFrontmatter):
    """Frontmatter for wiki-style documents.

    Attributes:
        doc_type: Always ``"wiki"``.
        tags: Optional list of categorisation tags.
        section: Optional wiki section or category name.
    """

    doc_type: Literal["wiki"] = "wiki"
    tags: list[str] = []
    section: str = ""


class WikiDocument(BaseDocument):
    """A wiki document with WikiFrontmatter.

    Attributes:
        frontmatter: Wiki-specific metadata.
        body: Markdown body content.
    """

    frontmatter: WikiFrontmatter  # type: ignore[assignment]


class AdrFrontmatter(BaseFrontmatter):
    """Frontmatter for Architecture Decision Record documents.

    Attributes:
        doc_type: Always ``"adr"``.
        status: ADR lifecycle status. Must be one of ``proposed``, ``accepted``,
            ``deprecated``, or ``superseded``.
        decision_date: ISO date string when the decision was made.
    """

    doc_type: Literal["adr"] = "adr"
    status: str
    decision_date: str = ""

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


class TranscriptFrontmatter(BaseFrontmatter):
    """Frontmatter for transcript documents (.vtt, .srt).

    Attributes:
        doc_type: Always ``"transcript"``.
        speaker_count: Number of distinct speakers in the transcript.
        duration_seconds: Total duration of the source recording in seconds.
    """

    doc_type: Literal["transcript"] = "transcript"
    speaker_count: int = 0
    duration_seconds: float = 0.0


class TranscriptDocument(BaseDocument):
    """A transcript document with TranscriptFrontmatter.

    Attributes:
        frontmatter: Transcript-specific metadata.
        body: Markdown body content.
    """

    frontmatter: TranscriptFrontmatter  # type: ignore[assignment]


class WebFrontmatter(BaseFrontmatter):
    """Frontmatter for web-crawled documents.

    Attributes:
        doc_type: Always ``"web"``.
        url: Source URL. Must start with ``http://`` or ``https://``.
        crawl_depth: Depth at which this page was discovered during crawling.
    """

    doc_type: Literal["web"] = "web"
    url: str
    crawl_depth: int = 0

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return value


class WebDocument(BaseDocument):
    """A web document with WebFrontmatter.

    Attributes:
        frontmatter: Web-specific metadata.
        body: Markdown body content.
    """

    frontmatter: WebFrontmatter  # type: ignore[assignment]
