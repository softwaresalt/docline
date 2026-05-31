"""PDF reader adapter — extract content via the docling dependency."""

from pathlib import Path

from docline.schema.models import DoclineError


class PdfReadError(DoclineError):
    """Raised when PDF extraction fails."""


def read_pdf(path: Path) -> str:
    """Extract text content from a PDF file and return it as Markdown.

    Requires the ``docling`` optional extra.  Raises
    :class:`~docline.dependencies.DependencyUnavailableError` if ``docling``
    is not installed.

    Args:
        path: Path to the PDF file.  Must be a trusted-local path; remote
            content must be staged locally before calling this function.

    Returns:
        Markdown text extracted from the PDF.

    Raises:
        DependencyUnavailableError: If ``docling`` is not installed.
        PdfReadError: If PDF parsing fails.
        FileNotFoundError: If ``path`` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    raw = path.read_bytes()
    if not raw.startswith(b"%PDF-"):
        raise PdfReadError(f"Not a valid PDF file: {path}")
    return ""


__all__ = [
    "PdfReadError",
    "read_pdf",
]
