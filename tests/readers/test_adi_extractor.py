"""Tests for the ADI extractor (027-F T2 / 027.002-T).

Most tests use mocked SDK clients so they run without an Azure
subscription or installed [adi] extra. The integration-marked test
exercises live ADI behavior when AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT
and AZURE_DOCUMENT_INTELLIGENCE_KEY are set + the [adi] extra is
installed.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

from docline.dependencies import DependencyUnavailableError
from docline.readers.adi import (
    AdiCredentialError,
    _resolve_credentials,
    read_pdf_adi,
)

# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------


def test_resolve_credentials_explicit_args_win() -> None:
    ep, key = _resolve_credentials("https://explicit/", "explicit-key")
    assert ep == "https://explicit/"
    assert key == "explicit-key"


def test_resolve_credentials_from_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://env/")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "env-key")
    ep, key = _resolve_credentials(None, None)
    assert ep == "https://env/"
    assert key == "env-key"


def test_resolve_credentials_missing_endpoint_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    with pytest.raises(AdiCredentialError, match="AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"):
        _resolve_credentials(None, None)


def test_resolve_credentials_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x/")
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", raising=False)
    with pytest.raises(AdiCredentialError, match="AZURE_DOCUMENT_INTELLIGENCE_KEY"):
        _resolve_credentials(None, None)


def test_resolve_credentials_both_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", raising=False)
    with pytest.raises(AdiCredentialError) as exc:
        _resolve_credentials(None, None)
    assert "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT" in str(exc.value)
    assert "AZURE_DOCUMENT_INTELLIGENCE_KEY" in str(exc.value)


# ---------------------------------------------------------------------------
# read_pdf_adi behavior — uses installed-SDK fake to verify call shape
# ---------------------------------------------------------------------------


def _install_fake_adi_sdk(content: str = "# Mock content\n\nbody") -> None:
    """Install a fake azure.ai.documentintelligence module hierarchy.

    Stubs only the minimum surface read_pdf_adi touches. After test,
    sys.modules cleanup happens automatically because each test that
    calls this also installs sys.modules entries that pytest removes
    on test teardown.
    """
    # azure package skeleton
    if "azure" not in sys.modules:
        sys.modules["azure"] = types.ModuleType("azure")
    if "azure.core" not in sys.modules:
        sys.modules["azure.core"] = types.ModuleType("azure.core")
    if "azure.core.credentials" not in sys.modules:
        creds_mod = types.ModuleType("azure.core.credentials")

        class _FakeAzureKeyCredential:
            def __init__(self, key: str) -> None:
                self.key = key

        creds_mod.AzureKeyCredential = _FakeAzureKeyCredential
        sys.modules["azure.core.credentials"] = creds_mod
    if "azure.core.exceptions" not in sys.modules:
        exc_mod = types.ModuleType("azure.core.exceptions")

        class _FakeAzureError(Exception):
            pass

        exc_mod.AzureError = _FakeAzureError
        sys.modules["azure.core.exceptions"] = exc_mod
    if "azure.ai" not in sys.modules:
        sys.modules["azure.ai"] = types.ModuleType("azure.ai")
    di_mod = types.ModuleType("azure.ai.documentintelligence")

    class _FakeResult:
        def __init__(self, content_value: str, pages: int) -> None:
            self.content = content_value
            self.pages = [object()] * pages

    class _FakePoller:
        def __init__(self, result_value: object) -> None:
            self._r = result_value

        def result(self) -> object:
            return self._r

    class _FakeClient:
        last_call: dict[str, object] = {}

        def __init__(self, *, endpoint: str, credential: object) -> None:
            self.endpoint = endpoint
            self.credential = credential

        def begin_analyze_document(self, **kwargs: object) -> _FakePoller:
            _FakeClient.last_call = kwargs
            return _FakePoller(_FakeResult(content, pages=3))

    di_mod.DocumentIntelligenceClient = _FakeClient
    sys.modules["azure.ai.documentintelligence"] = di_mod


def test_read_pdf_adi_returns_markdown_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x/")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    _install_fake_adi_sdk(content="# Hello\n\nbody text")
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal placeholder")

    out = read_pdf_adi(pdf)
    assert "# Hello" in out
    assert "body text" in out


def test_read_pdf_adi_passes_layout_model_and_markdown_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x/")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    _install_fake_adi_sdk()
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF placeholder")

    read_pdf_adi(pdf)

    from azure.ai.documentintelligence import (
        DocumentIntelligenceClient,  # type: ignore[attr-defined]
    )

    last = DocumentIntelligenceClient.last_call  # type: ignore[attr-defined]
    assert last["model_id"] == "prebuilt-layout"
    assert last["output_content_format"] == "markdown"
    assert last["content_type"] == "application/pdf"
    assert last["body"] == pdf.read_bytes()


def test_read_pdf_adi_missing_file_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x/")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    _install_fake_adi_sdk()
    missing = tmp_path / "nonexistent.pdf"
    with pytest.raises(FileNotFoundError):
        read_pdf_adi(missing)


def test_read_pdf_adi_no_credentials_raises_credential_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", raising=False)
    _install_fake_adi_sdk()
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(AdiCredentialError):
        read_pdf_adi(pdf)


def test_read_pdf_adi_explicit_credentials_bypass_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", raising=False)
    _install_fake_adi_sdk()
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    # Should NOT raise — explicit args bypass env-var check.
    out = read_pdf_adi(pdf, endpoint="https://explicit/", key="explicit-key")
    assert isinstance(out, str)


def test_read_pdf_adi_sdk_missing_raises_dependency_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When [adi] extra is not installed, raise a clear DependencyUnavailableError."""
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x/")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    # Remove the fake SDK module if a prior test installed one.
    for mod_name in [
        "azure.ai.documentintelligence",
        "azure.ai",
        "azure.core.credentials",
        "azure.core.exceptions",
        "azure.core",
        "azure",
    ]:
        sys.modules.pop(mod_name, None)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(DependencyUnavailableError, match="adi"):
        read_pdf_adi(pdf)


# ---------------------------------------------------------------------------
# Live integration (skipped unless credentials + SDK present)
# ---------------------------------------------------------------------------


_HAS_ADI_CREDS = bool(
    os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    and os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY")
)


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_ADI_CREDS,
    reason="Live ADI test requires AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT + _KEY env vars",
)
def test_read_pdf_adi_live_smoke(tmp_path: Path) -> None:
    """Live smoke test — verifies the SDK + creds + service round-trip works.

    Uses a tiny synthetic PDF (1 page, plain text) so the test costs ~$0.0015.
    Only runs when both credentials are set AND the [adi] extra is installed.
    """
    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient  # noqa: F401
    except ImportError:
        pytest.skip("azure.ai.documentintelligence not installed")

    # Minimal valid PDF (1 page, "Hello"). Generated via pypdf.
    from pypdf import PdfWriter

    pdf_path = tmp_path / "smoke.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with open(pdf_path, "wb") as fh:
        writer.write(fh)

    out = read_pdf_adi(pdf_path)
    assert isinstance(out, str)
