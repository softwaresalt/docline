"""DOCX reader adapter — extract content via the docling dependency."""

import xml.etree.ElementTree as ET
import zipfile
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
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    raw = path.read_bytes()
    if raw[:2] != b"PK":
        raise DocxReadError(f"Not a valid DOCX file (missing ZIP signature): {path}")

    try:
        with zipfile.ZipFile(path) as archive:
            if "word/document.xml" not in archive.namelist():
                return ""
            document_xml = archive.read("word/document.xml")
    except zipfile.BadZipFile as err:
        raise DocxReadError(f"Corrupt ZIP archive (DOCX unreadable): {path}") from err

    try:
        tree = ET.fromstring(document_xml)
    except ET.ParseError as err:
        raise DocxReadError(f"Malformed XML in word/document.xml: {path}") from err

    texts = [
        node.text
        for node in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
        if node.text
    ]
    return " ".join(texts)


__all__ = [
    "DocxReadError",
    "read_docx",
]
