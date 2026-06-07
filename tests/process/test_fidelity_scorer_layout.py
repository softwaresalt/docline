"""Tests for ``signal_layout_complexity`` (task 020.004-T / U3)."""

from __future__ import annotations

from pathlib import Path

import pypdf
import pytest


def _make_blank_pdf(path: Path, page_count: int = 1) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def test_signal_layout_complexity_no_metadata_returns_zero() -> None:
    """`signal_layout_complexity(text, page_metadata=None)` MUST return 0.0.

    Charitable-when-no-metadata pattern: without page metadata, the signal
    cannot inspect source PDF structure, so it returns 0.0 rather than
    falsely flagging. Mirrors the pattern from `signal_char_density`.
    """
    from docline.process.fidelity_scorer import signal_layout_complexity

    assert signal_layout_complexity("any text content", page_metadata=None) == pytest.approx(0.0)


def test_signal_layout_complexity_on_blank_page_returns_zero(tmp_path: Path) -> None:
    """A blank single-page PDF has no layout complexity to detect."""
    from docline.process.fidelity_scorer import signal_layout_complexity

    pdf_path = _make_blank_pdf(tmp_path / "blank.pdf", page_count=1)
    reader = pypdf.PdfReader(str(pdf_path), strict=False)
    page = reader.pages[0]
    score = signal_layout_complexity("", page_metadata=page)
    assert score == pytest.approx(0.0)


def test_layout_complexity_in_signal_names() -> None:
    """`layout_complexity` MUST appear in `_SIGNAL_NAMES`."""
    from docline.process.fidelity_scorer import _SIGNAL_NAMES

    assert "layout_complexity" in _SIGNAL_NAMES


def test_layout_complexity_default_weight_present() -> None:
    """`_DEFAULT_SIGNAL_WEIGHTS` MUST include layout_complexity with weight ~1.1."""
    from docline.process.fidelity_scorer import _DEFAULT_SIGNAL_WEIGHTS

    assert "layout_complexity" in _DEFAULT_SIGNAL_WEIGHTS
    assert _DEFAULT_SIGNAL_WEIGHTS["layout_complexity"] == pytest.approx(1.1)


def test_score_page_includes_layout_complexity_in_signals_dict(tmp_path: Path) -> None:
    """`score_page` output MUST include `layout_complexity` in the signals dict."""
    from docline.process.fidelity_scorer import score_page

    pdf_path = _make_blank_pdf(tmp_path / "blank.pdf", page_count=1)
    reader = pypdf.PdfReader(str(pdf_path), strict=False)
    result = score_page(0, "some prose text", page_metadata=reader.pages[0])
    assert "layout_complexity" in result.signals
