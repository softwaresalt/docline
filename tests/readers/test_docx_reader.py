"""Test harness for 003.008-T — Add DOCX reader adapter.

Acceptance criteria:
- read_docx() returns Markdown text from a valid DOCX path.
- read_docx() raises DocxReadError on parse failure.
- DocxReadError is a DoclineError subclass.
- read_docx() accepts a Path argument.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests assert return values or typed exceptions (FAIL in red phase).
"""

from pathlib import Path

import pytest

from docline.readers.docx import DocxReadError, read_docx
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Structural: error hierarchy (PASS in red phase)
# ---------------------------------------------------------------------------


def test_docx_read_error_is_docline_error() -> None:
    """DocxReadError is a subclass of DoclineError."""
    err = DocxReadError("DOCX parse failed")
    assert isinstance(err, DoclineError)


# ---------------------------------------------------------------------------
# Behavioral: read_docx (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_read_docx_returns_string(tmp_path: Path) -> None:
    """read_docx returns a string for a DOCX-like file."""
    docx_path = tmp_path / "sample.docx"
    docx_path.write_bytes(b"PK\x03\x04minimal docx content")
    result = read_docx(docx_path)
    assert isinstance(result, str)


def test_read_docx_returns_string_for_zip_file(tmp_path: Path) -> None:
    """read_docx returns a string for a ZIP-based DOCX file."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
    docx_path = tmp_path / "minimal.docx"
    docx_path.write_bytes(buf.getvalue())
    result = read_docx(docx_path)
    assert isinstance(result, str)


def test_read_docx_raises_for_nonexistent_file(tmp_path: Path) -> None:
    """read_docx raises FileNotFoundError for a non-existent path."""
    docx_path = tmp_path / "missing.docx"
    with pytest.raises(FileNotFoundError):
        read_docx(docx_path)


def test_read_docx_raises_for_corrupt_file(tmp_path: Path) -> None:
    """read_docx raises DocxReadError for a corrupt or non-DOCX file."""
    docx_path = tmp_path / "corrupt.docx"
    docx_path.write_bytes(b"\x00\x01\x02 not a zip at all GARBAGE DATA")
    with pytest.raises(DocxReadError):
        read_docx(docx_path)
