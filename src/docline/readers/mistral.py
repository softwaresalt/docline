"""Mistral OCR reader — accesses Foundry MaaS or direct Mistral REST endpoint.

Replaced ADI in 031-S after the 2026-06-12 empirical study found ADI's
``prebuilt-layout`` model loses on every structural fidelity metric vs
docling on cosmos-class technical reference PDFs (see
``docs/closure/029-S-adi-spike.md``).

Why raw httpx instead of the mistralai SDK
------------------------------------------
The mistralai>=1 SDK assumes a base URL it can append ``/v1/ocr`` to.
Foundry MaaS Mistral OCR deployments are path-routed
(e.g. ``https://<resource>.services.ai.azure.com/providers/mistral/azure/ocr``)
and the SDK appends a duplicate path, causing 404. Discovery probe
(2026-06-13, docs/plans/2026-06-13-mistral-ocr-replace-adi-plan.md
T2 prep) confirmed raw httpx POST against the full endpoint with
``Authorization: Bearer <key>`` and the standard Mistral OCR request
body works against both Foundry and direct-Mistral endpoints.

Credential resolution order
---------------------------
1. Explicit ``api_key`` + ``endpoint`` kwargs win
2. ``AZURE_AI_FOUNDRY_KEY`` + ``AZURE_AI_FOUNDRY_ENDPOINT`` env vars
   (Foundry MaaS — preferred when set)
3. ``MISTRAL_API_KEY`` env var with default
   ``https://api.mistral.ai/v1/ocr`` endpoint (direct Mistral fallback)
4. Else raise ``MistralCredentialError``

Model selection: defaults to ``mistral-document-ai-2505`` (May 2025
release); override via the ``model`` kwarg or ``MISTRAL_OCR_MODEL``
env var.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from pathlib import Path

from docline.dependencies import require_extra
from docline.schema.models import DoclineError

_log = logging.getLogger(__name__)

_DEFAULT_MODEL = "mistral-document-ai-2505"
_DEFAULT_DIRECT_ENDPOINT = "https://api.mistral.ai/v1/ocr"
_REQUEST_TIMEOUT_SECONDS = 120.0


class MistralCredentialError(DoclineError):
    """Raised when Mistral OCR credentials are missing, malformed, or rejected."""


def _resolve_credentials(
    api_key: str | None,
    endpoint: str | None,
) -> tuple[str, str]:
    """Resolve API key + endpoint using the documented precedence.

    Returns:
        Tuple of ``(resolved_api_key, resolved_endpoint)``.

    Raises:
        MistralCredentialError: When no credential pair is resolvable
            or when the endpoint shape is malformed.
    """
    if api_key and endpoint:
        resolved_key, resolved_endpoint = api_key, endpoint
    else:
        foundry_key = os.environ.get("AZURE_AI_FOUNDRY_KEY", "").strip()
        foundry_endpoint = os.environ.get("AZURE_AI_FOUNDRY_ENDPOINT", "").strip()
        if foundry_key and foundry_endpoint:
            resolved_key = api_key or foundry_key
            resolved_endpoint = endpoint or foundry_endpoint
        else:
            direct_key = os.environ.get("MISTRAL_API_KEY", "").strip()
            if direct_key:
                resolved_key = api_key or direct_key
                resolved_endpoint = endpoint or _DEFAULT_DIRECT_ENDPOINT
            else:
                raise MistralCredentialError(
                    "Mistral OCR credentials not found. Set either "
                    "AZURE_AI_FOUNDRY_KEY + AZURE_AI_FOUNDRY_ENDPOINT (Foundry MaaS) "
                    "or MISTRAL_API_KEY (direct Mistral) in the environment, "
                    "or pass api_key + endpoint kwargs explicitly."
                )

    if not resolved_endpoint.startswith("https://"):
        raise MistralCredentialError(
            f"Mistral OCR endpoint must start with https:// (got: {resolved_endpoint!r})"
        )
    return resolved_key, resolved_endpoint


def _build_request_body(pdf_bytes: bytes, model: str) -> dict:
    """Build the Mistral OCR JSON request body with an inline base64 data URL."""
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    document_url = f"data:application/pdf;base64,{pdf_b64}"
    return {
        "model": model,
        "document": {"type": "document_url", "document_url": document_url},
    }


def read_pdf_mistral(
    path: Path,
    api_key: str | None = None,
    endpoint: str | None = None,
    model: str = _DEFAULT_MODEL,
    *,
    _transport: object | None = None,
) -> str:
    """Extract markdown from a PDF via Mistral OCR (Foundry MaaS or direct).

    Args:
        path: Source PDF path.
        api_key: Explicit API key (overrides env vars when also passing endpoint).
        endpoint: Explicit endpoint URL (must include the model-routing path
            for Foundry MaaS deployments). Overrides env vars.
        model: Mistral OCR model id. Defaults to ``mistral-document-ai-2505``.
            Overridable via ``MISTRAL_OCR_MODEL`` env var.
        _transport: Internal use only — pass an ``httpx.MockTransport`` for
            in-process testing without network I/O. Not part of the public API.

    Returns:
        Concatenated markdown content across all pages of the response,
        joined with double newlines.

    Raises:
        FileNotFoundError: If ``path`` does not exist (not wrapped).
        MistralCredentialError: If no credentials are resolvable, the
            endpoint shape is invalid, or the server returns 401.
        DoclineError: For other HTTP errors (5xx, network failures) with
            path + status context.
        DependencyUnavailableError: When the optional ``[mistral]`` extra
            (``httpx``) is not installed.
    """
    require_extra("httpx", extra="mistral")
    import httpx

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    resolved_key, resolved_endpoint = _resolve_credentials(api_key, endpoint)
    resolved_model = os.environ.get("MISTRAL_OCR_MODEL", "").strip() or model

    pdf_bytes = path.read_bytes()
    body = _build_request_body(pdf_bytes, resolved_model)

    client_kwargs: dict = {"timeout": _REQUEST_TIMEOUT_SECONDS}
    if _transport is not None:
        client_kwargs["transport"] = _transport

    start = time.monotonic()
    try:
        with httpx.Client(**client_kwargs) as client:
            response = client.post(
                resolved_endpoint,
                json=body,
                headers={
                    "Authorization": f"Bearer {resolved_key}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.HTTPError as err:
        raise DoclineError(
            f"Mistral OCR request failed for {path}: {type(err).__name__}: {err}"
        ) from err

    elapsed = time.monotonic() - start

    if response.status_code == 401:
        raise MistralCredentialError(
            f"Mistral OCR rejected credentials (401) for {path}; body: {response.text[:200]}"
        )
    if response.status_code != 200:
        raise DoclineError(
            f"Mistral OCR returned HTTP {response.status_code} for {path}: {response.text[:300]}"
        )

    try:
        data = response.json()
    except ValueError as err:
        raise DoclineError(
            f"Mistral OCR returned non-JSON response for {path}: {response.text[:200]}"
        ) from err

    pages = data.get("pages", [])
    page_count = len(pages)
    markdown = "\n\n".join(p.get("markdown", "") for p in pages)
    usage = data.get("usage_info", {})

    _log.info(
        "Mistral OCR: %s pages, %.2fs wall, model=%s, usage=%s",
        page_count,
        elapsed,
        resolved_model,
        usage,
    )
    return markdown
