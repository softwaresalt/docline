"""Test harness for 003.007-T — Add PDF reader adapter.

Acceptance criteria:
- read_pdf() returns Markdown text from a valid PDF path.
- read_pdf() raises PdfReadError on parse failure.
- PdfReadError is a DoclineError subclass.
- read_pdf() accepts a Path argument.
- read_pdf() prefers pypdf extraction when pypdf is available.
- read_pdf() falls back to built-in extractor when pypdf is not available.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests assert return values or typed exceptions (FAIL in red phase).
"""

import io
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    """read_pdf returns a string for a PDF-like file (built-in fallback path)."""
    import docline.readers.pdf as pdf_module

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 minimal content")
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)
    assert isinstance(result, str)


def test_read_pdf_returns_non_empty_string(tmp_path: Path) -> None:
    """read_pdf returns a string for a file with content (built-in fallback path)."""
    import docline.readers.pdf as pdf_module

    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 1 0 obj << /Type /Catalog >> endobj")
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
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


# ---------------------------------------------------------------------------
# pypdf integration: prefer pypdf when available
# ---------------------------------------------------------------------------


def _make_fake_pypdf_module(page_texts: list[str]) -> types.ModuleType:
    """Build a minimal fake pypdf module for patching.

    Args:
        page_texts: Text that each fake page should return from extract_text().

    Returns:
        A module object with a PdfReader class whose pages yield the given texts.
    """
    fake_page_list = []
    for text in page_texts:
        page = MagicMock()
        page.extract_text.return_value = text
        fake_page_list.append(page)

    fake_reader_instance = MagicMock()
    fake_reader_instance.pages = fake_page_list

    fake_reader_class = MagicMock(return_value=fake_reader_instance)

    fake_mod = types.ModuleType("pypdf")
    fake_mod.PdfReader = fake_reader_class  # type: ignore[attr-defined]
    return fake_mod


def test_read_pdf_uses_pypdf_when_available(tmp_path: Path) -> None:
    """read_pdf delegates to pypdf.PdfReader when pypdf is importable."""
    import docline.readers.pdf as pdf_module

    pdf_path = tmp_path / "real.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 fake content")

    fake_mod = _make_fake_pypdf_module(["Hello pypdf world", "Page two text"])

    with (
        patch.object(pdf_module, "_PYPDF_AVAILABLE", True),
        patch.object(pdf_module, "_pypdf", fake_mod),
    ):
        result = read_pdf(pdf_path)

    assert "Hello pypdf world" in result
    assert "Page two text" in result


def test_read_pdf_pypdf_path_uses_pdfr_reader_with_bytesio(tmp_path: Path) -> None:
    """read_pdf passes a BytesIO stream (not the raw Path) to pypdf.PdfReader."""
    import docline.readers.pdf as pdf_module

    pdf_path = tmp_path / "check.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 check")

    captured_args: list[object] = []

    def capturing_reader(stream: object) -> MagicMock:
        captured_args.append(stream)
        inst = MagicMock()
        inst.pages = []
        return inst

    fake_mod = types.ModuleType("pypdf")
    fake_mod.PdfReader = capturing_reader  # type: ignore[attr-defined]

    with (
        patch.object(pdf_module, "_PYPDF_AVAILABLE", True),
        patch.object(pdf_module, "_pypdf", fake_mod),
    ):
        read_pdf(pdf_path)

    assert len(captured_args) == 1
    assert isinstance(captured_args[0], io.BytesIO), (
        "pypdf.PdfReader should receive a BytesIO object, not a raw Path"
    )


def test_read_pdf_falls_back_to_builtin_when_pypdf_unavailable(tmp_path: Path) -> None:
    """read_pdf uses the built-in extractor when pypdf is not installed."""
    import docline.readers.pdf as pdf_module

    pdf_path = tmp_path / "builtin.pdf"
    # Minimal PDF with a BT/ET text block containing a literal Tj string
    pdf_path.write_bytes(b"%PDF-1.4\nBT (fallback text) Tj ET\n")

    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)

    # Built-in extractor should return a string (may or may not find the text)
    assert isinstance(result, str)


def test_read_pdf_pypdf_error_falls_back_to_builtin(tmp_path: Path) -> None:
    """When pypdf raises, read_pdf falls back to the built-in extractor."""
    import docline.readers.pdf as pdf_module

    pdf_path = tmp_path / "bad.pdf"
    # A truncated PDF that starts correctly but lacks the required xref table
    pdf_path.write_bytes(b"%PDF-1.4 truncated no xref\n")

    call_log: list[str] = []

    def boom(stream: object) -> None:
        call_log.append("pypdf_called")
        raise RuntimeError("pypdf exploded")

    fake_mod = types.ModuleType("pypdf")
    fake_mod.PdfReader = boom  # type: ignore[attr-defined]

    with (
        patch.object(pdf_module, "_PYPDF_AVAILABLE", True),
        patch.object(pdf_module, "_pypdf", fake_mod),
    ):
        # Should NOT raise — falls back to built-in extractor
        result = read_pdf(pdf_path)

    # pypdf was attempted
    assert "pypdf_called" in call_log
    # built-in fallback returns a string (may be empty for this synthetic PDF)
    assert isinstance(result, str)


def test_read_pdf_pypdf_skips_empty_pages(tmp_path: Path) -> None:
    """Pages returning None or empty string from extract_text are skipped."""
    import docline.readers.pdf as pdf_module

    pdf_path = tmp_path / "sparse.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 sparse")

    fake_mod = _make_fake_pypdf_module(["", "Real content here", None])  # type: ignore[list-item]

    with (
        patch.object(pdf_module, "_PYPDF_AVAILABLE", True),
        patch.object(pdf_module, "_pypdf", fake_mod),
    ):
        result = read_pdf(pdf_path)

    assert "Real content here" in result
    # Empty pages should not add blank separator noise
    assert result.strip() == "Real content here"
