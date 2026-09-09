"""Terraform Registry provider-docs discovery adapter (structural stub).

Recognizes Terraform Registry provider documentation start URLs
(``registry.terraform.io/providers/{namespace}/{name}/(latest|<version>)/docs``)
and enumerates every documentation URL for that provider via the registry's
v2 JSON:API, without a runtime browser.

All outbound requests go through :func:`docline.fetch.http.fetch_page` — the
hardened, connect-time address-pinned, budget-aware transport — never a raw
HTTP client. This is what makes the SSRF (I3) and budget (I2) invariants hold.

Structural stub for 070.004-T's harness (:mod:`tests.fetch.test_tf_registry_source`):

* :meth:`TfRegistrySource.recognizes` and version resolution are implemented
  by 070.005-T (T4a).
* Paged ``provider-docs`` enumeration is implemented by 070.006-T (T4b).

This module is registered into the discovery-source seam
(:mod:`docline.fetch.link_sources`) at ``crawl.py``'s composition point
(070.010-T) — it never registers itself, keeping the generic seam free of
any concrete-provider import in the other direction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from docline.fetch.crawl_models import CrawlConfig
from docline.fetch.http import RemainingByteBudget, fetch_page
from docline.schema.models import DoclineError

REGISTRY_HOST: str = "registry.terraform.io"
"""The recognized origin host for Terraform Registry provider docs (I5)."""

_ = fetch_page
"""Retained reference (not a real call): keeps ``fetch_page`` imported at this
module's top level so the monkeypatch seam
``docline.fetch.tf_registry_source.fetch_page`` already matches what
070.005-T/070.006-T's real implementation imports and calls, without changing
070.004-T's test file across that task boundary."""


class TfRegistryAdapterError(DoclineError):
    """Raised when the Terraform Registry adapter cannot enumerate provider docs.

    Covers non-200 responses, JSON-decode failures, and schema drift from the
    registry's v2 JSON:API. Never raised for
    :class:`~docline.fetch.http.AggregateBudgetExceededError` or
    :class:`~docline.fetch.url_policy.CrawlUrlRejectedError` — those propagate
    unwrapped (I4 carve-out) so a budget/SSRF stop is never masked as an
    ordinary adapter failure.
    """


class TfRegistrySource:
    """:class:`~docline.fetch.link_sources.DiscoverySource` for the Terraform Registry."""

    def recognizes(self, start_url: str) -> bool:
        """Return ``True`` for a Terraform Registry provider-docs start URL."""
        raise NotImplementedError("070.005-T implements the recognizer")

    async def discover_doc_urls(
        self,
        start_url: str,
        config: CrawlConfig,
        budget: RemainingByteBudget | None,
    ) -> AsyncIterator[str]:
        """Lazily yield every provider-doc URL for the recognized start URL."""
        raise NotImplementedError("070.005-T/070.006-T implement enumeration")
        yield  # pragma: no cover -- unreachable; keeps this an async generator


__all__ = ["REGISTRY_HOST", "TfRegistryAdapterError", "TfRegistrySource"]
