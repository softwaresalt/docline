"""Red-first DOCX table emission tests (010.018-T, F4.T6).

Asserts the intended post-F4.T7 behavior: ``<w:tbl>`` elements are
emitted as GFM tables. The first row is treated as the table header.
Cells containing multiple paragraphs concatenate the paragraph text
with a single space. Pipe characters inside cell text are escaped to
preserve GFM column boundaries.

These tests are expected to FAIL until 010.019-T (F4.T7) lands.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from docline.readers.docx import read_docx

_DOCX_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _cell(*paragraph_texts: str) -> str:
    """Build a ``<w:tc>`` with one ``<w:p><w:r><w:t>`` per text item."""
    paras = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in paragraph_texts)
    return f"<w:tc><w:tcPr/>{paras}</w:tc>"


def _row(*cells: str) -> str:
    return "<w:tr>" + "".join(cells) + "</w:tr>"


def _table(*rows: str) -> str:
    return "<w:tbl>" + "".join(rows) + "</w:tbl>"


def _plain_para(text: str) -> str:
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def _make_docx(tmp_path: Path, body_inner_xml: str, name: str = "doc.docx") -> Path:
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
    path = tmp_path / name
    path.write_bytes(buf.getvalue())
    return path


# ---------------------------------------------------------------------------
# Basic table emission
# ---------------------------------------------------------------------------


def test_two_by_two_table_emits_gfm(tmp_path: Path) -> None:
    body = _table(
        _row(_cell("Name"), _cell("Role")),
        _row(_cell("Alice"), _cell("Engineer")),
    )
    docx = _make_docx(tmp_path, body)
    expected = "| Name | Role |\n| --- | --- |\n| Alice | Engineer |"
    assert read_docx(docx) == expected


def test_three_column_table_emits_three_columns(tmp_path: Path) -> None:
    body = _table(
        _row(_cell("A"), _cell("B"), _cell("C")),
        _row(_cell("1"), _cell("2"), _cell("3")),
        _row(_cell("4"), _cell("5"), _cell("6")),
    )
    docx = _make_docx(tmp_path, body)
    expected = (
        "| A | B | C |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |"
    )
    assert read_docx(docx) == expected


# ---------------------------------------------------------------------------
# Cell content handling
# ---------------------------------------------------------------------------


def test_multi_paragraph_cell_concatenates_with_space(tmp_path: Path) -> None:
    body = _table(
        _row(_cell("Header"), _cell("Description")),
        _row(_cell("Topic"), _cell("First sentence.", "Second sentence.")),
    )
    docx = _make_docx(tmp_path, body)
    expected = (
        "| Header | Description |\n"
        "| --- | --- |\n"
        "| Topic | First sentence. Second sentence. |"
    )
    assert read_docx(docx) == expected


def test_empty_cell_emits_blank(tmp_path: Path) -> None:
    body = _table(
        _row(_cell("A"), _cell("B")),
        _row(_cell("x"), _cell()),
    )
    docx = _make_docx(tmp_path, body)
    expected = "| A | B |\n| --- | --- |\n| x |  |"
    assert read_docx(docx) == expected


def test_pipe_in_cell_is_escaped(tmp_path: Path) -> None:
    body = _table(
        _row(_cell("Operator"), _cell("Meaning")),
        _row(_cell("|"), _cell("alternation")),
    )
    docx = _make_docx(tmp_path, body)
    expected = (
        "| Operator | Meaning |\n| --- | --- |\n| \\| | alternation |"
    )
    assert read_docx(docx) == expected


# ---------------------------------------------------------------------------
# Surrounding context
# ---------------------------------------------------------------------------


def test_table_between_paragraphs_has_blank_line_separation(tmp_path: Path) -> None:
    body = (
        _plain_para("Before.")
        + _table(
            _row(_cell("k"), _cell("v")),
            _row(_cell("a"), _cell("b")),
        )
        + _plain_para("After.")
    )
    docx = _make_docx(tmp_path, body)
    expected = (
        "Before.\n\n"
        "| k | v |\n| --- | --- |\n| a | b |\n\n"
        "After."
    )
    assert read_docx(docx) == expected


def test_two_tables_are_split_by_blank_line(tmp_path: Path) -> None:
    body = _table(
        _row(_cell("h1")),
        _row(_cell("v1")),
    ) + _table(
        _row(_cell("h2")),
        _row(_cell("v2")),
    )
    docx = _make_docx(tmp_path, body)
    expected = (
        "| h1 |\n| --- |\n| v1 |\n\n"
        "| h2 |\n| --- |\n| v2 |"
    )
    assert read_docx(docx) == expected


# ---------------------------------------------------------------------------
# Degenerate tables
# ---------------------------------------------------------------------------


def test_single_row_table_emits_header_only(tmp_path: Path) -> None:
    """A 1-row table renders as header + separator with no body rows."""
    body = _table(_row(_cell("Only"), _cell("Row")))
    docx = _make_docx(tmp_path, body)
    expected = "| Only | Row |\n| --- | --- |"
    assert read_docx(docx) == expected


def test_empty_table_is_dropped(tmp_path: Path) -> None:
    """A table with zero rows emits no output block."""
    body = _plain_para("Before.") + _table() + _plain_para("After.")
    docx = _make_docx(tmp_path, body)
    assert read_docx(docx) == "Before.\n\nAfter."
