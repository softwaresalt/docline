"""Tests for ``docline.process.pdf_triage`` orchestrator (task 019.003-T)."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pypdf
import pytest


def _make_pdf(path: Path, page_count: int) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def _runner_factory(markdown: str = "# Heading\nbody") -> Any:
    """Build a fake runner that writes an envelope and exits 0.

    Handles BOTH worker invocation modes (030-F T3):

    - **Single-chunk** ``[python, -m, ..., SPLICE_PDF, SPLICE_MD]``:
      writes one envelope file at ``SPLICE_MD`` whose ``pages`` list has
      one entry per page in ``SPLICE_PDF``, each set to ``markdown``.
    - **Batched** ``[python, -m, ..., --batch, MANIFEST_JSON]``: parses
      the manifest, iterates its chunks, writes one envelope per chunk
      following the same per-page rule.
    """

    def _write_one_envelope(input_pdf: Path, output_path: Path) -> None:
        reader = pypdf.PdfReader(str(input_pdf))
        pages_out = [markdown for _ in range(len(reader.pages))]
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


def _legacy_flat_runner(markdown: str = "# Legacy\nbody") -> Any:
    """Build a fake runner that writes flat markdown (pre-T1 contract).

    Used to verify the splice-back's defensive ``json.JSONDecodeError``
    fallback path. Single-chunk mode only.
    """

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        if "--batch" in args:
            # If batched mode somehow lands here, write flat markdown to
            # each chunk's output path so the consumer's defensive
            # JSONDecodeError fallback exercises consistently.
            manifest_idx = args.index("--batch") + 1
            manifest_path = Path(args[manifest_idx])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for chunk in manifest["chunks"]:
                output_path = Path(chunk["output"])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(markdown, encoding="utf-8")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        output_path = Path(args[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def _envelope_runner_with_pages(pages_seq: list[list[str]]) -> Any:
    """Build a fake runner that emits the i-th envelope with ``pages_seq[i]``.

    Lets a test inject a specific per-page list per invocation regardless of
    the input PDF page count. Used to exercise the length-mismatch fallback
    and the per-page-correct happy path independently.

    In batched mode, iterates the manifest's chunks in order and assigns
    ``pages_seq[i]`` to chunk i.
    """

    call = {"n": 0}

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        if "--batch" in args:
            manifest_idx = args.index("--batch") + 1
            manifest_path = Path(args[manifest_idx])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for i, chunk in enumerate(manifest["chunks"]):
                output_path = Path(chunk["output"])
                pages_out = pages_seq[i % len(pages_seq)]
                envelope = {
                    "schema_version": 1,
                    "pages": pages_out,
                    "page_count": len(pages_out),
                    "text": "\n\n".join(pages_out),
                }
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(json.dumps(envelope), encoding="utf-8")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        idx = call["n"]
        call["n"] += 1
        output_path = Path(args[-1])
        pages_out = pages_seq[idx % len(pages_seq)]
        envelope = {
            "schema_version": 1,
            "pages": pages_out,
            "page_count": len(pages_out),
            "text": "\n\n".join(pages_out),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(envelope), encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def _failing_runner() -> Any:
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args, returncode=5, stdout="", stderr="docling failed"
        )

    return runner


def _make_scorer(flagged: set[int]) -> Any:
    """Build a deterministic scorer that flags only the given page indices."""

    from docline.process.fidelity_scorer import PageScore

    def scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
        return PageScore(
            page_index=page_index,
            signals={},
            aggregate=1.0 if page_index in flagged else 0.0,
            needs_docling=page_index in flagged,
            reason="forced" if page_index in flagged else "ok",
        )

    return scorer


def test_no_flagged_pages_skips_docling_runner(tmp_path: Path) -> None:
    """When the scorer flags no pages, the docling runner must not be invoked."""
    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "small.pdf", page_count=10)
    runner = MagicMock(side_effect=_runner_factory())
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_make_scorer(flagged=set()),
    )

    assert runner.call_count == 0
    assert all(eng == "heuristic" for eng in result.engine_per_page)
    assert result.flagged_ranges == ()


def test_flagged_pages_route_to_docling_and_splice_back(tmp_path: Path) -> None:
    """Flagged page indices are coalesced and docling outputs splice into the right slots."""
    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    runner = MagicMock(side_effect=_runner_factory("# Docling page\nrich content"))
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_make_scorer(flagged={3, 4, 5}),
        buffer=0,
        merge_gap=2,
    )

    assert runner.call_count == 1
    assert (3, 5) in result.flagged_ranges
    for idx in (3, 4, 5):
        assert result.engine_per_page[idx] == "docling"
    for idx in (0, 1, 2, 6, 7, 8, 9):
        assert result.engine_per_page[idx] == "heuristic"


def test_docling_failure_falls_back_to_heuristic_per_range(tmp_path: Path) -> None:
    """Docling subprocess non-zero exit must fall back to heuristic for that range only."""
    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=_failing_runner(),
        scorer=_make_scorer(flagged={4, 5}),
        buffer=0,
    )

    for idx in (4, 5):
        assert result.engine_per_page[idx] == "heuristic"
    assert result.metadata.get("subprocess_fallback_count", 0) >= 1


def test_triage_result_is_frozen(tmp_path: Path) -> None:
    """TriageResult returned by the orchestrator must be a frozen dataclass."""
    import dataclasses

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=3)
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=_runner_factory(),
        scorer=_make_scorer(flagged=set()),
    )
    assert dataclasses.is_dataclass(result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.pages = ("changed",)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 030.002-T: per-page splice-back via envelope contract
# ---------------------------------------------------------------------------


def test_per_page_splice_back_assigns_distinct_content_per_page(tmp_path: Path) -> None:
    """030.002-T happy path: a 3-page envelope spreads across pages start..start+2.

    Pre-T2 behavior: the entire blob was attached to ``final_pages[start]``
    and the rest were ``""``. Post-T2: each envelope ``pages`` entry maps
    to its corresponding final_pages slot, restoring per-page fidelity.
    """

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    distinct_pages = ["# Page A\nalpha", "# Page B\nbeta", "# Page C\ngamma"]
    runner = _envelope_runner_with_pages([distinct_pages])

    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_make_scorer(flagged={3, 4, 5}),
        buffer=0,
        merge_gap=2,
    )

    assert (3, 5) in result.flagged_ranges
    assert result.pages[3] == "# Page A\nalpha"
    assert result.pages[4] == "# Page B\nbeta"
    assert result.pages[5] == "# Page C\ngamma"
    for idx in (3, 4, 5):
        assert result.engine_per_page[idx] == "docling"


def test_per_page_splice_back_single_entry_is_docling_range_no_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """039.001-T: a single-entry envelope for an N-page range is EXPECTED.

    docling renders a coalesced range as one coherent whole-range blob (its
    ``export_to_markdown`` over the range preserves heading nesting and tables
    across page breaks). That single-entry envelope for an N>1 range is the
    normal case — not an anomaly — so it is attributed ``"docling-range"`` and
    logs NO length-mismatch warning. The blob lands on the range's first page
    slot; the assembled markdown joins page slots anyway.
    """

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    # Range will be (3,5) = 3 pages, but envelope carries 1 whole-range blob.
    short_envelope = [["# Single chunk blob for range\nall content here"]]
    runner = _envelope_runner_with_pages(short_envelope)

    with caplog.at_level(logging.WARNING, logger="docline.process.pdf_triage"):
        result = process_pdf_triaged(
            pdf,
            output_dir=tmp_path / "out",
            runner=runner,
            scorer=_make_scorer(flagged={3, 4, 5}),
            buffer=0,
            merge_gap=2,
        )

    # First page of the range carries the blob; rest are empty.
    assert "Single chunk blob" in result.pages[3]
    assert result.pages[4] == ""
    assert result.pages[5] == ""
    # Attributed as the expected whole-range render.
    assert result.engine_per_page[3] == "docling-range"
    assert result.engine_per_page[4] == "docling-range"
    assert result.engine_per_page[5] == "docling-range"
    # No mismatch warning for the expected whole-range render.
    assert not any("length mismatch" in r.message.lower() for r in caplog.records)


def test_per_page_splice_back_unexpected_multientry_warns_and_collapses(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """039.001-T: a valid envelope with >1 pages but the wrong count is anomalous.

    Unlike the single-entry whole-range render, a multi-entry envelope whose
    count still != range length would silently drop pages, so it keeps the
    diagnostic WARNING and the ``"docling-collapsed"`` label.
    """

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    # 2 envelope pages for a 3-page range (3,5): genuinely unexpected.
    two_page_envelope = [["# page A blob", "# page B blob"]]
    runner = _envelope_runner_with_pages(two_page_envelope)

    with caplog.at_level(logging.WARNING, logger="docline.process.pdf_triage"):
        result = process_pdf_triaged(
            pdf,
            output_dir=tmp_path / "out",
            runner=runner,
            scorer=_make_scorer(flagged={3, 4, 5}),
            buffer=0,
            merge_gap=2,
        )

    assert result.engine_per_page[3] == "docling-collapsed"
    assert result.engine_per_page[4] == "docling-collapsed"
    assert result.engine_per_page[5] == "docling-collapsed"
    assert any("length mismatch" in r.message.lower() for r in caplog.records)


def test_per_page_splice_back_jsondecode_error_falls_back_defensively(
    tmp_path: Path,
) -> None:
    """030.002-T defensive fallback: legacy flat output triggers JSONDecodeError.

    A partial T1 rollout (or a downgrade) may leave a flat-markdown worker
    in place. The consumer must catch ``json.JSONDecodeError`` and treat
    the file body as a single-blob whole-range payload, attaching it to
    ``final_pages[start]``. Because a legacy flat blob is also a coherent
    whole-range render, it is attributed ``"docling-range"`` (039.001-T).
    """

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=8)
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=_legacy_flat_runner("# Pre-envelope content\nstill returns"),
        scorer=_make_scorer(flagged={4, 5}),
        buffer=0,
    )

    # First page of the range carries the legacy blob.
    assert "Pre-envelope content" in result.pages[4]
    assert result.pages[5] == ""
    # Attributed as a whole-range render (coherent single blob).
    assert result.engine_per_page[4] == "docling-range"
    assert result.engine_per_page[5] == "docling-range"


def test_single_page_range_assigns_envelope_page_at_index(tmp_path: Path) -> None:
    """A single flagged page (range = (i,i)) gets its envelope page at index i.

    Single-page ranges should also use the envelope path, not the
    collapsed fallback. Catches a regression where the consumer
    short-circuits on range length 1.
    """

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    pages_payload = [["# Just one page\nunique content"]]
    runner = _envelope_runner_with_pages(pages_payload)

    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_make_scorer(flagged={7}),
        buffer=0,
    )

    assert (7, 7) in result.flagged_ranges
    assert result.pages[7] == "# Just one page\nunique content"
    assert result.engine_per_page[7] == "docling"


# ---------------------------------------------------------------------------
# 030.003-T: batched worker mode integration for pdf_triage splice-back
# ---------------------------------------------------------------------------


def test_triage_batched_mode_invoked_when_two_or_more_ranges(tmp_path: Path) -> None:
    """When N>=2 flagged ranges, splice-back invokes the worker once with --batch."""

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=20)
    runner = MagicMock(side_effect=_runner_factory("# Batched per-range\nbody"))

    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_make_scorer(flagged={3, 4, 10, 11}),  # 2 ranges after coalesce
        buffer=0,
        merge_gap=2,
        use_batched_worker=True,
    )

    assert result.metadata["batched_worker"] is True
    assert runner.call_count == 1  # single subprocess invocation
    # Both ranges should be docling-attributed.
    for idx in (3, 4, 10, 11):
        assert result.engine_per_page[idx] == "docling"
    assert "Batched per-range" in result.pages[3]
    assert "Batched per-range" in result.pages[10]


def test_triage_per_range_mode_when_single_range(tmp_path: Path) -> None:
    """A single flagged range uses per-range mode even with batching enabled."""

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    runner = MagicMock(side_effect=_runner_factory("# Per-range path\nbody"))

    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_make_scorer(flagged={4, 5, 6}),  # 1 range
        buffer=0,
        use_batched_worker=True,
    )

    assert result.metadata["batched_worker"] is False
    assert runner.call_count == 1


def test_triage_batched_is_the_default_for_multi_range(tmp_path: Path) -> None:
    """037-S verification flip: bounded sub-batching is the DEFAULT for multi-range.

    032-S shipped ``use_batched_worker=True`` by default but ran all flagged
    ranges in ONE subprocess → cosmos OOM (86/86 fallback). 033-S reverted to
    per-range. 037-S added bounded sub-batching and the cosmos runtime
    verification (0/86 fallback, ~9.5% faster) justified making batched the
    default again. A multi-range triage with no explicit flag must invoke
    ``--batch``.
    """

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=20)

    batch_calls = {"n": 0}

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        if "--batch" in args:
            batch_calls["n"] += 1
        return _runner_factory("# Batched default")(args)

    spy = MagicMock(side_effect=runner)
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=spy,
        scorer=_make_scorer(flagged={3, 4, 10, 11}),  # 2 ranges after coalesce
        buffer=0,
        merge_gap=2,
    )

    assert result.metadata["batched_worker"] is True
    # 2 small ranges (<= MAX_BATCHED_PAGES) -> one bounded group -> one --batch.
    assert batch_calls["n"] >= 1, "default must invoke bounded-batched mode"
    for idx in (3, 4, 10, 11):
        assert result.engine_per_page[idx] == "docling"


def test_triage_batched_mode_opt_out_forces_per_range_loop(tmp_path: Path) -> None:
    """use_batched_worker=False forces per-range subprocess loop regardless of N."""

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=20)
    runner = MagicMock(side_effect=_runner_factory("# Per-range forced\nbody"))

    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_make_scorer(flagged={3, 4, 10, 11}),  # 2 ranges
        buffer=0,
        merge_gap=2,
        use_batched_worker=False,
    )

    assert result.metadata["batched_worker"] is False
    assert runner.call_count == 2  # one subprocess per range


def test_triage_batched_subprocess_failure_routes_all_ranges_to_heuristic(
    tmp_path: Path,
) -> None:
    """If the batched subprocess fails, every range falls back to heuristic."""

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=20)

    def failing_batched_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert "--batch" in args
        return subprocess.CompletedProcess(args=args, returncode=6, stdout="", stderr="boom")

    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=failing_batched_runner,
        scorer=_make_scorer(flagged={3, 4, 10, 11}),
        buffer=0,
        merge_gap=2,
        use_batched_worker=True,
    )

    assert result.metadata["batched_worker"] is True
    # All flagged pages stayed heuristic (no per-page envelope was processed).
    for idx in (3, 4, 10, 11):
        assert result.engine_per_page[idx] == "heuristic"
    # subprocess_fallback_count should equal the number of ranges.
    assert result.metadata["subprocess_fallback_count"] == 2


def test_triage_batched_per_range_error_envelope_falls_back(tmp_path: Path) -> None:
    """A range whose batched output is an error envelope falls back to heuristic."""

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=20)

    def mixed_batched_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert "--batch" in args
        manifest_idx = args.index("--batch") + 1
        manifest = json.loads(Path(args[manifest_idx]).read_text(encoding="utf-8"))
        for i, chunk in enumerate(manifest["chunks"]):
            output_path = Path(chunk["output"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if i == 0:
                # First range succeeds.
                envelope = {
                    "schema_version": 1,
                    "pages": ["# OK first range page 1", "# OK first range page 2"],
                    "page_count": 2,
                    "text": "# OK first range page 1\n\n# OK first range page 2",
                }
            else:
                # Second range gets an error envelope.
                envelope = {
                    "schema_version": 1,
                    "pages": [],
                    "page_count": 0,
                    "text": "",
                    "error": "RuntimeError('per-range failure in batched mode')",
                }
            output_path.write_text(json.dumps(envelope), encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=mixed_batched_runner,
        scorer=_make_scorer(flagged={3, 4, 10, 11}),
        buffer=0,
        merge_gap=2,
        use_batched_worker=True,
    )

    assert result.metadata["batched_worker"] is True
    # First range: per-page docling assignment from envelope.
    assert result.engine_per_page[3] == "docling"
    assert result.engine_per_page[4] == "docling"
    # Second range: error envelope → fell back to heuristic for both pages.
    assert result.engine_per_page[10] == "heuristic"
    assert result.engine_per_page[11] == "heuristic"
    assert result.metadata["subprocess_fallback_count"] == 1


def test_triage_batched_partial_crash_recovers_written_ranges(tmp_path: Path) -> None:
    """032.002-T: a batched worker that writes K valid range envelopes then
    crashes (non-zero exit) must not discard the written ranges.

    Only ranges with no envelope fall back; the whole batch is failed solely
    when no envelope was produced. Mirrors the pdf_batch partial-crash guard
    for the triage splice-back path.
    """

    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=20)

    def partial_crash_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert "--batch" in args
        manifest_idx = args.index("--batch") + 1
        manifest = json.loads(Path(args[manifest_idx]).read_text(encoding="utf-8"))
        chunks = manifest["chunks"]
        # Write a valid envelope for the FIRST range only, then "crash" before
        # the second range's envelope is written.
        first = chunks[0]
        input_pdf = Path(first["input"])
        output_path = Path(first["output"])
        reader = pypdf.PdfReader(str(input_pdf))
        pages_out = [f"# Recovered range page {i}" for i in range(len(reader.pages))]
        envelope = {
            "schema_version": 1,
            "pages": pages_out,
            "page_count": len(pages_out),
            "text": "\n\n".join(pages_out),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(envelope), encoding="utf-8")
        # OS-killed mid-batch: the second range envelope is never written.
        return subprocess.CompletedProcess(args=args, returncode=-9, stdout="", stderr="Killed")

    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=partial_crash_runner,
        scorer=_make_scorer(flagged={3, 4, 10, 11}),
        buffer=0,
        merge_gap=2,
        use_batched_worker=True,
    )

    assert result.metadata["batched_worker"] is True
    # First range (pages 3-4): a valid envelope was written before the crash,
    # so it must be recovered rather than discarded.
    assert result.engine_per_page[3] == "docling"
    assert result.engine_per_page[4] == "docling"
    # Second range (pages 10-11): no envelope was written, so it falls back.
    assert result.engine_per_page[10] == "heuristic"
    assert result.engine_per_page[11] == "heuristic"
    # Only the range with no envelope counts as a fallback.
    assert result.metadata["subprocess_fallback_count"] == 1
