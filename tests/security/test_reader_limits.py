"""Test harness for 003.006-T — Enforce reader safety limits.

Acceptance criteria:
- validate_document_input() returns None for valid files within limits.
- Raises ReaderLimitExceededError for oversized files.
- Raises ReaderLimitExceededError for disallowed MIME types.
- Raises UntrustedSourceError for PDF/DOCX without trusted=True.
- ReaderLimits defaults are safe and explicit.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests assert return values or typed exceptions (FAIL in red phase).
"""

from pathlib import Path

import pytest

from docline.readers.limits import (
    DEFAULT_MAX_BYTES,
    TRUSTED_LOCAL_ONLY_TYPES,
    ReaderLimitExceededError,
    ReaderLimits,
    UntrustedSourceError,
    validate_document_input,
)
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Structural: error hierarchy and constants (PASS in red phase)
# ---------------------------------------------------------------------------


def test_reader_limit_exceeded_error_is_docline_error() -> None:
    """ReaderLimitExceededError is a subclass of DoclineError."""
    err = ReaderLimitExceededError("too large")
    assert isinstance(err, DoclineError)


def test_untrusted_source_error_is_docline_error() -> None:
    """UntrustedSourceError is a subclass of DoclineError."""
    err = UntrustedSourceError("untrusted source")
    assert isinstance(err, DoclineError)


def test_trusted_local_only_contains_pdf_mime() -> None:
    """TRUSTED_LOCAL_ONLY_TYPES includes the PDF MIME type."""
    assert "application/pdf" in TRUSTED_LOCAL_ONLY_TYPES


def test_trusted_local_only_contains_docx_mime() -> None:
    """TRUSTED_LOCAL_ONLY_TYPES includes the DOCX MIME type."""
    assert (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        in TRUSTED_LOCAL_ONLY_TYPES
    )


def test_reader_limits_default_max_bytes_matches_constant() -> None:
    """ReaderLimits default max_bytes matches DEFAULT_MAX_BYTES."""
    limits = ReaderLimits()
    assert limits.max_bytes == DEFAULT_MAX_BYTES


def test_reader_limits_default_trusted_local_only_true() -> None:
    """ReaderLimits defaults trusted_local_only to True."""
    limits = ReaderLimits()
    assert limits.trusted_local_only is True


def test_reader_limits_default_allowed_mime_empty() -> None:
    """ReaderLimits default allowed_mime_types is empty (all MIME types accepted)."""
    limits = ReaderLimits()
    assert len(limits.allowed_mime_types) == 0


def test_reader_limits_custom_max_bytes() -> None:
    """ReaderLimits accepts a custom max_bytes."""
    limits = ReaderLimits(max_bytes=1024)
    assert limits.max_bytes == 1024


# ---------------------------------------------------------------------------
# Behavioral: validate_document_input (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_validate_document_input_returns_none_for_valid_file(tmp_path: Path) -> None:
    """validate_document_input returns None for a valid file within limits."""
    doc = tmp_path / "sample.txt"
    doc.write_text("hello world", encoding="utf-8")
    result = validate_document_input(doc, ReaderLimits())
    assert result is None


def test_validate_document_input_raises_for_oversized_file(tmp_path: Path) -> None:
    """validate_document_input raises ReaderLimitExceededError for oversized files."""
    doc = tmp_path / "big.txt"
    doc.write_bytes(b"x" * 200)
    limits = ReaderLimits(max_bytes=100)
    with pytest.raises(ReaderLimitExceededError):
        validate_document_input(doc, limits)


def test_validate_document_input_raises_for_disallowed_mime(tmp_path: Path) -> None:
    """validate_document_input raises ReaderLimitExceededError for disallowed MIME."""
    doc = tmp_path / "sample.xyz"
    doc.write_bytes(b"content")
    limits = ReaderLimits(allowed_mime_types=frozenset({"text/plain"}))
    with pytest.raises(ReaderLimitExceededError):
        validate_document_input(doc, limits, mime_hint="application/octet-stream")


def test_validate_document_input_raises_for_untrusted_pdf(tmp_path: Path) -> None:
    """validate_document_input raises UntrustedSourceError for PDF without trust."""
    doc = tmp_path / "remote.pdf"
    doc.write_bytes(b"%PDF-1.4 content")
    with pytest.raises(UntrustedSourceError):
        validate_document_input(
            doc,
            ReaderLimits(trusted_local_only=True),
            mime_hint="application/pdf",
            trusted=False,
        )


def test_validate_document_input_raises_for_untrusted_docx(tmp_path: Path) -> None:
    """validate_document_input raises UntrustedSourceError for DOCX without trust."""
    doc = tmp_path / "remote.docx"
    doc.write_bytes(b"PK\x03\x04minimal docx")
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    with pytest.raises(UntrustedSourceError):
        validate_document_input(
            doc,
            ReaderLimits(trusted_local_only=True),
            mime_hint=docx_mime,
            trusted=False,
        )


def test_validate_document_input_accepts_trusted_pdf(tmp_path: Path) -> None:
    """validate_document_input returns None for trusted PDF within limits."""
    doc = tmp_path / "local.pdf"
    doc.write_bytes(b"%PDF-1.4 content")
    result = validate_document_input(
        doc,
        ReaderLimits(trusted_local_only=True),
        mime_hint="application/pdf",
        trusted=True,
    )
    assert result is None
