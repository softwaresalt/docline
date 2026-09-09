"""Terraform Registry provider-docs discovery adapter.

Recognizes Terraform Registry provider documentation start URLs
(``registry.terraform.io/providers/{namespace}/{name}/(latest|<version>)/docs``)
and enumerates every documentation URL for that provider via the registry's
v2 JSON:API, without a runtime browser.

All outbound requests go through :func:`docline.fetch.http.fetch_page` — the
hardened, connect-time address-pinned, budget-aware transport — never a raw
HTTP client. This is what makes the SSRF (I3) and budget (I2) invariants hold.

* :meth:`TfRegistrySource.recognizes` and provider-version resolution
  (:func:`_resolve_provider_version`) are implemented by 070.005-T (T4a).
* Paged ``provider-docs`` enumeration is implemented by 070.006-T (T4b).

This module is registered into the discovery-source seam
(:mod:`docline.fetch.link_sources`) at ``crawl.py``'s composition point
(070.010-T) — it never registers itself, keeping the generic seam free of
any concrete-provider import in the other direction.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from urllib.parse import quote, urlparse

from docline.fetch.crawl_models import CrawlConfig
from docline.fetch.http import AggregateBudgetExceededError, RemainingByteBudget, fetch_page
from docline.fetch.url_policy import CrawlUrlRejectedError
from docline.schema.models import DoclineError

REGISTRY_HOST: str = "registry.terraform.io"
"""The recognized origin host for Terraform Registry provider docs (I5)."""

# Path-segment charset (I6): namespace/name/category/slug must all match this
# before being interpolated into any constructed URL, or trusted from a parsed
# start URL. A segment that fails this check is never fetched or interpolated
# -- recognition/construction simply fails for that segment.
_SEGMENT_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._-]+$")

# Matches ``/providers/{namespace}/{name}/(latest|<version>)/docs`` and any
# trailing path. ``namespace``/``name`` are captured as raw path segments here
# and separately charset-validated (I6) -- the pattern alone does not enforce
# the charset, only the path *shape*.
_PATH_PATTERN: re.Pattern[str] = re.compile(
    r"^/providers/([^/]+)/([^/]+)/(?:latest|[^/]+)/docs(?:/.*)?$"
)


def _parse_start_url(start_url: str) -> tuple[str, str] | None:
    """Return the ``(namespace, name)`` pair for a recognized start URL, else ``None``.

    Enforces host confinement (I5) and path-segment charset validation (I6)
    before any network call is made -- an unrecognized or invalid URL never
    reaches :func:`_resolve_provider_version`.
    """
    parsed = urlparse(start_url)
    if parsed.scheme.lower() != "https":
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    if host != REGISTRY_HOST:
        return None
    match = _PATH_PATTERN.match(parsed.path)
    if not match:
        return None
    namespace, name = match.group(1), match.group(2)
    if not _SEGMENT_PATTERN.match(namespace) or not _SEGMENT_PATTERN.match(name):
        return None
    return namespace, name


async def _resolve_provider_version(
    namespace: str,
    name: str,
    config: CrawlConfig,
    budget: RemainingByteBudget | None,
) -> str:
    """Resolve the latest provider-version id for ``namespace/name``.

    Calls ``GET /v2/providers/{namespace}/{name}?include=provider-versions``
    through :func:`fetch_page` and reads the ``latest-version`` relationship.

    Raises:
        AggregateBudgetExceededError: Propagated unwrapped (I4 carve-out).
        CrawlUrlRejectedError: Propagated unwrapped (I4 carve-out).
        TfRegistryAdapterError: For any other fetch failure, a non-JSON
            content-type, a JSON-decode failure, or schema drift (a missing or
            malformed ``latest-version`` relationship).
    """
    lookup_url = (
        f"https://{REGISTRY_HOST}/v2/providers/"
        f"{quote(namespace, safe='')}/{quote(name, safe='')}?include=provider-versions"
    )
    try:
        response = await fetch_page(
            lookup_url,
            timeout_seconds=config.page_timeout_seconds,
            max_redirects=config.max_redirects,
            budget=budget,
        )
    except (AggregateBudgetExceededError, CrawlUrlRejectedError):
        # I4 carve-out: never wrapped into TfRegistryAdapterError.
        raise
    except Exception as err:
        raise TfRegistryAdapterError(
            f"Failed to resolve provider version for {namespace}/{name}: {err}"
        ) from err

    content_type = (response.content_type or "").lower()
    if "json" not in content_type:
        raise TfRegistryAdapterError(
            f"Provider lookup for {namespace}/{name} returned non-JSON content-type "
            f"{response.content_type!r}."
        )
    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError as err:
        raise TfRegistryAdapterError(
            f"Provider lookup for {namespace}/{name} returned invalid JSON."
        ) from err

    try:
        version_id = payload["data"]["relationships"]["latest-version"]["data"]["id"]
    except (KeyError, TypeError) as err:
        raise TfRegistryAdapterError(
            f"Provider lookup for {namespace}/{name} is missing the "
            "latest-version relationship (schema drift)."
        ) from err
    if not isinstance(version_id, str) or not version_id:
        raise TfRegistryAdapterError(
            f"Provider lookup for {namespace}/{name} returned a malformed version id."
        )
    return version_id


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
        return _parse_start_url(start_url) is not None

    async def discover_doc_urls(
        self,
        start_url: str,
        config: CrawlConfig,
        budget: RemainingByteBudget | None,
    ) -> AsyncIterator[str]:
        """Lazily yield every provider-doc URL for the recognized start URL."""
        parsed = _parse_start_url(start_url)
        if parsed is None:
            raise TfRegistryAdapterError(
                f"Unrecognized Terraform Registry start URL: {start_url!r}"
            )
        namespace, name = parsed
        await _resolve_provider_version(namespace, name, config, budget)
        raise NotImplementedError("070.006-T implements paged provider-docs enumeration")
        yield  # pragma: no cover -- unreachable; keeps this an async generator


__all__ = ["REGISTRY_HOST", "TfRegistryAdapterError", "TfRegistrySource"]
