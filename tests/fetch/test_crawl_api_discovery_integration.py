"""Harness for 070.008-T (T5c) — discovery-seam composition point in ``crawl()``.

Test-first: ``crawl()`` does not yet consult
:func:`docline.fetch.link_sources.find_source` at its composition point
(070.010-T / T6 wires it in), so every test in this file is expected to be RED
until that task lands. A minimal fake :class:`~docline.fetch.link_sources.DiscoverySource`
is used here — not the concrete Terraform Registry adapter, which has its own
dedicated harness in ``test_tf_registry_source.py`` — so this file exercises
``crawl()``'s GENERIC composition contract in isolation:

* AC(a): a recognized start URL's discovery-source-yielded URLs are fetched in
  addition to the start page itself, bounded by ``max_pages``/``max_frontier``.
* AC(b): when ``max_frontier`` is smaller than the discovered URL count, the
  result is truncated (``frontier_truncated`` is ``True``) AND the source's
  own async generator is never driven past the admission ceiling — pagination
  stops the instant the frontier is full, never fetching one further page just
  to discard it (mirrors the lazy-early-stop contract already proven for the
  TF adapter itself in ``test_tf_registry_source.py``, one level up).
* AC(c): a recognized host whose start page ALSO carries static HTML anchors
  admits the union of both sources with no double-fetch — a URL yielded by
  discovery AND present as a static anchor is fetched exactly once.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import pytest

from docline.fetch import link_sources
from docline.fetch.crawl import CrawlConfig, crawl
from docline.fetch.http import FetchResponse, RemainingByteBudget

_HOST = "fake-registry.example.com"
_START_URL = f"https://{_HOST}/providers/x/y/latest/docs"


class _FakeDiscoverySource:
    """A minimal :class:`~docline.fetch.link_sources.DiscoverySource` test double.

    Unlike the concrete Terraform Registry adapter, this performs no network
    I/O of its own — it simply yields a canned URL list — so this file can pin
    ``crawl()``'s composition contract without depending on the TF-specific
    JSON:API shape at all.
    """

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


@pytest.fixture(autouse=True)
def _reset_discovery_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level discovery-source registry around every test.

    ``link_sources._sources`` is a shared module-level list; registering a
    fake source for one test must never leak into another test.
    """
    monkeypatch.setattr(link_sources, "_sources", [], raising=False)


def _html(url: str, body: str) -> FetchResponse:
    """Return a synthetic HTML :class:`FetchResponse` for *url*."""
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
# AC(a): full discovery, additive to the start page itself
# ---------------------------------------------------------------------------


def test_recognized_start_url_discovers_and_fetches_every_source_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every URL the discovery source yields is fetched, bounded by max_pages/max_frontier."""
    discovered = _discovered_urls(5)
    source = _FakeDiscoverySource(discovered)
    link_sources.register(source)

    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {_START_URL: _html(_START_URL, "<html><body>shell</body></html>")},
        requested,
    )

    outcome = asyncio.run(
        crawl(_START_URL, CrawlConfig(max_pages=50, max_frontier=50, max_depth=0))
    )

    fetched = {result.url for result in outcome.results if not result.skipped}
    assert fetched == {_START_URL, *discovered}
    assert outcome.frontier_truncated is False


def test_successful_seed_logs_one_info_summary(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A completed discovery-source seed logs one INFO summary (origin + count),
    per the plan's own observability commitment -- a sanitized origin only,
    never a raw discovered URL.
    """
    discovered = _discovered_urls(3)
    source = _FakeDiscoverySource(discovered)
    link_sources.register(source)

    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {_START_URL: _html(_START_URL, "<html><body>shell</body></html>")},
        requested,
    )

    with caplog.at_level(logging.INFO, logger="docline.fetch.crawl"):
        asyncio.run(crawl(_START_URL, CrawlConfig(max_pages=50, max_frontier=50, max_depth=0)))

    info_records = [
        record
        for record in caplog.records
        if record.name == "docline.fetch.crawl" and record.levelname == "INFO"
    ]
    assert len(info_records) == 1, "a completed seed must log exactly one INFO summary"
    message = info_records[0].getMessage()
    assert "3" in message
    for url in discovered:
        assert url not in message, "the seed summary must never embed a raw discovered URL"


# ---------------------------------------------------------------------------
# AC(b): cap-truncation stops both admission AND the source's own pagination
# ---------------------------------------------------------------------------


def test_max_frontier_below_discovery_count_truncates_and_stops_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tight max_frontier truncates and the source is never pulled past the cap."""
    discovered = _discovered_urls(5)
    source = _FakeDiscoverySource(discovered)
    link_sources.register(source)

    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {_START_URL: _html(_START_URL, "<html><body>shell</body></html>")},
        requested,
    )

    outcome = asyncio.run(crawl(_START_URL, CrawlConfig(max_pages=50, max_frontier=2, max_depth=0)))

    assert outcome.frontier_truncated is True
    assert len(source.pulled) == 2, (
        "the discovery source's async generator must never be driven past the "
        "admission ceiling -- pulling a 3rd item would mean fetching a page "
        "that can never be admitted"
    )
    fetched = {result.url for result in outcome.results if not result.skipped}
    assert fetched == {_START_URL, *discovered[:2]}


def test_max_frontier_zero_disables_discovery_without_false_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``max_frontier=0`` ("disable link discovery entirely") never even asks
    the discovery source for an item, and never reports a false-positive
    ``frontier_truncated`` for a seed that was never attempted.
    """
    discovered = _discovered_urls(5)
    source = _FakeDiscoverySource(discovered)
    link_sources.register(source)

    requested: list[str] = []
    _install_fetch(
        monkeypatch,
        {_START_URL: _html(_START_URL, "<html><body>shell</body></html>")},
        requested,
    )

    outcome = asyncio.run(crawl(_START_URL, CrawlConfig(max_pages=50, max_frontier=0, max_depth=0)))

    assert source.pulled == [], "max_frontier=0 must never drive the discovery source at all"
    assert outcome.frontier_truncated is False, (
        "a seed that was never attempted must not report truncation"
    )
    fetched = {result.url for result in outcome.results if not result.skipped}
    assert fetched == {_START_URL}


# ---------------------------------------------------------------------------
# AC(c): additive composition with static anchors, no double-fetch
# ---------------------------------------------------------------------------


def test_additive_composition_with_static_anchors_no_double_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The union of discovery-sourced and statically-anchored links is admitted once each."""
    shared_url = f"https://{_HOST}/docs/shared-page"
    unique_discovery_url = f"https://{_HOST}/providers/x/y/latest/docs/unique-api-page"
    source = _FakeDiscoverySource([shared_url, unique_discovery_url])
    link_sources.register(source)

    requested: list[str] = []
    start_body = f'<html><body><a href="{shared_url}">shared</a></body></html>'
    _install_fetch(
        monkeypatch,
        {_START_URL: _html(_START_URL, start_body)},
        requested,
    )

    # max_depth=1 (not 0): the start page's own static anchors are only
    # extracted when depth < max_depth, so this must be >=1 for the static
    # path to run at all -- the discovery seed itself is independent of depth.
    outcome = asyncio.run(
        crawl(_START_URL, CrawlConfig(max_pages=50, max_frontier=50, max_depth=1))
    )

    fetched = [result.url for result in outcome.results if not result.skipped]
    assert set(fetched) == {_START_URL, shared_url, unique_discovery_url}
    assert fetched.count(shared_url) == 1, "shared_url must appear in results exactly once"
    assert requested.count(shared_url) == 1, "shared_url must be fetched exactly once"
