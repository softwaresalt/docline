"""Red-first DOCX <w:pStyle> -> H1-H6 mapping tests (010.014-T, F4.T2).

These tests assert the intended post-F4.T3 behavior: paragraphs whose
``<w:pStyle w:val="HeadingN"/>`` resolves to a Word heading level are emitted
as Markdown ATX headings (``# ``, ``## `` ... ``###### ``). All other styles
(Normal, BodyText, ListParagraph, unknown) remain plain paragraphs.

These tests are expected to FAIL until 010.015-T (F4.T3) lands. Once the
style mapping implementation lands, the legacy characterization tests in
``test_docx_baseline_characterization.py`` will intentionally fail and be
updated or removed at that time, per the F4 handoff contract.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from docline.readers.docx import read_docx

_DOCX_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _make_docx(tmp_path: Path, body_inner_xml: str, name: str = "doc.docx") -> Path:
    """Build a minimal DOCX archive wrapping ``body_inner_xml`` inside ``<w:body>``."""
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


def _styled_para(style: str, text: str) -> str:
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'


def _plain_para(text: str) -> str:
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


# ---------------------------------------------------------------------------
# Heading1 .. Heading6 -> ATX heading markers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "style,prefix",
    [
        ("Heading1", "# "),
        ("Heading2", "## "),
        ("Heading3", "### "),
        ("Heading4", "#### "),
        ("Heading5", "##### "),
        ("Heading6", "###### "),
    ],
)
def test_heading_style_emits_atx_heading(tmp_path: Path, style: str, prefix: str) -> None:
    """Heading1..Heading6 paragraphs render as Markdown ATX headings."""
    docx = _make_docx(tmp_path, _styled_para(style, f"Title {style}"))
    output = read_docx(docx)
    assert output == f"{prefix}Title {style}"


def test_heading_styles_preserve_document_order(tmp_path: Path) -> None:
    """A mixed-heading document renders headings in source order."""
    body = (
        _styled_para("Heading1", "Top")
        + _styled_para("Heading2", "Sub")
        + _styled_para("Heading3", "SubSub")
    )
    docx = _make_docx(tmp_path, body)
    output = read_docx(docx)
    assert output == "# Top\n\n## Sub\n\n### SubSub"


def test_headings_interleaved_with_body_text(tmp_path: Path) -> None:
    """Heading and Normal paragraphs interleave with blank-line separators."""
    body = (
        _styled_para("Heading1", "Intro")
        + _styled_para("Normal", "Opening paragraph.")
        + _styled_para("Heading2", "Details")
        + _styled_para("Normal", "More text.")
    )
    docx = _make_docx(tmp_path, body)
    output = read_docx(docx)
    assert output == ("# Intro\n\nOpening paragraph.\n\n## Details\n\nMore text.")


# ---------------------------------------------------------------------------
# Non-heading and unknown styles remain plain text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("style", ["Normal", "BodyText", "ListParagraph", "Caption"])
def test_non_heading_styles_emit_plain_text(tmp_path: Path, style: str) -> None:
    """Non-heading paragraph styles render as plain text without prefixes."""
    docx = _make_docx(tmp_path, _styled_para(style, "Some text."))
    output = read_docx(docx)
    assert output == "Some text."


def test_unknown_style_falls_back_to_plain_text(tmp_path: Path) -> None:
    """An unrecognized pStyle value renders as plain text, not a heading."""
    docx = _make_docx(tmp_path, _styled_para("CustomStyle42", "Mystery text."))
    output = read_docx(docx)
    assert output == "Mystery text."


def test_paragraph_without_pstyle_emits_plain_text(tmp_path: Path) -> None:
    """A paragraph with no <w:pStyle> renders as plain text."""
    docx = _make_docx(tmp_path, _plain_para("Bare paragraph."))
    output = read_docx(docx)
    assert output == "Bare paragraph."


# ---------------------------------------------------------------------------
# Robustness: split runs, empty paragraphs, heading-level edge cases
# ---------------------------------------------------------------------------


def test_heading_with_split_runs_concatenates_text(tmp_path: Path) -> None:
    """A Heading1 paragraph whose text is split across runs concatenates the runs."""
    body = (
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        "<w:r><w:t>Part one </w:t></w:r>"
        "<w:r><w:t>part two</w:t></w:r></w:p>"
    )
    docx = _make_docx(tmp_path, body)
    output = read_docx(docx)
    assert output == "# Part one part two"


def test_heading_alias_heading_1_with_underscore_or_space_maps(tmp_path: Path) -> None:
    """Common Word aliases ``heading 1`` and ``Heading_1`` also resolve to H1."""
    body = _styled_para("heading 1", "Variant A") + _styled_para("Heading_1", "Variant B")
    docx = _make_docx(tmp_path, body)
    output = read_docx(docx)
    assert output == "# Variant A\n\n# Variant B"


def test_heading7_and_above_falls_back_to_plain_text(tmp_path: Path) -> None:
    """Heading7+ is not part of Markdown ATX; render as plain text."""
    docx = _make_docx(tmp_path, _styled_para("Heading7", "Deep level."))
    output = read_docx(docx)
    assert output == "Deep level."


def test_empty_heading_paragraph_is_dropped(tmp_path: Path) -> None:
    """A heading paragraph with no text content is skipped, like empty paragraphs."""
    body = (
        _styled_para("Heading1", "Real heading")
        + '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr></w:p>'
        + _plain_para("After.")
    )
    docx = _make_docx(tmp_path, body)
    output = read_docx(docx)
    assert output == "# Real heading\n\nAfter."
