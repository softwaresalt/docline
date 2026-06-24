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
