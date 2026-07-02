"""Calibrated, host-relative OCR peak-memory budgeting (041-F).

Applies the portable cost model measured in the 040.002-T calibration run
(``docs/decisions/2026-06-30-ocr-memory-calibration.md``) to decide, at runtime
on any host, how many OCR pages fit in one docling worker group and what render
scale brings an oversized single page under a safe fraction of available memory.

The model is::

    peak_mb ~= base_mb + k_mb_per_mpx * (page_megapixels * scale^2 * pages_per_group)

The 040.002-T run on a digital corpus additionally found a fixed per-page floor
(~207 MB/page) that the bitmap-area term underestimates (its fit R^2 was 0.148
because per-page cost was scale/mpx-insensitive), so the pages-per-group cap is
the *smaller* of the bitmap-area cap and the per-page-floor cap.

This module is intentionally dependency-free (no docling / psutil / torch) so
``page_range`` and ``resource_probe`` can import it cheaply and it stays
unit-testable with synthetic inputs.
"""

from __future__ import annotations

from collections.abc import Sequence

# Calibrated coefficients from the 040.002-T operator run. Re-calibration on a
# scanned / high-megapixel corpus (stash A3E6D72C) may refine these.
OCR_BASE_MB: float = 1412.84
OCR_K_MB_PER_MPX: float = 15.4942
OCR_PER_PAGE_FLOOR_MB: float = 207.0
OCR_SAFE_FRACTION: float = 0.6


def page_megapixels_from_points(width_points: float, height_points: float) -> float:
    """Page bitmap size in megapixels at the 72-DPI base from a PDF mediabox.

    A PostScript point is 1/72 inch, so at the 72-DPI base one point maps to one
    pixel and the 72 factor cancels: ``megapixels = width * height / 1e6``. This
    matches the calibration harness's ``page_megapixels`` definition.

    Args:
        width_points: Mediabox width in points.
        height_points: Mediabox height in points.

    Returns:
        The page bitmap size in megapixels.
    """
    return width_points * height_points / 1_000_000.0


def predict_peak_mb(*, page_megapixels: float, scale: float, pages_per_group: int) -> float:
    """Predicted docling OCR peak RSS (MB) for a group of like pages.

    Args:
        page_megapixels: Page bitmap size at the 72-DPI base, in megapixels.
        scale: docling ``images_scale`` render multiplier (1.0 == 72 DPI).
        pages_per_group: Number of pages accumulated in the worker subprocess.

    Returns:
        Predicted peak resident set size in megabytes.
    """
    return OCR_BASE_MB + OCR_K_MB_PER_MPX * page_megapixels * scale * scale * pages_per_group


def max_ocr_pages_per_group(
    available_mb: float,
    *,
    page_megapixels: float,
    scale: float = 2.0,
    safe_fraction: float = OCR_SAFE_FRACTION,
) -> int:
    """Max OCR pages per docling group within ``safe_fraction`` of available memory.

    Returns the smaller of the bitmap-area cap (from the calibrated marginal
    ``k`` term) and the empirical fixed per-page-floor cap. The result scales
    with the host's ``available_mb``, so a large box caps higher than a small
    one from the same coefficients. Never returns below 1: a single page is
    always attempted, then downscaled via :func:`recover_scale_for_single_page`
    if it still does not fit.

    Args:
        available_mb: Host available memory in megabytes (decimal).
        page_megapixels: Representative page bitmap size at 72-DPI base.
        scale: docling ``images_scale`` the group will render at (default 2.0,
            docling's own default).
        safe_fraction: Fraction of ``available_mb`` to stay within.

    Returns:
        The pages-per-group cap, an integer ``>= 1``.
    """
    budget = available_mb * safe_fraction
    usable = budget - OCR_BASE_MB
    if usable <= 0:
        return 1
    floor_cap = int(usable // OCR_PER_PAGE_FLOOR_MB) if OCR_PER_PAGE_FLOOR_MB > 0 else 1
    marginal = OCR_K_MB_PER_MPX * page_megapixels * scale * scale
    # When the bitmap term vanishes (tiny page/scale) the per-page floor governs.
    area_cap = int(usable // marginal) if marginal > 0 else floor_cap
    return max(1, min(area_cap, floor_cap))


def recover_render_scale(
    available_mb: float,
    *,
    page_megapixels: float,
    pages_per_group: int,
    candidate_scales: Sequence[float],
    safe_fraction: float = OCR_SAFE_FRACTION,
) -> float | None:
    """Highest candidate render scale at which ``pages_per_group`` pages fit budget.

    The downscale-retry path walks candidate scales from high to low; this
    returns the first (highest-resolution) scale whose predicted peak for the
    group fits ``safe_fraction`` of available memory. Accounting for the actual
    page count matters because a scale that fits one page can still OOM a
    multi-page chunk/range.

    Args:
        available_mb: Host available memory in megabytes (decimal).
        page_megapixels: The (largest) page bitmap size at 72-DPI base.
        pages_per_group: Number of pages the retried group will render.
        candidate_scales: Render scales to consider (any order).
        safe_fraction: Fraction of ``available_mb`` to stay within.

    Returns:
        The highest fitting scale, or ``None`` when no candidate scale brings the
        group under budget (the caller then concedes to heuristic).
    """
    budget = available_mb * safe_fraction
    for candidate in sorted(candidate_scales, reverse=True):
        peak = predict_peak_mb(
            page_megapixels=page_megapixels, scale=candidate, pages_per_group=pages_per_group
        )
        if peak <= budget:
            return candidate
    return None


def recover_scale_for_single_page(
    available_mb: float,
    *,
    page_megapixels: float,
    candidate_scales: Sequence[float],
    safe_fraction: float = OCR_SAFE_FRACTION,
) -> float | None:
    """Highest candidate render scale at which a SINGLE page fits the budget.

    Thin wrapper over :func:`recover_render_scale` with ``pages_per_group=1``.

    Args:
        available_mb: Host available memory in megabytes (decimal).
        page_megapixels: The oversized page's bitmap size at 72-DPI base.
        candidate_scales: Render scales to consider (any order).
        safe_fraction: Fraction of ``available_mb`` to stay within.

    Returns:
        The highest fitting scale, or ``None`` when no candidate scale brings a
        single page under budget (the caller then concedes to heuristic).
    """
    return recover_render_scale(
        available_mb,
        page_megapixels=page_megapixels,
        pages_per_group=1,
        candidate_scales=candidate_scales,
        safe_fraction=safe_fraction,
    )
