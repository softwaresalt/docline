"""Tests for ``docline.readers.pdf_splitter`` (019.001.001-T).

Covers ``split_pdf`` per the contract documented in
``docs/plans/2026-06-05-shipment-a-runtime-safety-primitives.md`` and the
revised stash F64683BC.

Tests build synthetic PDFs in-process via pypdf so no binary fixtures
are needed.
"""

from __future__ import annotations

from pathlib import Path

import pypdf
import pytest


def _make_pdf(path: Path, page_count: int) -> Path:
    """Write a syntactically-valid PDF with ``page_count`` blank pages."""

    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)  # US letter
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def test_split_pdf_clean_split_into_n_chunks(tmp_path: Path) -> None:
    """A 100-page PDF split with max_pages=25 and overlap=0 yields 4 chunks."""

    from docline.readers.pdf_splitter import split_pdf

    src = _make_pdf(tmp_path / "big.pdf", page_count=100)
    chunks = split_pdf(src, max_pages=25, page_overlap=0, cache_dir=tmp_path / "chunks")

    assert len(chunks) == 4
    for chunk in chunks:
        assert chunk.exists()
        reader = pypdf.PdfReader(str(chunk), strict=False)
        assert len(reader.pages) == 25


def test_split_pdf_with_overlap_repeats_tail_pages(tmp_path: Path) -> None:
    """Overlap=2, max_pages=10 on a 20-page PDF yields 3 chunks (10, 10, 4)."""

    from docline.readers.pdf_splitter import split_pdf

    src = _make_pdf(tmp_path / "doc.pdf", page_count=20)
    chunks = split_pdf(src, max_pages=10, page_overlap=2, cache_dir=tmp_path / "chunks")

    # stride = max_pages - page_overlap = 8
    # starts: 0, 8, 16 → chunks of size 10, 10, 4
    assert len(chunks) == 3
    sizes = [len(pypdf.PdfReader(str(c), strict=False).pages) for c in chunks]
    assert sizes == [10, 10, 4]


def test_split_pdf_smaller_than_max_returns_original(tmp_path: Path) -> None:
    """When page_count <= max_pages, returns [path] unchanged (no splitting)."""

    from docline.readers.pdf_splitter import split_pdf

    src = _make_pdf(tmp_path / "small.pdf", page_count=5)
    chunks = split_pdf(src, max_pages=25, cache_dir=tmp_path / "chunks")

    assert chunks == [src]


def test_split_pdf_single_page_returns_original(tmp_path: Path) -> None:
    """One-page PDF returns the original (under any positive max_pages)."""

    from docline.readers.pdf_splitter import split_pdf

    src = _make_pdf(tmp_path / "one.pdf", page_count=1)
    chunks = split_pdf(src, max_pages=10, cache_dir=tmp_path / "chunks")

    assert chunks == [src]


def test_split_pdf_zero_pages_returns_empty(tmp_path: Path) -> None:
    """Zero-page PDFs return an empty list rather than splitting."""

    from docline.readers.pdf_splitter import split_pdf

    src = _make_pdf(tmp_path / "empty.pdf", page_count=0)
    chunks = split_pdf(src, max_pages=25, cache_dir=tmp_path / "chunks")

    assert chunks == []


def test_split_pdf_cache_reuse_returns_same_paths(tmp_path: Path) -> None:
    """Re-running split on the same source returns identical paths and skips re-write."""

    from docline.readers.pdf_splitter import split_pdf

    src = _make_pdf(tmp_path / "doc.pdf", page_count=50)
    cache = tmp_path / "chunks"
    first = split_pdf(src, max_pages=25, page_overlap=0, cache_dir=cache)
    first_mtimes = [c.stat().st_mtime_ns for c in first]

    second = split_pdf(src, max_pages=25, page_overlap=0, cache_dir=cache)
    second_mtimes = [c.stat().st_mtime_ns for c in second]

    assert first == second
    assert first_mtimes == second_mtimes  # cache hit means no re-write


def test_split_pdf_rejects_max_pages_zero(tmp_path: Path) -> None:
    """max_pages < 1 is rejected with a clear message."""

    from docline.readers.pdf_splitter import split_pdf

    src = _make_pdf(tmp_path / "doc.pdf", page_count=5)
    with pytest.raises(ValueError, match="max_pages must be >= 1"):
        split_pdf(src, max_pages=0)


def test_split_pdf_rejects_overlap_ge_max(tmp_path: Path) -> None:
    """page_overlap >= max_pages is rejected."""

    from docline.readers.pdf_splitter import split_pdf

    src = _make_pdf(tmp_path / "doc.pdf", page_count=50)
    with pytest.raises(ValueError, match="page_overlap"):
        split_pdf(src, max_pages=5, page_overlap=10)


def test_split_pdf_rejects_negative_overlap(tmp_path: Path) -> None:
    """Negative page_overlap is rejected."""

    from docline.readers.pdf_splitter import split_pdf

    src = _make_pdf(tmp_path / "doc.pdf", page_count=50)
    with pytest.raises(ValueError, match="page_overlap"):
        split_pdf(src, max_pages=10, page_overlap=-1)


def test_split_pdf_raises_when_path_missing(tmp_path: Path) -> None:
    """Missing path propagates FileNotFoundError."""

    from docline.readers.pdf_splitter import split_pdf

    with pytest.raises(FileNotFoundError):
        split_pdf(tmp_path / "nope.pdf", max_pages=10)


def test_split_pdf_produces_valid_chunk_pdfs(tmp_path: Path) -> None:
    """Every chunk is itself a valid PDF that pypdf can re-read."""

    from docline.readers.pdf_splitter import split_pdf

    src = _make_pdf(tmp_path / "doc.pdf", page_count=30)
    chunks = split_pdf(src, max_pages=10, page_overlap=0, cache_dir=tmp_path / "chunks")

    for chunk in chunks:
        reader = pypdf.PdfReader(str(chunk), strict=False)
        # Each chunk reader should be able to enumerate its pages.
        for page in reader.pages:
            assert page is not None
