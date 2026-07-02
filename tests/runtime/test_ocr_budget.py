"""Calibrated host-relative OCR budget math (041-F T1 / 041.002-T).

Pure unit tests for :mod:`docline.runtime.ocr_budget` — the runtime application
of the portable cost model measured in the 040.002-T calibration run
(``docs/decisions/2026-06-30-ocr-memory-calibration.md``). No docling/psutil.
"""

from __future__ import annotations

import pytest

from docline.runtime import ocr_budget as ob


def test_constants_match_calibration_decision() -> None:
    assert ob.OCR_BASE_MB == pytest.approx(1412.84)
    assert ob.OCR_K_MB_PER_MPX == pytest.approx(15.4942)
    assert ob.OCR_PER_PAGE_FLOOR_MB == pytest.approx(207.0)
    assert ob.OCR_SAFE_FRACTION == pytest.approx(0.6)


def test_predict_peak_mb_formula() -> None:
    # base + k * mpx * scale^2 * pages = 1412.84 + 15.4942*2*1*3
    assert ob.predict_peak_mb(page_megapixels=2.0, scale=1.0, pages_per_group=3) == pytest.approx(
        1412.84 + 15.4942 * 2.0 * 1.0 * 3
    )


def test_per_page_floor_dominates_for_small_pages() -> None:
    # 16 GB host: budget 9600, usable 8187.16; floor cap = 8187.16 // 207 = 39.
    # Small bitmap => area cap is huge, so the fixed per-page floor governs.
    cap = ob.max_ocr_pages_per_group(16000.0, page_megapixels=0.083, scale=2.0)
    assert cap == 39


def test_bitmap_area_dominates_for_large_pages() -> None:
    # Large mpx*scale^2 => the marginal bitmap term caps below the per-page floor.
    # usable 8187.16; marginal = 15.4942*50*4 = 3098.84; area cap = 2.
    cap = ob.max_ocr_pages_per_group(16000.0, page_megapixels=50.0, scale=2.0)
    assert cap == 2


def test_cap_scales_up_with_available_memory() -> None:
    # The whole point of 041-F: a bigger box caps higher than a small one.
    small = ob.max_ocr_pages_per_group(8000.0, page_megapixels=0.5, scale=2.0)
    big = ob.max_ocr_pages_per_group(128000.0, page_megapixels=0.5, scale=2.0)
    assert big > small
    # 128 GB clearly exceeds the provisional fixed cap of 8.
    assert big > 8


def test_cap_never_below_one_when_base_exceeds_budget() -> None:
    # 2 GB host: budget 1200 < base 1412.84 => a single page is still attempted.
    assert ob.max_ocr_pages_per_group(2000.0, page_megapixels=8.0, scale=2.0) == 1


def test_recover_scale_picks_highest_fitting() -> None:
    # budget 1560; single 8 mpx page: s=1.0 -> 1536.8 fits, s=2.0 -> 1908 does not.
    scale = ob.recover_scale_for_single_page(
        2600.0, page_megapixels=8.0, candidate_scales=(2.0, 1.0, 0.5, 0.25)
    )
    assert scale == pytest.approx(1.0)


def test_recover_scale_returns_none_when_nothing_fits() -> None:
    # budget 1200 < even the smallest-scale single-page peak (~1420) => heuristic.
    scale = ob.recover_scale_for_single_page(
        2000.0, page_megapixels=8.0, candidate_scales=(2.0, 1.0, 0.5, 0.25)
    )
    assert scale is None
