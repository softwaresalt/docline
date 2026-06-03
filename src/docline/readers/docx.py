"""DOCX reader adapter — extract Markdown content from DOCX archives.

Uses the XXE-safe ``defusedxml`` parser for ``word/document.xml`` and
``word/numbering.xml`` (P2-1 security advisory carried over from F4
planning). Maps Word heading styles (``<w:pStyle w:val="HeadingN"/>``)
to ATX Markdown headings and ``<w:numPr>`` paragraphs to GFM list
items with ``w:ilvl`` indentation.
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
_VAL_ATTR = f"{_WORDPROCESSING_NS}val"
_NUMPR_TAG = f"{_WORDPROCESSING_NS}numPr"
_NUMID_TAG = f"{_WORDPROCESSING_NS}numId"
_ILVL_TAG = f"{_WORDPROCESSING_NS}ilvl"
_NUM_TAG = f"{_WORDPROCESSING_NS}num"
_NUM_ID_ATTR = f"{_WORDPROCESSING_NS}numId"
_ABSTRACT_NUM_TAG = f"{_WORDPROCESSING_NS}abstractNum"
_ABSTRACT_NUM_ID_QNAME = f"{_WORDPROCESSING_NS}abstractNumId"
_LVL_TAG = f"{_WORDPROCESSING_NS}lvl"
_ILVL_ATTR = f"{_WORDPROCESSING_NS}ilvl"
_NUMFMT_TAG = f"{_WORDPROCESSING_NS}numFmt"

_ORDERED_NUMFMTS = frozenset(
    {
        "decimal",
        "decimalZero",
        "upperRoman",
        "lowerRoman",
        "upperLetter",
        "lowerLetter",
    }
)


def _parse_numbering_xml(numbering_xml: bytes) -> dict[int, dict[int, str]]:
    """Parse ``word/numbering.xml`` into ``{num_id: {ilvl: numFmt}}``.

    Resolves the ``<w:num>`` → ``<w:abstractNum>`` reference chain. Returns
    an empty mapping when the payload is malformed or empty.
    """
    try:
        root = _defused_fromstring(numbering_xml)
    except DefusedParseError:
        return {}

    abstract_map: dict[int, dict[int, str]] = {}
    for abstract in root.iter(_ABSTRACT_NUM_TAG):
        a_id_str = abstract.get(_ABSTRACT_NUM_ID_QNAME)
        if a_id_str is None:
            continue
        try:
            a_id = int(a_id_str)
        except ValueError:
            continue
        lvl_map: dict[int, str] = {}
        for lvl in abstract.iter(_LVL_TAG):
            ilvl_str = lvl.get(_ILVL_ATTR)
            if ilvl_str is None:
                continue
            try:
                ilvl = int(ilvl_str)
            except ValueError:
                continue
            numfmt = lvl.find(_NUMFMT_TAG)
            if numfmt is None:
                continue
            fmt_val = numfmt.get(_VAL_ATTR)
            if fmt_val:
                lvl_map[ilvl] = fmt_val
        abstract_map[a_id] = lvl_map

    num_map: dict[int, dict[int, str]] = {}
    for num in root.iter(_NUM_TAG):
        n_id_str = num.get(_NUM_ID_ATTR)
        if not n_id_str:
            continue
        try:
            n_id = int(n_id_str)
        except ValueError:
            continue
        ref = num.find(_ABSTRACT_NUM_ID_QNAME)
        if ref is None:
            continue
        a_id_str = ref.get(_VAL_ATTR)
        if not a_id_str:
            continue
        try:
            a_id = int(a_id_str)
        except ValueError:
            continue
        if a_id in abstract_map:
            num_map[n_id] = abstract_map[a_id]
    return num_map


def _load_docx_data(path: Path) -> tuple[Element, dict[int, dict[int, str]]]:
    """Load ``document.xml`` root and (optionally) parsed numbering map.

    Args:
        path: Path to the DOCX file.

    Returns:
        Tuple of (document XML root, numbering map). The numbering map is
        empty when ``word/numbering.xml`` is absent or unparseable.

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
            names = archive.namelist()
            if "word/document.xml" not in names:
                return Element("document"), {}
            document_xml = archive.read("word/document.xml")
            numbering_map: dict[int, dict[int, str]] = {}
            if "word/numbering.xml" in names:
                numbering_map = _parse_numbering_xml(archive.read("word/numbering.xml"))
    except zipfile.BadZipFile as err:
        raise DocxReadError(f"Corrupt ZIP archive (DOCX unreadable): {path}") from err

    try:
        document_root = _defused_fromstring(document_xml)
    except DefusedParseError as err:
        raise DocxReadError(f"Malformed XML in word/document.xml: {path}") from err
    return document_root, numbering_map


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
    return pstyle.get(_VAL_ATTR)


def _paragraph_numpr(paragraph: Element) -> tuple[int, int] | None:
    """Return ``(num_id, ilvl)`` for a list paragraph, else ``None``.

    A missing ``<w:ilvl>`` element defaults to indent level 0. Paragraphs
    without ``<w:numPr>`` or without a parseable ``<w:numId>`` return ``None``.
    """
    ppr = paragraph.find(_PPR_TAG)
    if ppr is None:
        return None
    numpr = ppr.find(_NUMPR_TAG)
    if numpr is None:
        return None
    numid_el = numpr.find(_NUMID_TAG)
    if numid_el is None:
        return None
    nid_str = numid_el.get(_VAL_ATTR)
    if nid_str is None:
        return None
    try:
        nid = int(nid_str)
    except ValueError:
        return None
    ilvl = 0
    ilvl_el = numpr.find(_ILVL_TAG)
    if ilvl_el is not None:
        ilvl_str = ilvl_el.get(_VAL_ATTR)
        if ilvl_str is not None:
            try:
                ilvl = int(ilvl_str)
            except ValueError:
                ilvl = 0
    return nid, ilvl


def _paragraph_text(paragraph: Element) -> str:
    """Concatenate all ``<w:t>`` text nodes in a paragraph in document order."""
    return "".join(node.text for node in paragraph.iter(_TEXT_TAG) if node.text)


def _is_ordered_fmt(fmt: str) -> bool:
    """Return ``True`` when a numbering format renders as an ordered list."""
    return fmt in _ORDERED_NUMFMTS


def _resolve_numfmt(numbering_map: dict[int, dict[int, str]], num_id: int, ilvl: int) -> str:
    """Resolve ``numFmt`` for a (num_id, ilvl) pair, defaulting to ``bullet``."""
    lvl_map = numbering_map.get(num_id)
    if lvl_map is None:
        return "bullet"
    if ilvl in lvl_map:
        return lvl_map[ilvl]
    if 0 in lvl_map:
        return lvl_map[0]
    return "bullet"


def _render_list_block(
    items: list[tuple[int, str, int]],
    numbering_map: dict[int, dict[int, str]],
) -> str:
    """Render a contiguous run of list items as a single Markdown block.

    Args:
        items: Sequence of ``(ilvl, text, num_id)`` for the list run.
        numbering_map: Parsed numbering map keyed by ``num_id``.

    Returns:
        Markdown lines joined with newlines (no trailing newline).
    """
    counters: dict[int, int] = {}
    lines: list[str] = []
    for ilvl, text, nid in items:
        fmt = _resolve_numfmt(numbering_map, nid, ilvl)
        indent = "  " * ilvl
        if _is_ordered_fmt(fmt):
            counters[ilvl] = counters.get(ilvl, 0) + 1
            marker = f"{counters[ilvl]}. "
        else:
            marker = "- "
        lines.append(f"{indent}{marker}{text}")
    return "\n".join(lines)


def read_docx_blocks(path: Path) -> list[str]:
    """Extract ordered Markdown blocks from a DOCX file.

    Heading paragraphs whose ``<w:pStyle>`` resolves to a Word heading
    level 1-6 are emitted as ATX-prefixed strings (``# `` through
    ``###### ``). Paragraphs carrying ``<w:numPr>`` are accumulated into
    contiguous list blocks rendered as GFM lists with two-space indent
    per ``w:ilvl``. All other paragraphs (Normal, BodyText, unknown
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
    tree, numbering_map = _load_docx_data(path)
    blocks: list[str] = []
    current_list: list[tuple[int, str, int]] = []
    current_num_id: int | None = None

    def _flush_list() -> None:
        nonlocal current_list, current_num_id
        if current_list:
            blocks.append(_render_list_block(current_list, numbering_map))
            current_list = []
            current_num_id = None

    for paragraph in tree.iter(_PARA_TAG):
        numpr = _paragraph_numpr(paragraph)
        text = _paragraph_text(paragraph).strip()

        if numpr is not None:
            num_id, ilvl = numpr
            if not text:
                # Drop empty list items but keep the surrounding run intact.
                continue
            if current_num_id is not None and current_num_id != num_id:
                _flush_list()
            current_num_id = num_id
            current_list.append((ilvl, text, num_id))
            continue

        _flush_list()
        if not text:
            continue
        level = _heading_level(_paragraph_style(paragraph))
        if level is not None:
            blocks.append(f"{'#' * level} {text}")
        else:
            blocks.append(text)

    _flush_list()
    return blocks


def read_docx(path: Path) -> str:
    """Extract text content from a DOCX file and return it as Markdown.

    Reads ``word/document.xml`` (and optionally ``word/numbering.xml``)
    from the DOCX ZIP archive using an XXE-safe XML parser and joins
    extracted blocks with blank lines. Heading paragraphs render as
    ATX headings; ``<w:numPr>`` paragraphs render as GFM list items
    with two-space indentation per ``w:ilvl``.

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
