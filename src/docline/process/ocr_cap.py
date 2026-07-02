"""Resolve the runtime, host-relative OCR pages-per-group cap (041-F).

Bridges the host resource probe and the calibrated cost model
(:mod:`docline.runtime.ocr_budget`) into the concrete ``ocr_max_pages`` that the
batched grouping (:func:`docline.process.page_range.group_by_page_count_ocr_aware`)
and adaptive dispatch
(:func:`docline.process.batch_dispatch.dispatch_batched_groups_with_retry`) use.

The provisional fixed :data:`~docline.process.page_range.OCR_MAX_BATCHED_PAGES`
is now only the degraded-probe fallback: when the host's available memory and a
representative page size are both known, the cap scales with the host so a large
box caps higher than a small one.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import pypdf

from docline.process.page_range import OCR_MAX_BATCHED_PAGES
from docline.runtime import ocr_budget

_log = logging.getLogger(__name__)

_MB_PER_GB = 1000.0  # decimal MB per GB, matching psutil / ResourceBudget units


def representative_ocr_megapixels(pdf_paths: Sequence[Path]) -> float | None:
    """Largest page bitmap size (megapixels) across all pages of the given OCR PDFs.

    The largest page drives peak OCR memory, so the cap is derived from it. Every
    page's mediabox is inspected (chunks/ranges are bounded) because page 0 is
    not necessarily the largest in a mixed-size document.

    Args:
        pdf_paths: OCR-flagged input PDF paths to sample.

    Returns:
        The maximum page megapixels seen, or ``None`` when no path yields a
        readable mediabox.
    """
    best: float | None = None
    for pdf_path in pdf_paths:
        try:
            reader = pypdf.PdfReader(str(pdf_path), strict=False)
            for page in reader.pages:
                box = page.mediabox
                mpx = ocr_budget.page_megapixels_from_points(float(box.width), float(box.height))
                if best is None or mpx > best:
                    best = mpx
        except Exception as err:  # noqa: BLE001 — a bad/missing PDF just falls back
            _log.debug("could not read mediabox from %s (%s); skipping", pdf_path, err)
            continue
    return best


def resolve_ocr_cap(
    available_ram_gb: float, ocr_pdf_paths: Sequence[Path]
) -> tuple[int, float | None]:
    """Host-relative OCR cap and the representative page size it was derived from.

    Args:
        available_ram_gb: Host available RAM in decimal GB (from
            :attr:`docline.runtime.resource_probe.ResourceBudget.available_ram_gb`).
        ocr_pdf_paths: OCR-flagged input PDFs used to size a representative page.

    Returns:
        ``(ocr_max_pages, page_megapixels)``. ``page_megapixels`` is ``None`` and
        the cap is :data:`~docline.process.page_range.OCR_MAX_BATCHED_PAGES` when
        the probe is degraded, there are no OCR paths, or no page size can be
        read — signalling callers to disable memory-derived downsizing too.
    """
    if available_ram_gb <= 0 or not ocr_pdf_paths:
        return OCR_MAX_BATCHED_PAGES, None
    mpx = representative_ocr_megapixels(ocr_pdf_paths)
    if mpx is None or mpx <= 0:
        return OCR_MAX_BATCHED_PAGES, None
    cap = ocr_budget.max_ocr_pages_per_group(available_ram_gb * _MB_PER_GB, page_megapixels=mpx)
    return cap, mpx


def resolve_ocr_max_pages(available_ram_gb: float, ocr_pdf_paths: Sequence[Path]) -> int:
    """Host-relative OCR pages-per-group cap, or the fallback when undeterminable.

    Thin wrapper over :func:`resolve_ocr_cap` for callers that only need the cap.

    Args:
        available_ram_gb: Host available RAM in decimal GB.
        ocr_pdf_paths: OCR-flagged input PDFs used to size a representative page.

    Returns:
        The memory-aware ``ocr_max_pages`` (``>= 1``), or
        :data:`~docline.process.page_range.OCR_MAX_BATCHED_PAGES` when
        undeterminable.
    """
    return resolve_ocr_cap(available_ram_gb, ocr_pdf_paths)[0]
