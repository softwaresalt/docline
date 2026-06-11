"""Tests for pdf_engine routing including the new azure_di peer.

Covers 027-F T3 / 027.003-T:
- pdf_engine='azure_di' explicit dispatches to adi reader
- pdf_engine='auto' routing policy:
    1. azure_di when AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT set + SDK installed
    2. docling when [pdf] extra installed and ADI not preferred
    3. heuristic fallback
- CLI accepts --pdf-engine azure_di
- Manifest schema includes azure_di in the enum
- ProcessRequest pdf_engine Literal includes azure_di
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from docline import dependencies
from docline.readers.pdf import _resolve_layout_engine

# ---------------------------------------------------------------------------
# _resolve_layout_engine policy
# ---------------------------------------------------------------------------


def test_explicit_azure_di_passes_through() -> None:
    assert _resolve_layout_engine("azure_di") == "azure_di"


def test_explicit_docling_passes_through() -> None:
    assert _resolve_layout_engine("docling") == "docling"


def test_explicit_heuristic_passes_through() -> None:
    assert _resolve_layout_engine("heuristic") == "heuristic"


def test_invalid_engine_raises() -> None:
    with pytest.raises(ValueError, match="Unknown PDF layout_engine"):
        _resolve_layout_engine("foobar")


def test_auto_prefers_azure_di_when_creds_and_sdk_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x/")
    with (
        patch.object(dependencies, "adi_available", return_value=True),
        patch.object(dependencies, "pdf_available", return_value=True),
    ):
        assert _resolve_layout_engine("auto") == "azure_di"


def test_auto_falls_back_to_docling_when_no_azure_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    with (
        patch.object(dependencies, "adi_available", return_value=True),
        patch.object(dependencies, "pdf_available", return_value=True),
    ):
        assert _resolve_layout_engine("auto") == "docling"


def test_auto_falls_back_to_docling_when_adi_sdk_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x/")
    with (
        patch.object(dependencies, "adi_available", return_value=False),
        patch.object(dependencies, "pdf_available", return_value=True),
    ):
        assert _resolve_layout_engine("auto") == "docling"


def test_auto_falls_back_to_heuristic_when_nothing_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    with (
        patch.object(dependencies, "adi_available", return_value=False),
        patch.object(dependencies, "pdf_available", return_value=False),
    ):
        assert _resolve_layout_engine("auto") == "heuristic"


# ---------------------------------------------------------------------------
# CLI + manifest surface includes azure_di
# ---------------------------------------------------------------------------


def test_cli_accepts_pdf_engine_azure_di(tmp_path: Path) -> None:
    """`docline process --pdf-engine azure_di` is accepted at the argparse layer."""
    result = subprocess.run(
        [sys.executable, "-m", "docline", "process", "--pdf-engine", "azure_di", "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    # --help short-circuits before action; the choices are advertised in help text.
    assert result.returncode == 0
    assert "azure_di" in result.stdout


def test_cli_ingest_accepts_pdf_engine_azure_di(tmp_path: Path) -> None:
    """`docline ingest local-dir --pdf-engine azure_di` is also accepted."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "docline",
            "ingest",
            "local-dir",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "azure_di" in result.stdout


def test_manifest_includes_azure_di_in_pdf_engine_enum(tmp_path: Path) -> None:
    """The MCP tool manifest for ingest_local_dir lists azure_di in pdf_engine's enum."""
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
    assert "azure_di" in pdf_engine_schema["enum"]


def test_process_request_accepts_azure_di() -> None:
    """ProcessRequest.pdf_engine Literal includes azure_di."""
    from docline.app_models import ProcessRequest

    req = ProcessRequest(pdf_engine="azure_di")
    assert req.pdf_engine == "azure_di"


def test_process_request_rejects_unknown_engine() -> None:
    """Pydantic Literal validation rejects unknown values."""
    from pydantic import ValidationError

    from docline.app_models import ProcessRequest

    with pytest.raises(ValidationError):
        ProcessRequest(pdf_engine="foobar")  # type: ignore[arg-type]


def test_auto_surfaces_adi_credential_error_immediately(tmp_path, monkeypatch) -> None:
    """When --pdf-engine auto routes to ADI but credentials are missing,
    AdiCredentialError MUST surface immediately rather than fall back to
    docling silently per-file (which would just spam warnings)."""
    import sys
    import types

    import pytest as _pytest

    from docline import dependencies as _dep
    from docline.readers.adi import AdiCredentialError
    from docline.readers.pdf import read_pdf_pages

    # Install a minimal fake azure.* SDK so require_extra's import check
    # passes; the test specifically exercises the credential-missing branch
    # AFTER the SDK gate.
    monkeypatch.setitem(sys.modules, "azure", types.ModuleType("azure"))
    monkeypatch.setitem(sys.modules, "azure.core", types.ModuleType("azure.core"))
    creds_mod = types.ModuleType("azure.core.credentials")
    creds_mod.AzureKeyCredential = type("FakeCred", (), {"__init__": lambda self, k: None})
    monkeypatch.setitem(sys.modules, "azure.core.credentials", creds_mod)
    exc_mod = types.ModuleType("azure.core.exceptions")
    exc_mod.AzureError = type("FakeAzureError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "azure.core.exceptions", exc_mod)
    monkeypatch.setitem(sys.modules, "azure.ai", types.ModuleType("azure.ai"))
    di_mod = types.ModuleType("azure.ai.documentintelligence")
    di_mod.DocumentIntelligenceClient = type("FakeClient", (), {})
    monkeypatch.setitem(sys.modules, "azure.ai.documentintelligence", di_mod)

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 placeholder")

    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x/")
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", raising=False)

    # Force the auto policy to resolve to azure_di by claiming ADI is available.
    monkeypatch.setattr(_dep, "adi_available", lambda: True)
    monkeypatch.setattr(_dep, "pdf_available", lambda: True)

    with _pytest.raises(AdiCredentialError):
        read_pdf_pages(pdf, layout_engine="auto")
