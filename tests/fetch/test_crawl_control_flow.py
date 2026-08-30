"""Characterization harness for 068.003-T (A.T2b).

Pins the *non-counting* control-flow branches of ``crawl()`` that the
``_Frontier`` extraction (A.T3) and the module split (A.T4) must preserve
verbatim. Unlike ``tests/fetch/test_crawl_section_scope.py`` — which rejects a
*discovered* sibling before it enters the frontier — these cases exercise the
**post-fetch** branches at the final-URL stage:

* the section-scope ``continue`` (an admitted URL whose *final* URL resolves
  outside the inferred section): no ``CrawlResult``, no ``page_count``
  increment, no progress event, and no discovery from its body, while later
  queued work still runs;
* the duplicate-final ``continue`` (two admitted URLs whose final URLs collide):
  the canonical page is emitted exactly once and the duplicate is non-counting;
* the redirect-alias branch (final URL differs but stays in scope): the page is
  emitted under its *final* URL.

This is characterization, not a red harness: it is **green against current
source** and must stay green through A.T3 and A.T4. It migrates to
``CrawlOutcome`` in 068.019-T (A.T7b).
"""

import asyncio

import pytest

from docline.fetch.crawl import CrawlConfig, crawl
from docline.fetch.http import FetchResponse, RemainingByteBudget

SECTION = "https://example.com/docs/guide/"


def _html(url: str, body: str) -> FetchResponse:
    """Return a synthetic HTML :class:`FetchResponse` for *url*."""
    return FetchResponse(url=url, status=200, content_type="text/html", body=body)


def _anchors(*paths: str) -> str:
    """Return an HTML body linking to each path in *paths*."""
    hrefs = "".join(f'<a href="{path}">{path}</a>' for path in paths)
    return f"<html><body>{hrefs}</body></html>"


def _install(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, FetchResponse],
    requested: list[str],
) -> None:
    """Monkeypatch ``crawl.fetch_page`` with a per-URL redirect-aware double."""

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
        if url in responses:
            return responses[url]
        return _html(url, "<html><body><h1>leaf</h1></body></html>")

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)


def _recorder(progress_calls: list[tuple[int, int | None, str]]):
    """Return a progress callback that records ``(count, total, url)`` tuples."""

    def _record(count: int, total: int | None, url: str) -> None:
        progress_calls.append((count, total, url))

    return _record


def _run(
    responses: dict[str, FetchResponse],
    requested: list[str],
    monkeypatch: pytest.MonkeyPatch,
    progress_calls: list[tuple[int, int | None, str]],
):
    """Run a bounded in-scope crawl of :data:`SECTION`."""
    _install(monkeypatch, responses, requested)
    return asyncio.run(
        crawl(
            SECTION,
            CrawlConfig(max_pages=50, max_depth=1, respect_robots=False),
            progress=_recorder(progress_calls),
        )
    ).results


# ---------------------------------------------------------------------------
# Section-scope non-counting continue (crawl.py:316)
# ---------------------------------------------------------------------------


def test_out_of_section_final_url_is_non_counting(monkeypatch: pytest.MonkeyPatch) -> None:
    """An admitted URL whose final URL leaves the section is fully non-counting.

    It produces no ``CrawlResult``, fires no progress event, does not increment
    the page budget, and contributes no discovered links — yet a later in-scope
    sibling is still crawled.
    """
    child = "https://example.com/docs/guide/child"
    sibling = "https://example.com/docs/guide/sibling"
    escaped = "https://example.com/elsewhere/page"
    responses = {
        SECTION: _html(SECTION, _anchors("/docs/guide/child", "/docs/guide/sibling")),
        # ``child`` redirects out of the inferred /docs/guide/ section.
        child: _html(escaped, _anchors("/docs/guide/leaked")),
        sibling: _html(sibling, "<html><body><h1>sibling</h1></body></html>"),
    }
    requested: list[str] = []
    progress_calls: list[tuple[int, int | None, str]] = []

    results = _run(responses, requested, monkeypatch, progress_calls)

    emitted = [result.url for result in results]
    assert emitted == [SECTION, sibling]
    # No discovery from the out-of-section body.
    assert "https://example.com/docs/guide/leaked" not in requested
    # The out-of-section URL fired no progress event; only counting pages did.
    assert [call[2] for call in progress_calls] == [SECTION, sibling]
    # child was fetched but never emitted; sibling (later queued work) still ran.
    assert child in requested
    assert sibling in requested


# ---------------------------------------------------------------------------
# Duplicate-final non-counting continue
# ---------------------------------------------------------------------------


def test_duplicate_final_url_is_emitted_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two admitted URLs resolving to one final URL emit the canonical once."""
    a = "https://example.com/docs/guide/a"
    b = "https://example.com/docs/guide/b"
    canonical = "https://example.com/docs/guide/canonical"
    responses = {
        SECTION: _html(SECTION, _anchors("/docs/guide/a", "/docs/guide/b")),
        a: _html(canonical, "<html><body><h1>canonical</h1></body></html>"),
        b: _html(canonical, "<html><body><h1>canonical-again</h1></body></html>"),
    }
    requested: list[str] = []
    progress_calls: list[tuple[int, int | None, str]] = []

    results = _run(responses, requested, monkeypatch, progress_calls)

    emitted = [result.url for result in results]
    assert emitted.count(canonical) == 1
    assert emitted == [SECTION, canonical]
    # Both aliases were fetched, but the duplicate did not fire progress.
    assert a in requested
    assert b in requested
    assert [call[2] for call in progress_calls] == [SECTION, a]


# ---------------------------------------------------------------------------
# Redirect-alias branch (final URL differs, stays in scope)
# ---------------------------------------------------------------------------


def test_redirect_alias_is_emitted_under_final_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """A redirect that stays in scope emits under the resolved final URL."""
    requested_url = "https://example.com/docs/guide/x"
    final_url = "https://example.com/docs/guide/x-final"
    responses = {
        SECTION: _html(SECTION, _anchors("/docs/guide/x")),
        requested_url: _html(final_url, "<html><body><h1>x</h1></body></html>"),
    }
    requested: list[str] = []
    progress_calls: list[tuple[int, int | None, str]] = []

    results = _run(responses, requested, monkeypatch, progress_calls)

    emitted = [result.url for result in results]
    assert emitted == [SECTION, final_url]
    assert requested_url in requested
