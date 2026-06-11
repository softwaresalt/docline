"""Azure Document Intelligence (ADI) extractor — 027-F / 029-S T2 spike.

Optional third PDF layout extractor, peer to ``docling`` and the
built-in heuristic engine. Wraps Microsoft's
``azure.ai.documentintelligence.DocumentIntelligenceClient`` and uses
the ``prebuilt-layout`` model with ``output_content_format='markdown'``
to return graphtor-docs-ready Markdown directly from Azure's cloud API.

Spike intent (per deliberation
``docs/decisions/2026-06-10-next-pdf-pipeline-shipment-deliberation.md``):

* solves the cosmos PDF throughput problem (~25h docling → ~30min ADI)
* eliminates the ``pdf_batch.py`` subprocess-containment surface that
  exists solely to work around docling's failure modes
* trades compute time for cloud cost (~$0.0015/page at the
  prebuilt-layout list price as of 2026-06)

Authentication
--------------
ADI requires an endpoint + key (or Entra ID token). The default
credential resolution is environment-based:

* ``AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`` — full API endpoint URL
* ``AZURE_DOCUMENT_INTELLIGENCE_KEY`` — primary or secondary key

Callers MAY pass an explicit endpoint + key (or
``azure.core.credentials.TokenCredential``) to :func:`read_pdf_adi` to
override the env-based default.

Optional dependency gate
------------------------
``azure-ai-documentintelligence`` is an OPTIONAL extra (``[adi]``).
This module raises :class:`docline.dependencies.DependencyUnavailableError`
with a clear install hint when the SDK is absent and a caller attempts
to use it. Importing this module itself does NOT require the SDK; the
import is deferred until the first ``read_pdf_adi`` call.

Public API:
    :func:`read_pdf_adi` — PDF path → markdown body string
    :class:`AdiCredentialError` — raised when credentials are missing
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from docline.dependencies import require_extra
from docline.schema.models import DoclineError

_log = logging.getLogger(__name__)

# Env var names for default credential resolution.
_ENV_ENDPOINT = "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"
_ENV_KEY = "AZURE_DOCUMENT_INTELLIGENCE_KEY"

# Prebuilt model identifier — the layout model is the closest peer to
# docling's structural-extraction behavior. The 'document' model adds
# entity extraction but costs more and is overkill for our markdown
# pipeline target.
_DEFAULT_MODEL_ID = "prebuilt-layout"

# Output format — 'markdown' is the canonical request format that maps
# directly to docline's downstream pipeline. Available in SDK
# v1.0+ (older versions return only 'text').
_DEFAULT_OUTPUT_FORMAT = "markdown"


class AdiCredentialError(DoclineError):
    """Raised when ADI credentials (endpoint + key) are missing or invalid."""


def _resolve_credentials(
    endpoint: str | None,
    key: str | None,
) -> tuple[str, str]:
    """Resolve ``(endpoint, key)`` from explicit args or env vars.

    Args:
        endpoint: Explicit endpoint URL (overrides env var).
        key: Explicit primary/secondary key (overrides env var).

    Returns:
        Tuple of ``(endpoint, key)`` strings, both guaranteed non-empty.

    Raises:
        AdiCredentialError: When neither explicit args nor env vars
            provide both endpoint and key.
    """
    resolved_endpoint = endpoint or os.environ.get(_ENV_ENDPOINT, "")
    resolved_key = key or os.environ.get(_ENV_KEY, "")

    if not resolved_endpoint or not resolved_key:
        missing: list[str] = []
        if not resolved_endpoint:
            missing.append(_ENV_ENDPOINT)
        if not resolved_key:
            missing.append(_ENV_KEY)
        raise AdiCredentialError(
            "Azure Document Intelligence credentials not configured. "
            f"Set environment variables: {', '.join(missing)}. "
            "Or pass endpoint= and key= explicitly to read_pdf_adi()."
        )
    return resolved_endpoint, resolved_key


def read_pdf_adi(
    path: Path,
    *,
    endpoint: str | None = None,
    key: str | None = None,
    model_id: str = _DEFAULT_MODEL_ID,
) -> str:
    """Extract markdown from a PDF via Azure Document Intelligence.

    Sends ``path`` to the ADI ``prebuilt-layout`` model with
    ``output_content_format='markdown'``. Returns the markdown body
    string ready to feed into docline's downstream pipeline.

    Args:
        path: PDF file path. Must exist; readable as bytes.
        endpoint: ADI service endpoint URL. Defaults to the
            ``AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`` env var.
        key: ADI primary or secondary key. Defaults to the
            ``AZURE_DOCUMENT_INTELLIGENCE_KEY`` env var.
        model_id: Prebuilt model identifier. Defaults to
            ``"prebuilt-layout"`` (the structural-extraction peer to
            docling). Override only if a customer-specific custom model
            is needed.

    Returns:
        Markdown body string (the ``AnalyzeResult.content`` field).
        Empty string when the API returns no content (rare; logged as
        a warning).

    Raises:
        DependencyUnavailableError: When the ``[adi]`` extra is not
            installed (``azure-ai-documentintelligence`` missing).
        AdiCredentialError: When endpoint/key cannot be resolved.
        FileNotFoundError: When ``path`` does not exist.
        DoclineError: When the ADI API request fails after the SDK is
            installed and credentials are valid (wraps the underlying
            SDK exception).
    """
    require_extra("azure.ai.documentintelligence", extra="adi")

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    resolved_endpoint, resolved_key = _resolve_credentials(endpoint, key)

    # Lazy import — only invoked after dependency + credential checks pass.
    # The require_extra() call above ensured the import will succeed.
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential
    from azure.core.exceptions import AzureError

    client = DocumentIntelligenceClient(
        endpoint=resolved_endpoint,
        credential=AzureKeyCredential(resolved_key),
    )

    pdf_bytes = path.read_bytes()
    start = time.monotonic()
    try:
        poller = client.begin_analyze_document(
            model_id=model_id,
            body=pdf_bytes,
            content_type="application/pdf",
            output_content_format=_DEFAULT_OUTPUT_FORMAT,
        )
        result = poller.result()
    except AzureError as err:
        raise DoclineError(f"Azure Document Intelligence analyze failed for {path}: {err}") from err
    elapsed = time.monotonic() - start

    # Telemetry: page count + wall time + projected cost line item.
    page_count = len(getattr(result, "pages", []) or [])
    projected_cost_usd = page_count * 0.0015  # prebuilt-layout list price
    _log.info(
        "ADI analyze complete: path=%s pages=%d wall_s=%.2f projected_cost_usd=%.4f",
        path,
        page_count,
        elapsed,
        projected_cost_usd,
    )

    content = getattr(result, "content", "") or ""
    if not content:
        _log.warning("ADI returned empty content for %s (pages=%d)", path, page_count)
    return content


__all__ = ["read_pdf_adi", "AdiCredentialError"]
