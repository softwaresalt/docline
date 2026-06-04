"""DOCX reader adapter — extract Markdown content from DOCX archives.

Uses the XXE-safe ``defusedxml`` parser for ``word/document.xml`` and
``word/numbering.xml`` (P2-1 security advisory carried over from F4
planning). Maps Word heading styles (``<w:pStyle w:val="HeadingN"/>``)
to ATX Markdown headings and ``<w:numPr>`` paragraphs to GFM list
items with ``w:ilvl`` indentation.
"""

import logging
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import ParseError as DefusedParseError
from defusedxml.ElementTree import fromstring as _defused_fromstring

from docline.readers.picture_sink import MediaReference, PictureSink
from docline.schema.models import DoclineError

_log = logging.getLogger(__name__)


class DocxReadError(DoclineError):
    """Raised when DOCX extraction fails."""


_WORDPROCESSING_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_BODY_TAG = f"{_WORDPROCESSING_NS}body"
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
_TBL_TAG = f"{_WORDPROCESSING_NS}tbl"
_TR_TAG = f"{_WORDPROCESSING_NS}tr"
_TC_TAG = f"{_WORDPROCESSING_NS}tc"
_DRAWING_TAG = f"{_WORDPROCESSING_NS}drawing"

_DRAWINGML_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_BLIP_TAG = f"{_DRAWINGML_NS}blip"

_RELS_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_R_EMBED_ATTR = f"{_RELS_NS}embed"
_PACKAGE_RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_RELATIONSHIP_TAG = f"{_PACKAGE_RELS_NS}Relationship"

_EXT_TO_MIME: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}

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


def _escape_cell(text: str) -> str:
    """Escape pipe characters so GFM column boundaries remain intact."""
    return text.replace("|", "\\|")


def _cell_text(cell: Element) -> str:
    """Concatenate direct-child paragraph text in a ``<w:tc>``.

    Paragraph blocks inside a cell are joined with a single space; empty
    paragraphs are dropped. List and heading formatting inside a cell is
    flattened to plain text for GFM table compatibility.
    """
    parts: list[str] = []
    for para in cell.findall(_PARA_TAG):
        text = _paragraph_text(para).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _render_table(table: Element) -> str | None:
    """Render a ``<w:tbl>`` element as a GFM Markdown table.

    The first row is treated as the header. Returns ``None`` for tables
    with zero rows or zero columns (caller should skip emission).
    """
    rows = table.findall(_TR_TAG)
    if not rows:
        return None
    grid: list[list[str]] = []
    max_cols = 0
    for row in rows:
        cells = row.findall(_TC_TAG)
        cell_texts = [_escape_cell(_cell_text(cell)) for cell in cells]
        grid.append(cell_texts)
        if len(cell_texts) > max_cols:
            max_cols = len(cell_texts)
    if max_cols == 0:
        return None
    for row_cells in grid:
        while len(row_cells) < max_cols:
            row_cells.append("")
    lines: list[str] = ["| " + " | ".join(grid[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    for row_cells in grid[1:]:
        lines.append("| " + " | ".join(row_cells) + " |")
    return "\n".join(lines)


def read_docx_blocks(path: Path) -> list[str]:
    """Extract ordered Markdown blocks from a DOCX file.

    Heading paragraphs whose ``<w:pStyle>`` resolves to a Word heading
    level 1-6 are emitted as ATX-prefixed strings (``# `` through
    ``###### ``). Paragraphs carrying ``<w:numPr>`` are accumulated into
    contiguous list blocks rendered as GFM lists with two-space indent
    per ``w:ilvl``. ``<w:tbl>`` elements render as GFM tables with the
    first row as the header. All other paragraphs (Normal, BodyText,
    unknown styles, or no style at all) are emitted as plain text.
    Empty paragraphs and empty tables are skipped.

    Args:
        path: Path to the DOCX file. Must be a trusted-local path.

    Returns:
        Ordered Markdown blocks suitable for joining with blank lines.

    Raises:
        DocxReadError: If DOCX parsing fails.
        FileNotFoundError: If ``path`` does not exist.
    """
    tree, numbering_map = _load_docx_data(path)
    body = tree.find(_BODY_TAG)
    elements = list(body) if body is not None else list(tree)

    blocks: list[str] = []
    current_list: list[tuple[int, str, int]] = []
    current_num_id: int | None = None

    def _flush_list() -> None:
        nonlocal current_list, current_num_id
        if current_list:
            blocks.append(_render_list_block(current_list, numbering_map))
            current_list = []
            current_num_id = None

    for element in elements:
        if element.tag == _PARA_TAG:
            numpr = _paragraph_numpr(element)
            text = _paragraph_text(element).strip()
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
            level = _heading_level(_paragraph_style(element))
            if level is not None:
                blocks.append(f"{'#' * level} {text}")
            else:
                blocks.append(text)
        elif element.tag == _TBL_TAG:
            _flush_list()
            rendered = _render_table(element)
            if rendered is not None:
                blocks.append(rendered)
        # Other block-level body elements (sectPr, bookmarks, etc.) are skipped.

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


# ---------------------------------------------------------------------------
# G3c (014-S) — DOCX image extraction with PictureSink integration
# ---------------------------------------------------------------------------


def _parse_relationships(rels_xml: bytes) -> dict[str, str]:
    """Parse ``word/_rels/document.xml.rels`` into ``{Id: Target}``.

    Uses ``defusedxml`` for XXE safety. Returns an empty mapping when the
    payload is malformed or empty.
    """
    try:
        root = _defused_fromstring(rels_xml)
    except DefusedParseError:
        return {}
    rels: dict[str, str] = {}
    for rel in root.iter(_RELATIONSHIP_TAG):
        rid = rel.get("Id")
        target = rel.get("Target")
        if rid and target:
            rels[rid] = target
    return rels


def _safe_target_path(target: str) -> str | None:
    """Resolve a rels ``Target`` relative to ``word/``; reject path traversal.

    Returns the path within the DOCX zip (e.g. ``"word/media/image1.png"``)
    or ``None`` if the target attempts to escape the ``word/`` namespace
    (leading slash, ``..`` segments, or absolute path).
    """
    if not target:
        return None
    if target.startswith("/"):
        return None
    normalized = target.replace("\\", "/")
    if ".." in normalized.split("/"):
        return None
    return f"word/{normalized}"


def _mime_for_target(target: str) -> str:
    """Infer MIME type from the file extension of a rels Target."""
    lower = target.lower()
    for ext, mime in _EXT_TO_MIME.items():
        if lower.endswith(ext):
            return mime
    return "application/octet-stream"


def _extract_blip_embed_ids(paragraph: Element) -> list[str]:
    """Return ordered ``r:embed`` ids from every ``<a:blip>`` inside ``<w:drawing>``.

    Walks every ``<w:drawing>`` descendant of ``paragraph`` and collects
    the ``r:embed`` attribute of each ``<a:blip>`` it contains. Empty
    or missing attributes are dropped silently.
    """
    embed_ids: list[str] = []
    for drawing in paragraph.iter(_DRAWING_TAG):
        for blip in drawing.iter(_BLIP_TAG):
            rid = blip.get(_R_EMBED_ATTR)
            if rid:
                embed_ids.append(rid)
    return embed_ids


def _emit_image_for_embed(
    *,
    rid: str,
    rels: dict[str, str],
    archive: zipfile.ZipFile,
    archive_names: set[str],
    picture_sink: PictureSink,
) -> tuple[str, MediaReference] | None:
    """Resolve ``rid`` to bytes via ``rels`` and emit through ``picture_sink``.

    Returns a ``(markdown_image_reference, media_reference)`` tuple on
    success, or ``None`` when the embed id cannot be resolved or the
    target bytes cannot be read. The ``media_reference`` is the value
    ``picture_sink.emit`` returned — capturing it at the call site
    avoids reaching into sink-private state (which would not work for
    arbitrary ``PictureSink`` implementations that do not maintain a
    ``references`` collection).
    """
    target = rels.get(rid)
    if target is None:
        _log.warning("DOCX image rId %s has no matching relationship; skipping", rid)
        return None
    archive_path = _safe_target_path(target)
    if archive_path is None:
        _log.warning("DOCX image target %r failed path-traversal check; skipping", target)
        return None
    if archive_path not in archive_names:
        _log.warning("DOCX image target %r missing from archive; skipping", archive_path)
        return None
    try:
        data = archive.read(archive_path)
    except (KeyError, RuntimeError, zipfile.BadZipFile) as err:
        _log.warning("DOCX image %r failed to read: %s", archive_path, err)
        return None
    mime = _mime_for_target(target)
    # Honor the source extension verbatim so jpeg/jpg distinction is preserved.
    suffix = Path(target).suffix.lower() or None
    reference = picture_sink.emit(mime, data, ext=suffix)
    return f"![](media/{reference.filename})", reference


def read_docx_blocks_with_media(
    path: Path, picture_sink: PictureSink | None
) -> tuple[list[str], list[MediaReference]]:
    """Read DOCX blocks and optionally extract embedded images to ``picture_sink``.

    When ``picture_sink`` is provided, every ``<a:blip r:embed="rIdN"/>``
    inside ``<w:drawing>`` is resolved via ``word/_rels/document.xml.rels``,
    the corresponding ``word/media/imageN.<ext>`` bytes are passed to the
    sink, and the paragraph emits ``![](media/<assigned_filename>)`` in
    place. When ``picture_sink`` is ``None``, this function delegates to
    :func:`read_docx_blocks` for the text-only back-compat path.

    Embed ids that cannot be resolved (missing rels entry, target outside
    ``word/``, file absent from the archive, or read error) are skipped
    silently with a ``logging.WARNING`` and the surrounding paragraph
    text still emits.

    Args:
        path: Path to the DOCX file.
        picture_sink: Optional ``PictureSink`` that persists extracted
            image bytes and assigns sidecar filenames. When ``None``,
            the function emits text blocks only (legacy behavior).

    Returns:
        Tuple of ``(blocks, references)`` where ``blocks`` is the ordered
        markdown block list (including any ``![](media/...)`` insertions)
        and ``references`` is the ordered list of ``MediaReference``
        objects the sink emitted. ``references`` is always empty when
        ``picture_sink`` is ``None``.

    Raises:
        DocxReadError: If DOCX parsing fails.
        FileNotFoundError: If ``path`` does not exist.
    """
    if picture_sink is None:
        return read_docx_blocks(path), []

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    raw = path.read_bytes()
    if raw[:2] != b"PK":
        raise DocxReadError(f"Not a valid DOCX file (missing ZIP signature): {path}")

    try:
        with zipfile.ZipFile(path) as archive:
            archive_names = set(archive.namelist())
            if "word/document.xml" not in archive_names:
                return [], []
            document_xml = archive.read("word/document.xml")
            numbering_map: dict[int, dict[int, str]] = {}
            if "word/numbering.xml" in archive_names:
                numbering_map = _parse_numbering_xml(archive.read("word/numbering.xml"))
            rels: dict[str, str] = {}
            if "word/_rels/document.xml.rels" in archive_names:
                rels = _parse_relationships(archive.read("word/_rels/document.xml.rels"))

            try:
                document_root = _defused_fromstring(document_xml)
            except DefusedParseError as err:
                raise DocxReadError(f"Malformed XML in word/document.xml: {path}") from err

            body = document_root.find(_BODY_TAG)
            elements = list(body) if body is not None else list(document_root)

            blocks: list[str] = []
            references: list[MediaReference] = []
            current_list: list[tuple[int, str, int]] = []
            current_num_id: int | None = None

            def _flush_list() -> None:
                nonlocal current_list, current_num_id
                if current_list:
                    blocks.append(_render_list_block(current_list, numbering_map))
                    current_list = []
                    current_num_id = None

            for element in elements:
                if element.tag == _PARA_TAG:
                    embed_ids = _extract_blip_embed_ids(element)
                    image_markdowns: list[str] = []
                    for rid in embed_ids:
                        emitted = _emit_image_for_embed(
                            rid=rid,
                            rels=rels,
                            archive=archive,
                            archive_names=archive_names,
                            picture_sink=picture_sink,
                        )
                        if emitted is not None:
                            markdown, reference = emitted
                            image_markdowns.append(markdown)
                            references.append(reference)

                    numpr = _paragraph_numpr(element)
                    text = _paragraph_text(element).strip()
                    combined = text
                    if image_markdowns:
                        if combined:
                            combined = combined + "\n\n" + "\n\n".join(image_markdowns)
                        else:
                            combined = "\n\n".join(image_markdowns)

                    if numpr is not None:
                        num_id, ilvl = numpr
                        if not combined:
                            continue
                        if current_num_id is not None and current_num_id != num_id:
                            _flush_list()
                        current_num_id = num_id
                        current_list.append((ilvl, combined, num_id))
                        continue

                    _flush_list()
                    if not combined:
                        continue
                    level = _heading_level(_paragraph_style(element))
                    if level is not None:
                        blocks.append(f"{'#' * level} {combined}")
                    else:
                        blocks.append(combined)
                elif element.tag == _TBL_TAG:
                    _flush_list()
                    rendered = _render_table(element)
                    if rendered is not None:
                        blocks.append(rendered)
                # Other block-level body elements (sectPr, bookmarks) skipped.

            _flush_list()
            return blocks, references

    except zipfile.BadZipFile as err:
        raise DocxReadError(f"Corrupt ZIP archive (DOCX unreadable): {path}") from err


__all__ = [
    "DocxReadError",
    "read_docx_blocks",
    "read_docx_blocks_with_media",
    "read_docx",
]
