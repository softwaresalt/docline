"""Characterization snapshots pinning current PDF emission (010-S F5.T1).

These tests do NOT prescribe ideal behavior — they PIN the current behavior
of ``read_pdf`` and ``read_pdf_pages`` so that subsequent F5 tasks
(010.021-T red-first font-size histogram, 010.022-T heuristic phase 1 impl,
010.023-T+ phase 2 opt-in ``docling`` integration) can safely refactor with
a baseline diff signal.

When F5.T2/F5.T3 begin, the heading-absence assertions here are expected to
break by design once the font-size histogram heuristic starts emitting
``# ``/``## ``/``### `` markers. That is the characterization handoff: these
tests document what was; F5.T2 documents what should be; F5.T3 makes it so,
at which point this file is updated or removed per the F5 handoff contract.

Pypdf is pinned off for these fixtures so the built-in extractor path is
exercised deterministically. Synthetic minimal PDFs without xref tables also
cause pypdf to fall back naturally — patching ``_PYPDF_AVAILABLE`` simply
removes that dependency on pypdf's failure mode for cross-version stability.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

import docline.readers.pdf as pdf_module
from docline.readers.pdf import read_pdf, read_pdf_pages

# ---------------------------------------------------------------------------
# Fixture builders — minimal synthetic PDFs exercising the built-in extractor
# ---------------------------------------------------------------------------


def _build_simple_literal_pdf(tmp_path: Path) -> Path:
    """Build a PDF with a single page using literal ``(text) Tj`` operators."""
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog >> endobj\n"
        b"2 0 obj << /Length 60 >>\nstream\n"
        b"BT (Top Title) Tj ET\n"
        b"BT (Body paragraph one.) Tj ET\n"
        b"endstream\nendobj\n"
        b"%%EOF\n"
    )
    path = tmp_path / "simple_literal.pdf"
    path.write_bytes(body)
    return path


def _build_multi_page_pdf(tmp_path: Path) -> Path:
    """Build a PDF with two content streams that act as two ``pages`` to the built-in path."""
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog >> endobj\n"
        b"2 0 obj << /Length 30 >>\nstream\n"
        b"BT (Page one text) Tj ET\n"
        b"endstream\nendobj\n"
        b"3 0 obj << /Length 30 >>\nstream\n"
        b"BT (Page two text) Tj ET\n"
        b"endstream\nendobj\n"
        b"%%EOF\n"
    )
    path = tmp_path / "multi_page.pdf"
    path.write_bytes(body)
    return path


def _build_array_tj_pdf(tmp_path: Path) -> Path:
    """Build a PDF using the ``[(a) (b)] TJ`` array-of-strings operator."""
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog >> endobj\n"
        b"2 0 obj << /Length 80 >>\nstream\n"
        b"BT [(Array start ) -100 (middle ) -100 (end)] TJ ET\n"
        b"endstream\nendobj\n"
        b"%%EOF\n"
    )
    path = tmp_path / "array_tj.pdf"
    path.write_bytes(body)
    return path


def _build_hex_tj_pdf(tmp_path: Path) -> Path:
    """Build a PDF using ``<hex> Tj`` hex-string operators (ASCII ``Hex text``)."""
    # "Hex text" -> 48 65 78 20 74 65 78 74
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog >> endobj\n"
        b"2 0 obj << /Length 50 >>\nstream\n"
        b"BT <4865782074657874> Tj ET\n"
        b"endstream\nendobj\n"
        b"%%EOF\n"
    )
    path = tmp_path / "hex_tj.pdf"
    path.write_bytes(body)
    return path


# ---------------------------------------------------------------------------
# Baseline: read_pdf returns concatenated text joined by ``\n\n``
# ---------------------------------------------------------------------------


def test_baseline_simple_literal_emits_plain_text(tmp_path: Path) -> None:
    """Current behavior: literal ``Tj`` operators emit as plain text, no headings.

    F5.T2 will introduce a font-size heuristic; until then the top-of-document
    string is emitted without an ATX ``# `` marker. This assertion intentionally
    fails when F5.T2's heuristic begins emitting headers.
    """
    pdf_path = _build_simple_literal_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)
    assert result == "Top Title Body paragraph one."
    assert not result.startswith("# ")
    assert not result.startswith("## ")
    assert not result.startswith("### ")


def test_baseline_multi_page_joins_with_blank_line(tmp_path: Path) -> None:
    """Current behavior: ``read_pdf`` joins page texts with ``\\n\\n``."""
    pdf_path = _build_multi_page_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)
    assert result == "Page one text\n\nPage two text"


def test_baseline_array_tj_concatenates_strings_with_space(tmp_path: Path) -> None:
    """Current behavior: ``[(a) (b)] TJ`` array entries join via single space."""
    pdf_path = _build_array_tj_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)
    assert result == "Array start  middle  end"


def test_baseline_hex_tj_decodes_to_ascii(tmp_path: Path) -> None:
    """Current behavior: ``<hex> Tj`` decodes hex bytes through latin-1 fallback."""
    pdf_path = _build_hex_tj_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)
    assert result == "Hex text"


# ---------------------------------------------------------------------------
# Baseline: read_pdf_pages returns ordered non-empty page list
# ---------------------------------------------------------------------------


def test_baseline_read_pdf_pages_returns_one_page_for_single_stream(tmp_path: Path) -> None:
    """Current behavior: one content stream -> one page entry in the list."""
    pdf_path = _build_simple_literal_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        pages = read_pdf_pages(pdf_path)
    assert pages == ["Top Title Body paragraph one."]


def test_baseline_read_pdf_pages_returns_two_pages_for_two_streams(tmp_path: Path) -> None:
    """Current behavior: two content streams -> two ordered page entries."""
    pdf_path = _build_multi_page_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        pages = read_pdf_pages(pdf_path)
    assert pages == ["Page one text", "Page two text"]


# ---------------------------------------------------------------------------
# Baseline: no heading markers emitted on any fixture
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "builder",
    [
        _build_simple_literal_pdf,
        _build_multi_page_pdf,
        _build_array_tj_pdf,
        _build_hex_tj_pdf,
    ],
)
def test_baseline_no_atx_heading_markers_in_current_output(
    builder: Callable[[Path], Path], tmp_path: Path
) -> None:
    """Current behavior: no font-size heuristic, no ATX heading markers in output.

    This invariant is expected to break in F5.T3 when the font-size histogram
    heuristic begins emitting ``# `` / ``## `` / ``### `` markers for the
    top three glyph-size bands.
    """
    pdf_path = builder(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)
    for line in result.splitlines():
        assert not line.startswith("# "), f"Unexpected H1 in baseline output: {line!r}"
        assert not line.startswith("## "), f"Unexpected H2 in baseline output: {line!r}"
        assert not line.startswith("### "), f"Unexpected H3 in baseline output: {line!r}"
