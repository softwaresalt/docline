"""Failing harness tests for deterministic document identity."""

from uuid import UUID

from docline.process.identity import canonical_source_key, derive_document_uuid
from docline.types import SourceInput, SourceKind


def _source(kind: SourceKind, raw: str) -> SourceInput:
    return SourceInput(kind=kind, raw=raw)


def test_derive_document_uuid_is_deterministic_for_same_source() -> None:
    source = _source(SourceKind.URL, "https://docs.example.com/wiki/architecture")
    first = derive_document_uuid(source)
    second = derive_document_uuid(source)
    assert first == second


def test_derive_document_uuid_changes_for_different_sources() -> None:
    first = derive_document_uuid(
        _source(SourceKind.URL, "https://docs.example.com/wiki/architecture")
    )
    second = derive_document_uuid(_source(SourceKind.URL, "https://docs.example.com/wiki/runtime"))
    assert first != second


def test_canonical_source_key_derives_a_stable_identifier() -> None:
    key = canonical_source_key(_source(SourceKind.FILE, "docs/adr/0001-record-architecture.md"))
    assert isinstance(key, str)
    assert key == "file:docs/adr/0001-record-architecture.md"


def test_canonical_source_key_normalizes_file_like_path_separators() -> None:
    file_key = canonical_source_key(
        _source(SourceKind.FILE, r"docs\adr\0001-record-architecture.md")
    )
    transcript_key = canonical_source_key(
        _source(SourceKind.TRANSCRIPT, r"meetings\weekly-sync.vtt")
    )
    assert file_key == "file:docs/adr/0001-record-architecture.md"
    assert transcript_key == "transcript:meetings/weekly-sync.vtt"


def test_derive_document_uuid_returns_a_uuid_instance() -> None:
    document_uuid = derive_document_uuid(_source(SourceKind.TRANSCRIPT, "meetings/weekly-sync.vtt"))
    assert isinstance(document_uuid, UUID)
