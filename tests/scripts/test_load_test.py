"""Tests for ``scripts/load_test.py`` (020.001.001-T).

The harness module is imported via ``importlib`` from ``scripts/`` since
the project doesn't package it as an installed entry point. Tests focus
on the pure helpers (tier classification, TSV row construction, corpus
iteration) and the CLI argument layer. The end-to-end ``main()`` call
against a real corpus is exercised manually by the operator, not in CI.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
import time
from pathlib import Path

import pypdf
import pytest

# Load scripts/load_test.py as a module without installing it.
_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "load_test.py"
_spec = importlib.util.spec_from_file_location("docline_load_test", str(_SCRIPT_PATH))
assert _spec is not None and _spec.loader is not None
load_test = importlib.util.module_from_spec(_spec)
sys.modules["docline_load_test"] = load_test
_spec.loader.exec_module(load_test)


def _make_pdf(path: Path, page_count: int, padding_bytes: int = 0) -> Path:
    """Write a syntactically-valid PDF with a target page count + optional padding."""

    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    if padding_bytes:
        with path.open("ab") as fh:
            fh.write(b"\x00" * padding_bytes)
    return path


# ---------------------------------------------------------------------------
# classify_tier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "size_mb,expected",
    [
        (1.0, "small"),
        (9.99, "small"),
        (10.0, "small"),
        (10.01, "medium"),
        (29.99, "medium"),
        (30.0, "medium"),
        (30.01, "large"),
        (109.0, "large"),
    ],
)
def test_classify_tier(size_mb: float, expected: str) -> None:
    assert load_test.classify_tier(size_mb) == expected


def test_classify_tier_respects_custom_thresholds() -> None:
    custom = load_test.TierThresholds(small_max_mb=5.0, medium_max_mb=15.0)
    assert load_test.classify_tier(4.0, custom) == "small"
    assert load_test.classify_tier(10.0, custom) == "medium"
    assert load_test.classify_tier(20.0, custom) == "large"


# ---------------------------------------------------------------------------
# iter_corpus
# ---------------------------------------------------------------------------


def test_iter_corpus_all_returns_every_pdf(tmp_path: Path) -> None:
    _make_pdf(tmp_path / "a.pdf", page_count=1)
    _make_pdf(tmp_path / "b.pdf", page_count=1)
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    files = list(load_test.iter_corpus(tmp_path, tier_filter="all"))

    names = sorted(p.name for p, _ in files)
    assert names == ["a.pdf", "b.pdf"]


def test_iter_corpus_filters_by_tier(tmp_path: Path) -> None:
    # Build PDFs sized roughly into each tier via padding.
    _make_pdf(tmp_path / "small.pdf", page_count=1, padding_bytes=int(2 * 1_000_000))  # ~2 MB
    _make_pdf(tmp_path / "medium.pdf", page_count=1, padding_bytes=int(15 * 1_000_000))  # ~15 MB
    _make_pdf(tmp_path / "large.pdf", page_count=1, padding_bytes=int(60 * 1_000_000))  # ~60 MB

    small = [p.name for p, _ in load_test.iter_corpus(tmp_path, tier_filter="small")]
    medium = [p.name for p, _ in load_test.iter_corpus(tmp_path, tier_filter="medium")]
    large = [p.name for p, _ in load_test.iter_corpus(tmp_path, tier_filter="large")]

    assert small == ["small.pdf"]
    assert medium == ["medium.pdf"]
    assert large == ["large.pdf"]


def test_iter_corpus_rejects_unknown_tier(tmp_path: Path) -> None:
    _make_pdf(tmp_path / "doc.pdf", page_count=1)
    with pytest.raises(ValueError, match="Unknown tier filter"):
        list(load_test.iter_corpus(tmp_path, tier_filter="huge"))


def test_iter_corpus_raises_when_dir_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        list(load_test.iter_corpus(tmp_path / "nope"))


# ---------------------------------------------------------------------------
# build_rows_for_result + write_tsv_rows
# ---------------------------------------------------------------------------


def _fake_batch_result(chunk_count: int, fallback_count: int = 0) -> object:
    """Build a minimal BatchResult duck-typed for the harness rows."""

    from docline.process.pdf_batch import BatchResult, ChunkResult

    chunks = tuple(
        ChunkResult(
            chunk_path=Path(f"chunk-{i + 1:04d}.pdf"),
            engine="docling" if i >= fallback_count else "heuristic",
            exit_code=0 if i >= fallback_count else 5,
            markdown=f"# Section {i + 1}\nbody {i + 1}",
            reason="ok" if i >= fallback_count else "subprocess_failed",
        )
        for i in range(chunk_count)
    )
    return BatchResult(
        source=Path("test.pdf"),
        chunks=chunks,
        stitched_markdown="\n\n".join(c.markdown for c in chunks),
        fallback_chunk_count=fallback_count,
        metadata={"split_chunks": chunk_count},
    )


def test_build_rows_includes_summary(tmp_path: Path) -> None:
    result = _fake_batch_result(chunk_count=3, fallback_count=1)
    rows = load_test.build_rows_for_result(
        pdf_path=tmp_path / "test.pdf",
        size_mb=15.0,
        result=result,
        elapsed_s=12.34,
        peak_rss_mb=200.5,
        budget_snapshot={
            "available_ram_gb": "24.00",
            "recommended_docling_max_pages": 75,
            "serialize_docling": False,
        },
    )

    # 3 chunks + 1 summary row
    assert len(rows) == 4
    summary = rows[-1]
    assert summary["chunk_index"] == "summary"
    assert summary["engine"] == "summary"
    assert summary["elapsed_s"] == "12.34"
    assert summary["peak_rss_mb"] == "200.50"
    assert summary["fallback_reason"] == "1/3"


def test_write_tsv_rows_writes_header_and_data(tmp_path: Path) -> None:
    tsv_path = tmp_path / "out.tsv"
    rows = [
        {
            "timestamp": "2026-06-06T00:00:00",
            "file": "test.pdf",
            "mb": "5.00",
            "chunk_index": 1,
            "engine": "docling",
            "exit_code": 0,
            "elapsed_s": "1.50",
            "peak_rss_mb": "150.0",
            "output_chars": 42,
            "fallback_reason": "ok",
            "probe_available_gb": "24.0",
            "probe_max_pages": 75,
            "probe_serialize": False,
        },
    ]
    load_test.write_tsv_rows(tsv_path, rows, append=False)

    with tsv_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        records = list(reader)

    assert len(records) == 1
    assert records[0]["file"] == "test.pdf"
    assert records[0]["chunk_index"] == "1"
    assert records[0]["engine"] == "docling"


def test_write_tsv_rows_append_preserves_existing_data(tmp_path: Path) -> None:
    tsv_path = tmp_path / "out.tsv"
    first = [{"file": "a.pdf", "chunk_index": 1, "engine": "docling"}]
    second = [{"file": "b.pdf", "chunk_index": 1, "engine": "heuristic"}]

    load_test.write_tsv_rows(tsv_path, first, append=False)
    load_test.write_tsv_rows(tsv_path, second, append=True)

    with tsv_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        records = list(reader)

    assert len(records) == 2
    assert records[0]["file"] == "a.pdf"
    assert records[1]["file"] == "b.pdf"


# ---------------------------------------------------------------------------
# main CLI
# ---------------------------------------------------------------------------


def test_main_returns_1_when_corpus_missing(tmp_path: Path) -> None:
    rc = load_test.main(
        [
            "--corpus-dir",
            str(tmp_path / "nope"),
            "--output-dir",
            str(tmp_path / "out"),
            "--tsv-path",
            str(tmp_path / "out.tsv"),
        ]
    )
    assert rc == 1


def test_main_handles_empty_corpus_with_warning(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    rc = load_test.main(
        [
            "--corpus-dir",
            str(corpus),
            "--output-dir",
            str(tmp_path / "out"),
            "--tsv-path",
            str(tmp_path / "out.tsv"),
            "--tier",
            "all",
        ]
    )
    assert rc == 0


def test_main_processes_a_tiny_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end smoke: small corpus + mocked process_pdf_in_chunks."""

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _make_pdf(corpus / "doc.pdf", page_count=2)

    def fake_process(path: Path, *, output_dir: Path):  # type: ignore[no-untyped-def]
        from docline.process.pdf_batch import BatchResult, ChunkResult

        return BatchResult(
            source=path,
            chunks=(
                ChunkResult(
                    chunk_path=path,
                    engine="docling",
                    exit_code=0,
                    markdown="# Title\nbody",
                    reason="ok",
                ),
            ),
            stitched_markdown="# Title\nbody",
            fallback_chunk_count=0,
            metadata={"split_chunks": 1},
        )

    # Replace the bound reference inside the loaded module, not the original.
    monkeypatch.setattr("docline_load_test.process_pdf_in_chunks", fake_process)
    # Speed up the sleep between PDFs.
    monkeypatch.setattr(time, "sleep", lambda s: None)

    tsv_path = tmp_path / "out.tsv"
    rc = load_test.main(
        [
            "--corpus-dir",
            str(corpus),
            "--output-dir",
            str(tmp_path / "out"),
            "--tsv-path",
            str(tsv_path),
            "--tier",
            "all",
            "--pause-seconds",
            "0",
        ]
    )

    assert rc == 0
    with tsv_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        records = list(reader)

    # 1 chunk row + 1 summary row
    assert len(records) == 2
    assert records[0]["file"] == "doc.pdf"
    assert records[0]["engine"] == "docling"
    assert records[1]["chunk_index"] == "summary"
