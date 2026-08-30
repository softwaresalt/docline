"""Red harness for 068.016-T (A.T12) — TOC-first ordering under truncation.

At depth zero, mdBook TOC-derived links must be ordered **ahead of** in-page
anchors so that, when the admission ceiling binds, the authoritative navigation
set survives and in-page anchors are the ones dropped (plan decision D6.2). The
same ordering also decides *which* pages are fetched when ``max_pages`` binds
below the eligible-candidate count even with no truncation (D6.1).

Order-dependency survey (required before writing): a repo-wide read of
``tests/fetch/`` found **no** existing test asserting a TOC-vs-anchor ordering
of crawl results — ``test_crawl_discovers_mdbook_toc_links_from_root_page``
uses a TOC-only page with no in-page anchors, so A.T13's reordering cannot
regress it. No existing test is updated by this task.

Red before 068.017-T (A.T13) flips ``discovered_links`` to ``toc + anchors``;
green afterwards.
"""

import asyncio

import pytest

from docline.fetch.crawl import CrawlConfig, crawl
from docline.fetch.http import FetchResponse, RemainingByteBudget

BOOK = "https://example.com/book/"
TOC_ASSET = "https://example.com/book/toc-1.js"


def _html(url: str, body: str) -> FetchResponse:
    """Return a synthetic HTML :class:`FetchResponse` for *url*."""
    return FetchResponse(url=url, status=200, content_type="text/html", body=body)


def _root_body() -> str:
    """Root page: two in-page anchors plus an mdBook TOC script reference."""
    return (
        "<html><head><script src='toc-1.js'></script></head><body>"
        '<a href="anchor-0.html">A0</a>'
        '<a href="anchor-1.html">A1</a>'
        "</body></html>"
    )


def _toc_asset_body() -> str:
    """TOC script payload advertising two in-scope chapter links."""
    return 'this.innerHTML = \'<a href="toc-0.html">T0</a><a href="toc-1.html">T1</a>\';'


def _pages() -> dict[str, FetchResponse]:
    """Return the synthetic mdBook site (root, TOC asset, leaf chapters)."""
    return {
        BOOK: _html(BOOK, _root_body()),
        TOC_ASSET: FetchResponse(
            url=TOC_ASSET, status=200, content_type="application/javascript", body=_toc_asset_body()
        ),
    }


def _install(monkeypatch: pytest.MonkeyPatch, requested: list[str]) -> None:
    """Monkeypatch ``crawl.fetch_page`` with the synthetic mdBook site."""
    pages = _pages()

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


TOC_0 = "https://example.com/book/toc-0.html"
TOC_1 = "https://example.com/book/toc-1.html"
ANCHOR_0 = "https://example.com/book/anchor-0.html"
ANCHOR_1 = "https://example.com/book/anchor-1.html"


def test_truncation_drops_anchors_and_keeps_toc_links(monkeypatch: pytest.MonkeyPatch) -> None:
    """D6.2: with the ceiling below N+M, TOC links are admitted, anchors dropped."""
    requested: list[str] = []
    _install(monkeypatch, requested)

    outcome = asyncio.run(
        crawl(
            BOOK,
            CrawlConfig(max_pages=500, max_depth=1, max_frontier=2, respect_robots=False),
        )
    )

    emitted = {result.url for result in outcome.results}
    assert TOC_0 in emitted
    assert TOC_1 in emitted
    assert ANCHOR_0 not in requested
    assert ANCHOR_1 not in requested
    assert outcome.frontier_truncated is True


def test_max_pages_prefers_toc_pages_without_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    """D6.1: when max_pages binds below the candidate count, TOC pages win.

    No truncation occurs (the ceiling is generous); the ``max_pages`` budget
    simply stops after the TOC-derived pages, which are ordered first.
    """
    requested: list[str] = []
    _install(monkeypatch, requested)

    outcome = asyncio.run(
        crawl(
            BOOK,
            CrawlConfig(max_pages=3, max_depth=1, max_frontier=50, respect_robots=False),
        )
    )

    assert TOC_0 in requested
    assert TOC_1 in requested
    assert ANCHOR_0 not in requested
    assert ANCHOR_1 not in requested
    assert outcome.frontier_truncated is False
