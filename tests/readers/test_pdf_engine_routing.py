"""Tests for pdf_engine routing including the azure_di peer.

Covers 027-F T3 / 027.003-T plus the post-empirical-study auto-policy
revision (docs/closure/029-S-adi-spike.md, 2026-06-12):
- pdf_engine='azure_di' explicit dispatches to adi reader
- pdf_engine='auto' routing policy:
    1. docling when [pdf] extra installed (PRIMARY default)
    2. heuristic fallback when docling not installed
- azure_di is NEVER auto-selected, even with credentials + SDK present;
  the operator must explicitly request --pdf-engine azure_di
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


def test_auto_never_selects_azure_di_even_with_creds_and_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-2026-06-12 empirical study: auto MUST NOT select azure_di.

    ADI loses on every structural fidelity metric vs docling on the
    docline-target corpus class (technical reference PDFs). Operators
    who want ADI for forms/invoices or throughput-dominated use cases
    must opt in explicitly via --pdf-engine azure_di.
    """
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x/")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    with (
        patch.object(dependencies, "adi_available", return_value=True),
        patch.object(dependencies, "pdf_available", return_value=True),
    ):
        assert _resolve_layout_engine("auto") == "docling"


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


def test_cli_ingest_help_advertises_azure_di(tmp_path: Path) -> None:
    """`docline ingest local-dir --help` lists azure_di as a pdf-engine choice."""
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


def test_explicit_azure_di_surfaces_adi_credential_error_immediately(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    install_fake_adi_sdk,
) -> None:
    """When --pdf-engine azure_di is explicitly requested but credentials are missing,
    AdiCredentialError MUST surface immediately rather than fall back to
    docling silently per-file (which would just spam warnings)."""
    from docline.readers.adi import AdiCredentialError
    from docline.readers.pdf import read_pdf_pages

    install_fake_adi_sdk()

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 placeholder")

    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x/")
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", raising=False)

    monkeypatch.setattr(dependencies, "adi_available", lambda: True)
    monkeypatch.setattr(dependencies, "pdf_available", lambda: True)

    with pytest.raises(AdiCredentialError):
        read_pdf_pages(pdf, layout_engine="azure_di")


def test_explicit_azure_di_surfaces_transient_error_loudly(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    install_fake_adi_sdk,
) -> None:
    """When --pdf-engine azure_di is explicit, transient ADI errors MUST raise.

    The silent-fallback chain (warn + use docling, then heuristic) was
    scoped to the legacy `auto` path that pre-2026-06-12 could resolve
    to `azure_di`. Now that `auto` never selects ADI, the only path
    into the ADI dispatch is an explicit operator request. Surprising
    that operator by silently switching engines would be wrong;
    surfacing the error so they can decide (retry? change engine? add
    --pdf-engine fallback flag?) is the correct contract.
    """
    from docline.readers.pdf import read_pdf_pages
    from docline.schema.models import DoclineError

    def _make_blippy_client(azure_error_cls: type[Exception]) -> type:
        class _BlippyClient:
            def __init__(self, *, endpoint, credential) -> None:
                pass

            def begin_analyze_document(self, **kwargs):
                raise azure_error_cls("transient: simulated 503 from ADI")

        return _BlippyClient

    install_fake_adi_sdk()
    from azure.core.exceptions import AzureError  # type: ignore[attr-defined]

    install_fake_adi_sdk(client_cls=_make_blippy_client(AzureError))

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(
        b"%PDF-1.4\n1 0 obj <<>> endobj\nxref\n0 1\n0000000000 65535 f \n"
        b"trailer <</Size 1>>\nstartxref\n40\n%%EOF\n"
    )

    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x/")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    monkeypatch.setattr(dependencies, "adi_available", lambda: True)

    with pytest.raises(DoclineError, match="transient"):
        read_pdf_pages(pdf, layout_engine="azure_di")
