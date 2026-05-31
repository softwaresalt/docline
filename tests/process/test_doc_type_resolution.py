"""Failing harness tests for staged document-type resolution."""

import pytest

from docline.process.metadata import resolve_document_type
from docline.schema.library import (
    AdrFrontmatter,
    TranscriptFrontmatter,
    WebFrontmatter,
    WikiFrontmatter,
)
from docline.schema.models import DoclineError
from docline.types import SourceInput, SourceKind


def _source(kind: SourceKind, raw: str) -> SourceInput:
    return SourceInput(kind=kind, raw=raw)


def test_resolve_document_type_for_wiki_sources() -> None:
    schema_family = resolve_document_type(
        _source(SourceKind.URL, "https://docs.example.com/wiki/architecture"),
        {"content_type": "text/html", "title": "Architecture Wiki"},
    )
    assert schema_family is WikiFrontmatter


def test_resolve_document_type_for_adr_sources() -> None:
    schema_family = resolve_document_type(
        _source(SourceKind.FILE, "docs/adr/0002-record-ingestion.md"),
        {"content_type": "text/markdown", "title": "ADR 0002"},
    )
    assert schema_family is AdrFrontmatter


def test_resolve_document_type_for_transcript_sources() -> None:
    schema_family = resolve_document_type(
        _source(SourceKind.TRANSCRIPT, "meetings/weekly-sync.vtt"),
        {"content_type": "text/vtt", "title": "Weekly Sync"},
    )
    assert schema_family is TranscriptFrontmatter


def test_resolve_document_type_for_web_document_sources() -> None:
    schema_family = resolve_document_type(
        _source(SourceKind.URL, "https://example.com/reference/runtime"),
        {"content_type": "text/html", "title": "Runtime Reference"},
    )
    assert schema_family is WebFrontmatter


def test_resolve_document_type_rejects_unknown_sources() -> None:
    with pytest.raises(DoclineError):
        resolve_document_type(
            _source(SourceKind.UNKNOWN, "notes/random.txt"),
            {"content_type": "text/plain", "title": "Random Note"},
        )
