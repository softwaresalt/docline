"""Tests for ``docline.process.pdf_batch`` (019.001.003-T)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pypdf
import pytest

from docline.runtime.resource_probe import ResourceBudget


def _make_pdf(path: Path, page_count: int) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def _budget(**overrides: Any) -> ResourceBudget:
    defaults: dict[str, Any] = {
        "available_ram_gb": 24.0,
        "total_ram_gb": 32.0,
        "logical_cpus": 8,
        "pagefile_pressure": False,
        "accelerator_device": "cpu",
        "gpu_name": None,
        "gpu_vram_gb": None,
        "gpu_compute_capability": None,
        "recommended_concurrency": 2,
        "recommended_docling_max_pages": 10,
        "recommended_docling_max_mb": 30,
        "serialize_docling": False,
        "omp_thread_count": 2,
    }
    defaults.update(overrides)
    return ResourceBudget(**defaults)


def _runner_factory(success_markdown: str = "# Heading\nbody") -> Any:
    """Build a fake runner that writes ``success_markdown`` and exits 0."""

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        output_path = Path(args[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(success_markdown, encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def test_small_pdf_no_split_returns_one_chunk(tmp_path: Path) -> None:
    """A PDF small enough to fit the budget runs as a single chunk."""

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "small.pdf", page_count=5)
    out = tmp_path / "out"

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=_runner_factory("# Doc Title\nhello"),
    )

    assert len(result.chunks) == 1
    assert result.chunks[0].engine == "docling"
    assert result.chunks[0].exit_code == 0
    assert "Doc Title" in result.stitched_markdown
    assert result.fallback_chunk_count == 0
    assert result.metadata["split_chunks"] == 1


def test_large_pdf_splits_and_runs_each_chunk(tmp_path: Path) -> None:
    """A PDF larger than max_pages splits into chunks; all run docling."""

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "big.pdf", page_count=25)
    out = tmp_path / "out"

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=_runner_factory("# Section A\nlorem"),
        reclaim_pause_seconds=0,
    )

    # 25 pages / (10 - 2 overlap) = 3 chunks plus tail
    assert len(result.chunks) >= 2
    assert all(c.engine == "docling" for c in result.chunks)
    assert result.fallback_chunk_count == 0


def test_chunk_subprocess_failure_falls_back_to_heuristic(tmp_path: Path) -> None:
    """When the docling subprocess exits non-zero, the chunk uses heuristic."""

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=15)
    out = tmp_path / "out"

    def failing_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=5, stdout="", stderr="docling OOM")

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=failing_runner,
        reclaim_pause_seconds=0,
    )

    # Every chunk should have fallen back to heuristic
    assert all(c.engine == "heuristic" for c in result.chunks)
    assert all(c.reason == "subprocess_failed" for c in result.chunks)
    assert result.fallback_chunk_count == len(result.chunks)


def test_partial_chunk_failure_does_not_abort_batch(tmp_path: Path) -> None:
    """Mixed success: chunk #2 fails, but the rest succeed — batch survives."""

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=25)
    out = tmp_path / "out"

    call_count = {"n": 0}

    def mixed_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        call_count["n"] += 1
        if call_count["n"] == 2:
            return subprocess.CompletedProcess(args=args, returncode=5, stdout="", stderr="OOM")
        output_path = Path(args[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"# Chunk {call_count['n']}\nbody", encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=mixed_runner,
        reclaim_pause_seconds=0,
    )

    engines = [c.engine for c in result.chunks]
    assert "docling" in engines
    assert "heuristic" in engines  # chunk #2 fell back
    assert result.fallback_chunk_count == 1


def test_zero_max_pages_routes_entire_pdf_to_heuristic(tmp_path: Path) -> None:
    """When the probe says docling is unsafe (< 4 GB host), use heuristic for whole PDF."""

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=5)
    out = tmp_path / "out"

    def runner_that_should_never_be_called(args: list[str]) -> subprocess.CompletedProcess[str]:
        raise AssertionError("Docling subprocess should not be invoked when max_pages=0")

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=0, recommended_docling_max_mb=0),
        runner=runner_that_should_never_be_called,
    )

    assert len(result.chunks) == 1
    assert result.chunks[0].engine == "heuristic"
    assert result.metadata["split_chunks"] == 0


def test_overlapping_h1_deduplication(tmp_path: Path) -> None:
    """Adjacent chunks producing the same H1 keep only the first occurrence."""

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=15)
    out = tmp_path / "out"

    chunk_bodies = [
        "# Chapter One\nintro\n# Chapter Two\nspan",  # last H1 here
        "# Chapter Two\ndup intro\n# Chapter Three\ncontent",  # duplicate H1
    ]
    call = {"n": 0}

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        idx = call["n"]
        call["n"] += 1
        output_path = Path(args[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(chunk_bodies[idx % len(chunk_bodies)], encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=runner,
        reclaim_pause_seconds=0,
    )

    # "Chapter Two" should appear exactly once in the stitched output
    assert result.stitched_markdown.count("# Chapter Two") == 1
    assert "# Chapter One" in result.stitched_markdown
    assert "# Chapter Three" in result.stitched_markdown


def test_serialize_docling_sleeps_between_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When budget.serialize_docling=True, sleep is called between chunks."""

    from docline.process import pdf_batch

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=20)
    out = tmp_path / "out"

    sleep_calls: list[float] = []
    monkeypatch.setattr("docline.process.pdf_batch.time.sleep", lambda s: sleep_calls.append(s))

    pdf_batch.process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10, serialize_docling=True),
        runner=_runner_factory("# A\nbody"),
        reclaim_pause_seconds=5.0,
    )

    # 20 pages / (10-2 overlap) → 3 chunks → 2 inter-chunk pauses
    assert sleep_calls.count(5.0) >= 2


def test_concurrent_mode_does_not_sleep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When budget.serialize_docling=False, no reclaim pauses."""

    from docline.process import pdf_batch

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=20)
    out = tmp_path / "out"

    sleep_calls: list[float] = []
    monkeypatch.setattr("docline.process.pdf_batch.time.sleep", lambda s: sleep_calls.append(s))

    pdf_batch.process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10, serialize_docling=False),
        runner=_runner_factory("# A\nbody"),
        reclaim_pause_seconds=5.0,
    )

    assert sleep_calls == []


def test_non_adjacent_duplicate_h1s_are_preserved(tmp_path: Path) -> None:
    """Regression: H1s that repeat across non-adjacent chunks must be kept.

    Copilot review identified a global-dedup bug in an earlier version
    where any H1 appearing in chunk K was dropped if it reappeared in
    any later chunk, even across non-overlapping content. Documents
    with legitimately repeated headings (e.g. "Introduction" in both
    Chapter 1 and Appendix A) were silently corrupted.

    The fix limits deduplication to the adjacent-chunk boundary case
    introduced by page_overlap, where chunk K's first H1 equals
    chunk K-1's last H1. Non-adjacent duplicates are preserved.
    """

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=25)
    out = tmp_path / "out"

    chunk_bodies = [
        "# Chapter One\n# Introduction\nintro to chapter 1\n# Chapter One Content\nbody",
        "# Different Section\ncontent\n# Subsection\nmore",
        "# Appendix A\n# Introduction\nintro to appendix\nmore content",
        "# Glossary\nterm defs\nmore terms",
    ]
    call = {"n": 0}

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        idx = call["n"]
        call["n"] += 1
        output_path = Path(args[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Cycle defensively in case the splitter emits more chunks than we have bodies.
        output_path.write_text(chunk_bodies[idx % len(chunk_bodies)], encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=runner,
        reclaim_pause_seconds=0,
    )

    # "Introduction" appears in chunks 1 and 3 (non-adjacent) — both must be preserved.
    # Use newline-bounded matches to avoid substring false positives like
    # "# Chapter One" counting "# Chapter One Content" twice.
    intro_lines = sum(1 for line in result.stitched_markdown.splitlines() if line == "# Introduction")
    chapter_one_lines = sum(1 for line in result.stitched_markdown.splitlines() if line == "# Chapter One")
    different_section_lines = sum(1 for line in result.stitched_markdown.splitlines() if line == "# Different Section")
    appendix_lines = sum(1 for line in result.stitched_markdown.splitlines() if line == "# Appendix A")

    assert intro_lines == 2
    assert chapter_one_lines == 1
    assert different_section_lines == 1
    assert appendix_lines == 1


def test_missing_pdf_raises_file_not_found(tmp_path: Path) -> None:
    from docline.process.pdf_batch import process_pdf_in_chunks

    with pytest.raises(FileNotFoundError):
        process_pdf_in_chunks(tmp_path / "nope.pdf", output_dir=tmp_path / "out")
