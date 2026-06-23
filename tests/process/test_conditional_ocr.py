"""Conditional docling OCR tests (034.006-T / feature 034-F).

The triage and batch layers compute a per-range / per-chunk ``do_ocr``
decision from the per-page text-layer signal and thread it through the
``docling_worker`` dispatch. A range is OCR-free only when every page has
an extractable text layer; any image-only page forces OCR on for that
range (conservative — no scanned-PDF fidelity regression).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pypdf

from docline.process.fidelity_scorer import PageScore, page_needs_ocr
from docline.process.pdf_batch import process_pdf_in_chunks
from docline.process.pdf_triage import process_pdf_triaged
from docline.runtime.resource_probe import ResourceBudget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakePage:
    """Minimal stand-in for a ``pypdf.PageObject`` with a fixed image list."""

    def __init__(self, images: list[object]) -> None:
        self.images = images


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


def _capturing_runner(captured: list[list[str]]) -> Any:
    """Fake worker runner that records each cmd and writes valid envelopes."""

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
        captured.append(list(args))
        if "--batch" in args:
            manifest_path = Path(args[args.index("--batch") + 1])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for chunk in manifest["chunks"]:
                _write_one_envelope(Path(chunk["input"]), Path(chunk["output"]))
        else:
            positional = [a for a in args if not a.startswith("--") and a.endswith((".pdf", ".md"))]
            _write_one_envelope(Path(positional[0]), Path(positional[1]))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def _flag_all_scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
    return PageScore(page_index=page_index, needs_docling=True, reason="forced")


def _flag_only(indices: set[int]) -> Any:
    def scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
        return PageScore(
            page_index=page_index, needs_docling=page_index in indices, reason="forced"
        )

    return scorer


def _worker_cmds(captured: list[list[str]]) -> list[list[str]]:
    return [c for c in captured if any("docling_worker" in part for part in c)]


def _range_cmds(captured: list[list[str]]) -> list[list[str]]:
    return [c for c in _worker_cmds(captured) if "--batch" not in c]


# ---------------------------------------------------------------------------
# page_needs_ocr signal (fidelity_scorer)
# ---------------------------------------------------------------------------


def test_page_with_text_layer_does_not_need_ocr() -> None:
    assert page_needs_ocr("a" * 250, _FakePage([object()])) is False


def test_image_only_page_needs_ocr() -> None:
    """Sparse text + embedded image = scanned/image-only page → OCR."""
    assert page_needs_ocr("", _FakePage([object()])) is True


def test_blank_page_without_images_does_not_need_ocr() -> None:
    assert page_needs_ocr("", _FakePage([])) is False


def test_page_without_metadata_does_not_need_ocr() -> None:
    assert page_needs_ocr("", None) is False


# ---------------------------------------------------------------------------
# pdf_triage per-range + batched dispatch
# ---------------------------------------------------------------------------


def test_triage_per_range_passes_no_ocr_for_text_layer_pages(tmp_path: Path) -> None:
    """Flagged ranges whose pages need no OCR get ``--no-ocr`` on the worker cmd."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 3)
    captured: list[list[str]] = []

    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(),
        runner=_capturing_runner(captured),
        scorer=_flag_all_scorer,
        baseline_engine="pypdf",
    )

    range_cmds = _range_cmds(captured)
    assert range_cmds, "expected at least one per-range worker cmd"
    assert all("--no-ocr" in cmd for cmd in range_cmds)


def test_triage_per_range_keeps_ocr_when_page_needs_it(tmp_path: Path, monkeypatch: Any) -> None:
    """When a range needs OCR, the worker cmd must NOT carry ``--no-ocr``."""
    monkeypatch.setattr("docline.process.pdf_triage._range_needs_ocr", lambda *a, **k: True)
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 3)
    captured: list[list[str]] = []

    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(),
        runner=_capturing_runner(captured),
        scorer=_flag_all_scorer,
        baseline_engine="pypdf",
    )

    range_cmds = _range_cmds(captured)
    assert range_cmds, "expected at least one per-range worker cmd"
    assert all("--no-ocr" not in cmd for cmd in range_cmds)


def test_triage_batched_manifest_carries_do_ocr(tmp_path: Path) -> None:
    """Batched-mode manifest chunks carry the per-range do_ocr flag."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 4)
    captured: list[list[str]] = []

    # Flag two non-adjacent pages so coalescing yields two ranges (>=2 splice
    # jobs) and the batched-splice path is taken.
    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(),
        runner=_capturing_runner(captured),
        scorer=_flag_only({0, 3}),
        baseline_engine="pypdf",
        buffer=0,
        merge_gap=0,
        use_batched_worker=True,
    )

    batch_cmds = [c for c in _worker_cmds(captured) if "--batch" in c]
    assert batch_cmds, "expected a batched worker cmd"
    manifest_path = Path(batch_cmds[0][batch_cmds[0].index("--batch") + 1])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["chunks"]) >= 2
    # Blank pages carry no text and no images -> no OCR needed.
    assert all(chunk.get("do_ocr") is False for chunk in manifest["chunks"])


# ---------------------------------------------------------------------------
# pdf_batch single-chunk + batched dispatch
# ---------------------------------------------------------------------------


def test_batch_single_chunk_passes_no_ocr_for_text_layer_pages(tmp_path: Path) -> None:
    """Chunks with no OCR need get ``--no-ocr`` on the single-chunk worker cmd."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 6)
    captured: list[list[str]] = []

    process_pdf_in_chunks(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(recommended_docling_max_pages=4),
        runner=_capturing_runner(captured),
    )

    range_cmds = _range_cmds(captured)
    assert range_cmds, "expected at least one single-chunk worker cmd"
    assert all("--no-ocr" in cmd for cmd in range_cmds)


def test_batch_batched_manifest_carries_do_ocr(tmp_path: Path) -> None:
    """Batched pdf_batch manifest chunks carry the per-chunk do_ocr flag."""
    pdf = _make_blank_pdf(tmp_path / "doc.pdf", 6)
    captured: list[list[str]] = []

    process_pdf_in_chunks(
        pdf,
        output_dir=tmp_path / "out",
        budget=_budget(recommended_docling_max_pages=4),
        runner=_capturing_runner(captured),
        use_batched_worker=True,
    )

    batch_cmds = [c for c in _worker_cmds(captured) if "--batch" in c]
    assert batch_cmds, "expected a batched worker cmd"
    manifest_path = Path(batch_cmds[0][batch_cmds[0].index("--batch") + 1])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["chunks"], "expected at least one chunk in the manifest"
    assert all(chunk.get("do_ocr") is False for chunk in manifest["chunks"])
