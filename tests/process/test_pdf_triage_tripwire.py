"""Tests for the QA tripwire mode in ``pdf_triage`` (task 019.007-T)."""

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


def _ok_runner(markdown: str = "# docling output") -> Any:
    """Mock worker that writes a JSON envelope (production-accurate, post-032-F).

    The real ``docline._tools.docling_worker`` writes a JSON envelope, not
    flat markdown. Mocking flat markdown (the pre-033-S fixture) hid the
    QA-path envelope-parsing bug. This fixture mirrors production: it wraps
    ``markdown`` in a single-page envelope.
    """

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        out = Path(args[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "schema_version": 1,
            "pages": [markdown],
            "page_count": 1,
            "text": markdown,
        }
        out.write_text(json.dumps(envelope), encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def _no_flag_scorer() -> Any:
    from docline.process.fidelity_scorer import PageScore

    def scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
        return PageScore(
            page_index=page_index,
            signals={},
            aggregate=0.0,
            needs_docling=False,
            reason="ok",
        )

    return scorer


def test_sample_rate_zero_invokes_runner_only_for_flagged_ranges(tmp_path: Path) -> None:
    """qa_sampling=None or sample_rate=0 must not trigger any tripwire docling calls."""
    from docline.process.pdf_triage import QASampling, process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    runner = MagicMock(side_effect=_ok_runner())
    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_no_flag_scorer(),
        qa_sampling=QASampling(sample_rate=0.0, random_seed=42),
    )
    assert runner.call_count == 0


def test_sample_rate_one_samples_every_unflagged_page_subject_to_cap(tmp_path: Path) -> None:
    """sample_rate=1.0 samples every unflagged page (up to max_sampled_pages cap)."""
    from docline.process.pdf_triage import QASampling, process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    runner = MagicMock(side_effect=_ok_runner())
    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=runner,
        scorer=_no_flag_scorer(),
        qa_sampling=QASampling(sample_rate=1.0, random_seed=42, max_sampled_pages=50),
    )
    assert runner.call_count == 10


def test_disagreement_counter_increments_when_outputs_differ(tmp_path: Path) -> None:
    """When sampled docling output differs from heuristic, qa_disagreements increments."""
    from docline.process.pdf_triage import QASampling, process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=5)
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=_ok_runner("# This is wildly different from heuristic output"),
        scorer=_no_flag_scorer(),
        qa_sampling=QASampling(sample_rate=1.0, random_seed=42),
    )
    assert result.metadata.get("qa_disagreements", 0) >= 1


def test_random_seed_makes_sampling_deterministic(tmp_path: Path) -> None:
    """Two runs with the same seed select the same set of sampled pages."""
    from docline.process.pdf_triage import QASampling, process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=20)
    sampling = QASampling(sample_rate=0.3, random_seed=99)
    runner_a = MagicMock(side_effect=_ok_runner())
    runner_b = MagicMock(side_effect=_ok_runner())

    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "a",
        runner=runner_a,
        scorer=_no_flag_scorer(),
        qa_sampling=sampling,
    )
    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "b",
        runner=runner_b,
        scorer=_no_flag_scorer(),
        qa_sampling=sampling,
    )

    assert runner_a.call_count == runner_b.call_count
    pages_a = sorted(Path(call.args[0][-2]).stem for call in runner_a.call_args_list)
    pages_b = sorted(Path(call.args[0][-2]).stem for call in runner_b.call_args_list)
    assert pages_a == pages_b


# ---------------------------------------------------------------------------
# 033-S: QA tripwire must parse the worker JSON envelope, not read it raw
# ---------------------------------------------------------------------------


def test_qa_tripwire_compares_envelope_text_not_raw_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QA similarity must be computed against the envelope ``text``, not raw JSON.

    Regression: post-032-S the worker writes a JSON envelope, but the QA
    tripwire path read the file with ``qa_md.read_text()`` and passed the
    raw JSON string to ``_content_similarity``. That compared a JSON blob
    against heuristic markdown — always spuriously dissimilar. The fix
    parses the envelope and compares its ``text`` field.

    This test spies on ``_content_similarity`` and asserts the docling-side
    argument is the envelope's text marker, NOT the JSON envelope string.
    """
    from docline.process import pdf_triage
    from docline.process.pdf_triage import QASampling, process_pdf_triaged

    marker = "UNIQUE DOCLING TEXT MARKER 12345"
    captured: list[str] = []

    def spy_similarity(docling_text: str, heuristic_text: str) -> float:
        captured.append(docling_text)
        return 1.0

    monkeypatch.setattr(pdf_triage, "_content_similarity", spy_similarity)

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=5)
    process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=_ok_runner(marker),
        scorer=_no_flag_scorer(),
        qa_sampling=QASampling(sample_rate=1.0, random_seed=42),
        baseline_engine="pypdf",
    )

    assert captured, "QA tripwire did not invoke the similarity comparison"
    for docling_text in captured:
        assert docling_text == marker, (
            "QA tripwire passed raw worker output to the similarity check "
            "instead of the parsed envelope text"
        )
        assert "schema_version" not in docling_text


# ---------------------------------------------------------------------------
# 033-S: worker subprocess failures must surface their stderr diagnostic
# ---------------------------------------------------------------------------


def _failing_runner_with_stderr(stderr_marker: str) -> Any:
    """Mock worker that exits non-zero and emits a stderr diagnostic."""

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=5, stdout="", stderr=stderr_marker)

    return runner


def _flag_all_scorer() -> Any:
    from docline.process.fidelity_scorer import PageScore

    def scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
        return PageScore(
            page_index=page_index,
            signals={},
            aggregate=1.0,
            needs_docling=True,
            reason="forced",
        )

    return scorer


def test_worker_subprocess_failure_logs_stderr_diagnostic(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When a worker subprocess fails, its stderr diagnostic must be logged.

    Regression (033-S): the cosmos run had subprocess_fallback_count == 86
    (100% docling failure) but the operator could not see WHY because the
    captured ``completed.stderr`` was discarded. Observability (Constitution
    Principle V) requires the worker's diagnostic to be surfaced so failures
    are root-causable.
    """
    from docline.process.pdf_triage import process_pdf_triaged

    marker = "WORKER_STDERR_DIAG_MARKER_xyz"
    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=6)

    with caplog.at_level(logging.WARNING, logger="docline.process.pdf_triage"):
        result = process_pdf_triaged(
            pdf,
            output_dir=tmp_path / "out",
            runner=_failing_runner_with_stderr(marker),
            scorer=_flag_all_scorer(),
            buffer=0,
            baseline_engine="pypdf",
        )

    # All flagged ranges fell back (subprocess failed).
    assert result.metadata["subprocess_fallback_count"] >= 1
    # The worker's stderr diagnostic must appear in the logs for diagnosis.
    assert any(marker in rec.message for rec in caplog.records), (
        "worker stderr diagnostic was discarded; it must be logged on failure"
    )
