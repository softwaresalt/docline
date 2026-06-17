"""Tests for ``docline.process.pdf_batch`` (019.001.003-T)."""

from __future__ import annotations

import json
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
    """Build a fake runner that writes an envelope and exits 0.

    Handles BOTH worker invocation modes (030-F T3):

    - **Single-chunk** ``[python, -m, ..., INPUT, OUTPUT]``: writes one
      envelope file at ``OUTPUT`` whose ``pages`` list has one entry per
      page in ``INPUT``, each set to ``success_markdown``.
    - **Batched** ``[python, -m, ..., --batch, MANIFEST_JSON]``: parses
      the manifest, iterates its chunks, writes one envelope per chunk
      following the same per-page rule.

    Matches the real worker behavior post-030-F so the per-page contract
    is honored regardless of which mode pdf_batch chose.
    """

    def _write_one_envelope(input_pdf: Path, output_path: Path) -> None:
        reader = pypdf.PdfReader(str(input_pdf))
        pages_out = [success_markdown for _ in range(len(reader.pages))]
        envelope = {
            "schema_version": 1,
            "pages": pages_out,
            "page_count": len(pages_out),
            "text": "\n\n".join(pages_out),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(envelope), encoding="utf-8")

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        if "--batch" in args:
            manifest_idx = args.index("--batch") + 1
            manifest_path = Path(args[manifest_idx])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for chunk in manifest["chunks"]:
                _write_one_envelope(Path(chunk["input"]), Path(chunk["output"]))
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        # Single-chunk mode.
        input_pdf = Path(args[-2])
        output_path = Path(args[-1])
        _write_one_envelope(input_pdf, output_path)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def _legacy_flat_runner(success_markdown: str = "# Legacy\nbody") -> Any:
    """Build a fake runner that writes flat markdown (pre-T1 contract).

    Used to verify the consumer's defensive ``json.JSONDecodeError``
    fallback path: when the output is not valid envelope JSON, the
    consumer treats the body as a single-blob single-page payload.
    """

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        output_path = Path(args[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(success_markdown, encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def _write_envelope_md(output_path: Path, markdown_text: str) -> None:
    """Helper used by inline runners: wrap markdown as a single-page envelope."""

    envelope = {
        "schema_version": 1,
        "pages": [markdown_text],
        "page_count": 1,
        "text": markdown_text,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(envelope), encoding="utf-8")


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
        _write_envelope_md(output_path, f"# Chunk {call_count['n']}\nbody")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=mixed_runner,
        reclaim_pause_seconds=0,
        use_batched_worker=False,  # this test validates per-chunk fallback semantics
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
        _write_envelope_md(output_path, chunk_bodies[idx % len(chunk_bodies)])
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=runner,
        reclaim_pause_seconds=0,
        use_batched_worker=False,  # per-chunk runner cycles bodies by call_count
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
        # Cycle defensively in case the splitter emits more chunks than we have bodies.
        _write_envelope_md(output_path, chunk_bodies[idx % len(chunk_bodies)])
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=runner,
        reclaim_pause_seconds=0,
        use_batched_worker=False,  # per-chunk runner cycles bodies by call_count
    )
    # Use newline-bounded matches to avoid substring false positives like
    # "# Chapter One" counting "# Chapter One Content" twice.
    intro_lines = sum(
        1 for line in result.stitched_markdown.splitlines() if line == "# Introduction"
    )
    chapter_one_lines = sum(
        1 for line in result.stitched_markdown.splitlines() if line == "# Chapter One"
    )
    different_section_lines = sum(
        1 for line in result.stitched_markdown.splitlines() if line == "# Different Section"
    )
    appendix_lines = sum(
        1 for line in result.stitched_markdown.splitlines() if line == "# Appendix A"
    )

    assert intro_lines == 2
    assert chapter_one_lines == 1
    assert different_section_lines == 1
    assert appendix_lines == 1


def test_missing_pdf_raises_file_not_found(tmp_path: Path) -> None:
    from docline.process.pdf_batch import process_pdf_in_chunks

    with pytest.raises(FileNotFoundError):
        process_pdf_in_chunks(tmp_path / "nope.pdf", output_dir=tmp_path / "out")


def test_chunk_result_carries_per_page_envelope_field(tmp_path: Path) -> None:
    """030.002-T: ChunkResult.chunk_pages tuple exposes per-page envelope data.

    The envelope-aware runner emits ``pages == [success_markdown] * page_count``
    per chunk PDF. The consumer must populate ChunkResult.chunk_pages with
    this list so downstream graph writers can index by page.
    """

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=5)
    out = tmp_path / "out"

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=_runner_factory("# Page payload\nbody"),
    )

    assert len(result.chunks) == 1
    cr = result.chunks[0]
    assert cr.engine == "docling"
    assert cr.reason == "ok"
    assert isinstance(cr.chunk_pages, tuple)
    assert len(cr.chunk_pages) == 5
    assert all(p == "# Page payload\nbody" for p in cr.chunk_pages)


def test_legacy_flat_output_triggers_defensive_fallback(tmp_path: Path) -> None:
    """030.002-T: A pre-T1 worker (or partial rollout) writes flat markdown.

    The consumer's ``json.JSONDecodeError`` fallback must keep the chunk
    alive by treating the body as a single-blob single-page payload.
    ChunkResult.engine stays ``"docling"`` (subprocess succeeded);
    chunk_pages becomes a one-element tuple containing the raw body so
    downstream consumers do not crash on a missing per-page field.
    """

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "small.pdf", page_count=3)
    out = tmp_path / "out"

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=_legacy_flat_runner("# Plain markdown\nstill works"),
    )

    assert len(result.chunks) == 1
    cr = result.chunks[0]
    assert cr.engine == "docling"
    assert cr.reason == "ok"
    assert "Plain markdown" in cr.markdown
    # Defensive fallback: legacy flat body becomes a one-page envelope.
    assert cr.chunk_pages == ("# Plain markdown\nstill works",)


def test_chunk_pages_empty_when_subprocess_fails(tmp_path: Path) -> None:
    """When the subprocess fails and the heuristic fallback runs, chunk_pages is empty.

    Heuristic fallback does not produce per-page envelope output (it uses
    ``read_pdf_pages(chunk, layout_engine="heuristic")`` directly). The
    chunk_pages tuple is therefore empty for fallback paths to keep the
    contract honest — only docling-sourced chunks expose per-page data.
    """

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=5)
    out = tmp_path / "out"

    def always_fails(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=5, stdout="", stderr="OOM")

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=always_fails,
    )

    for cr in result.chunks:
        assert cr.engine == "heuristic"
        assert cr.chunk_pages == ()


# ---------------------------------------------------------------------------
# 030.003-T: batched worker mode integration
# ---------------------------------------------------------------------------


def test_batched_mode_invoked_when_two_or_more_chunks(tmp_path: Path) -> None:
    """When N>=2 chunks AND batching is allowed, the runner is called ONCE with --batch.

    The envelope-aware `_runner_factory` handles batched manifests by
    iterating chunks and writing per-chunk envelopes. metadata.batched_worker
    is set to True; all chunks return engine=docling.
    """

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "big.pdf", page_count=25)
    out = tmp_path / "out"

    call_count = {"n": 0}

    def counting_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        call_count["n"] += 1
        # Delegate to the envelope-aware default factory.
        return _runner_factory("# Batched payload\nbody")(args)

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=counting_runner,
        use_batched_worker=True,
    )

    assert result.metadata["batched_worker"] is True
    assert call_count["n"] == 1  # single subprocess for all chunks
    assert len(result.chunks) >= 2
    for cr in result.chunks:
        assert cr.engine == "docling"
        assert cr.reason == "ok"
        assert "Batched payload" in cr.markdown


def test_batched_mode_skipped_for_single_chunk(tmp_path: Path) -> None:
    """A 1-chunk PDF uses the per-chunk loop even with use_batched_worker=True."""

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "tiny.pdf", page_count=3)
    out = tmp_path / "out"

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=_runner_factory("# Single"),
        use_batched_worker=True,
    )

    assert result.metadata["batched_worker"] is False
    assert len(result.chunks) == 1


def test_batched_mode_disabled_when_serialize_docling(tmp_path: Path) -> None:
    """budget.serialize_docling=True forces per-chunk loop (preserves reclaim pause semantics)."""

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "big.pdf", page_count=25)
    out = tmp_path / "out"

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10, serialize_docling=True),
        runner=_runner_factory("# Per-chunk"),
        reclaim_pause_seconds=0,
        use_batched_worker=True,
    )

    assert result.metadata["batched_worker"] is False
    assert len(result.chunks) >= 2


def test_per_chunk_loop_is_the_default_for_multi_chunk(tmp_path: Path) -> None:
    """033-S regression guard: batched mode is OPT-IN; default is per-chunk.

    032-S shipped ``use_batched_worker=True`` by default, which ran all
    chunks in one long-lived subprocess and exhausted memory on large
    corpora (cosmos: 86/86 docling fallback). The default reverted to the
    proven per-chunk subprocess loop. A multi-chunk PDF with no explicit
    flag must use per-chunk (one subprocess per chunk).
    """

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "big.pdf", page_count=25)
    out = tmp_path / "out"

    call_count = {"n": 0}

    def counting_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        call_count["n"] += 1
        assert "--batch" not in args, "default must not invoke batched mode"
        return _runner_factory("# Per-chunk default")(args)

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=counting_runner,
        reclaim_pause_seconds=0,
    )

    assert result.metadata["batched_worker"] is False
    assert call_count["n"] == len(result.chunks)  # one subprocess per chunk
    assert len(result.chunks) >= 2


def test_batched_mode_opt_out_via_flag(tmp_path: Path) -> None:
    """use_batched_worker=False forces the per-chunk loop regardless of N."""

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "big.pdf", page_count=25)
    out = tmp_path / "out"

    call_count = {"n": 0}

    def counting_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        call_count["n"] += 1
        return _runner_factory("# Per-chunk")(args)

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=counting_runner,
        reclaim_pause_seconds=0,
        use_batched_worker=False,
    )

    assert result.metadata["batched_worker"] is False
    assert call_count["n"] == len(result.chunks)  # one subprocess per chunk
    assert len(result.chunks) >= 2


def test_batched_mode_per_chunk_error_envelope_routes_to_heuristic(tmp_path: Path) -> None:
    """A chunk with an error envelope in batched output falls back to heuristic."""

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "big.pdf", page_count=25)
    out = tmp_path / "out"

    def batched_runner_with_one_failure(
        args: list[str],
    ) -> subprocess.CompletedProcess[str]:
        assert "--batch" in args
        manifest = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
        for i, chunk in enumerate(manifest["chunks"]):
            output_path = Path(chunk["output"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if i == 1:
                # Error envelope for the 2nd chunk.
                envelope = {
                    "schema_version": 1,
                    "pages": [],
                    "page_count": 0,
                    "text": "",
                    "error": "RuntimeError('per-chunk failure')",
                }
            else:
                envelope = {
                    "schema_version": 1,
                    "pages": [f"# OK chunk {i}"],
                    "page_count": 1,
                    "text": f"# OK chunk {i}",
                }
            output_path.write_text(json.dumps(envelope), encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=batched_runner_with_one_failure,
        use_batched_worker=True,
    )

    assert result.metadata["batched_worker"] is True
    # Second chunk fell back to heuristic; others stayed docling.
    engines = [cr.engine for cr in result.chunks]
    assert "heuristic" in engines  # at least one fallback
    assert engines.count("heuristic") == 1
    assert result.fallback_chunk_count == 1


def test_batched_mode_subprocess_failure_routes_all_to_heuristic(tmp_path: Path) -> None:
    """If the batched subprocess itself exits non-zero, every chunk falls back."""

    from docline.process.pdf_batch import process_pdf_in_chunks

    pdf = _make_pdf(tmp_path / "big.pdf", page_count=25)
    out = tmp_path / "out"

    def failing_batched_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        # Don't write any output files; non-zero exit.
        return subprocess.CompletedProcess(args=args, returncode=6, stdout="", stderr="boom")

    result = process_pdf_in_chunks(
        pdf,
        output_dir=out,
        budget=_budget(recommended_docling_max_pages=10),
        runner=failing_batched_runner,
        use_batched_worker=True,
    )

    assert result.metadata["batched_worker"] is True
    assert all(cr.engine == "heuristic" for cr in result.chunks)
    assert result.fallback_chunk_count == len(result.chunks)
