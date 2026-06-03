"""Red-first PDF layout heuristic tests (010-S F5.T2).

These tests pin the **target** behavior of the phase-1 font-size histogram
heuristic that F5.T3 (010.022-T) will implement in ``src/docline/readers/pdf.py``.

The heuristic clusters glyph sizes emitted via PDF ``Tf`` (set-font) operators
into at most three bands and assigns:

* top band → ``# `` (H1)
* second band → ``## `` (H2)
* third band → ``### `` (H3)

These assertions are expected to **fail** before F5.T3 lands because the
current built-in extractor and the ``pypdf`` extractor both discard glyph
size information. Pypdf is patched off so the deterministic built-in path
is exercised regardless of optional-dependency availability.

When F5.T3 lands and the heuristic begins emitting ATX heading markers,
these tests must pass and the corresponding "no headings" baseline
invariants in ``test_pdf_baseline_characterization.py`` will be retired or
inverted per the F5.T1→T2→T3 handoff contract documented in the plan.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import docline.readers.pdf as pdf_module
from docline.readers.pdf import read_pdf

# ---------------------------------------------------------------------------
# Synthetic PDF builders — text blocks scoped under ``Tf`` font-size operators
# ---------------------------------------------------------------------------
#
# The minimal PDF blobs below intentionally omit xref tables so the built-in
# extractor path is exercised. Each block uses the ``/F1 <size> Tf`` operator
# to declare the active font size for the subsequent ``Tj`` text.


def _build_three_band_pdf(tmp_path: Path) -> Path:
    """Three distinct font sizes → H1, H2, H3, body."""
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog >> endobj\n"
        b"2 0 obj << /Length 200 >>\nstream\n"
        b"BT /F1 24 Tf (Document Title) Tj ET\n"
        b"BT /F1 16 Tf (Section Heading) Tj ET\n"
        b"BT /F1 12 Tf (Subsection) Tj ET\n"
        b"BT /F1 10 Tf (Body paragraph one.) Tj ET\n"
        b"BT /F1 10 Tf (Body paragraph two.) Tj ET\n"
        b"endstream\nendobj\n"
        b"%%EOF\n"
    )
    path = tmp_path / "three_band.pdf"
    path.write_bytes(body)
    return path


def _build_two_band_pdf(tmp_path: Path) -> Path:
    """Two distinct font sizes → H1 + body (no H2/H3 should appear)."""
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog >> endobj\n"
        b"2 0 obj << /Length 140 >>\nstream\n"
        b"BT /F1 24 Tf (Title Only) Tj ET\n"
        b"BT /F1 10 Tf (First body line.) Tj ET\n"
        b"BT /F1 10 Tf (Second body line.) Tj ET\n"
        b"endstream\nendobj\n"
        b"%%EOF\n"
    )
    path = tmp_path / "two_band.pdf"
    path.write_bytes(body)
    return path


def _build_uniform_pdf(tmp_path: Path) -> Path:
    """All glyphs at one size → no heading markers; body-only emission."""
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog >> endobj\n"
        b"2 0 obj << /Length 120 >>\nstream\n"
        b"BT /F1 11 Tf (Uniform paragraph one.) Tj ET\n"
        b"BT /F1 11 Tf (Uniform paragraph two.) Tj ET\n"
        b"endstream\nendobj\n"
        b"%%EOF\n"
    )
    path = tmp_path / "uniform.pdf"
    path.write_bytes(body)
    return path


# ---------------------------------------------------------------------------
# Tests — target behavior the F5.T3 heuristic must satisfy
# ---------------------------------------------------------------------------


def test_three_band_emits_h1_h2_h3_markers(tmp_path: Path) -> None:
    """Three font sizes cluster into three bands; each band assigned a heading level."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)
    lines = [ln for ln in result.splitlines() if ln.strip()]

    h1_lines = [ln for ln in lines if ln.startswith("# ")]
    h2_lines = [ln for ln in lines if ln.startswith("## ")]
    h3_lines = [ln for ln in lines if ln.startswith("### ")]

    assert any("Document Title" in ln for ln in h1_lines), (
        f"Expected 'Document Title' at H1 in output: {result!r}"
    )
    assert any("Section Heading" in ln for ln in h2_lines), (
        f"Expected 'Section Heading' at H2 in output: {result!r}"
    )
    assert any("Subsection" in ln for ln in h3_lines), (
        f"Expected 'Subsection' at H3 in output: {result!r}"
    )


def test_three_band_body_text_remains_unmarked(tmp_path: Path) -> None:
    """Glyphs in the smallest band (body) must NOT be marked with ATX headings."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)

    for body_phrase in ("Body paragraph one.", "Body paragraph two."):
        for line in result.splitlines():
            if body_phrase in line:
                assert not line.startswith("# "), f"Body text should not be H1: {line!r}"
                assert not line.startswith("## "), f"Body text should not be H2: {line!r}"
                assert not line.startswith("### "), f"Body text should not be H3: {line!r}"


def test_two_band_emits_only_h1_and_body(tmp_path: Path) -> None:
    """Two font sizes → only H1 emitted; body text remains unmarked."""
    pdf_path = _build_two_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)
    lines = [ln for ln in result.splitlines() if ln.strip()]

    h1_lines = [ln for ln in lines if ln.startswith("# ")]
    h2_lines = [ln for ln in lines if ln.startswith("## ")]
    h3_lines = [ln for ln in lines if ln.startswith("### ")]

    assert any("Title Only" in ln for ln in h1_lines), (
        f"Expected 'Title Only' at H1 in output: {result!r}"
    )
    assert h2_lines == [], f"With only two bands no H2 should be emitted; got: {h2_lines!r}"
    assert h3_lines == [], f"With only two bands no H3 should be emitted; got: {h3_lines!r}"

    for body_phrase in ("First body line.", "Second body line."):
        for line in lines:
            if body_phrase in line:
                assert not line.startswith("#"), f"Body text should not start with '#': {line!r}"


def test_uniform_font_size_emits_no_headings(tmp_path: Path) -> None:
    """Single font size → no heading bands; all output is body text."""
    pdf_path = _build_uniform_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)

    for line in result.splitlines():
        assert not line.startswith("# "), f"Uniform text should not be H1: {line!r}"
        assert not line.startswith("## "), f"Uniform text should not be H2: {line!r}"
        assert not line.startswith("### "), f"Uniform text should not be H3: {line!r}"


def test_three_band_heading_order_preserved(tmp_path: Path) -> None:
    """Heading markers must appear in document order (H1 before H2 before H3)."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)

    idx_h1 = result.find("# Document Title")
    idx_h2 = result.find("## Section Heading")
    idx_h3 = result.find("### Subsection")

    assert idx_h1 >= 0, f"H1 marker missing in: {result!r}"
    assert idx_h2 >= 0, f"H2 marker missing in: {result!r}"
    assert idx_h3 >= 0, f"H3 marker missing in: {result!r}"
    assert idx_h1 < idx_h2 < idx_h3, (
        f"Heading order not preserved (h1={idx_h1}, h2={idx_h2}, h3={idx_h3}): {result!r}"
    )


@pytest.mark.parametrize(
    "builder,expected_phrases",
    [
        (
            _build_three_band_pdf,
            (
                "Document Title",
                "Section Heading",
                "Subsection",
                "Body paragraph one.",
                "Body paragraph two.",
            ),
        ),
        (_build_two_band_pdf, ("Title Only", "First body line.", "Second body line.")),
        (_build_uniform_pdf, ("Uniform paragraph one.", "Uniform paragraph two.")),
    ],
)
def test_layout_extraction_preserves_all_text_content(
    builder, expected_phrases, tmp_path: Path
) -> None:
    """Heuristic must not drop any extracted text — heading markers only annotate."""
    pdf_path = builder(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path)
    for phrase in expected_phrases:
        assert phrase in result, (
            f"Expected text '{phrase}' missing from heuristic output: {result!r}"
        )
