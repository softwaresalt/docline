"""Harness for 070.004-T (T3) — Terraform Registry adapter enumeration contract.

This is the test-first harness for the **entire** Terraform Registry adapter:
recognizer + version resolution (070.005-T / T4a) and paged provider-docs
enumeration (070.006-T / T4b) both consume these tests rather than getting
separate test-writing tasks, per the plan. Recorded, trimmed v2 JSON:API
fixtures live in ``tests/fetch/fixtures/tf_registry/``:

* ``provider_lookup.json`` — ``GET /v2/providers/{ns}/{name}?include=provider-versions``,
  resolving the latest provider-version id via a ``latest-version`` relationship.
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


def _json_response(body_text: str, content_type: str = "application/json") -> FetchResponse:
    return FetchResponse(url="", status=200, content_type=content_type, body=body_text)


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
    source = TfRegistrySource()
    assert (
        source.recognizes(
            "https://registry.terraform.io/providers/hashicorp/../azurerm/latest/docs"
        )
        is False
    )


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
    """A response missing the ``latest-version`` relationship is schema drift."""
    requested: list[str] = []
    drifted = json.dumps({"data": {"type": "providers", "id": "1440", "attributes": {}}})
    _install_fetch(monkeypatch, {_LOOKUP_URL: _json_response(drifted)}, requested)
    source = TfRegistrySource()

    with pytest.raises(TfRegistryAdapterError):
        asyncio_run_collect(source, _START_URL)


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
