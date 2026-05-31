"""Tests for source router classification logic."""

from docline.router import classify_source
from docline.types import SourceInput, SourceKind


def test_classify_http_url() -> None:
    """HTTP URLs are classified as URL."""
    result = classify_source("http://example.com/doc.pdf")
    assert result.kind == SourceKind.URL
    assert result.raw == "http://example.com/doc.pdf"


def test_classify_https_url() -> None:
    """HTTPS URLs are classified as URL."""
    result = classify_source("https://example.com/page")
    assert result.kind == SourceKind.URL


def test_classify_vtt_transcript() -> None:
    """Files with .vtt extension are classified as TRANSCRIPT."""
    result = classify_source("meeting.vtt")
    assert result.kind == SourceKind.TRANSCRIPT


def test_classify_srt_transcript() -> None:
    """Files with .srt extension are classified as TRANSCRIPT."""
    result = classify_source("subtitles.srt")
    assert result.kind == SourceKind.TRANSCRIPT


def test_classify_vtt_with_path() -> None:
    """VTT files with path components are classified as TRANSCRIPT."""
    result = classify_source("/recordings/meeting.vtt")
    assert result.kind == SourceKind.TRANSCRIPT


def test_classify_pdf_file() -> None:
    """PDF files are classified as FILE."""
    result = classify_source("document.pdf")
    assert result.kind == SourceKind.FILE


def test_classify_docx_file() -> None:
    """DOCX files are classified as FILE."""
    result = classify_source("report.docx")
    assert result.kind == SourceKind.FILE


def test_classify_no_extension_file() -> None:
    """Files without extension are classified as FILE."""
    result = classify_source("README")
    assert result.kind == SourceKind.FILE


def test_classify_returns_source_input() -> None:
    """classify_source always returns a SourceInput instance."""
    result = classify_source("test.txt")
    assert isinstance(result, SourceInput)


def test_classify_raw_preserved() -> None:
    """The raw input string is preserved on SourceInput."""
    raw = "https://docs.example.com/api"
    result = classify_source(raw)
    assert result.raw == raw


def test_classify_uppercase_extension_as_file() -> None:
    """Uppercase .VTT is still treated as TRANSCRIPT."""
    result = classify_source("recording.VTT")
    assert result.kind == SourceKind.TRANSCRIPT


def test_classify_http_prefix_only() -> None:
    """Bare http:// prefix is classified as URL."""
    result = classify_source("http://localhost")
    assert result.kind == SourceKind.URL
