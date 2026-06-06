"""PDF splitter for oversized PDFs that exceed the docling memory budget.

This module is the default routing target for any PDF whose size or page
count exceeds the per-call budget returned by
:func:`docline.runtime.resource_probe.probe`. Each chunk is small enough
that docling can process it safely on the host class that motivated the
2026-06-04 RCA (i7-4700MQ + 32 GB RAM, no usable GPU).

Design:

* **Lossless page extraction** via ``pypdf`` (already a project
  dependency). Each chunk file is a valid standalone PDF.
* **Deterministic chunk naming** ``{source_hash}-chunk-NNNN.pdf`` so
  re-running on the same PDF reuses cached splits.
* **Page-count splitting** rather than byte-count. Docling memory
  pressure scales with page count × image density, not file size.
* **Page overlap** option lets the downstream batch processor reconcile
  H1 anchors that span chunk boundaries — when ``page_overlap=2`` the
  first two pages of chunk N+1 are the last two pages of chunk N.

See ``docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md``
remediation 3 for the motivating failure pattern.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path

import pypdf

_log = logging.getLogger(__name__)

_DEFAULT_PAGE_OVERLAP = 2


def split_pdf(
    path: Path,
    *,
    max_pages: int,
    page_overlap: int = _DEFAULT_PAGE_OVERLAP,
    cache_dir: Path | None = None,
) -> list[Path]:
    """Split a PDF into deterministic page-aligned chunks under ``max_pages`` each.

    Args:
        path: Source PDF path. Must exist.
        max_pages: Maximum pages per chunk. Must be >= 1. Typically
            sourced from
            :attr:`docline.runtime.resource_probe.ResourceBudget.recommended_docling_max_pages`.
        page_overlap: Number of pages to repeat at the start of each
            chunk after the first. Default 2 so the batch processor
            can reconcile headers that span chunk boundaries. Must be
            >= 0 and < ``max_pages``.
        cache_dir: Directory under which chunk files are written.
            Defaults to a per-source subdirectory of
            ``tempfile.gettempdir()`` so re-runs reuse the same paths.

    Returns:
        Ordered list of chunk file paths. When the input PDF has
        ``page_count <= max_pages``, returns ``[path]`` unchanged
        (no splitting needed). When the input has zero pages, returns
        an empty list.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If ``max_pages < 1`` or ``page_overlap >= max_pages``
            or ``page_overlap < 0``.
        pypdf.errors.PdfReadError: If pypdf cannot parse the input PDF.
    """
    if max_pages < 1:
        raise ValueError(f"max_pages must be >= 1, got {max_pages}")
    if page_overlap < 0:
        raise ValueError(f"page_overlap must be >= 0, got {page_overlap}")
    if page_overlap >= max_pages:
        raise ValueError(f"page_overlap ({page_overlap}) must be < max_pages ({max_pages})")
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    reader = pypdf.PdfReader(str(path), strict=False)
    total_pages = len(reader.pages)
    if total_pages == 0:
        return []
    if total_pages <= max_pages:
        # No need to split — the original PDF already fits within the budget.
        return [path]

    source_hash = _hash_path(path)
    target_dir = _resolve_cache_dir(cache_dir, source_hash)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Compute chunk ranges with overlap. Each chunk after the first
    # starts (max_pages - page_overlap) pages later than its predecessor.
    stride = max_pages - page_overlap
    chunk_starts: list[int] = []
    start = 0
    while start < total_pages:
        chunk_starts.append(start)
        start += stride

    chunk_paths: list[Path] = []
    for idx, start_page in enumerate(chunk_starts):
        end_page = min(start_page + max_pages, total_pages)
        chunk_name = f"{source_hash}-chunk-{idx + 1:04d}.pdf"
        chunk_path = target_dir / chunk_name

        if chunk_path.exists():
            # Cached chunk reused.
            chunk_paths.append(chunk_path)
            continue

        writer = pypdf.PdfWriter()
        for page_idx in range(start_page, end_page):
            writer.add_page(reader.pages[page_idx])
        with chunk_path.open("wb") as fh:
            writer.write(fh)
        chunk_paths.append(chunk_path)

    return chunk_paths


def _hash_path(path: Path) -> str:
    """Hash the source path's bytes + size for a stable, short chunk-set id."""

    hasher = hashlib.sha256()
    hasher.update(str(path.resolve()).encode("utf-8"))
    hasher.update(str(path.stat().st_size).encode("utf-8"))
    return hasher.hexdigest()[:16]


def _resolve_cache_dir(cache_dir: Path | None, source_hash: str) -> Path:
    """Pick a per-source cache directory under ``cache_dir`` or the temp dir."""

    base = (
        cache_dir if cache_dir is not None else Path(tempfile.gettempdir()) / "docline-pdf-chunks"
    )
    return base / source_hash
