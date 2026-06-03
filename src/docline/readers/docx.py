"""DOCX reader adapter — extract Markdown content from DOCX archives.

Uses the XXE-safe ``defusedxml`` parser for ``word/document.xml`` (P2-1
security advisory carried over from F4 planning). Maps Word heading
styles (``<w:pStyle w:val="HeadingN"/>``) to ATX Markdown headings.
"""

import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import ParseError as DefusedParseError
from defusedxml.ElementTree import fromstring as _defused_fromstring

from docline.schema.models import DoclineError


class DocxReadError(DoclineError):
    """Raised when DOCX extraction fails."""


_WORDPROCESSING_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_PARA_TAG = f"{_WORDPROCESSING_NS}p"
_TEXT_TAG = f"{_WORDPROCESSING_NS}t"
_PPR_TAG = f"{_WORDPROCESSING_NS}pPr"
_PSTYLE_TAG = f"{_WORDPROCESSING_NS}pStyle"
_PSTYLE_VAL_ATTR = f"{_WORDPROCESSING_NS}val"


def _load_docx_tree(path: Path) -> Element:
    """Load and parse the DOCX document XML tree using an XXE-safe parser.

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
                return Element("document")
            document_xml = archive.read("word/document.xml")
    except zipfile.BadZipFile as err:
        raise DocxReadError(f"Corrupt ZIP archive (DOCX unreadable): {path}") from err

    try:
        return _defused_fromstring(document_xml)
    except DefusedParseError as err:
        raise DocxReadError(f"Malformed XML in word/document.xml: {path}") from err


def _normalize_style(value: str) -> str:
    """Normalize a Word style identifier for matching.

    Lowercases the value and strips spaces and underscores so common Word
    variants like ``Heading1``, ``heading 1``, and ``Heading_1`` collapse
    to a single canonical key (``heading1``).
    """
    return value.replace(" ", "").replace("_", "").lower()


def _heading_level(style_val: str | None) -> int | None:
    """Return the ATX heading level (1-6) for a pStyle value, else ``None``.

    Accepts common Word heading aliases. Levels outside 1-6 (e.g.,
    ``Heading7``) are not valid Markdown ATX headings and return ``None``.
    """
    if not style_val:
        return None
    normalized = _normalize_style(style_val)
    if not normalized.startswith("heading"):
        return None
    suffix = normalized[len("heading") :]
    if not suffix.isdigit():
        return None
    level = int(suffix)
    if 1 <= level <= 6:
        return level
    return None


def _paragraph_style(paragraph: Element) -> str | None:
    """Return the raw ``w:val`` of a paragraph's ``<w:pStyle>``, if present."""
    ppr = paragraph.find(_PPR_TAG)
    if ppr is None:
        return None
    pstyle = ppr.find(_PSTYLE_TAG)
    if pstyle is None:
        return None
    return pstyle.get(_PSTYLE_VAL_ATTR)


def _paragraph_text(paragraph: Element) -> str:
    """Concatenate all ``<w:t>`` text nodes in a paragraph in document order."""
    return "".join(node.text for node in paragraph.iter(_TEXT_TAG) if node.text)


def read_docx_blocks(path: Path) -> list[str]:
    """Extract ordered Markdown blocks from a DOCX file.

    Heading paragraphs whose ``<w:pStyle>`` resolves to a Word heading
    level 1-6 are emitted as ATX-prefixed strings (``# `` through
    ``###### ``). All other paragraphs (Normal, BodyText, unknown
    styles, or no style at all) are emitted as plain text. Empty
    paragraphs are skipped regardless of style.

    Args:
        path: Path to the DOCX file. Must be a trusted-local path.

    Returns:
        Ordered Markdown blocks suitable for joining with blank lines.

    Raises:
        DocxReadError: If DOCX parsing fails.
        FileNotFoundError: If ``path`` does not exist.
    """
    tree = _load_docx_tree(path)
    blocks: list[str] = []
    for paragraph in tree.iter(_PARA_TAG):
        text = _paragraph_text(paragraph).strip()
        if not text:
            continue
        level = _heading_level(_paragraph_style(paragraph))
        if level is not None:
            blocks.append(f"{'#' * level} {text}")
        else:
            blocks.append(text)
    return blocks


def read_docx(path: Path) -> str:
    """Extract text content from a DOCX file and return it as Markdown.

    Reads ``word/document.xml`` from the DOCX ZIP archive using an
    XXE-safe XML parser and joins extracted blocks with blank lines.
    Heading paragraphs (``<w:pStyle w:val="HeadingN"/>``, ``N`` in
    ``1..6``) are rendered as Markdown ATX headings.

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
