"""Red-first DOCX list emission tests (010.016-T, F4.T4).

These tests assert the intended post-F4.T5 behavior: paragraphs carrying a
``<w:numPr>`` element are emitted as GFM Markdown list items. Indent level
(``<w:ilvl w:val="N"/>``) maps to N levels of two-space indentation.

When ``word/numbering.xml`` is present and a referenced ``<w:abstractNum>``
declares ``<w:numFmt w:val="decimal"/>`` (or other ordered formats) the
items are emitted as ordered list items (``1. ``, ``2. ``, ...). Otherwise
items are emitted as unordered bullets (``- ``).

These tests are expected to FAIL until 010.017-T (F4.T5) lands.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from docline.readers.docx import read_docx

_DOCX_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _list_para(text: str, ilvl: int = 0, num_id: int = 1) -> str:
    return (
        "<w:p><w:pPr><w:numPr>"
        f'<w:ilvl w:val="{ilvl}"/><w:numId w:val="{num_id}"/>'
        "</w:numPr></w:pPr>"
        f"<w:r><w:t>{text}</w:t></w:r></w:p>"
    )


def _plain_para(text: str) -> str:
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def _heading_para(level: int, text: str) -> str:
    return (
        f'<w:p><w:pPr><w:pStyle w:val="Heading{level}"/></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'
    )


def _make_docx(
    tmp_path: Path,
    body_inner_xml: str,
    name: str = "doc.docx",
    numbering_xml: str | None = None,
) -> Path:
    """Build a minimal DOCX archive wrapping ``body_inner_xml`` in ``<w:body>``."""
    body_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_DOCX_NS}">'
        f"<w:body>{body_inner_xml}</w:body>"
        f"</w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        zf.writestr("word/document.xml", body_xml)
        if numbering_xml is not None:
            zf.writestr("word/numbering.xml", numbering_xml)
    path = tmp_path / name
    path.write_bytes(buf.getvalue())
    return path


def _ordered_numbering(num_id: int = 1, abstract_num_id: int = 7) -> str:
    """Return a minimal numbering.xml declaring ``num_id`` as an ordered list."""
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:numbering xmlns:w="{_DOCX_NS}">'
        f'<w:abstractNum w:abstractNumId="{abstract_num_id}">'
        f'<w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>'
        f"</w:abstractNum>"
        f'<w:num w:numId="{num_id}">'
        f'<w:abstractNumId w:val="{abstract_num_id}"/>'
        f"</w:num>"
        f"</w:numbering>"
    )


def _bullet_numbering(num_id: int = 1, abstract_num_id: int = 7) -> str:
    """Return a minimal numbering.xml declaring ``num_id`` as a bullet list."""
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:numbering xmlns:w="{_DOCX_NS}">'
        f'<w:abstractNum w:abstractNumId="{abstract_num_id}">'
        f'<w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl>'
        f"</w:abstractNum>"
        f'<w:num w:numId="{num_id}">'
        f'<w:abstractNumId w:val="{abstract_num_id}"/>'
        f"</w:num>"
        f"</w:numbering>"
    )


# ---------------------------------------------------------------------------
# Basic bullet emission (no numbering.xml -> default bullet)
# ---------------------------------------------------------------------------


def test_single_list_item_emits_bullet(tmp_path: Path) -> None:
    docx = _make_docx(tmp_path, _list_para("Only item"))
    assert read_docx(docx) == "- Only item"


def test_multiple_bullets_emit_in_order(tmp_path: Path) -> None:
    body = _list_para("Alpha") + _list_para("Bravo") + _list_para("Charlie")
    docx = _make_docx(tmp_path, body)
    assert read_docx(docx) == "- Alpha\n- Bravo\n- Charlie"


def test_bullet_list_explicit_numbering_xml(tmp_path: Path) -> None:
    body = _list_para("First") + _list_para("Second")
    docx = _make_docx(tmp_path, body, numbering_xml=_bullet_numbering())
    assert read_docx(docx) == "- First\n- Second"


# ---------------------------------------------------------------------------
# Ordered list emission (numbering.xml with decimal format)
# ---------------------------------------------------------------------------


def test_ordered_list_emits_decimal_markers(tmp_path: Path) -> None:
    body = _list_para("One") + _list_para("Two") + _list_para("Three")
    docx = _make_docx(tmp_path, body, numbering_xml=_ordered_numbering())
    assert read_docx(docx) == "1. One\n2. Two\n3. Three"


def test_ordered_list_restarts_per_numid(tmp_path: Path) -> None:
    """Two distinct numId references produce two separate ordered lists."""
    body = (
        _list_para("A1", num_id=1)
        + _list_para("A2", num_id=1)
        + _plain_para("Divider.")
        + _list_para("B1", num_id=2)
    )
    numbering = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:numbering xmlns:w="{_DOCX_NS}">'
        f'<w:abstractNum w:abstractNumId="7">'
        f'<w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>'
        f"</w:abstractNum>"
        f'<w:abstractNum w:abstractNumId="8">'
        f'<w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>'
        f"</w:abstractNum>"
        f'<w:num w:numId="1"><w:abstractNumId w:val="7"/></w:num>'
        f'<w:num w:numId="2"><w:abstractNumId w:val="8"/></w:num>'
        f"</w:numbering>"
    )
    docx = _make_docx(tmp_path, body, numbering_xml=numbering)
    assert read_docx(docx) == "1. A1\n2. A2\n\nDivider.\n\n1. B1"


# ---------------------------------------------------------------------------
# Indent levels (ilvl) -> two-space indentation per level
# ---------------------------------------------------------------------------


def test_nested_bullets_indent_two_spaces_per_level(tmp_path: Path) -> None:
    body = (
        _list_para("Top", ilvl=0)
        + _list_para("Mid", ilvl=1)
        + _list_para("Deep", ilvl=2)
        + _list_para("Back", ilvl=0)
    )
    docx = _make_docx(tmp_path, body)
    assert read_docx(docx) == "- Top\n  - Mid\n    - Deep\n- Back"


# ---------------------------------------------------------------------------
# Interleaving with headings and body text
# ---------------------------------------------------------------------------


def test_list_before_and_after_body_paragraph(tmp_path: Path) -> None:
    body = (
        _plain_para("Intro paragraph.")
        + _list_para("First")
        + _list_para("Second")
        + _plain_para("Outro paragraph.")
    )
    docx = _make_docx(tmp_path, body)
    assert read_docx(docx) == ("Intro paragraph.\n\n- First\n- Second\n\nOutro paragraph.")


def test_list_under_heading(tmp_path: Path) -> None:
    body = _heading_para(1, "Section") + _list_para("Item A") + _list_para("Item B")
    docx = _make_docx(tmp_path, body)
    assert read_docx(docx) == "# Section\n\n- Item A\n- Item B"


def test_two_separated_bullet_lists_are_split(tmp_path: Path) -> None:
    """Two bullet runs separated by a body paragraph render as two list groups."""
    body = (
        _list_para("Group1-a")
        + _list_para("Group1-b")
        + _plain_para("Gap.")
        + _list_para("Group2-a")
    )
    docx = _make_docx(tmp_path, body)
    assert read_docx(docx) == ("- Group1-a\n- Group1-b\n\nGap.\n\n- Group2-a")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_list_item_is_dropped(tmp_path: Path) -> None:
    """A <w:numPr> paragraph with no text content is skipped."""
    body = (
        _list_para("Real")
        + "<w:p><w:pPr><w:numPr>"
        + '<w:ilvl w:val="0"/><w:numId w:val="1"/>'
        + "</w:numPr></w:pPr></w:p>"
        + _list_para("Also real")
    )
    docx = _make_docx(tmp_path, body)
    assert read_docx(docx) == "- Real\n- Also real"


def test_missing_ilvl_defaults_to_level_zero(tmp_path: Path) -> None:
    """A <w:numPr> without <w:ilvl> renders at indent level 0."""
    body = (
        "<w:p><w:pPr><w:numPr>"
        '<w:numId w:val="1"/>'
        "</w:numPr></w:pPr>"
        "<w:r><w:t>No ilvl</w:t></w:r></w:p>"
    )
    docx = _make_docx(tmp_path, body)
    assert read_docx(docx) == "- No ilvl"
