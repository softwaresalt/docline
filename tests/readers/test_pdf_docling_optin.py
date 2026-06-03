"""Red-first PDF docling opt-in tests (010-S F5.T4).

These tests pin the library-level contract that F5.T5 (010.024-T) must
satisfy when adding phase-2 ``docling`` opt-in support to ``read_pdf``:

* a ``layout_engine`` keyword parameter exists on ``read_pdf`` /
  ``read_pdf_pages`` accepting the literals ``"heuristic"`` (default) and
  ``"docling"``
* default behavior (no kwarg) is bit-identical to the explicit
  ``layout_engine="heuristic"`` call — the phase-1 heuristic emits today's
  output regardless of how it is invoked
* requesting ``layout_engine="docling"`` while the ``docling`` package is
  not importable raises :class:`DependencyUnavailableError` with a message
  that names the missing package
* unknown engine values raise a clear ``DoclineError`` subclass rather than
  silently falling back

These assertions are expected to **fail today** because ``read_pdf`` accepts
only a single positional ``path`` argument. F5.T5 lands the ``layout_engine``
parameter, the docling-availability gate, and the engine-value validator
that turn these red tests green.

Pypdf is patched off in the heuristic-parity tests so the deterministic
built-in path is exercised regardless of optional-dependency availability.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import docline.dependencies as dependencies_module
import docline.readers.pdf as pdf_module
from docline.dependencies import DependencyUnavailableError
from docline.readers.pdf import read_pdf, read_pdf_pages
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Minimal PDF fixture — three-band layout shared with the heuristic suite
# ---------------------------------------------------------------------------


def _build_three_band_pdf(tmp_path: Path) -> Path:
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog >> endobj\n"
        b"2 0 obj << /Length 200 >>\nstream\n"
        b"BT /F1 24 Tf (Document Title) Tj ET\n"
        b"BT /F1 16 Tf (Section Heading) Tj ET\n"
        b"BT /F1 12 Tf (Subsection) Tj ET\n"
        b"BT /F1 10 Tf (Body paragraph one.) Tj ET\n"
        b"BT /F1 10 Tf (Body paragraph two.) Tj ET\n"
        b"endstream\nendobj\n"
        b"%%EOF\n"
    )
    path = tmp_path / "three_band_docling_optin.pdf"
    path.write_bytes(body)
    return path


# ---------------------------------------------------------------------------
# Tests — target behavior the F5.T5 docling integration must satisfy
# ---------------------------------------------------------------------------


def test_read_pdf_accepts_layout_engine_kwarg(tmp_path: Path) -> None:
    """``read_pdf`` must accept a ``layout_engine`` keyword parameter."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        # The call itself must not raise TypeError for an unexpected kwarg.
        result = read_pdf(pdf_path, layout_engine="heuristic")  # type: ignore[call-arg]
    assert isinstance(result, str)


def test_read_pdf_pages_accepts_layout_engine_kwarg(tmp_path: Path) -> None:
    """``read_pdf_pages`` must accept the same ``layout_engine`` keyword."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf_pages(pdf_path, layout_engine="heuristic")  # type: ignore[call-arg]
    assert isinstance(result, list)
    assert all(isinstance(page, str) for page in result)


def test_default_engine_matches_explicit_heuristic(tmp_path: Path) -> None:
    """Default invocation must be bit-identical to ``layout_engine='heuristic'``."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        default_result = read_pdf(pdf_path)
        explicit_result = read_pdf(pdf_path, layout_engine="heuristic")  # type: ignore[call-arg]
    assert default_result == explicit_result, (
        "Default engine must equal explicit 'heuristic' to keep "
        "phase-1 behavior unchanged for existing callers."
    )


def test_docling_engine_without_docling_raises_dependency_error(
    tmp_path: Path,
) -> None:
    """Requesting docling when not importable must raise a typed dependency error."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(dependencies_module, "pdf_available", return_value=False):
        with pytest.raises(DependencyUnavailableError) as excinfo:
            read_pdf(pdf_path, layout_engine="docling")  # type: ignore[call-arg]
    assert "docling" in str(excinfo.value).lower()


def test_unknown_engine_value_raises_clear_error(tmp_path: Path) -> None:
    """Unrecognized engine values must fail loudly via a DoclineError subclass."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        with pytest.raises((DoclineError, ValueError)) as excinfo:
            read_pdf(pdf_path, layout_engine="not-a-real-engine")  # type: ignore[call-arg]
    # The error message must mention the offending engine value so operators
    # can correct the flag without reading the source.
    assert "not-a-real-engine" in str(excinfo.value)


def test_heuristic_engine_emits_phase1_heading_markers(tmp_path: Path) -> None:
    """The 'heuristic' engine must reuse the F5.T3 phase-1 banding output."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path, layout_engine="heuristic")  # type: ignore[call-arg]
    assert "# Document Title" in result
    assert "## Section Heading" in result
    assert "### Subsection" in result
