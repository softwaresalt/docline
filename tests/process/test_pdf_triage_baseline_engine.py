"""Tests for ``baseline_engine`` parameter in pdf_triage (task 020.002-T / U1)."""

from __future__ import annotations

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
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        output_path = Path(args[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
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


def test_baseline_engine_default_is_markitdown(tmp_path: Path) -> None:
    """When `baseline_engine` is not specified, the default MUST be 'markitdown'."""
    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=3)
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=MagicMock(side_effect=_runner_factory()),
        scorer=_no_flag_scorer(),
    )
    assert result.metadata.get("baseline_engine") == "markitdown", (
        f"default baseline_engine must be 'markitdown'; "
        f"got: {result.metadata.get('baseline_engine')!r}"
    )


def test_baseline_engine_markitdown_invokes_heuristic_extract_helper(tmp_path: Path) -> None:
    """`baseline_engine='markitdown'` MUST route through `_heuristic_extract`.

    Behavior assertion: when markitdown engine is selected, the orchestrator
    records the engine choice in metadata AND maintains a valid fallback
    counter (integer, increments when markitdown fails on a page and the
    pypdf fallback runs).
    """
    from docline.process.pdf_triage import process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=3)
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=MagicMock(side_effect=_runner_factory()),
        scorer=_no_flag_scorer(),
        baseline_engine="markitdown",
    )
    # Engine choice recorded
    assert result.metadata.get("baseline_engine") == "markitdown"
    # Fallback counter is a valid integer (0 when markitdown succeeds on
    # all pages; positive when some pages fell back to pypdf). On a blank
    # 3-page PDF, markitdown handles the input cleanly so counter is 0.
    fallback = result.metadata.get("baseline_engine_fallback")
    assert isinstance(fallback, int) and fallback >= 0, (
        f"baseline_engine_fallback must be a non-negative int; got {fallback!r}"
    )


def test_get_markitdown_silences_noisy_pdfminer_loggers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_get_markitdown` MUST suppress pdfminer's per-page font / interp
    warnings to ERROR level.

    The cosmos PDF has malformed FontBBox entries on thousands of pages.
    Without suppression pdfminer.pdffont emits one WARNING per affected
    page, drowning out real diagnostics on long runs. The suppression is
    applied at module-load-time of MarkItDown (inside `_get_markitdown`)
    so it covers every subsequent pdfminer call in the process.

    Uses ``monkeypatch`` so the singleton reset and logger-level mutations
    are restored automatically on test teardown — preventing cross-test
    contamination from this test's mutation of process-wide state.
    """
    import logging

    from docline.process import pdf_triage

    # Reset both loggers and the singleton so we exercise the install
    # path. monkeypatch.setattr restores the original singleton value on
    # teardown; logger levels are restored by capturing + setting back.
    pdffont_logger = logging.getLogger("pdfminer.pdffont")
    pdfinterp_logger = logging.getLogger("pdfminer.pdfinterp")
    original_pdffont_level = pdffont_logger.level
    original_pdfinterp_level = pdfinterp_logger.level

    pdffont_logger.setLevel(logging.NOTSET)
    pdfinterp_logger.setLevel(logging.NOTSET)
    monkeypatch.setattr(pdf_triage, "_MARKITDOWN_INSTANCE", None)

    try:
        pdf_triage._get_markitdown()

        for name in ("pdfminer.pdffont", "pdfminer.pdfinterp"):
            assert logging.getLogger(name).level >= logging.ERROR, (
                f"{name} logger should be suppressed to ERROR; "
                f"got level {logging.getLogger(name).level}"
            )
    finally:
        pdffont_logger.setLevel(original_pdffont_level)
        pdfinterp_logger.setLevel(original_pdfinterp_level)
