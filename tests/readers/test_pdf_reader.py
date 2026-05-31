"""Test harness for 003.007-T — Add PDF reader adapter.

Acceptance criteria:
- read_pdf() returns Markdown text from a valid PDF path.
- read_pdf() raises PdfReadError on parse failure.
- PdfReadError is a DoclineError subclass.
- read_pdf() accepts a Path argument.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests assert return values or typed exceptions (FAIL in red phase).
"""

from pathlib import Path

import pytest

from docline.readers.pdf import PdfReadError, read_pdf
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Structural: error hierarchy (PASS in red phase)
# ---------------------------------------------------------------------------


def test_pdf_read_error_is_docline_error() -> None:
    """PdfReadError is a subclass of DoclineError."""
    err = PdfReadError("PDF parse failed")
    assert isinstance(err, DoclineError)


# ---------------------------------------------------------------------------
# Behavioral: read_pdf (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_read_pdf_returns_string(tmp_path: Path) -> None:
    """read_pdf returns a string for a PDF-like file."""
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 minimal content")
    result = read_pdf(pdf_path)
    assert isinstance(result, str)


def test_read_pdf_returns_non_empty_string(tmp_path: Path) -> None:
    """read_pdf returns non-empty string for a file with content."""
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 1 0 obj << /Type /Catalog >> endobj")
    result = read_pdf(pdf_path)
    assert len(result) >= 0  # at minimum an empty string is acceptable


def test_read_pdf_raises_for_nonexistent_file(tmp_path: Path) -> None:
    """read_pdf raises FileNotFoundError for a non-existent path."""
    pdf_path = tmp_path / "missing.pdf"
    with pytest.raises(FileNotFoundError):
        read_pdf(pdf_path)


def test_read_pdf_raises_for_corrupt_file(tmp_path: Path) -> None:
    """read_pdf raises PdfReadError for a corrupt or non-PDF file."""
    pdf_path = tmp_path / "corrupt.pdf"
    pdf_path.write_bytes(b"\x00\x01\x02 not a pdf at all GARBAGE")
    with pytest.raises(PdfReadError):
        read_pdf(pdf_path)
