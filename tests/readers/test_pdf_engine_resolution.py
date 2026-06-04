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
