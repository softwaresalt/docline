"""Bounded sub-batching tests (032.003-T / 037-S).

Batched docling-worker mode splits the manifest into bounded GROUPS capped by
``MAX_BATCHED_PAGES`` cumulative pages and spawns one ``--batch`` worker per
group (torch memory reclaimed between groups, model load amortized within).
These tests assert the per-group dispatch in both ``pdf_triage`` and
``pdf_batch`` while preserving output correctness and the 036-S ``do_ocr`` flag.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pypdf

from docline.process.fidelity_scorer import PageScore
from docline.process.pdf_batch import process_pdf_in_chunks
from docline.process.pdf_triage import process_pdf_triaged
from docline.runtime.resource_probe import ResourceBudget


def _make_blank_pdf(path: Path, page_count: int) -> Path:
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


def _capturing_runner(batch_manifests: list[list[dict[str, Any]]]) -> Any:
    """Fake runner that records each --batch manifest's chunks and writes envelopes."""

    def _write_one_envelope(input_pdf: Path, output_path: Path) -> None:
        reader = pypdf.PdfReader(str(input_pdf))
        pages_out = ["# body" for _ in range(len(reader.pages))]
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
            manifest_path = Path(args[args.index("--batch") + 1])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            batch_manifests.append(manifest["chunks"])
            for chunk in manifest["chunks"]:
                _write_one_envelope(Path(chunk["input"]), Path(chunk["output"]))
        else:
            positional = [a for a in args if not a.startswith("--") and a.endswith((".pdf", ".md"))]
            _write_one_envelope(Path(positional[0]), Path(positional[1]))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def _flag_only(indices: set[int]) -> Any:
    def scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
        return PageScore(page_index=page_index, needs_docling=page_index in indices, reason="x")

    return scorer


# ---------------------------------------------------------------------------
# pdf_triage per-group dispatch
# ---------------------------------------------------------------------------


def test_triage_splits_batched_manifest_into_bounded_groups(tmp_path: Path) -> None:
    """Ranges totaling >MAX_BATCHED_PAGES are dispatched as multiple --batch groups."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 60)
    batch_manifests: list[list[dict[str, Any]]] = []

    # buffer=7 -> three 15-page ranges: (0,14),(15,29),(45,59) = 45 pages > cap 40.
    # group_by_page_count([15,15,15], 40) -> [[0,1],[2]] -> 2 groups.
    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(),
        runner=_capturing_runner(batch_manifests),
        scorer=_flag_only({7, 22, 52}),
        baseline_engine="pypdf",
        buffer=7,
        merge_gap=0,
        use_batched_worker=True,
    )

    # Two bounded groups -> two --batch invocations.
    assert len(batch_manifests) == 2
    # Every spliced range is dispatched exactly once across the groups.
    all_outputs = [chunk["output"] for manifest in batch_manifests for chunk in manifest]
    assert len(all_outputs) == 3
    assert len(set(all_outputs)) == 3
    # 036-S do_ocr flag preserved on every chunk.
    assert all("do_ocr" in chunk for manifest in batch_manifests for chunk in manifest)


def test_triage_per_group_dispatch_preserves_docling_splice_back(tmp_path: Path) -> None:
    """Per-group dispatch still splices docling output back (no spurious fallback)."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 60)
    batch_manifests: list[list[dict[str, Any]]] = []

    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(),
        runner=_capturing_runner(batch_manifests),
        scorer=_flag_only({7, 22, 52}),
        baseline_engine="pypdf",
        buffer=7,
        merge_gap=0,
        use_batched_worker=True,
    )

    assert result.metadata["subprocess_fallback_count"] == 0
    # Flagged ranges came back as docling pages.
    for start, end in [(0, 14), (15, 29), (45, 59)]:
        for idx in range(start, end + 1):
            assert result.engine_per_page[idx] == "docling"


def test_triage_single_group_when_under_cap(tmp_path: Path) -> None:
    """Ranges totaling <=MAX_BATCHED_PAGES stay a single --batch invocation."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 40)
    batch_manifests: list[list[dict[str, Any]]] = []

    # Two 1-page ranges (buffer=0): 2 pages total << cap -> one group.
    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(),
        runner=_capturing_runner(batch_manifests),
        scorer=_flag_only({5, 20}),
        baseline_engine="pypdf",
        buffer=0,
        merge_gap=0,
        use_batched_worker=True,
    )

    assert len(batch_manifests) == 1
    assert len(batch_manifests[0]) == 2


# ---------------------------------------------------------------------------
# pdf_batch per-group dispatch
# ---------------------------------------------------------------------------


def test_batch_splits_chunks_into_bounded_groups(tmp_path: Path) -> None:
    """Chunks totaling >MAX_BATCHED_PAGES are dispatched as multiple --batch groups."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 60)
    batch_manifests: list[list[dict[str, Any]]] = []

    # 60 pages / 10-page chunks -> 6 chunks; cap 40 -> >=2 groups.
    process_pdf_in_chunks(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(recommended_docling_max_pages=10),
        runner=_capturing_runner(batch_manifests),
        use_batched_worker=True,
    )

    assert len(batch_manifests) >= 2
    all_outputs = [chunk["output"] for manifest in batch_manifests for chunk in manifest]
    # Every chunk dispatched exactly once across the groups.
    assert len(all_outputs) == len(set(all_outputs))
    assert all("do_ocr" in chunk for manifest in batch_manifests for chunk in manifest)


def test_batch_single_group_when_under_cap(tmp_path: Path) -> None:
    """Few chunks under the cap stay a single --batch invocation."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 20)
    batch_manifests: list[list[dict[str, Any]]] = []

    # 20 pages / 10-page chunks -> 2 chunks; 20 pages <= cap 40 -> one group.
    process_pdf_in_chunks(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(recommended_docling_max_pages=10),
        runner=_capturing_runner(batch_manifests),
        use_batched_worker=True,
    )

    assert len(batch_manifests) == 1


# ---------------------------------------------------------------------------
# OCR-isolated grouping + OOM blast-radius containment (038-F)
# ---------------------------------------------------------------------------


def _ocr_crashing_runner(batch_manifests: list[list[dict[str, Any]]]) -> Any:
    """Fake runner that hard-crashes any --batch group containing an OCR chunk.

    Simulates the 0xC0000005 / std::bad_alloc OCR OOM: a group whose manifest
    contains any ``do_ocr is True`` chunk returns a non-zero exit and writes NO
    envelopes (the worker subprocess died before flushing output). OCR-free
    groups write valid envelopes and return 0.
    """

    def _write_one_envelope(input_pdf: Path, output_path: Path) -> None:
        reader = pypdf.PdfReader(str(input_pdf))
        pages_out = ["# body" for _ in range(len(reader.pages))]
        envelope = {
            "schema_version": 1,
            "pages": pages_out,
            "page_count": len(pages_out),
            "text": "\n\n".join(pages_out),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(envelope), encoding="utf-8")

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        manifest_path = Path(args[args.index("--batch") + 1])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        chunks = manifest["chunks"]
        batch_manifests.append(chunks)
        if any(chunk.get("do_ocr") for chunk in chunks):
            # Hard crash: no envelopes written, access-violation-style exit code.
            return subprocess.CompletedProcess(
                args=args, returncode=3221225477, stdout="", stderr="bad_alloc"
            )
        for chunk in chunks:
            _write_one_envelope(Path(chunk["input"]), Path(chunk["output"]))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def test_triage_ocr_group_crash_isolated_from_ocr_free_ranges(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """An OCR group crash forces only OCR ranges to heuristic; OCR-free survive."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 30)
    # The range starting at/near page 2 needs OCR; the range near page 20 does not.
    monkeypatch.setattr(
        "docline.process.pdf_triage._range_needs_ocr",
        lambda reader, start, end, heuristic_pages: start <= 5,
    )
    batch_manifests: list[list[dict[str, Any]]] = []

    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(),
        runner=_ocr_crashing_runner(batch_manifests),
        scorer=_flag_only({2, 20}),
        baseline_engine="pypdf",
        buffer=1,
        merge_gap=0,
        use_batched_worker=True,
    )

    # Isolation: OCR and OCR-free ranges never share a --batch manifest.
    per_manifest_flags = [{bool(c["do_ocr"]) for c in m} for m in batch_manifests]
    assert all(len(f) == 1 for f in per_manifest_flags), per_manifest_flags
    assert {next(iter(f)) for f in per_manifest_flags} == {True, False}
    # Blast radius: OCR range crashed -> heuristic; OCR-free range survived -> docling.
    assert result.engine_per_page[2] == "heuristic"
    assert result.engine_per_page[20] == "docling"
    assert result.metadata["subprocess_fallback_count"] >= 1


def test_batch_ocr_group_crash_isolated_from_ocr_free_chunks(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """An OCR group crash forces only OCR chunks to heuristic; OCR-free survive."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 40)
    # Only the first chunk needs OCR (chunk file names end with -chunk-0001.pdf).
    monkeypatch.setattr(
        "docline.process.pdf_batch._chunk_needs_ocr",
        lambda path: Path(path).name.endswith("-chunk-0001.pdf"),
    )
    batch_manifests: list[list[dict[str, Any]]] = []

    result = process_pdf_in_chunks(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(recommended_docling_max_pages=10),
        runner=_ocr_crashing_runner(batch_manifests),
        use_batched_worker=True,
    )

    # Isolation: OCR and OCR-free chunks never share a --batch manifest.
    per_manifest_flags = [{bool(c["do_ocr"]) for c in m} for m in batch_manifests]
    assert all(len(f) == 1 for f in per_manifest_flags), per_manifest_flags
    assert {next(iter(f)) for f in per_manifest_flags} == {True, False}
    # Blast radius: the OCR chunk crashed -> heuristic; OCR-free chunks -> docling.
    by_name = {cr.chunk_path.name: cr for cr in result.chunks}
    ocr_chunk = next(name for name in by_name if name.endswith("-chunk-0001.pdf"))
    assert by_name[ocr_chunk].engine == "heuristic"
    assert by_name[ocr_chunk].reason != "ok"
    assert any(cr.engine == "docling" for cr in result.chunks)


def _ocr_oom_above_runner(batch_manifests: list[list[dict[str, Any]]], threshold: int) -> Any:
    """Runner that crashes a --batch group whose OCR page total exceeds ``threshold``.

    Models a memory ceiling: a group with too many OCR page bitmaps OOMs (no
    envelopes), but the same ranges succeed once downsizing shrinks the group.
    """

    def _write_one_envelope(input_pdf: Path, output_path: Path) -> None:
        reader = pypdf.PdfReader(str(input_pdf))
        pages_out = ["# body" for _ in range(len(reader.pages))]
        envelope = {
            "schema_version": 1,
            "pages": pages_out,
            "page_count": len(pages_out),
            "text": "\n\n".join(pages_out),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(envelope), encoding="utf-8")

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        manifest_path = Path(args[args.index("--batch") + 1])
        chunks = json.loads(manifest_path.read_text(encoding="utf-8"))["chunks"]
        batch_manifests.append(chunks)
        ocr_pages = sum(len(pypdf.PdfReader(c["input"]).pages) for c in chunks if c["do_ocr"])
        if ocr_pages > threshold:
            return subprocess.CompletedProcess(
                args=args, returncode=3221225477, stdout="", stderr="bad_alloc"
            )
        for chunk in chunks:
            _write_one_envelope(Path(chunk["input"]), Path(chunk["output"]))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def test_triage_ocr_oom_recovers_via_adaptive_downsizing(tmp_path: Path, monkeypatch: Any) -> None:
    """An OCR group that OOMs is shrunk and retried until every range succeeds."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 30)
    # Every flagged range needs OCR; the runner OOMs any OCR group > 2 pages.
    monkeypatch.setattr(
        "docline.process.pdf_triage._range_needs_ocr",
        lambda *a, **k: True,
    )
    batch_manifests: list[list[dict[str, Any]]] = []

    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(),
        runner=_ocr_oom_above_runner(batch_manifests, threshold=2),
        scorer=_flag_only({2, 6, 10, 14}),
        baseline_engine="pypdf",
        buffer=0,
        merge_gap=0,
        use_batched_worker=True,
    )

    # Full recovery: no range conceded to heuristic, all came back as docling.
    assert result.metadata["subprocess_fallback_count"] == 0
    for idx in (2, 6, 10, 14):
        assert result.engine_per_page[idx] == "docling"
    # Downsizing actually retried (more dispatches than the single initial group).
    assert len(batch_manifests) > 1
