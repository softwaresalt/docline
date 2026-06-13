"""Tests for src/docline/readers/mistral.py (029.002-T / 031-S).

Mistral OCR via Foundry MaaS (or direct Mistral API) using raw httpx.
The mistralai SDK is NOT used — Foundry endpoints are path-routed
(e.g. https://<resource>.services.ai.azure.com/providers/mistral/azure/ocr)
and the SDK assumes a base URL it can append /v1/ocr to. Discovery
probe (2026-06-13) confirmed raw httpx POST against the full endpoint
with `Authorization: Bearer <key>` works.

Tests use httpx.MockTransport for in-process HTTP mocking — no external
mocking library needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pypdf
import pytest


def _make_blank_pdf(path: Path, page_count: int = 1) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def _mock_ocr_handler(
    *,
    pages_markdown: list[str] | None = None,
    status: int = 200,
    expect_model: str | None = None,
    expect_endpoint: str | None = None,
    expect_auth_value: str | None = None,
    record: dict | None = None,
):
    """Build a httpx.MockTransport handler that simulates Foundry OCR.

    Returns 200 with a `{pages: [{markdown}], usage_info, model}` shape
    by default; override `status` to simulate failures.
    """
    import httpx

    pages = pages_markdown if pages_markdown is not None else ["# Mock\n\nbody"]

    def handler(request: httpx.Request) -> httpx.Response:
        if record is not None:
            record["url"] = str(request.url)
            record["headers"] = dict(request.headers)
            record["body"] = json.loads(request.content.decode("utf-8"))
        if expect_endpoint is not None:
            assert str(request.url) == expect_endpoint
        if expect_auth_value is not None:
            assert request.headers.get("authorization") == expect_auth_value
        if expect_model is not None:
            body = json.loads(request.content.decode("utf-8"))
            assert body.get("model") == expect_model
        if status != 200:
            return httpx.Response(
                status,
                json={"error": {"code": str(status), "message": "simulated"}},
            )
        return httpx.Response(
            200,
            json={
                "pages": [{"markdown": md} for md in pages],
                "model": "mistral-document-ai-2505",
                "usage_info": {"pages_processed": len(pages)},
            },
        )

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_read_pdf_mistral_happy_path_returns_concatenated_markdown(tmp_path: Path) -> None:
    """Multi-page response is concatenated with double newlines."""
    from docline.readers.mistral import read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    transport = _mock_ocr_handler(pages_markdown=["# Page 1\n\nA", "# Page 2\n\nB"])
    result = read_pdf_mistral(
        pdf,
        api_key="kkk",
        endpoint="https://example.com/foundry/mistral/ocr",
        _transport=transport,
    )
    assert "# Page 1" in result
    assert "# Page 2" in result
    assert "\n\n" in result  # double-newline separator


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------


def test_explicit_args_win_over_env_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When api_key + endpoint args are passed, env vars MUST NOT be consulted."""
    from docline.readers.mistral import read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_KEY", "env-key")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_ENDPOINT", "https://env.example/ocr")
    record: dict = {}
    transport = _mock_ocr_handler(
        expect_endpoint="https://explicit.example/ocr",
        expect_auth_value="Bearer explicit-key",
        record=record,
    )
    read_pdf_mistral(
        pdf,
        api_key="explicit-key",
        endpoint="https://explicit.example/ocr",
        _transport=transport,
    )
    assert record["url"] == "https://explicit.example/ocr"
    assert record["headers"]["authorization"] == "Bearer explicit-key"


def test_foundry_env_vars_preferred_over_mistral_direct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AZURE_AI_FOUNDRY_* set + MISTRAL_API_KEY set → Foundry wins."""
    from docline.readers.mistral import read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_KEY", "foundry-key")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_ENDPOINT", "https://foundry.example/ocr")
    monkeypatch.setenv("MISTRAL_API_KEY", "direct-key")
    record: dict = {}
    transport = _mock_ocr_handler(record=record)
    read_pdf_mistral(pdf, _transport=transport)
    assert record["url"] == "https://foundry.example/ocr"
    assert record["headers"]["authorization"] == "Bearer foundry-key"


def test_mistral_direct_used_when_only_mistral_api_key_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No Foundry vars + MISTRAL_API_KEY set → direct Mistral endpoint."""
    from docline.readers.mistral import read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    monkeypatch.delenv("AZURE_AI_FOUNDRY_KEY", raising=False)
    monkeypatch.delenv("AZURE_AI_FOUNDRY_ENDPOINT", raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY", "direct-key")
    record: dict = {}
    transport = _mock_ocr_handler(record=record)
    read_pdf_mistral(pdf, _transport=transport)
    assert "api.mistral.ai" in record["url"]
    assert record["headers"]["authorization"] == "Bearer direct-key"


def test_mistral_credential_error_when_nothing_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No credentials anywhere → MistralCredentialError before any HTTP call."""
    from docline.readers.mistral import MistralCredentialError, read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    monkeypatch.delenv("AZURE_AI_FOUNDRY_KEY", raising=False)
    monkeypatch.delenv("AZURE_AI_FOUNDRY_ENDPOINT", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(MistralCredentialError):
        read_pdf_mistral(pdf)


def test_mistral_credential_error_when_foundry_endpoint_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Foundry key set but endpoint missing → MistralCredentialError."""
    from docline.readers.mistral import MistralCredentialError, read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_KEY", "k")
    monkeypatch.delenv("AZURE_AI_FOUNDRY_ENDPOINT", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(MistralCredentialError):
        read_pdf_mistral(pdf)


def test_mistral_credential_error_when_endpoint_malformed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Endpoint that doesn't start with https:// raises MistralCredentialError."""
    from docline.readers.mistral import MistralCredentialError, read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    monkeypatch.delenv("AZURE_AI_FOUNDRY_KEY", raising=False)
    monkeypatch.delenv("AZURE_AI_FOUNDRY_ENDPOINT", raising=False)
    with pytest.raises(MistralCredentialError, match="https://"):
        read_pdf_mistral(pdf, api_key="k", endpoint="ftp://wrong/")


# ---------------------------------------------------------------------------
# Model parameter
# ---------------------------------------------------------------------------


def test_default_model_is_mistral_document_ai_2505(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default model is mistral-document-ai-2505 (newer May 2025)."""
    from docline.readers.mistral import read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    monkeypatch.delenv("MISTRAL_OCR_MODEL", raising=False)
    transport = _mock_ocr_handler(expect_model="mistral-document-ai-2505")
    read_pdf_mistral(
        pdf,
        api_key="k",
        endpoint="https://example.com/ocr",
        _transport=transport,
    )


def test_explicit_model_arg_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`model="mistral-ocr-2503"` passes through to request body."""
    from docline.readers.mistral import read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    monkeypatch.delenv("MISTRAL_OCR_MODEL", raising=False)
    transport = _mock_ocr_handler(expect_model="mistral-ocr-2503")
    read_pdf_mistral(
        pdf,
        api_key="k",
        endpoint="https://example.com/ocr",
        model="mistral-ocr-2503",
        _transport=transport,
    )


def test_mistral_ocr_model_env_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MISTRAL_OCR_MODEL env var overrides the default model arg."""
    from docline.readers.mistral import read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    monkeypatch.setenv("MISTRAL_OCR_MODEL", "mistral-ocr-2503")
    transport = _mock_ocr_handler(expect_model="mistral-ocr-2503")
    read_pdf_mistral(
        pdf,
        api_key="k",
        endpoint="https://example.com/ocr",
        _transport=transport,
    )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_http_500_re_wrapped_as_docline_error(tmp_path: Path) -> None:
    """A 500 response surfaces as DoclineError with path + status context."""
    from docline.readers.mistral import read_pdf_mistral
    from docline.schema.models import DoclineError

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    transport = _mock_ocr_handler(status=500)
    with pytest.raises(DoclineError) as exc:
        read_pdf_mistral(
            pdf,
            api_key="k",
            endpoint="https://example.com/ocr",
            _transport=transport,
        )
    assert "500" in str(exc.value) or "simulated" in str(exc.value)


def test_http_401_surfaces_as_credential_error(tmp_path: Path) -> None:
    """A 401 response surfaces as MistralCredentialError (clearer signal)."""
    from docline.readers.mistral import MistralCredentialError, read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    transport = _mock_ocr_handler(status=401)
    with pytest.raises(MistralCredentialError):
        read_pdf_mistral(
            pdf,
            api_key="bad-key",
            endpoint="https://example.com/ocr",
            _transport=transport,
        )


def test_file_not_found_propagates(tmp_path: Path) -> None:
    """Missing PDF raises FileNotFoundError (not wrapped as DoclineError)."""
    from docline.readers.mistral import read_pdf_mistral

    with pytest.raises(FileNotFoundError):
        read_pdf_mistral(
            tmp_path / "does-not-exist.pdf",
            api_key="k",
            endpoint="https://example.com/ocr",
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_two_invocations_return_same_result(tmp_path: Path) -> None:
    """Same input → same output (no global state)."""
    from docline.readers.mistral import read_pdf_mistral

    pdf = _make_blank_pdf(tmp_path / "doc.pdf")
    transport = _mock_ocr_handler(pages_markdown=["# A", "# B"])
    transport2 = _mock_ocr_handler(pages_markdown=["# A", "# B"])
    r1 = read_pdf_mistral(
        pdf, api_key="k", endpoint="https://example.com/ocr", _transport=transport
    )
    r2 = read_pdf_mistral(
        pdf, api_key="k", endpoint="https://example.com/ocr", _transport=transport2
    )
    assert r1 == r2
