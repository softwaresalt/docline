"""Runtime OCR pages-per-group cap resolution (041-F T2 / 041.001-T).

Tests for :mod:`docline.process.ocr_cap`, which bridges the host resource probe
and the calibrated cost model into the concrete ``ocr_max_pages`` used by the
batched grouping + dispatch, falling back to the provisional
``OCR_MAX_BATCHED_PAGES`` when memory or page size is undeterminable.
"""

from __future__ import annotations

from pathlib import Path

import pypdf
import pytest

from docline.process.ocr_cap import representative_ocr_megapixels, resolve_ocr_max_pages
from docline.process.page_range import OCR_MAX_BATCHED_PAGES
from docline.runtime.ocr_budget import page_megapixels_from_points


def _make_pdf(path: Path, width_pts: float, height_pts: float, pages: int = 1) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width_pts, height=height_pts)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def test_page_megapixels_from_points_letter() -> None:
    # 612 x 792 pt letter page at the 72-DPI base -> width*height/1e6 mpx.
    assert page_megapixels_from_points(612.0, 792.0) == pytest.approx(612.0 * 792.0 / 1_000_000.0)


def test_representative_takes_largest_page(tmp_path: Path) -> None:
    small = _make_pdf(tmp_path / "a.pdf", 300.0, 400.0)
    big = _make_pdf(tmp_path / "b.pdf", 1920.0, 1080.0)
    mpx = representative_ocr_megapixels([small, big])
    assert mpx == pytest.approx(1920.0 * 1080.0 / 1_000_000.0)


def test_representative_scans_all_pages_not_just_first(tmp_path: Path) -> None:
    # A mixed-size PDF whose FIRST page is small but a later page is large:
    # scanning only page 0 would underestimate and inflate the cap.
    path = tmp_path / "mixed.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=300.0, height=400.0)  # small first page
    writer.add_blank_page(width=1920.0, height=1080.0)  # large later page
    with path.open("wb") as fh:
        writer.write(fh)
    mpx = representative_ocr_megapixels([path])
    assert mpx == pytest.approx(1920.0 * 1080.0 / 1_000_000.0)


def test_representative_none_when_unreadable(tmp_path: Path) -> None:
    assert representative_ocr_megapixels([tmp_path / "missing.pdf"]) is None


def test_cap_scales_with_available_ram(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "p.pdf", 612.0, 792.0)
    big = resolve_ocr_max_pages(64.0, [pdf])
    small = resolve_ocr_max_pages(5.0, [pdf])
    assert big > small
    # A 128 GB-class host caps higher than the provisional fixed 8 (the point of 041-F).
    assert big > OCR_MAX_BATCHED_PAGES


def test_cap_falls_back_when_probe_degraded(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "p.pdf", 612.0, 792.0)
    assert resolve_ocr_max_pages(0.0, [pdf]) == OCR_MAX_BATCHED_PAGES


def test_cap_falls_back_when_no_ocr_paths() -> None:
    assert resolve_ocr_max_pages(64.0, []) == OCR_MAX_BATCHED_PAGES


def test_cap_falls_back_when_pdf_unreadable(tmp_path: Path) -> None:
    assert resolve_ocr_max_pages(64.0, [tmp_path / "nope.pdf"]) == OCR_MAX_BATCHED_PAGES
