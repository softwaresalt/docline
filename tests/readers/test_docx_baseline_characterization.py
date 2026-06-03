"""Characterization snapshots pinning current DOCX emission (010-S F4.T1).

These tests do NOT prescribe ideal behavior — they PIN the current behavior
of ``read_docx`` and ``read_docx_blocks`` so that subsequent F4 tasks
(010.014-T red-first style mapping, 010.015-T defusedxml + style impl) can
safely refactor with a baseline diff signal.

When F4.T2 begins, the assertions here are expected to break by design.
That is the characterization handoff: the tests document what was, then
F4.T2 documents what should be, then F4.T3+ make it so.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from docline.readers.docx import read_docx, read_docx_blocks

_DOCX_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _build_styled_docx(tmp_path: Path) -> Path:
    """Build a minimal DOCX with Heading 1, Heading 2, Normal, ListParagraph runs."""
    body_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_DOCX_NS}">'
        f"<w:body>"
        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        f"<w:r><w:t>Top Title</w:t></w:r></w:p>"
        f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>'
        f"<w:r><w:t>Subsection A</w:t></w:r></w:p>"
        f'<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
        f"<w:r><w:t>Body paragraph one.</w:t></w:r></w:p>"
        f'<w:p><w:pPr><w:pStyle w:val="ListParagraph"/></w:pPr>'
        f"<w:r><w:t>Bullet item alpha</w:t></w:r></w:p>"
        f'<w:p><w:pPr><w:pStyle w:val="ListParagraph"/></w:pPr>'
        f"<w:r><w:t>Bullet item beta</w:t></w:r></w:p>"
        f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>'
        f"<w:r><w:t>Subsection B</w:t></w:r></w:p>"
        f'<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
        f"<w:r><w:t>Body paragraph two.</w:t></w:r></w:p>"
        f"</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        zf.writestr("word/document.xml", body_xml)
    docx_path = tmp_path / "styled.docx"
    docx_path.write_bytes(buf.getvalue())
    return docx_path


def _build_split_run_docx(tmp_path: Path) -> Path:
    """Build a DOCX where a paragraph's text is split across multiple <w:t> runs."""
    body_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_DOCX_NS}"><w:body>'
        f"<w:p>"
        f"<w:r><w:t>Part one </w:t></w:r>"
        f"<w:r><w:t>part two </w:t></w:r>"
        f"<w:r><w:t>part three.</w:t></w:r>"
        f"</w:p>"
        f"</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        zf.writestr("word/document.xml", body_xml)
    docx_path = tmp_path / "split_runs.docx"
    docx_path.write_bytes(buf.getvalue())
    return docx_path


def _build_empty_para_docx(tmp_path: Path) -> Path:
    """Build a DOCX with empty/whitespace-only paragraphs interleaved."""
    body_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_DOCX_NS}"><w:body>'
        f"<w:p><w:r><w:t>First</w:t></w:r></w:p>"
        f"<w:p></w:p>"
        f"<w:p><w:r><w:t>   </w:t></w:r></w:p>"
        f"<w:p><w:r><w:t>Second</w:t></w:r></w:p>"
        f"</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        zf.writestr("word/document.xml", body_xml)
    docx_path = tmp_path / "empty_paras.docx"
    docx_path.write_bytes(buf.getvalue())
    return docx_path


# ---------------------------------------------------------------------------
# Characterization: current behavior flattens all paragraphs to plain text.
# read_docx does NOT translate pStyle into Markdown heading prefixes today.
# These assertions PIN that fact so F4.T2 red tests can intentionally invert.
# ---------------------------------------------------------------------------


def test_baseline_styled_docx_emits_plain_paragraphs(tmp_path: Path) -> None:
    """Current behavior: heading styles are stripped; all paragraphs join with \\n\\n."""
    docx = _build_styled_docx(tmp_path)
    output = read_docx(docx)

    expected = (
        "Top Title\n\n"
        "Subsection A\n\n"
        "Body paragraph one.\n\n"
        "Bullet item alpha\n\n"
        "Bullet item beta\n\n"
        "Subsection B\n\n"
        "Body paragraph two."
    )
    assert output == expected


def test_baseline_styled_docx_emits_no_markdown_heading_markers(tmp_path: Path) -> None:
    """Pin: no '#', '##', or '-' markers appear in baseline output."""
    docx = _build_styled_docx(tmp_path)
    output = read_docx(docx)
    assert "# " not in output
    assert "## " not in output
    # Bullet items render as plain prose, no leading '-'
    assert "- Bullet" not in output


def test_baseline_blocks_returns_ordered_text_only(tmp_path: Path) -> None:
    """read_docx_blocks returns list[str] of stripped paragraph text in order."""
    docx = _build_styled_docx(tmp_path)
    blocks = read_docx_blocks(docx)
    assert blocks == [
        "Top Title",
        "Subsection A",
        "Body paragraph one.",
        "Bullet item alpha",
        "Bullet item beta",
        "Subsection B",
        "Body paragraph two.",
    ]


def test_baseline_split_runs_concatenate_within_paragraph(tmp_path: Path) -> None:
    """Multi-run paragraphs are joined run-by-run without separators."""
    docx = _build_split_run_docx(tmp_path)
    output = read_docx(docx)
    assert output == "Part one part two part three."


def test_baseline_empty_paragraphs_dropped(tmp_path: Path) -> None:
    """Empty and whitespace-only paragraphs are skipped, not preserved as blank lines."""
    docx = _build_empty_para_docx(tmp_path)
    blocks = read_docx_blocks(docx)
    assert blocks == ["First", "Second"]


@pytest.mark.parametrize(
    "para_count,expected_separator_count",
    [(1, 0), (2, 1), (3, 2), (5, 4)],
)
def test_baseline_separator_count_is_para_minus_one(
    tmp_path: Path,
    para_count: int,
    expected_separator_count: int,
) -> None:
    """Output joins N non-empty paragraphs with exactly N-1 blank-line separators."""
    paragraphs = "".join(f"<w:p><w:r><w:t>P{i}</w:t></w:r></w:p>" for i in range(para_count))
    body_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_DOCX_NS}"><w:body>{paragraphs}</w:body></w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        zf.writestr("word/document.xml", body_xml)
    docx = tmp_path / f"n{para_count}.docx"
    docx.write_bytes(buf.getvalue())

    output = read_docx(docx)
    assert output.count("\n\n") == expected_separator_count
