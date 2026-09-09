"""Harness for 070.004-T (T3) — Terraform Registry adapter enumeration contract.

This is the test-first harness for the **entire** Terraform Registry adapter:
recognizer + version resolution (070.005-T / T4a) and paged provider-docs
enumeration (070.006-T / T4b) both consume these tests rather than getting
separate test-writing tasks, per the plan. Recorded, trimmed v2 JSON:API
fixtures live in ``tests/fetch/fixtures/tf_registry/``:

* ``provider_lookup.json`` — ``GET /v2/providers/{ns}/{name}?include=provider-versions``,
  resolving the latest provider-version id by comparing every included
  version's ``published-at`` timestamp (the real API exposes
  ``provider-versions`` as a plain list of every published version, with no
  singular "latest" relationship or flag -- verified live against the real
  API; two entries with distinct timestamps let the fixture assert the
  correct one, not merely the first or last, is chosen).
* ``provider_docs_page1.json`` — ``GET /v2/provider-versions/{id}?include=provider-docs``,
  3 entries (2 ``resources`` + 1 ``data-sources``) plus a same-host ``links.next``.
* ``provider_docs_page2.json`` — the paginated continuation (a plain
  ``provider-docs`` collection response), 2 valid entries (``guides`` +
  ``data-sources``) plus **one hostile-slug entry** (``../../etc``) that must
  be skipped, not aborted on.
* ``provider_docs_offhost_next.json`` — a page-1-shaped response whose
  ``links.next`` points **off-host**, used to assert pagination aborts
  without ever fetching it.

Every fetch is asserted to flow through the mocked
``docline.fetch.tf_registry_source.fetch_page`` seam (never a raw HTTP
client), mirroring the pattern used throughout ``tests/fetch/``.

Red before 070.005-T/070.006-T: :class:`TfRegistrySource`'s methods raise
``NotImplementedError``. No production code changed in this task.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.error import HTTPError

import pytest

from docline.fetch.crawl_models import CrawlConfig
from docline.fetch.http import AggregateBudgetExceededError, FetchResponse
from docline.fetch.tf_registry_source import TfRegistryAdapterError, TfRegistrySource
from docline.fetch.url_policy import CrawlUrlRejectedError, validate_crawl_url

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "tf_registry"

_START_URL = "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs"
_LOOKUP_URL = (
    "https://registry.terraform.io/v2/providers/hashicorp/azurerm?include=provider-versions"
)
_DOCS_PAGE1_URL = "https://registry.terraform.io/v2/provider-versions/107778?include=provider-docs"
_DOCS_PAGE2_URL = (
    "https://registry.terraform.io/v2/provider-versions/107778/provider-docs?page%5Bnumber%5D=2"
)
_OFFHOST_NEXT_URL = (
    "https://evil.example.com/v2/provider-versions/107778/provider-docs?page%5Bnumber%5D=2"
)

_EXPECTED_URLS = frozenset(
    {
        "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/resource_group",
        "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/virtual_network",
        "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/resource_group",
        "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/azurerm_provider_guide",
        "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/virtual_network",
    }
)


def _fixture(name: str) -> str:
    return (_FIXTURE_DIR / name).read_text(encoding="utf-8")


def _json_response(
    body_text: str, content_type: str = "application/json", url: str = ""
) -> FetchResponse:
    return FetchResponse(url=url, status=200, content_type=content_type, body=body_text)


def _install_fetch(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, FetchResponse | Exception],
    requested: list[str],
) -> None:
    """Monkeypatch ``tf_registry_source.fetch_page`` with a canned response table."""

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
        budget: object = None,
        **_kwargs: object,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        requested.append(url)
        result = responses.get(url)
        if result is None:
            raise AssertionError(f"unexpected fetch_page call for {url!r}")
        if isinstance(result, Exception):
            raise result
        if not result.url:
            # Real fetch_page always populates the final (post-redirect) URL;
            # canned test fixtures built via _json_response() leave it blank,
            # so backfill it here to keep the host-confinement check (I5)
            # exercising real same-host responses rather than an empty string.
            result = dataclasses.replace(result, url=url)
        return result

    monkeypatch.setattr("docline.fetch.tf_registry_source.fetch_page", fake_fetch_page)


async def _collect(iterator: AsyncIterator[str]) -> list[str]:
    return [item async for item in iterator]


async def _collect_up_to(iterator: AsyncIterator[str], limit: int) -> list[str]:
    collected: list[str] = []
    async for item in iterator:
        collected.append(item)
        if len(collected) >= limit:
            break
    return collected


def _happy_path_responses() -> dict[str, FetchResponse | Exception]:
    return {
        _LOOKUP_URL: _json_response(_fixture("provider_lookup.json")),
        _DOCS_PAGE1_URL: _json_response(_fixture("provider_docs_page1.json")),
        _DOCS_PAGE2_URL: _json_response(_fixture("provider_docs_page2.json")),
    }


# ---------------------------------------------------------------------------
# Recognizer (T4a)
# ---------------------------------------------------------------------------


def test_recognizes_valid_provider_docs_url() -> None:
    source = TfRegistrySource()
    assert source.recognizes(_START_URL) is True
    assert (
        source.recognizes("https://registry.terraform.io/providers/hashicorp/azurerm/4.1.0/docs")
        is True
    )


def test_recognizes_rejects_non_tf_url() -> None:
    source = TfRegistrySource()
    assert source.recognizes("https://example.com/docs") is False


def test_recognizes_rejects_off_host_url() -> None:
    source = TfRegistrySource()
    assert (
        source.recognizes("https://evil.example.com/providers/hashicorp/azurerm/latest/docs")
        is False
    )


def test_recognizes_rejects_bad_char_namespace() -> None:
    """A namespace with a disallowed character fails recognition; no API call."""
    source = TfRegistrySource()
    assert (
        source.recognizes("https://registry.terraform.io/providers/hashi;corp/azurerm/latest/docs")
        is False
    )


def test_recognizes_rejects_bad_char_name() -> None:
    """A name with a disallowed character fails recognition (path shape is otherwise valid)."""
    source = TfRegistrySource()
    assert (
        source.recognizes("https://registry.terraform.io/providers/hashicorp/azure;rm/latest/docs")
        is False
    )


def test_recognizes_rejects_bare_relative_segment_in_name() -> None:
    """A bare '.' or '..' namespace/name segment fails recognition (P2 security
    fix): both match the plain charset allowlist but are reserved
    relative-path segments that must never reach path construction."""
    source = TfRegistrySource()
    assert (
        source.recognizes("https://registry.terraform.io/providers/hashicorp/../latest/docs")
        is False
    )
    assert (
        source.recognizes("https://registry.terraform.io/providers/../azurerm/latest/docs") is False
    )


def test_recognizes_rejects_non_standard_port() -> None:
    """A start URL on a non-standard port fails recognition even though scheme
    and hostname both match -- the recognizer must enforce the same origin
    invariant (_is_registry_origin) as pagination/response-URL confinement,
    not merely a scheme+hostname subset of it (Copilot review finding)."""
    source = TfRegistrySource()
    assert (
        source.recognizes(
            "https://registry.terraform.io:8443/providers/hashicorp/azurerm/latest/docs"
        )
        is False
    )


def test_recognizes_rejects_malformed_port_without_raising() -> None:
    """A syntactically malformed port fails recognition and never raises --
    ParseResult.port raises ValueError for a non-numeric port, which
    _is_registry_origin must catch rather than let escape."""
    source = TfRegistrySource()
    assert (
        source.recognizes(
            "https://registry.terraform.io:notaport/providers/hashicorp/azurerm/latest/docs"
        )
        is False
    )


# ---------------------------------------------------------------------------
# Path-segment safety helper (I6, P2 security fix)
# ---------------------------------------------------------------------------


def test_is_safe_path_segment_rejects_bare_relative_segments() -> None:
    """``_is_safe_path_segment`` rejects the reserved '.'/'..' segments even
    though both match the plain charset allowlist -- the gap a category/slug
    or version id from an attacker-influenced JSON:API response could
    otherwise exploit to smuggle a literal './'/'../' into a constructed URL.
    """
    from docline.fetch.tf_registry_source import _is_safe_path_segment

    assert _is_safe_path_segment("resources") is True
    assert _is_safe_path_segment("azurerm_provider_guide") is True
    assert _is_safe_path_segment(".") is False
    assert _is_safe_path_segment("..") is False
    assert _is_safe_path_segment("../../etc") is False
    assert _is_safe_path_segment("a;b") is False


def test_is_registry_origin_rejects_malformed_port_without_raising() -> None:
    """``_is_registry_origin`` never raises for a syntactically malformed
    port -- ``ParseResult.port`` raises ``ValueError`` for a non-numeric or
    out-of-range port, and *url* may be attacker-influenced remote JSON (a
    ``links.next`` value), so this must fail closed (return False) rather
    than let a raw parse error escape an async generator and abort the crawl
    (Copilot review finding).
    """
    from docline.fetch.tf_registry_source import _is_registry_origin

    assert _is_registry_origin("https://registry.terraform.io/v2/providers") is True
    assert _is_registry_origin("https://registry.terraform.io:443/v2/providers") is True
    assert _is_registry_origin("https://registry.terraform.io:8443/v2/providers") is False
    assert _is_registry_origin("http://registry.terraform.io/v2/providers") is False
    assert _is_registry_origin("https://registry.terraform.io:notaport/v2/providers") is False
    assert _is_registry_origin("https://registry.terraform.io:99999999/v2/providers") is False


# ---------------------------------------------------------------------------
# Redirect confinement (Copilot review finding): every adapter fetch forbids
# redirects outright, rather than relying solely on a post-hoc final-URL check
# ---------------------------------------------------------------------------


def test_every_adapter_fetch_forbids_redirects_regardless_of_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every fetch_page call the adapter makes passes max_redirects=0, even when
    the crawl config's own max_redirects is nonzero -- closing the window
    where a same-host request could still be redirected off-host by a
    compromised or misconfigured endpoint before any final-URL check runs.
    """
    captured_max_redirects: list[int] = []

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
        budget: object = None,
        **_kwargs: object,
    ) -> FetchResponse:
        del timeout_seconds, budget
        captured_max_redirects.append(max_redirects)
        if url == _LOOKUP_URL:
            return _json_response(_fixture("provider_lookup.json"), url=url)
        if url == _DOCS_PAGE1_URL:
            return _json_response(_fixture("provider_docs_page1.json"), url=url)
        if url == _DOCS_PAGE2_URL:
            return _json_response(_fixture("provider_docs_page2.json"), url=url)
        raise AssertionError(f"unexpected fetch_page call for {url!r}")

    monkeypatch.setattr("docline.fetch.tf_registry_source.fetch_page", fake_fetch_page)
    source = TfRegistrySource()

    # A crawl config with a nonzero max_redirects must not leak through.
    import asyncio

    urls = asyncio.run(
        _collect(source.discover_doc_urls(_START_URL, CrawlConfig(max_redirects=5), None))
    )

    assert len(urls) == len(_EXPECTED_URLS)
    assert captured_max_redirects, "at least one fetch must have occurred"
    assert all(value == 0 for value in captured_max_redirects), (
        "every adapter fetch must forbid redirects (max_redirects=0) "
        "regardless of the crawl config's own max_redirects"
    )


# ---------------------------------------------------------------------------
# Cyclic pagination (Copilot review finding): a repeated links.next must stop
# pagination rather than looping until the global attempt budget exhausts
# ---------------------------------------------------------------------------


def test_discover_doc_urls_stops_on_cyclic_links_next(monkeypatch: pytest.MonkeyPatch) -> None:
    """A links.next that points back to an already-fetched pagination URL stops
    pagination immediately instead of looping indefinitely.
    """
    requested: list[str] = []
    cyclic_page1 = json.dumps(
        {
            "data": {
                "type": "provider-versions",
                "id": "107778",
                "attributes": {"version": "4.1.0"},
                "relationships": {
                    "provider-docs": {
                        "data": [{"type": "provider-docs", "id": "d1"}],
                        "links": {"next": _DOCS_PAGE1_URL},
                    }
                },
            },
            "included": [
                {
                    "type": "provider-docs",
                    "id": "d1",
                    "attributes": {"category": "resources", "slug": "resource_group"},
                }
            ],
        }
    )
    _install_fetch(
        monkeypatch,
        {
            _LOOKUP_URL: _json_response(_fixture("provider_lookup.json")),
            _DOCS_PAGE1_URL: _json_response(cyclic_page1),
        },
        requested,
    )
    source = TfRegistrySource()

    urls = asyncio_run_collect(source, _START_URL)

    assert urls == [
        "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/resource_group"
    ]
    assert requested.count(_DOCS_PAGE1_URL) == 1, (
        "a links.next cycle back to an already-fetched pagination URL must "
        "stop pagination on first repeat, never re-fetch it"
    )


# ---------------------------------------------------------------------------
# Pinned-version recognition vs. enumeration (P1 fix)
# ---------------------------------------------------------------------------


def test_discover_doc_urls_fails_closed_for_pinned_version() -> None:
    """A recognized pinned-version URL fails closed, never silently substituting
    the current latest version's docs.

    ``recognizes()`` accepts a pinned version (per the plan's recognizer
    pattern), but only ``"latest"`` is actually resolved and enumerated:
    enumeration for any other version raises explicitly so the
    crawl-composition layer's existing adapter-failure fallback degrades to
    static-only extraction, rather than the adapter quietly linking to the
    wrong version's documents.
    """
    pinned_url = "https://registry.terraform.io/providers/hashicorp/azurerm/4.1.0/docs"
    source = TfRegistrySource()
    assert source.recognizes(pinned_url) is True, "a pinned version is still recognized"

    with pytest.raises(TfRegistryAdapterError):
        asyncio_run_collect(source, pinned_url)


# ---------------------------------------------------------------------------
# Version resolution error handling (T4a)
# ---------------------------------------------------------------------------


def test_version_resolution_non_200_raises_adapter_error(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {_LOOKUP_URL: HTTPError(_LOOKUP_URL, 404, "Not Found", None, None)},
        requested,
    )
    source = TfRegistrySource()

    with pytest.raises(TfRegistryAdapterError):
        asyncio_run_collect(source, _START_URL)


def test_version_resolution_json_decode_failure_raises_adapter_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[str] = []
    _install_fetch(monkeypatch, {_LOOKUP_URL: _json_response("not json at all")}, requested)
    source = TfRegistrySource()

    with pytest.raises(TfRegistryAdapterError):
        asyncio_run_collect(source, _START_URL)


def test_version_resolution_non_json_content_type_raises_adapter_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {_LOOKUP_URL: _json_response("<html>not json</html>", content_type="text/html")},
        requested,
    )
    source = TfRegistrySource()

    with pytest.raises(TfRegistryAdapterError):
        asyncio_run_collect(source, _START_URL)


def test_version_resolution_schema_drift_raises_adapter_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A response missing the ``included`` provider-versions set is schema drift."""
    requested: list[str] = []
    drifted = json.dumps({"data": {"type": "providers", "id": "1440", "attributes": {}}})
    _install_fetch(monkeypatch, {_LOOKUP_URL: _json_response(drifted)}, requested)
    source = TfRegistrySource()

    with pytest.raises(TfRegistryAdapterError):
        asyncio_run_collect(source, _START_URL)


def test_version_resolution_picks_max_published_at_not_first_or_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The latest version is the one with the maximum published-at timestamp,
    not merely whichever entry happens to appear first or last in the
    included array -- the real API's provider-versions relationship is an
    unordered list with no explicit 'latest' flag.
    """
    requested: list[str] = []
    payload = json.dumps(
        {
            "data": {
                "type": "providers",
                "id": "1440",
                "attributes": {"namespace": "hashicorp", "name": "azurerm"},
                "relationships": {
                    "provider-versions": {
                        "data": [
                            {"type": "provider-versions", "id": "999999"},
                            {"type": "provider-versions", "id": "1"},
                            {"type": "provider-versions", "id": "42"},
                        ]
                    }
                },
            },
            "included": [
                # Listed out of both id-order and chronological order.
                {
                    "type": "provider-versions",
                    "id": "999999",
                    "attributes": {"version": "1.0.0", "published-at": "2020-01-01T00:00:00Z"},
                },
                {
                    "type": "provider-versions",
                    "id": "42",
                    "attributes": {"version": "9.9.9", "published-at": "2026-06-01T00:00:00Z"},
                },
                {
                    "type": "provider-versions",
                    "id": "1",
                    "attributes": {"version": "2.0.0", "published-at": "2022-03-01T00:00:00Z"},
                },
            ],
        }
    )
    docs_page_url = "https://registry.terraform.io/v2/provider-versions/42?include=provider-docs"
    _install_fetch(
        monkeypatch,
        {
            _LOOKUP_URL: _json_response(payload),
            docs_page_url: _json_response(_fixture("provider_docs_page1.json")),
            _DOCS_PAGE2_URL: _json_response(_fixture("provider_docs_page2.json")),
        },
        requested,
    )
    source = TfRegistrySource()

    asyncio_run_collect(source, _START_URL)

    assert docs_page_url in requested, (
        "id '42' has the maximum published-at (2026-06-01) despite being "
        "neither the numerically largest id (999999) nor the first/last "
        "included entry -- it must be the one resolved and fetched"
    )


def test_version_resolution_budget_error_propagates_unwrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The I4 carve-out: a budget error is never wrapped into TfRegistryAdapterError."""
    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {_LOOKUP_URL: AggregateBudgetExceededError("budget exhausted")},
        requested,
    )
    source = TfRegistrySource()

    with pytest.raises(AggregateBudgetExceededError):
        asyncio_run_collect(source, _START_URL)


def test_version_resolution_ssrf_error_propagates_unwrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The I4 carve-out: an SSRF rejection is never wrapped into TfRegistryAdapterError."""
    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {_LOOKUP_URL: CrawlUrlRejectedError("host rejected")},
        requested,
    )
    source = TfRegistrySource()

    with pytest.raises(CrawlUrlRejectedError):
        asyncio_run_collect(source, _START_URL)


# ---------------------------------------------------------------------------
# Paged enumeration (T4b)
# ---------------------------------------------------------------------------


def test_discover_doc_urls_yields_expected_url_set_across_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact expected URL set is yielded across both pages; hostile slug skipped."""
    requested: list[str] = []
    _install_fetch(monkeypatch, _happy_path_responses(), requested)
    source = TfRegistrySource()

    urls = asyncio_run_collect(source, _START_URL)

    assert set(urls) == _EXPECTED_URLS
    assert len(urls) == len(_EXPECTED_URLS), "no duplicate or hostile-slug URL may be yielded"
    for url in urls:
        assert validate_crawl_url(url) == url
        assert url.startswith("https://registry.terraform.io/"), (
            "every yielded URL must be host-confined to the recognized origin"
        )
    assert _DOCS_PAGE2_URL in requested, "pagination must follow links.next for the full set"


def test_discover_doc_urls_off_host_next_aborts_pagination_without_fetching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An off-host ``links.next`` stops pagination without ever fetching it."""
    requested: list[str] = []
    responses: dict[str, FetchResponse | Exception] = {
        _LOOKUP_URL: _json_response(_fixture("provider_lookup.json")),
        _DOCS_PAGE1_URL: _json_response(_fixture("provider_docs_offhost_next.json")),
    }
    _install_fetch(monkeypatch, responses, requested)
    source = TfRegistrySource()

    urls = asyncio_run_collect(source, _START_URL)

    assert urls == [
        "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/resource_group"
    ]
    assert _OFFHOST_NEXT_URL not in requested, (
        "the off-host links.next target must never be fetched"
    )


def test_discover_doc_urls_scheme_downgrade_next_aborts_pagination_without_fetching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A same-host but plain-``http://`` ``links.next`` is treated as
    off-origin: host confinement alone would not catch a cleartext downgrade,
    since fetch_page's own URL policy allows http generically."""
    downgraded_next = (
        "http://registry.terraform.io/v2/provider-versions/107778/provider-docs?page%5Bnumber%5D=2"
    )
    page1 = json.dumps(
        {
            "data": {
                "type": "provider-versions",
                "id": "107778",
                "attributes": {"version": "4.1.0"},
                "relationships": {
                    "provider-docs": {
                        "data": [{"type": "provider-docs", "id": "d1"}],
                        "links": {"next": downgraded_next},
                    }
                },
            },
            "included": [
                {
                    "type": "provider-docs",
                    "id": "d1",
                    "attributes": {"category": "resources", "slug": "resource_group"},
                }
            ],
        }
    )
    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {
            _LOOKUP_URL: _json_response(_fixture("provider_lookup.json")),
            _DOCS_PAGE1_URL: _json_response(page1),
        },
        requested,
    )
    source = TfRegistrySource()

    urls = asyncio_run_collect(source, _START_URL)

    assert urls == [
        "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/resource_group"
    ]
    assert downgraded_next not in requested, (
        "a same-host cleartext-downgraded links.next must never be fetched"
    )


def test_discover_doc_urls_nonstandard_port_next_aborts_pagination_without_fetching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A same-host, HTTPS, but non-standard-port ``links.next`` is treated as
    off-origin, not merely off-host."""
    odd_port_next = (
        "https://registry.terraform.io:8443/v2/provider-versions/107778"
        "/provider-docs?page%5Bnumber%5D=2"
    )
    page1 = json.dumps(
        {
            "data": {
                "type": "provider-versions",
                "id": "107778",
                "attributes": {"version": "4.1.0"},
                "relationships": {
                    "provider-docs": {
                        "data": [{"type": "provider-docs", "id": "d1"}],
                        "links": {"next": odd_port_next},
                    }
                },
            },
            "included": [
                {
                    "type": "provider-docs",
                    "id": "d1",
                    "attributes": {"category": "resources", "slug": "resource_group"},
                }
            ],
        }
    )
    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {
            _LOOKUP_URL: _json_response(_fixture("provider_lookup.json")),
            _DOCS_PAGE1_URL: _json_response(page1),
        },
        requested,
    )
    source = TfRegistrySource()

    urls = asyncio_run_collect(source, _START_URL)

    assert urls == [
        "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/resource_group"
    ]
    assert odd_port_next not in requested, (
        "a same-host, non-standard-port links.next must never be fetched"
    )


def test_discover_doc_urls_enumeration_budget_error_propagates_unwrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A budget error raised mid-enumeration (page 2) propagates unwrapped."""
    requested: list[str] = []
    responses: dict[str, FetchResponse | Exception] = {
        _LOOKUP_URL: _json_response(_fixture("provider_lookup.json")),
        _DOCS_PAGE1_URL: _json_response(_fixture("provider_docs_page1.json")),
        _DOCS_PAGE2_URL: AggregateBudgetExceededError("budget exhausted mid-enumeration"),
    }
    _install_fetch(monkeypatch, responses, requested)
    source = TfRegistrySource()

    with pytest.raises(AggregateBudgetExceededError):
        asyncio_run_collect(source, _START_URL)


def test_discover_doc_urls_stops_pagination_when_consumer_stops_early(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stopping consumption after page 1's 3 items never triggers page 2's fetch."""
    requested: list[str] = []
    _install_fetch(monkeypatch, _happy_path_responses(), requested)
    source = TfRegistrySource()

    import asyncio

    iterator = source.discover_doc_urls(_START_URL, CrawlConfig(), None)
    collected = asyncio.run(_collect_up_to(iterator, 3))

    assert len(collected) == 3
    assert _DOCS_PAGE2_URL not in requested, (
        "consuming only page 1's items must never trigger page 2's fetch (lazy)"
    )


def asyncio_run_collect(source: TfRegistrySource, start_url: str) -> list[str]:
    """Run ``discover_doc_urls`` to completion and return the collected URLs."""
    import asyncio

    return asyncio.run(_collect(source.discover_doc_urls(start_url, CrawlConfig(), None)))
