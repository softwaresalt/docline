"""Failing-first tests for PDF layout engine resolution (G3c task 015.001-T).

Covers ``_resolve_layout_engine`` which resolves ``"auto"`` to ``"docling"``
when the optional ``docline[pdf]`` extras are installed (probe via
``dependencies.pdf_available``), and to ``"heuristic"`` otherwise. Pass-through
behavior for explicit ``"heuristic"`` / ``"docling"`` is also covered.
"""

from __future__ import annotations

import pytest

from docline.readers.pdf import (
    DependencyUnavailableError,
    _resolve_layout_engine,
    read_pdf_pages,
)


def test_auto_resolves_to_docling_when_pdf_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """``"auto"`` returns ``"docling"`` when the docling probe reports available."""
    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: True)
    assert _resolve_layout_engine("auto") == "docling"


def test_auto_resolves_to_heuristic_when_pdf_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """``"auto"`` returns ``"heuristic"`` when the docling probe reports unavailable."""
    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: False)
    assert _resolve_layout_engine("auto") == "heuristic"


def test_heuristic_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit ``"heuristic"`` is passed through regardless of probe state."""
    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: True)
    assert _resolve_layout_engine("heuristic") == "heuristic"


def test_docling_passthrough_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit ``"docling"`` is passed through when the probe reports available."""
    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: True)
    assert _resolve_layout_engine("docling") == "docling"


def test_invalid_engine_rejected() -> None:
    """An unknown engine value raises :class:`ValueError`."""
    with pytest.raises(ValueError, match="Unknown PDF layout_engine"):
        _resolve_layout_engine("bogus")


def test_docling_raises_when_unavailable(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling ``read_pdf_pages(layout_engine="docling")`` raises when docling is unavailable.

    Regression coverage — this behavior already exists in the heuristic
    fallback path. Ensures the engine selector does not silently downgrade.
    """
    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: False)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(DependencyUnavailableError):
        read_pdf_pages(pdf, layout_engine="docling")


# ---------------------------------------------------------------------------
# 018.001.002-T — resolve_pdf_engine_for_file (probe-driven size gate)
# ---------------------------------------------------------------------------


def _make_budget(**overrides):
    """Build a ResourceBudget with sensible defaults for size-gate tests."""

    from docline.runtime.resource_probe import ResourceBudget

    defaults = {
        "available_ram_gb": 24.0,
        "total_ram_gb": 32.0,
        "logical_cpus": 8,
        "pagefile_pressure": False,
        "accelerator_device": "cpu",
        "gpu_name": None,
        "gpu_vram_gb": None,
        "gpu_compute_capability": None,
        "recommended_concurrency": 2,
        "recommended_docling_max_pages": 75,
        "recommended_docling_max_mb": 30,
        "serialize_docling": False,
        "omp_thread_count": 2,
    }
    defaults.update(overrides)
    return ResourceBudget(**defaults)


def _write_pdf_of_size(path, size_mb: float) -> None:
    """Write a syntactically-valid PDF padded to approximately ``size_mb`` MB."""

    header = b"%PDF-1.4\n"
    payload_bytes = max(int(size_mb * 1_000_000) - len(header), 0)
    path.write_bytes(header + b"\x00" * payload_bytes)


def test_resolve_for_file_passes_through_explicit_heuristic(tmp_path) -> None:
    """Explicit 'heuristic' bypasses the probe."""

    from docline.readers.pdf import resolve_pdf_engine_for_file

    pdf = tmp_path / "doc.pdf"
    _write_pdf_of_size(pdf, 1.0)
    engine, reason = resolve_pdf_engine_for_file(pdf, requested="heuristic")
    assert engine == "heuristic"
    assert reason == "explicit_request"


def test_resolve_for_file_passes_through_explicit_docling(tmp_path) -> None:
    """Explicit 'docling' bypasses the probe — caller opted in."""

    from docline.readers.pdf import resolve_pdf_engine_for_file

    pdf = tmp_path / "doc.pdf"
    _write_pdf_of_size(pdf, 1.0)
    engine, reason = resolve_pdf_engine_for_file(pdf, requested="docling")
    assert engine == "docling"
    assert reason == "explicit_request"


def test_resolve_for_file_auto_returns_heuristic_when_engine_unavailable(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When docling isn't installed, 'auto' falls back without probing."""

    from docline.readers.pdf import resolve_pdf_engine_for_file

    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: False)
    pdf = tmp_path / "doc.pdf"
    _write_pdf_of_size(pdf, 1.0)
    engine, reason = resolve_pdf_engine_for_file(pdf, requested="auto")
    assert engine == "heuristic"
    assert reason == "engine_unavailable"


def test_resolve_for_file_auto_under_budget_returns_docling(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Small PDF + ample budget → docling with reason 'ok'."""

    from docline.readers.pdf import resolve_pdf_engine_for_file

    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: True)
    monkeypatch.setattr("docline.runtime.resource_probe.probe", lambda: _make_budget())
    monkeypatch.setattr("docline.readers.pdf._approximate_pdf_page_count", lambda path: 10)
    pdf = tmp_path / "doc.pdf"
    _write_pdf_of_size(pdf, 5.0)
    engine, reason = resolve_pdf_engine_for_file(pdf, requested="auto")
    assert engine == "docling"
    assert reason == "ok"


def test_resolve_for_file_auto_oversize_file_downgrades_to_heuristic(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cosmos-class PDF (109 MB) under a 30 MB budget → heuristic with 'file_too_large'."""

    from docline.readers.pdf import resolve_pdf_engine_for_file

    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: True)
    monkeypatch.setattr("docline.runtime.resource_probe.probe", lambda: _make_budget())
    monkeypatch.setattr("docline.readers.pdf._approximate_pdf_page_count", lambda path: 700)
    pdf = tmp_path / "huge.pdf"
    _write_pdf_of_size(pdf, 109.0)
    engine, reason = resolve_pdf_engine_for_file(pdf, requested="auto")
    assert engine == "heuristic"
    assert reason == "file_too_large"


def test_resolve_for_file_auto_excess_pages_downgrades_to_heuristic(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Small file with too many pages → heuristic with 'page_count_too_high'."""

    from docline.readers.pdf import resolve_pdf_engine_for_file

    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: True)
    monkeypatch.setattr("docline.runtime.resource_probe.probe", lambda: _make_budget())
    monkeypatch.setattr("docline.readers.pdf._approximate_pdf_page_count", lambda path: 500)
    pdf = tmp_path / "small.pdf"
    _write_pdf_of_size(pdf, 2.0)
    engine, reason = resolve_pdf_engine_for_file(pdf, requested="auto")
    assert engine == "heuristic"
    assert reason == "page_count_too_high"


def test_resolve_for_file_auto_low_ram_returns_heuristic(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the host budget is zero (< 4 GB RAM tier), 'auto' → heuristic."""

    from docline.readers.pdf import resolve_pdf_engine_for_file

    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: True)
    monkeypatch.setattr(
        "docline.runtime.resource_probe.probe",
        lambda: _make_budget(recommended_docling_max_pages=0, recommended_docling_max_mb=0),
    )
    monkeypatch.setattr("docline.readers.pdf._approximate_pdf_page_count", lambda path: 5)
    pdf = tmp_path / "doc.pdf"
    _write_pdf_of_size(pdf, 1.0)
    engine, reason = resolve_pdf_engine_for_file(pdf, requested="auto")
    assert engine == "heuristic"
    assert reason == "insufficient_ram"


def test_resolve_for_file_auto_unknown_page_count_trusts_size_gate(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When pypdf can't read a PDF (returns None), file size alone gates the decision."""

    from docline.readers.pdf import resolve_pdf_engine_for_file

    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: True)
    monkeypatch.setattr("docline.runtime.resource_probe.probe", lambda: _make_budget())
    monkeypatch.setattr("docline.readers.pdf._approximate_pdf_page_count", lambda path: None)
    pdf = tmp_path / "doc.pdf"
    _write_pdf_of_size(pdf, 10.0)
    engine, reason = resolve_pdf_engine_for_file(pdf, requested="auto")
    assert engine == "docling"
    assert reason == "ok"


def test_resolve_for_file_rejects_unknown_engine(tmp_path) -> None:
    """Unknown ``requested`` raises ValueError before any probe / IO."""

    from docline.readers.pdf import resolve_pdf_engine_for_file

    pdf = tmp_path / "doc.pdf"
    _write_pdf_of_size(pdf, 1.0)
    with pytest.raises(ValueError, match="Unknown PDF layout_engine"):
        resolve_pdf_engine_for_file(pdf, requested="bogus")


def test_resolve_for_file_raises_when_path_missing(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing path propagates FileNotFoundError in auto mode."""

    from docline.readers.pdf import resolve_pdf_engine_for_file

    monkeypatch.setattr("docline.readers.pdf.dependencies.pdf_available", lambda: True)
    with pytest.raises(FileNotFoundError):
        resolve_pdf_engine_for_file(tmp_path / "missing.pdf", requested="auto")
