"""Document reader dispatcher — route files to the correct format adapter."""

from pathlib import Path

from docline.readers.limits import ReaderLimits
from docline.schema.models import DoclineError


class UnsupportedDocumentTypeError(DoclineError):
    """Raised when no adapter is available for the given document type."""


def read_document(
    path: Path,
    limits: ReaderLimits | None = None,
    *,
    mime_hint: str | None = None,
    trusted: bool = False,
) -> str:
    """Read a document file and return its content as Markdown text.

    Selects the appropriate adapter based on the file extension and
    ``mime_hint``, validates the input against ``limits``, and delegates
    to the adapter.

    Supported adapters:

    * ``.pdf`` / ``application/pdf`` → PDF adapter
    * ``.docx`` / DOCX MIME → DOCX adapter
    * ``.txt``, ``.md`` → plain-text adapter
    * ``.vtt`` → VTT transcript adapter

    Args:
        path: Path to the document file.
        limits: Reader safety limits.  Uses default :class:`~docline.readers.limits.ReaderLimits`
            when ``None``.
        mime_hint: Optional MIME type hint to override extension-based detection.
        trusted: Whether the source has been verified as trusted-local.

    Returns:
        Markdown text extracted from the document.

    Raises:
        UnsupportedDocumentTypeError: If no adapter matches the file type.
        ReaderLimitExceededError: If the file violates the safety limits.
        UntrustedSourceError: If a restricted type is submitted without trust.
    """
    raise NotImplementedError("stub: documents.read_document not yet implemented")


__all__ = [
    "UnsupportedDocumentTypeError",
    "read_document",
]
