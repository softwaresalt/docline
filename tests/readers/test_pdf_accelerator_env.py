"""Tests for the ``DOCLINE_ACCELERATOR`` env-gated docling accelerator override (048-F).

The override lets an operator explicitly pin the docling compute device
(``auto``/``cpu``/``cuda``/``mps``/``xpu``) rather than relying on docling's
implicit ``auto`` detection. ``auto`` (and an unset variable) preserve the prior
behavior exactly, so the default path is unchanged; a concrete device — most
usefully ``cpu`` — is an escape hatch when the auto-detected accelerator is
unreliable. The resolver is pure (no docling import) so it is always testable;
the option builder is exercised only when docling is installed.
"""

from __future__ import annotations

import pytest

from docline.readers.pdf import (
    PdfConfigError,
    _accelerator_options_for,
    _resolve_accelerator_device,
)


@pytest.mark.parametrize("raw", [None, "", "   ", "\t"])
def test_resolve_unset_or_blank_returns_none(raw: str | None) -> None:
    """Unset or blank env means 'no override' — docling keeps its default."""
    assert _resolve_accelerator_device(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("auto", "auto"),
        ("AUTO", "auto"),
        ("cpu", "cpu"),
        ("CPU", "cpu"),
        (" Cuda ", "cuda"),
        ("mps", "mps"),
        ("XPU", "xpu"),
    ],
)
def test_resolve_normalizes_valid_devices(raw: str, expected: str) -> None:
    """Recognized devices normalize to lowercase, whitespace-trimmed form."""
    assert _resolve_accelerator_device(raw) == expected


@pytest.mark.parametrize("raw", ["gpu", "nonsense", "cud a", "cpu0"])
def test_resolve_invalid_device_raises_typed_error(raw: str) -> None:
    """An unrecognized device fails fast with a typed, descriptive error."""
    with pytest.raises(PdfConfigError) as excinfo:
        _resolve_accelerator_device(raw)
    message = str(excinfo.value)
    assert "DOCLINE_ACCELERATOR" in message
    assert raw.strip() in message


def test_resolve_invalid_error_is_docline_error() -> None:
    """PdfConfigError participates in the docline typed-exception hierarchy."""
    from docline.schema.models import DoclineError

    assert issubclass(PdfConfigError, DoclineError)


@pytest.mark.parametrize("device", [None, "auto"])
def test_accelerator_options_none_for_default(device: str | None) -> None:
    """None and 'auto' both mean 'no override', so no options object is built."""
    pytest.importorskip("docling")
    assert _accelerator_options_for(device) is None


@pytest.mark.parametrize("device", ["cpu", "cuda", "mps", "xpu"])
def test_accelerator_options_maps_concrete_device(device: str) -> None:
    """A concrete device maps onto docling's AcceleratorOptions with matching device."""
    pytest.importorskip("docling")
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions

    options = _accelerator_options_for(device)
    assert isinstance(options, AcceleratorOptions)
    assert options.device == AcceleratorDevice(device)


def test_env_override_wires_accelerator_into_pipeline_options(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``DOCLINE_ACCELERATOR=cpu`` reaches docling's PdfPipelineOptions.

    Exercises the full read path (env read -> resolve -> options build ->
    constructor injection) without loading an OCR model by faking the
    DocumentConverter so ``convert`` never runs.
    """
    pytest.importorskip("docling")
    pytest.importorskip("pypdf")
    import pypdf
    from docling.datamodel.accelerator_options import AcceleratorDevice
    from docling.datamodel.base_models import InputFormat

    from docline.readers import pdf as pdf_reader

    pdf_path = tmp_path / "doc.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with pdf_path.open("wb") as fh:
        writer.write(fh)

    captured: dict[str, object] = {}

    class _FakeDocument:
        def export_to_markdown(self) -> str:
            return ""

    class _FakeResult:
        document = _FakeDocument()

    class _FakeConverter:
        def __init__(self, *, format_options: dict) -> None:
            captured["pipeline_options"] = format_options[InputFormat.PDF].pipeline_options

        def convert(self, _source: str) -> _FakeResult:
            return _FakeResult()

    monkeypatch.setenv("DOCLINE_ACCELERATOR", "cpu")
    monkeypatch.setattr("docling.document_converter.DocumentConverter", _FakeConverter)

    pdf_reader._read_pdf_docling_pages(pdf_path)

    pipeline_options = captured["pipeline_options"]
    assert pipeline_options.accelerator_options.device == AcceleratorDevice("cpu")
