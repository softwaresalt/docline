"""Tests for transcript and web document schemas."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from docline.schema.library import (
    TranscriptDocument,
    TranscriptFrontmatter,
    WebDocument,
    WebFrontmatter,
)


def _base_fields() -> dict:
    return {"title": "My Doc", "source": "http://example.com", "ingested_at": datetime(2024, 1, 1)}


def test_transcript_frontmatter_doc_type_literal() -> None:
    """TranscriptFrontmatter doc_type is always 'transcript'."""
    fm = TranscriptFrontmatter(**_base_fields())
    assert fm.doc_type == "transcript"


def test_transcript_frontmatter_default_speaker_count() -> None:
    """TranscriptFrontmatter speaker_count defaults to 0."""
    fm = TranscriptFrontmatter(**_base_fields())
    assert fm.speaker_count == 0


def test_transcript_frontmatter_default_duration() -> None:
    """TranscriptFrontmatter duration_seconds defaults to 0.0."""
    fm = TranscriptFrontmatter(**_base_fields())
    assert fm.duration_seconds == 0.0


def test_transcript_frontmatter_accepts_values() -> None:
    """TranscriptFrontmatter accepts speaker_count and duration_seconds."""
    fm = TranscriptFrontmatter(**_base_fields(), speaker_count=3, duration_seconds=3600.5)
    assert fm.speaker_count == 3
    assert fm.duration_seconds == 3600.5


def test_transcript_document_valid_construction() -> None:
    """TranscriptDocument accepts valid TranscriptFrontmatter and body."""
    fm = TranscriptFrontmatter(**_base_fields(), speaker_count=2)
    doc = TranscriptDocument(frontmatter=fm, body="[Speaker A]: Hello")
    assert doc.frontmatter.doc_type == "transcript"
    assert doc.body == "[Speaker A]: Hello"


def test_web_frontmatter_doc_type_literal() -> None:
    """WebFrontmatter doc_type is always 'web'."""
    fm = WebFrontmatter(**_base_fields(), source_url="https://example.com/page")
    assert fm.doc_type == "web"


def test_web_frontmatter_default_crawl_depth() -> None:
    """WebFrontmatter crawl_depth defaults to 0."""
    fm = WebFrontmatter(**_base_fields(), source_url="https://example.com")
    assert fm.crawl_depth == 0


def test_web_frontmatter_accepts_https_url() -> None:
    """WebFrontmatter accepts https:// URLs."""
    fm = WebFrontmatter(**_base_fields(), source_url="https://docs.example.com/api")
    assert fm.source_url == "https://docs.example.com/api"


def test_web_frontmatter_accepts_http_url() -> None:
    """WebFrontmatter accepts http:// URLs."""
    fm = WebFrontmatter(**_base_fields(), source_url="http://example.com")
    assert fm.source_url == "http://example.com"


def test_web_frontmatter_invalid_url_raises() -> None:
    """WebFrontmatter raises ValidationError for non-http(s) URL."""
    with pytest.raises(ValidationError):
        WebFrontmatter(**_base_fields(), source_url="ftp://example.com/file")


def test_web_frontmatter_bare_path_raises() -> None:
    """WebFrontmatter raises ValidationError for bare file paths."""
    with pytest.raises(ValidationError):
        WebFrontmatter(**_base_fields(), source_url="/local/path/file.html")


def test_web_frontmatter_uses_source_url_field_in_schema() -> None:
    """WebFrontmatter JSON schema exposes source_url instead of url."""
    schema = WebFrontmatter.model_json_schema()
    assert "source_url" in schema["properties"]
    assert "url" not in schema["properties"]


def test_web_document_valid_construction() -> None:
    """WebDocument accepts valid WebFrontmatter and body."""
    fm = WebFrontmatter(**_base_fields(), source_url="https://example.com", crawl_depth=1)
    doc = WebDocument(frontmatter=fm, body="Page content")
    assert doc.frontmatter.doc_type == "web"
    assert doc.frontmatter.crawl_depth == 1
