"""Tests for pdf_engine routing including mistral_ocr.

Post-031-S surface (ADI removed):
- pdf_engine values: 'auto', 'docling', 'mistral_ocr', 'heuristic'
- 'auto' policy: docling > heuristic; mistral_ocr is NEVER auto-selected
  pending 031-S T4 empirical study verdict
- Explicit mistral_ocr requests surface errors loudly (no silent fallback)
- CLI + MCP manifest enum match the supported set
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pypdf
import pytest

from docline import dependencies
from docline.readers.pdf import _SUPPORTED_LAYOUT_ENGINES, _resolve_layout_engine


def _make_blank_pdf(path: Path, page_count: int = 1) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


# ---------------------------------------------------------------------------
# _resolve_layout_engine policy
# ---------------------------------------------------------------------------


def test_supported_engines_set() -> None:
    assert _SUPPORTED_LAYOUT_ENGINES == frozenset({"auto", "heuristic", "docling", "mistral_ocr"})


def test_explicit_mistral_ocr_passes_through() -> None:
    assert _resolve_layout_engine("mistral_ocr") == "mistral_ocr"


def test_explicit_docling_passes_through() -> None:
    assert _resolve_layout_engine("docling") == "docling"


def test_explicit_heuristic_passes_through() -> None:
    assert _resolve_layout_engine("heuristic") == "heuristic"


def test_invalid_engine_raises() -> None:
    with pytest.raises(ValueError, match="Unknown PDF layout_engine"):
        _resolve_layout_engine("foobar")


def test_auto_never_selects_mistral_ocr_even_with_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-031-S: auto MUST NOT select mistral_ocr pending T4 verdict.

    The 029-S precedent (ADI was auto-selected then later removed when
    empirical study failed) is the basis for keeping mistral_ocr opt-in
    until the 031-S T4 verdict comes in. Even if the operator has
    Foundry credentials configured, auto stays docling-first.
    """
    monkeypatch.setenv("AZURE_AI_FOUNDRY_KEY", "k")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_ENDPOINT", "https://x/")
    monkeypatch.setenv("MISTRAL_API_KEY", "direct-k")
    with (
        patch.object(dependencies, "mistral_available", return_value=True),
        patch.object(dependencies, "pdf_available", return_value=True),
    ):
        assert _resolve_layout_engine("auto") == "docling"


def test_auto_falls_back_to_heuristic_when_nothing_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_AI_FOUNDRY_KEY", raising=False)
    monkeypatch.delenv("AZURE_AI_FOUNDRY_ENDPOINT", raising=False)
    with (
        patch.object(dependencies, "mistral_available", return_value=False),
        patch.object(dependencies, "pdf_available", return_value=False),
    ):
        assert _resolve_layout_engine("auto") == "heuristic"


# ---------------------------------------------------------------------------
# Explicit mistral_ocr dispatch — errors must surface loudly
# ---------------------------------------------------------------------------


def test_explicit_mistral_ocr_surfaces_credential_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When --pdf-engine mistral_ocr is explicit but credentials missing,
    MistralCredentialError MUST surface immediately (no silent fallback)."""
    from docline.readers.mistral import MistralCredentialError
    from docline.readers.pdf import read_pdf_pages

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    monkeypatch.delenv("AZURE_AI_FOUNDRY_KEY", raising=False)
    monkeypatch.delenv("AZURE_AI_FOUNDRY_ENDPOINT", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(dependencies, "mistral_available", lambda: True)

    with pytest.raises(MistralCredentialError):
        read_pdf_pages(pdf, layout_engine="mistral_ocr")


def test_explicit_mistral_ocr_raises_when_extra_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When [mistral] not installed, explicit request raises DependencyUnavailableError."""
    from docline.dependencies import DependencyUnavailableError
    from docline.readers.pdf import read_pdf_pages

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    monkeypatch.setattr(dependencies, "mistral_available", lambda: False)

    with pytest.raises(DependencyUnavailableError, match="mistral"):
        read_pdf_pages(pdf, layout_engine="mistral_ocr")


# ---------------------------------------------------------------------------
# CLI + MCP manifest surface
# ---------------------------------------------------------------------------


def test_cli_process_accepts_pdf_engine_mistral_ocr(tmp_path: Path) -> None:
    """`docline process --pdf-engine mistral_ocr` is accepted at the argparse layer."""
    result = subprocess.run(
        [sys.executable, "-m", "docline", "process", "--pdf-engine", "mistral_ocr", "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "mistral_ocr" in result.stdout


def test_cli_ingest_local_dir_help_advertises_mistral_ocr(tmp_path: Path) -> None:
    """`docline ingest local-dir --help` lists mistral_ocr as a pdf-engine choice."""
    result = subprocess.run(
        [sys.executable, "-m", "docline", "ingest", "local-dir", "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "mistral_ocr" in result.stdout


def test_manifest_includes_mistral_ocr_in_pdf_engine_enum(tmp_path: Path) -> None:
    """The MCP tool manifest lists mistral_ocr in pdf_engine's enum."""
    result = subprocess.run(
        [sys.executable, "-m", "docline", "--manifest"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    manifest = json.loads(result.stdout)
    ingest_tool = next(t for t in manifest["tools"] if t["name"] == "ingest_local_dir")
    pdf_engine_schema = ingest_tool["parameters"]["properties"]["pdf_engine"]
    assert "mistral_ocr" in pdf_engine_schema["enum"]


def test_process_request_accepts_mistral_ocr() -> None:
    """ProcessRequest.pdf_engine Literal includes mistral_ocr."""
    from docline.app_models import ProcessRequest

    req = ProcessRequest(pdf_engine="mistral_ocr")
    assert req.pdf_engine == "mistral_ocr"


def test_process_request_rejects_azure_di_after_removal() -> None:
    """Post-031-S: pdf_engine='azure_di' is no longer a valid value."""
    from pydantic import ValidationError

    from docline.app_models import ProcessRequest

    with pytest.raises(ValidationError):
        ProcessRequest(pdf_engine="azure_di")  # type: ignore[arg-type]


def test_process_request_rejects_unknown_engine() -> None:
    """Pydantic Literal validation rejects unknown values."""
    from pydantic import ValidationError

    from docline.app_models import ProcessRequest

    with pytest.raises(ValidationError):
        ProcessRequest(pdf_engine="foobar")  # type: ignore[arg-type]
