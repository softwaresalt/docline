"""Terraform Registry provider-docs discovery adapter.

Recognizes Terraform Registry provider documentation start URLs
(``registry.terraform.io/providers/{namespace}/{name}/(latest|<version>)/docs``)
and enumerates every documentation URL for that provider via the registry's
v2 JSON:API, without a runtime browser.

Only the ``"latest"`` version segment is actually resolved and enumerated.
A pinned, non-``"latest"`` version URL is recognized (so it is never treated
as an ordinary static-only host) but ``discover_doc_urls`` fails closed with
an explicit :class:`TfRegistryAdapterError` for it, degrading to static-only
extraction at the crawl-composition layer rather than silently substituting
the current latest version's docs. Genuine pinned-version resolution (listing
provider-versions and matching by version string, not just reading the
``latest-version`` relationship) is tracked as follow-up work, not part of
this adapter's current scope.

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
from docline.fetch.http import (
    AggregateBudgetExceededError,
    FetchResponse,
    RemainingByteBudget,
    fetch_page,
)
from docline.fetch.url_policy import CrawlUrlRejectedError, validate_crawl_url
from docline.schema.models import DoclineError

REGISTRY_HOST: str = "registry.terraform.io"
"""The recognized origin host for Terraform Registry provider docs (I5)."""

_API_MAX_REDIRECTS: int = 0
"""Redirect cap for every adapter-internal v2 JSON:API fetch (I5, hardened).

Deliberately ``0`` -- never ``config.max_redirects`` -- for the version-lookup
and provider-docs-page fetches. The shared transport's redirect handler
rejects private/reserved redirect targets (SSRF, I3) but permits redirecting
to any other *public* host, and it only reads the outbound Location header
after the request has already been dispatched: checking the *final* response
URL after the fact (:func:`_assert_response_on_registry_host`) cannot prevent
that outbound hop, only detect it post-hoc. Forbidding all redirects for these
API endpoints closes the gap entirely without adding a host allow-list to the
shared transport (an explicitly rejected design per the plan's constraint
#4). A genuine redirect from either endpoint fails the fetch outright and
degrades via the same fail-open path as any other adapter failure.
"""


def _is_registry_origin(url: str) -> bool:
    """Return whether *url* is same-origin with the recognized registry (I5).

    Confines to the ``https`` scheme, :data:`REGISTRY_HOST` hostname, and the
    default HTTPS port (``None``/``443``). Host confinement alone would still
    permit a same-host cleartext downgrade (``http://``) or a non-standard
    port, since ``fetch_page``'s own URL policy allows ``http``/``https``
    generically and is not itself scoped to this one origin.

    Never raises: both ``urlparse()`` itself (e.g. an unmatched IPv6 bracket)
    and ``ParseResult.port`` (a non-numeric or out-of-range port) can raise
    ``ValueError`` for a malformed authority, and *url* may be
    attacker-influenced remote JSON (a ``links.next`` value) or an
    externally-supplied start URL -- any parse failure is treated as a
    fail-closed non-match, never propagated as an exception that would abort
    an async generator or break the ``DiscoverySource.recognizes`` protocol's
    boolean, exception-free contract.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            return False
        host = (parsed.hostname or "").lower().rstrip(".")
        if host != REGISTRY_HOST:
            return False
        port = parsed.port
    except ValueError:
        return False
    return port is None or port == 443


def _assert_response_on_registry_host(response: FetchResponse, context: str) -> None:
    """Raise unless *response*'s final (post-redirect) URL is host-confined (I5).

    Defense-in-depth, secondary to :data:`_API_MAX_REDIRECTS`: with redirects
    forbidden for every adapter fetch, this should only ever observe the
    original request URL echoed back unchanged. Retained in case a future
    call site is added that does permit redirects, or the transport's
    redirect-rejection behavior ever changes, so an off-origin response is
    never silently trusted based on the *request* URL alone.
    """
    if not _is_registry_origin(response.url):
        raise TfRegistryAdapterError(
            f"{context}: final response URL resolved off-origin to {response.url!r}."
        )


# Path-segment charset (I6): namespace/name/category/slug must all match this
# before being interpolated into any constructed URL, or trusted from a parsed
# start URL. A segment that fails this check is never fetched or interpolated
# -- recognition/construction simply fails for that segment.
_SEGMENT_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._-]+$")

# The reserved relative-path segments. Both match _SEGMENT_PATTERN (``.`` is an
# accepted character) but would otherwise produce a literal ``./`` or ``../``
# path segment once percent-encoded via ``quote(safe="")`` (which does not
# encode ``.``) -- rejected explicitly, independent of the charset check.
_RESERVED_RELATIVE_SEGMENTS: frozenset[str] = frozenset({".", ".."})


def _is_safe_path_segment(segment: str) -> bool:
    """Return whether *segment* is safe to percent-encode into a constructed URL.

    Combines the I6 charset allowlist with an explicit rejection of the
    reserved relative-path segments ``"."``/``".."``.
    """
    if not _SEGMENT_PATTERN.match(segment):
        return False
    return segment not in _RESERVED_RELATIVE_SEGMENTS


# Matches ``/providers/{namespace}/{name}/(latest|<version>)/docs`` and any
# trailing path. ``namespace``/``name``/the version segment are captured as
# raw path segments here and separately charset-validated (I6) -- the pattern
# alone does not enforce the charset, only the path *shape*.
_PATH_PATTERN: re.Pattern[str] = re.compile(
    r"^/providers/([^/]+)/([^/]+)/(latest|[^/]+)/docs(?:/.*)?$"
)


def _parse_start_url(start_url: str) -> tuple[str, str, str] | None:
    """Return ``(namespace, name, version)`` for a recognized start URL, else ``None``.

    ``version`` is the literal string ``"latest"`` or a pinned version segment
    (e.g. ``"4.1.0"``) exactly as it appeared in the start URL. Enforces host
    confinement (I5) and path-segment charset validation (I6) before any
    network call is made -- an unrecognized or invalid URL never reaches
    :func:`_resolve_provider_version`.

    Note: recognizing a pinned-version start URL does not imply
    :func:`_resolve_provider_version`/:meth:`TfRegistrySource.discover_doc_urls`
    can enumerate docs for it -- only ``"latest"`` is currently resolved (see
    their own docstrings). A pinned-version URL is recognized (so
    ``crawl()`` never treats it as an ordinary static-only host) but
    enumeration for it fails closed with an explicit
    :class:`TfRegistryAdapterError`, which degrades to static-only extraction
    at the crawl-composition layer rather than silently substituting the
    current latest version's docs.
    """
    if not _is_registry_origin(start_url):
        # Checked before any local urlparse() call: urlparse() itself can
        # raise ValueError for a malformed authority (e.g. an unmatched IPv6
        # bracket), and _is_registry_origin already absorbs that -- calling
        # it first preserves this function's (and recognizes()'s) fail-closed,
        # exception-free contract for a malformed start URL.
        return None
    parsed = urlparse(start_url)
    match = _PATH_PATTERN.match(parsed.path)
    if not match:
        return None
    namespace, name, version = match.group(1), match.group(2), match.group(3)
    if not _is_safe_path_segment(namespace) or not _is_safe_path_segment(name):
        return None
    if version != "latest" and not _is_safe_path_segment(version):
        return None
    return namespace, name, version


async def _resolve_provider_version(
    namespace: str,
    name: str,
    config: CrawlConfig,
    budget: RemainingByteBudget | None,
) -> str:
    """Resolve the latest provider-version id for ``namespace/name``.

    Calls ``GET /v2/providers/{namespace}/{name}?include=provider-versions``
    through :func:`fetch_page`. The registry's real v2 JSON:API exposes
    ``relationships["provider-versions"]`` as a plain list of *every*
    published version -- there is no singular ``latest-version``
    relationship or explicit "is latest" flag anywhere in this response
    (verified against the live API; an earlier assumed shape citing such a
    relationship was never live-verified and was wrong). The latest version
    is therefore determined by comparing every included provider-version's
    ``published-at`` timestamp (ISO 8601, lexicographically sortable in this
    fixed-offset ``Z``-suffixed form) and returning the id of the maximum.

    Raises:
        AggregateBudgetExceededError: Propagated unwrapped (I4 carve-out).
        CrawlUrlRejectedError: Propagated unwrapped (I4 carve-out).
        TfRegistryAdapterError: For any other fetch failure, a non-JSON
            content-type, a JSON-decode failure, or schema drift (a missing,
            empty, or entirely-malformed ``included`` provider-versions set).
    """
    lookup_url = (
        f"https://{REGISTRY_HOST}/v2/providers/"
        f"{quote(namespace, safe='')}/{quote(name, safe='')}?include=provider-versions"
    )
    try:
        response = await fetch_page(
            lookup_url,
            timeout_seconds=config.page_timeout_seconds,
            max_redirects=_API_MAX_REDIRECTS,
            budget=budget,
        )
    except (AggregateBudgetExceededError, CrawlUrlRejectedError):
        # I4 carve-out: never wrapped into TfRegistryAdapterError.
        raise
    except Exception as err:
        raise TfRegistryAdapterError(
            f"Failed to resolve provider version for {namespace}/{name}: {err}"
        ) from err
    _assert_response_on_registry_host(response, f"Provider lookup for {namespace}/{name}")

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
    if not isinstance(payload, dict):
        raise TfRegistryAdapterError(
            f"Provider lookup for {namespace}/{name} returned a malformed body."
        )

    included = payload.get("included")
    if not isinstance(included, list):
        raise TfRegistryAdapterError(
            f"Provider lookup for {namespace}/{name} is missing the "
            "included provider-versions set (schema drift)."
        )

    best_id: str | None = None
    best_published_at: str = ""
    for item in included:
        if not isinstance(item, dict) or item.get("type") != "provider-versions":
            continue
        attrs = _entry_attrs(item)
        version_id = item.get("id")
        if attrs is None or not isinstance(version_id, str):
            continue
        published_at = attrs.get("published-at")
        if not isinstance(published_at, str):
            continue
        if published_at > best_published_at:
            best_published_at = published_at
            best_id = version_id

    if best_id is None or not _is_safe_path_segment(best_id):
        # version_id is interpolated into the provider-docs page URL (I6): an
        # attacker-influenced JSON:API response must never smuggle a bad
        # character or a reserved relative-path segment into that URL, and a
        # response with no usable provider-version entries is schema drift.
        raise TfRegistryAdapterError(
            f"Provider lookup for {namespace}/{name} has no usable provider-version entries."
        )
    return best_id


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

        Raises:
            TfRegistryAdapterError: When *start_url* is unrecognized, or when
                it pins a specific, non-``"latest"`` provider version. Only
                ``"latest"`` is currently resolved and enumerated; a pinned
                version fails closed here rather than silently substituting
                the current latest version's docs (see
                :func:`_parse_start_url`'s docstring). This is caught and
                degraded to static-only extraction by the crawl-composition
                layer, the same as any other adapter failure.
        """
        parsed = _parse_start_url(start_url)
        if parsed is None:
            raise TfRegistryAdapterError(
                f"Unrecognized Terraform Registry start URL: {start_url!r}"
            )
        namespace, name, version = parsed
        if version != "latest":
            raise TfRegistryAdapterError(
                f"Pinned provider-version enumeration is not supported for "
                f"{namespace}/{name}@{version!r}; only 'latest' is resolved."
            )
        version_id = await _resolve_provider_version(namespace, name, config, budget)

        docs_url: str | None = (
            f"https://{REGISTRY_HOST}/v2/provider-versions/"
            f"{quote(version_id, safe='')}?include=provider-docs"
        )
        # Tracks every pagination URL already fetched (I2 defense-in-depth):
        # a cyclic links.next (same-host, so the I5 off-host check alone
        # cannot catch it) would otherwise loop until the global
        # MAX_FETCH_ATTEMPTS budget exhausts -- potentially a long time
        # against a fast-responding malicious or buggy server. A repeat stops
        # pagination immediately, the same graceful-stop shape as an
        # off-host links.next.
        seen_docs_urls: set[str] = set()
        first_page = True
        while docs_url is not None:
            if docs_url in seen_docs_urls:
                docs_url = None
                continue
            seen_docs_urls.add(docs_url)
            try:
                response = await fetch_page(
                    docs_url,
                    timeout_seconds=config.page_timeout_seconds,
                    max_redirects=_API_MAX_REDIRECTS,
                    budget=budget,
                )
            except (AggregateBudgetExceededError, CrawlUrlRejectedError):
                # I4 carve-out: never wrapped into TfRegistryAdapterError.
                raise
            except Exception as err:
                raise TfRegistryAdapterError(
                    f"Failed to enumerate provider docs for {namespace}/{name}: {err}"
                ) from err
            _assert_response_on_registry_host(
                response, f"Provider-docs page for {namespace}/{name}"
            )

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
                if not _is_safe_path_segment(category) or not _is_safe_path_segment(slug):
                    # Hostile or malformed entry (e.g. a path-traversal slug,
                    # or a bare "." / ".." segment): skipped, never aborts the
                    # rest of the enumeration (I6).
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
            if not _is_registry_origin(next_url):
                # I5: an off-origin links.next (off-host, non-HTTPS, or a
                # non-standard port) stops pagination without ever fetching
                # it -- a graceful stop preserving every already-yielded
                # valid item from earlier pages, not a fail-open trigger.
                docs_url = None
                continue
            docs_url = next_url


__all__ = ["REGISTRY_HOST", "TfRegistryAdapterError", "TfRegistrySource"]
