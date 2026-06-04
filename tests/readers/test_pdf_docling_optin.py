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
        result = read_pdf(pdf_path, layout_engine="heuristic")
    assert isinstance(result, str)


def test_read_pdf_pages_accepts_layout_engine_kwarg(tmp_path: Path) -> None:
    """``read_pdf_pages`` must accept the same ``layout_engine`` keyword."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf_pages(pdf_path, layout_engine="heuristic")
    assert isinstance(result, list)
    assert all(isinstance(page, str) for page in result)


def test_default_engine_matches_explicit_heuristic(tmp_path: Path) -> None:
    """Default invocation must be bit-identical to ``layout_engine='heuristic'``."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        default_result = read_pdf(pdf_path)
        explicit_result = read_pdf(pdf_path, layout_engine="heuristic")
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
            read_pdf(pdf_path, layout_engine="docling")
    assert "docling" in str(excinfo.value).lower()


def test_unknown_engine_value_raises_clear_error(tmp_path: Path) -> None:
    """Unrecognized engine values must fail loudly via a DoclineError subclass."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        with pytest.raises((DoclineError, ValueError)) as excinfo:
            read_pdf(pdf_path, layout_engine="not-a-real-engine")
    # The error message must mention the offending engine value so operators
    # can correct the flag without reading the source.
    assert "not-a-real-engine" in str(excinfo.value)


def test_heuristic_engine_emits_phase1_heading_markers(tmp_path: Path) -> None:
    """The 'heuristic' engine must reuse the F5.T3 phase-1 banding output."""
    pdf_path = _build_three_band_pdf(tmp_path)
    with patch.object(pdf_module, "_PYPDF_AVAILABLE", False):
        result = read_pdf(pdf_path, layout_engine="heuristic")
    assert "# Document Title" in result
    assert "## Section Heading" in result
    assert "### Subsection" in result


# ---------------------------------------------------------------------------
# 015-S — picture_sink kwarg threading + docling tuning options
# ---------------------------------------------------------------------------


def test_docling_engine_accepts_picture_sink_kwarg(tmp_path: Path) -> None:
    """``read_pdf_pages(layout_engine="docling", picture_sink=...)`` is accepted.

    Skip-gated when docling is not installed: this exercises the call-site
    contract surface, not the runtime conversion behavior.
    """
    if not dependencies_module.pdf_available():
        pytest.skip("docling not installed; skipping picture_sink kwarg surface test")

    from docline.readers.picture_sink import CountingPictureSink

    pdf_path = _build_three_band_pdf(tmp_path)
    sink = CountingPictureSink(tmp_path / "media")
    # Should not raise TypeError for unexpected keyword argument.
    try:
        read_pdf_pages(pdf_path, layout_engine="docling", picture_sink=sink)
    except TypeError as err:
        raise AssertionError(f"picture_sink kwarg not accepted: {err}") from err
    except Exception:
        # Docling parse failure on synthetic PDF is acceptable for this surface
        # test — what we care about is the kwarg being accepted.
        pass


def test_docling_pipeline_tuning_options_enabled_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When picture_sink is set, docling pipeline opts in to table-structure and picture generation.

    Captures the ``PdfPipelineOptions`` constructed by ``_read_pdf_docling_pages``
    via a converter-class monkeypatch and asserts the expected tuning flags
    are enabled. Skip-gated when docling is not installed.
    """
    if not dependencies_module.pdf_available():
        pytest.skip("docling not installed; skipping tuning-options test")

    from docline.readers.picture_sink import CountingPictureSink

    captured: dict[str, object] = {}

    def fake_converter_factory(
        *, format_options: dict[object, object] | None = None, **_kw: object
    ) -> object:
        # Capture the format options for assertion; return a stub that converts
        # to an object yielding an empty markdown string.
        captured["format_options"] = format_options

        class _Stub:
            def convert(self, _path: str) -> object:
                class _Result:
                    class document:  # type: ignore[no-untyped-def]
                        @staticmethod
                        def export_to_markdown() -> str:
                            return ""

                return _Result()

        return _Stub()

    # Patch the converter import inside _read_pdf_docling_pages by monkeypatching
    # the module the helper imports from.
    import docling.document_converter as dc_module  # type: ignore[import-untyped]

    monkeypatch.setattr(dc_module, "DocumentConverter", fake_converter_factory)

    pdf_path = _build_three_band_pdf(tmp_path)
    sink = CountingPictureSink(tmp_path / "media")
    read_pdf_pages(pdf_path, layout_engine="docling", picture_sink=sink)

    fmt_opts = captured.get("format_options")
    assert fmt_opts is not None, "expected DocumentConverter to be constructed with format_options"
    # The InputFormat.PDF key holds a PdfFormatOption with pipeline_options;
    # walk into it and confirm the tuning flags.
    from docling.datamodel.base_models import InputFormat  # type: ignore[import-untyped]

    pdf_format_option = fmt_opts[InputFormat.PDF]  # type: ignore[index]
    pipeline_options = pdf_format_option.pipeline_options
    assert pipeline_options.do_table_structure is True
    assert pipeline_options.generate_picture_images is True
