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
from docline.fetch.url_policy import CrawlUrlRejectedError, validate_crawl_url
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


def _entry_attrs(item: object) -> dict[str, object] | None:
    """Return an ``attributes`` mapping from a JSON:API resource object, else ``None``."""
    if not isinstance(item, dict):
        return None
    attrs = item.get("attributes")
    return attrs if isinstance(attrs, dict) else None


def _get_next_url(container: dict[str, object]) -> str | None:
    """Return a validated string ``links.next`` from a JSON:API-shaped mapping."""
    links = container.get("links")
    if not isinstance(links, dict):
        return None
    next_url = links.get("next")
    return next_url if isinstance(next_url, str) else None


def _extract_docs_page(
    payload: dict[str, object], *, first_page: bool
) -> tuple[list[dict[str, object]], str | None]:
    """Return ``(entries, next_url)`` for one page of a provider-docs response.

    The first page (``GET /v2/provider-versions/{id}?include=provider-docs``)
    nests refs under ``data.relationships["provider-docs"]`` with the full
    attributes in a top-level ``included`` array, and paginates via that
    relationship's own ``links.next``. Every subsequent page (the ``links.next``
    target) is a plain provider-docs collection: ``data`` is a list of full
    resource objects directly, and pagination is the top-level ``links.next``.
    """
    if first_page:
        try:
            relationship = payload["data"]["relationships"]["provider-docs"]  # type: ignore[index]
        except (KeyError, TypeError) as err:
            raise TfRegistryAdapterError(
                "Provider-docs page is missing the provider-docs relationship (schema drift)."
            ) from err
        if not isinstance(relationship, dict):
            raise TfRegistryAdapterError(
                "Provider-docs page's provider-docs relationship is malformed (schema drift)."
            )
        refs = relationship.get("data")
        refs = refs if isinstance(refs, list) else []
        next_url = _get_next_url(relationship)
        included = payload.get("included")
        included = included if isinstance(included, list) else []
        attrs_by_id: dict[object, dict[str, object]] = {}
        for item in included:
            if isinstance(item, dict) and item.get("type") == "provider-docs":
                attrs = _entry_attrs(item)
                if attrs is not None:
                    attrs_by_id[item.get("id")] = attrs
        entries: list[dict[str, object]] = []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            attrs = attrs_by_id.get(ref.get("id"))
            if attrs is not None:
                entries.append(attrs)
        return entries, next_url

    items = payload.get("data")
    items = items if isinstance(items, list) else []
    next_url = _get_next_url(payload)
    entries = [attrs for item in items if (attrs := _entry_attrs(item)) is not None]
    return entries, next_url


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
        """Lazily yield every provider-doc URL for the recognized start URL.

        Follows ``links.next`` pagination across the registry's v2 JSON:API,
        confining every followed page to :data:`REGISTRY_HOST` (I5) and
        charset-validating (I6) every ``category``/``slug`` pair before it is
        interpolated into a constructed doc URL -- a hostile or malformed entry
        is skipped, never aborts enumeration. Genuinely async and lazy: no page
        beyond the one a consumer is currently draining is ever fetched.
        """
        parsed = _parse_start_url(start_url)
        if parsed is None:
            raise TfRegistryAdapterError(
                f"Unrecognized Terraform Registry start URL: {start_url!r}"
            )
        namespace, name = parsed
        version_id = await _resolve_provider_version(namespace, name, config, budget)

        docs_url: str | None = (
            f"https://{REGISTRY_HOST}/v2/provider-versions/"
            f"{quote(version_id, safe='')}?include=provider-docs"
        )
        first_page = True
        while docs_url is not None:
            try:
                response = await fetch_page(
                    docs_url,
                    timeout_seconds=config.page_timeout_seconds,
                    max_redirects=config.max_redirects,
                    budget=budget,
                )
            except (AggregateBudgetExceededError, CrawlUrlRejectedError):
                # I4 carve-out: never wrapped into TfRegistryAdapterError.
                raise
            except Exception as err:
                raise TfRegistryAdapterError(
                    f"Failed to enumerate provider docs for {namespace}/{name}: {err}"
                ) from err

            content_type = (response.content_type or "").lower()
            if "json" not in content_type:
                raise TfRegistryAdapterError(
                    f"Provider-docs page for {namespace}/{name} returned non-JSON "
                    f"content-type {response.content_type!r}."
                )
            try:
                payload = json.loads(response.body)
            except json.JSONDecodeError as err:
                raise TfRegistryAdapterError(
                    f"Provider-docs page for {namespace}/{name} returned invalid JSON."
                ) from err
            if not isinstance(payload, dict):
                raise TfRegistryAdapterError(
                    f"Provider-docs page for {namespace}/{name} returned a malformed body."
                )

            entries, next_url = _extract_docs_page(payload, first_page=first_page)
            first_page = False

            for attrs in entries:
                category = attrs.get("category")
                slug = attrs.get("slug")
                if not isinstance(category, str) or not isinstance(slug, str):
                    continue
                if not _SEGMENT_PATTERN.match(category) or not _SEGMENT_PATTERN.match(slug):
                    # Hostile or malformed entry (e.g. a path-traversal slug):
                    # skipped, never aborts the rest of the enumeration (I6).
                    continue
                doc_url = (
                    f"https://{REGISTRY_HOST}/providers/{quote(namespace, safe='')}"
                    f"/{quote(name, safe='')}/latest/docs/"
                    f"{quote(category, safe='')}/{quote(slug, safe='')}"
                )
                yield validate_crawl_url(doc_url)

            if next_url is None:
                docs_url = None
                continue
            next_host = (urlparse(next_url).hostname or "").lower().rstrip(".")
            if next_host != REGISTRY_HOST:
                # I5: an off-host links.next stops pagination without ever
                # fetching it -- a graceful stop preserving every already-
                # yielded valid item from earlier pages, not a fail-open trigger.
                docs_url = None
                continue
            docs_url = next_url


__all__ = ["REGISTRY_HOST", "TfRegistryAdapterError", "TfRegistrySource"]
