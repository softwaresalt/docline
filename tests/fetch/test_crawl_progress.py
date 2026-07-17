"""Progress-callback tests for :func:`docline.fetch.crawl.crawl` (056.008-T).

The callback reports *budget-consumed* pages: it fires once per ``page_count``
increment (the budget-consuming branches), not once per dequeued URL. Branches
that ``continue`` without consuming the budget — e.g. print pages — fire no
callback and leave the count unchanged.
"""

from __future__ import annotations

import asyncio

import pytest

from docline.fetch.crawl import CrawlConfig, crawl
from docline.fetch.http import FetchResponse


def _run(pages: dict[str, FetchResponse], monkeypatch, start: str, **cfg):
    async def fake_fetch_page(
        url: str, *, timeout_seconds: float = 30.0, max_redirects: int = 5
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        return pages[url]

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)
    calls: list[tuple[int, int | None, str]] = []

    def record(done: int, total: int | None, detail: str) -> None:
        calls.append((done, total, detail))

    results = asyncio.run(
        crawl(start, CrawlConfig(respect_robots=False, domain_lock=False, **cfg), progress=record)
    )
    return results, calls


def test_progress_fires_once_per_budget_consumed_page(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        "https://ex.org/a.html": FetchResponse(
            url="https://ex.org/a.html",
            status=200,
            content_type="text/html",
            body='<html><body><a href="/b.html">b</a></body></html>',
        ),
        "https://ex.org/b.html": FetchResponse(
            url="https://ex.org/b.html",
            status=200,
            content_type="text/html",
            body="<html><body><h1>b</h1></body></html>",
        ),
    }
    results, calls = _run(pages, monkeypatch, "https://ex.org/a.html", max_pages=10, max_depth=2)

    staged = [r for r in results if r.response is not None]
    assert len(calls) == len(staged)  # one callback per budget-consumed page
    dones = [c[0] for c in calls]
    assert dones == sorted(dones)  # monotonic non-decreasing
    assert dones[-1] == len(staged)
    assert all(total == 10 for _, total, _ in calls)  # total is the max_pages budget
    assert all(done <= 10 for done, _, _ in calls)


def test_non_consuming_print_page_fires_no_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        "https://ex.org/a.html": FetchResponse(
            url="https://ex.org/a.html",
            status=200,
            content_type="text/html",
            body=(
                '<html><body><a href="/b.html">b</a><a href="/print.html">print</a></body></html>'
            ),
        ),
        "https://ex.org/b.html": FetchResponse(
            url="https://ex.org/b.html",
            status=200,
            content_type="text/html",
            body="<html><body><h1>b</h1></body></html>",
        ),
        "https://ex.org/print.html": FetchResponse(
            url="https://ex.org/print.html",
            status=200,
            content_type="text/html",
            body="<html><body><h1>print</h1></body></html>",
        ),
    }
    _results, calls = _run(pages, monkeypatch, "https://ex.org/a.html", max_pages=10, max_depth=2)

    # a.html and b.html consume the budget; print.html is skipped without counting.
    assert len(calls) == 2
    assert [c[0] for c in calls] == [1, 2]


def test_progress_none_default_leaves_results_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        "https://ex.org/a.html": FetchResponse(
            url="https://ex.org/a.html",
            status=200,
            content_type="text/html",
            body='<html><body><a href="/b.html">b</a></body></html>',
        ),
        "https://ex.org/b.html": FetchResponse(
            url="https://ex.org/b.html",
            status=200,
            content_type="text/html",
            body="<html><body><h1>b</h1></body></html>",
        ),
    }

    async def fake_fetch_page(
        url: str, *, timeout_seconds: float = 30.0, max_redirects: int = 5
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        return pages[url]

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)
    cfg = CrawlConfig(respect_robots=False, domain_lock=False, max_pages=10, max_depth=2)

    without = asyncio.run(crawl("https://ex.org/a.html", cfg))
    with_noop = asyncio.run(crawl("https://ex.org/a.html", cfg, progress=lambda *a: None))

    assert [r.url for r in without] == [r.url for r in with_noop]
    assert [r.response is not None for r in without] == [r.response is not None for r in with_noop]


def test_progress_fires_for_robots_denied_page(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _deny(*_args, **_kwargs) -> bool:
        return False

    monkeypatch.setattr("docline.fetch.crawl._robots_allow", _deny)

    async def fake_fetch_page(url, *, timeout_seconds=30.0, max_redirects=5):
        raise AssertionError("fetch_page must not run when robots denies the URL")

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)
    calls: list[tuple[int, int | None, str]] = []
    results = asyncio.run(
        crawl(
            "https://ex.org/a.html",
            CrawlConfig(respect_robots=True, domain_lock=False, max_pages=5),
            progress=lambda d, t, det: calls.append((d, t, det)),
        )
    )
    assert results[0].skipped is True
    assert calls == [(1, 5, "https://ex.org/a.html")]  # robots denial consumes the budget


def test_progress_fires_for_fetch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_fetch_page(url, *, timeout_seconds=30.0, max_redirects=5):
        raise OSError("connection reset")

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", failing_fetch_page)
    calls: list[tuple[int, int | None, str]] = []
    results = asyncio.run(
        crawl(
            "https://ex.org/a.html",
            CrawlConfig(respect_robots=False, domain_lock=False, max_pages=5, max_retries=0),
            progress=lambda d, t, det: calls.append((d, t, det)),
        )
    )
    assert results[0].skipped is True
    assert calls == [(1, 5, "https://ex.org/a.html")]  # fetch failure consumes the budget


def test_progress_fires_for_domain_rejected_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    async def redirecting_fetch_page(url, *, timeout_seconds=30.0, max_redirects=5):
        # redirect resolves to a different host than the (locked) start host
        return FetchResponse(
            url="https://evil.org/a.html",
            status=200,
            content_type="text/html",
            body="<html><body>x</body></html>",
        )

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", redirecting_fetch_page)
    calls: list[tuple[int, int | None, str]] = []
    results = asyncio.run(
        crawl(
            "https://ex.org/a.html",
            CrawlConfig(respect_robots=False, domain_lock=True, max_pages=5),
            progress=lambda d, t, det: calls.append((d, t, det)),
        )
    )
    assert results[0].skipped is True
    assert calls == [
        (1, 5, "https://ex.org/a.html")
    ]  # domain-rejected redirect consumes the budget
