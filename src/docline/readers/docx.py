"""DOCX reader adapter — extract content via the docling dependency."""

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from docline.schema.models import DoclineError


class DocxReadError(DoclineError):
    """Raised when DOCX extraction fails."""


_WORDPROCESSING_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _load_docx_tree(path: Path) -> ET.Element:
    """Load and parse the DOCX document XML tree.

    Args:
        path: Path to the DOCX file.

    Returns:
        Parsed XML root element.

    Raises:
        DocxReadError: If the archive or XML payload is invalid.
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
                return ET.Element("document")
            document_xml = archive.read("word/document.xml")
    except zipfile.BadZipFile as err:
        raise DocxReadError(f"Corrupt ZIP archive (DOCX unreadable): {path}") from err

    try:
        return ET.fromstring(document_xml)
    except ET.ParseError as err:
        raise DocxReadError(f"Malformed XML in word/document.xml: {path}") from err


def read_docx_blocks(path: Path) -> list[str]:
    """Extract ordered text blocks from a DOCX file.

    Args:
        path: Path to the DOCX file. Must be a trusted-local path.

    Returns:
        Ordered non-empty paragraph blocks.

    Raises:
        DocxReadError: If DOCX parsing fails.
        FileNotFoundError: If ``path`` does not exist.
    """
    tree = _load_docx_tree(path)
    blocks: list[str] = []
    for paragraph in tree.iter(f"{_WORDPROCESSING_NS}p"):
        texts = [node.text for node in paragraph.iter(f"{_WORDPROCESSING_NS}t") if node.text]
        block = "".join(texts).strip()
        if block:
            blocks.append(block)
    return blocks


def read_docx(path: Path) -> str:
    """Extract text content from a DOCX file and return it as Markdown.

    Reads ``word/document.xml`` from the DOCX ZIP archive and joins extracted
    paragraph text blocks with blank lines.

    Args:
        path: Path to the DOCX file.  Must be a trusted-local path; remote
            content must be staged locally before calling this function.

    Returns:
        Markdown text extracted from the DOCX.

    Raises:
        DocxReadError: If DOCX parsing fails.
        FileNotFoundError: If ``path`` does not exist.
    """
    return "\n\n".join(read_docx_blocks(path))


__all__ = [
    "DocxReadError",
    "read_docx_blocks",
    "read_docx",
]
