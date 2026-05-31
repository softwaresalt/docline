"""DOCX reader adapter — extract content via the docling dependency."""

from pathlib import Path

from docline.schema.models import DoclineError


class DocxReadError(DoclineError):
    """Raised when DOCX extraction fails."""


def read_docx(path: Path) -> str:
    """Extract text content from a DOCX file and return it as Markdown.

    Requires the ``docling`` optional extra.  Raises
    :class:`~docline.dependencies.DependencyUnavailableError` if ``docling``
    is not installed.

    Args:
        path: Path to the DOCX file.  Must be a trusted-local path; remote
            content must be staged locally before calling this function.

    Returns:
        Markdown text extracted from the DOCX.

    Raises:
        DependencyUnavailableError: If ``docling`` is not installed.
        DocxReadError: If DOCX parsing fails.
        FileNotFoundError: If ``path`` does not exist.
    """
    raise NotImplementedError("stub: docx.read_docx not yet implemented")


__all__ = [
    "DocxReadError",
    "read_docx",
]
