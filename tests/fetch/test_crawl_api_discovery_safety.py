"""Harness for 070.009-T (T5s) — discovery-seam security + degradation contract.

Test-first: none of these tests exercise anything crawl() currently does,
since the discovery seam is not yet wired at crawl()'s composition point
(070.010-T / T6). Every test in this file is expected to fail until that task
lands. Covers, at the full ``crawl()`` composition level (not just the
adapter or the seam in isolation, both already covered by their own dedicated
harnesses):

* AC(a): a discovery-sourced URL resolving to a private/loopback address is
  refused at connect time by the real, hardened ``fetch_page`` transport, and
  the rejection propagates uncaught out of ``crawl()``.
* AC(b): an off-host ``links.next`` (driven through the real
  :class:`~docline.fetch.tf_registry_source.TfRegistrySource` + its recorded
  fixtures) is never fetched end-to-end, and an off-host redirect surfacing
  as a policy rejection during an API GET propagates uncaught.
* AC(c): even a hypothetically buggy discovery source yielding an off-host URL
  is refused by ``crawl()``'s own domain-lock filter — the same filter static
  links go through, applied uniformly regardless of a URL's origin.
* AC(d): a generic adapter failure degrades to static-extraction fallback (the
  crawl still completes, logged exactly once), while a budget/SSRF error
  raised mid-discovery is never masked at either the adapter or the
  crawl-composition layer — it propagates unwrapped.
* AC(e): ``enable_api_discovery=False`` on an otherwise-recognized host yields
  results indistinguishable from a crawl with no discovery source registered
  at all — proven via two full ``crawl()`` runs, not a narrow unit assertion.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from docline.fetch import link_sources
from docline.fetch.crawl import CrawlConfig, crawl
from docline.fetch.http import (
    AggregateBudgetExceededError,
    FetchResponse,
    RemainingByteBudget,
)
from docline.fetch.http import fetch_page as real_fetch_page
from docline.fetch.tf_registry_source import TfRegistrySource
from docline.fetch.url_policy import CrawlUrlRejectedError, is_unsafe_resolved_address
from docline.schema.models import DoclineError

_HOST = "fake-registry.example.com"
_START_URL = f"https://{_HOST}/providers/x/y/latest/docs"

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "tf_registry"


def _fixture(name: str) -> str:
    return (_FIXTURE_DIR / name).read_text(encoding="utf-8")


def _json_response(body_text: str, content_type: str = "application/json") -> FetchResponse:
    return FetchResponse(url="", status=200, content_type=content_type, body=body_text)


class _FakeDiscoverySource:
    """A minimal :class:`~docline.fetch.link_sources.DiscoverySource` test double."""

    def __init__(self, urls: list[str]) -> None:
        self._urls = urls
        self.pulled: list[str] = []

    def recognizes(self, start_url: str) -> bool:
        return start_url == _START_URL

    async def discover_doc_urls(
        self, start_url: str, config: CrawlConfig, budget: RemainingByteBudget | None
    ) -> AsyncIterator[str]:
        del start_url, config, budget
        for url in self._urls:
            self.pulled.append(url)
            yield url


class _FailingDiscoverySource:
    """Recognizes the start URL but raises *error* on first enumeration pull."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def recognizes(self, start_url: str) -> bool:
        return start_url == _START_URL

    async def discover_doc_urls(
        self, start_url: str, config: CrawlConfig, budget: RemainingByteBudget | None
    ) -> AsyncIterator[str]:
        del start_url, config, budget
        raise self._error
        yield  # pragma: no cover -- unreachable; keeps this an async generator


@pytest.fixture(autouse=True)
def _reset_discovery_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level discovery-source registry around every test."""
    monkeypatch.setattr(link_sources, "_sources", [], raising=False)


def _html(url: str, body: str) -> FetchResponse:
    return FetchResponse(url=url, status=200, content_type="text/html", body=body)


def _install_fetch(
    monkeypatch: pytest.MonkeyPatch,
    pages: dict[str, FetchResponse],
    requested: list[str],
) -> None:
    """Monkeypatch ``crawl.fetch_page`` with a synthetic in-memory site."""

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
        budget: RemainingByteBudget | None = None,
        **_kwargs: object,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        assert budget is not None, "crawl() must thread the request-scoped budget through"
        budget.debit_attempt()
        requested.append(url)
        if url in pages:
            return pages[url]
        return _html(url, "<html><body><h1>leaf</h1></body></html>")

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)


def _discovered_urls(count: int) -> list[str]:
    return [f"https://{_HOST}/providers/x/y/latest/docs/item-{i}" for i in range(count)]


# ---------------------------------------------------------------------------
# AC(a): private/loopback enumerated URL rejected at connect time
# ---------------------------------------------------------------------------


def test_private_loopback_discovery_url_rejected_at_fetch_via_real_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A discovery-sourced loopback URL is refused by the real, hardened
    ``fetch_page`` transport, and the rejection propagates uncaught out of
    ``crawl()`` -- the same fail-closed guarantee already applied uniformly to
    any admitted URL, regardless of whether it came from static extraction or
    the discovery seam.
    """
    assert is_unsafe_resolved_address("127.0.0.1") is True

    malicious_url = "http://127.0.0.1/private-target"
    source = _FakeDiscoverySource([malicious_url])
    link_sources.register(source)

    requested: list[str] = []

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
        budget: RemainingByteBudget | None = None,
        **_kwargs: object,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        requested.append(url)
        if url == _START_URL:
            return _html(_START_URL, "<html><body>shell</body></html>")
        # Anything else (the malicious discovered URL) goes through the REAL
        # transport so its own connect-time SSRF validation applies -- no
        # network I/O actually occurs since a literal loopback IP is rejected
        # synchronously in validate_crawl_url before any socket is opened.
        return await real_fetch_page(url, budget=budget)

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(crawl(_START_URL, CrawlConfig(max_pages=50, max_frontier=50)))


# ---------------------------------------------------------------------------
# AC(b): off-host links.next / off-host redirect on an API GET refused
# ---------------------------------------------------------------------------


def test_off_host_links_next_via_real_adapter_never_fetched_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real TfRegistrySource + recorded fixtures, driven through the full
    crawl() composition: an off-host links.next must never be fetched.
    """
    link_sources.register(TfRegistrySource())

    tf_start_url = "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs"
    lookup_url = (
        "https://registry.terraform.io/v2/providers/hashicorp/azurerm?include=provider-versions"
    )
    docs_page1_url = (
        "https://registry.terraform.io/v2/provider-versions/107778?include=provider-docs"
    )
    offhost_next_url = (
        "https://evil.example.com/v2/provider-versions/107778/provider-docs?page%5Bnumber%5D=2"
    )

    adapter_requested: list[str] = []

    async def fake_adapter_fetch(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
        budget: RemainingByteBudget | None = None,
        **_kwargs: object,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects, budget
        adapter_requested.append(url)
        if url == lookup_url:
            return _json_response(_fixture("provider_lookup.json"))
        if url == docs_page1_url:
            return _json_response(_fixture("provider_docs_offhost_next.json"))
        raise AssertionError(f"unexpected adapter fetch: {url!r}")

    monkeypatch.setattr("docline.fetch.tf_registry_source.fetch_page", fake_adapter_fetch)

    crawl_requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {tf_start_url: _html(tf_start_url, "<html><body>shell</body></html>")},
        crawl_requested,
    )

    outcome = asyncio.run(crawl(tf_start_url, CrawlConfig(max_pages=50, max_frontier=50)))

    fetched = {result.url for result in outcome.results if not result.skipped}
    assert fetched == {
        tf_start_url,
        "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs"
        "/resources/resource_group",
    }
    assert offhost_next_url not in adapter_requested
    assert offhost_next_url not in crawl_requested


def test_off_host_redirect_during_api_get_propagates_uncaught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An SSRF rejection raised mid-discovery (e.g. a redirect resolving off-host)
    propagates uncaught out of crawl() -- the I4 carve-out held at the
    crawl-composition layer too, not just inside the adapter's own function
    (already proven separately in test_tf_registry_source.py).
    """
    link_sources.register(TfRegistrySource())

    tf_start_url = "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs"

    async def fake_adapter_fetch(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
        budget: RemainingByteBudget | None = None,
        **_kwargs: object,
    ) -> FetchResponse:
        del url, timeout_seconds, max_redirects, budget
        raise CrawlUrlRejectedError("redirect target rejected: off-host")

    monkeypatch.setattr("docline.fetch.tf_registry_source.fetch_page", fake_adapter_fetch)

    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {tf_start_url: _html(tf_start_url, "<html><body>shell</body></html>")},
        requested,
    )

    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(crawl(tf_start_url, CrawlConfig(max_pages=50, max_frontier=50)))


# ---------------------------------------------------------------------------
# AC(c): defense-in-depth -- crawl()'s own domain-lock filter refuses an
# off-host discovery URL uniformly, regardless of adapter behavior
# ---------------------------------------------------------------------------


def test_off_host_discovery_url_never_admitted_defense_in_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even a hypothetically buggy discovery source yielding an off-host URL is
    refused by crawl()'s own domain-lock filter -- the same filter static links
    go through, applied uniformly to discovery-sourced URLs too. No exception:
    an out-of-scope candidate is silently never admitted, exactly like an
    out-of-scope static anchor.

    Mixes in one legitimate in-scope discovered URL alongside the off-host one
    so this test cannot pass vacuously before the discovery seam is wired: the
    in-scope URL asserts discovery genuinely ran, while the off-host one
    proves the domain-lock filter still refused it.
    """
    off_host_url = "https://evil.example.com/stolen-page"
    in_scope_url = f"https://{_HOST}/providers/x/y/latest/docs/legit-page"
    source = _FakeDiscoverySource([off_host_url, in_scope_url])
    link_sources.register(source)

    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {_START_URL: _html(_START_URL, "<html><body>shell</body></html>")},
        requested,
    )

    outcome = asyncio.run(crawl(_START_URL, CrawlConfig(max_pages=50, max_frontier=50)))

    assert off_host_url not in requested
    fetched = {result.url for result in outcome.results if not result.skipped}
    assert fetched == {_START_URL, in_scope_url}, (
        "the in-scope discovered URL must still be fetched -- proving discovery "
        "genuinely ran and only the off-host candidate was filtered"
    )


# ---------------------------------------------------------------------------
# AC(d): adapter failure -> static fallback (logged once); budget/SSRF errors
# propagate unwrapped through the crawl-composition layer
# ---------------------------------------------------------------------------


def test_adapter_failure_falls_back_to_static_extraction_logged_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A generic adapter failure degrades to static-extraction fallback: the
    crawl still completes (fetching the start page's own static anchors), and
    the failure is logged exactly once under the crawl loop's logger.
    """
    static_target = f"https://{_HOST}/docs/static-only-page"
    source = _FailingDiscoverySource(DoclineError("adapter exploded"))
    link_sources.register(source)

    requested: list[str] = []
    start_body = f'<html><body><a href="{static_target}">static</a></body></html>'
    _install_fetch(monkeypatch, {_START_URL: _html(_START_URL, start_body)}, requested)

    with caplog.at_level(logging.WARNING, logger="docline.fetch.crawl"):
        outcome = asyncio.run(
            crawl(_START_URL, CrawlConfig(max_pages=50, max_frontier=50, max_depth=1))
        )

    fetched = {result.url for result in outcome.results if not result.skipped}
    assert fetched == {_START_URL, static_target}, (
        "static extraction must still complete the crawl after an adapter failure"
    )

    fallback_records = [
        record
        for record in caplog.records
        if record.name == "docline.fetch.crawl" and "falling back to static" in record.getMessage()
    ]
    assert len(fallback_records) == 1, "the adapter failure must be logged exactly once"


def test_budget_error_during_discovery_propagates_unwrapped_through_crawl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A budget error raised mid-discovery is never masked as a generic adapter
    failure -- it propagates unwrapped all the way out of crawl().
    """
    source = _FailingDiscoverySource(AggregateBudgetExceededError("budget exhausted"))
    link_sources.register(source)

    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {_START_URL: _html(_START_URL, "<html><body>shell</body></html>")},
        requested,
    )

    with pytest.raises(AggregateBudgetExceededError):
        asyncio.run(crawl(_START_URL, CrawlConfig(max_pages=50, max_frontier=50)))


def test_ssrf_error_during_discovery_propagates_unwrapped_through_crawl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An SSRF rejection raised mid-discovery is never masked as a generic
    adapter failure -- it propagates unwrapped all the way out of crawl().
    """
    source = _FailingDiscoverySource(CrawlUrlRejectedError("host rejected"))
    link_sources.register(source)

    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {_START_URL: _html(_START_URL, "<html><body>shell</body></html>")},
        requested,
    )

    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(crawl(_START_URL, CrawlConfig(max_pages=50, max_frontier=50)))


# ---------------------------------------------------------------------------
# AC(e): enable_api_discovery=False yields byte-identical legacy behavior
# ---------------------------------------------------------------------------


def test_enable_api_discovery_false_yields_legacy_static_only_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``enable_api_discovery=False`` on a recognized host is indistinguishable
    from a crawl with no discovery source registered at all -- proven via full
    crawl() runs, not a narrow unit assertion on the config field.

    Includes an explicit ``enable_api_discovery=True`` contrast run first: this
    is what makes the test genuinely red before 070.010-T wires the seam (an
    always-vacuously-true "nothing extra happened" assertion would pass both
    before and after implementation and prove nothing).
    """
    static_target = f"https://{_HOST}/docs/static-only-page"
    start_body = f'<html><body><a href="{static_target}">static</a></body></html>'

    # Contrast run: discovery ENABLED with a source registered must actually
    # pick up the discovered URLs.
    discovered = _discovered_urls(3)
    source_enabled = _FakeDiscoverySource(discovered)
    link_sources.register(source_enabled)
    requested_enabled: list[str] = []
    _install_fetch(monkeypatch, {_START_URL: _html(_START_URL, start_body)}, requested_enabled)
    outcome_enabled = asyncio.run(
        crawl(
            _START_URL,
            CrawlConfig(max_pages=50, max_frontier=50, max_depth=1, enable_api_discovery=True),
        )
    )
    assert source_enabled.pulled != [], "discovery must actually run when enabled"
    fetched_enabled = {result.url for result in outcome_enabled.results if not result.skipped}
    assert fetched_enabled == {_START_URL, static_target, *discovered}

    monkeypatch.setattr(link_sources, "_sources", [], raising=False)
    source_disabled = _FakeDiscoverySource(_discovered_urls(3))
    link_sources.register(source_disabled)

    requested_disabled: list[str] = []
    _install_fetch(monkeypatch, {_START_URL: _html(_START_URL, start_body)}, requested_disabled)
    outcome_disabled = asyncio.run(
        crawl(
            _START_URL,
            CrawlConfig(max_pages=50, max_frontier=50, max_depth=1, enable_api_discovery=False),
        )
    )

    assert source_disabled.pulled == [], "a disabled discovery source must never be driven at all"
    fetched_disabled = {result.url for result in outcome_disabled.results if not result.skipped}
    assert fetched_disabled == {_START_URL, static_target}

    # Legacy baseline: no discovery source registered at all, flag left at its
    # (enabled) default -- must be indistinguishable from the disabled run.
    monkeypatch.setattr(link_sources, "_sources", [], raising=False)
    requested_legacy: list[str] = []
    _install_fetch(monkeypatch, {_START_URL: _html(_START_URL, start_body)}, requested_legacy)
    outcome_legacy = asyncio.run(
        crawl(_START_URL, CrawlConfig(max_pages=50, max_frontier=50, max_depth=1))
    )

    assert outcome_disabled.results == outcome_legacy.results
    assert outcome_disabled.frontier_truncated == outcome_legacy.frontier_truncated
