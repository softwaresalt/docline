"""Fetch-seam progress tests (056.011-T).

Verifies the ``progress`` callback is forwarded through the fetch seam into
``crawl`` and that ``_fetch_url`` emits a final count-only event carrying the
authoritative ``staged_count`` (pages actually written), transported without
changing the ``FetchRequest``/``FetchResult`` schema.
"""

from __future__ import annotations

import pytest

from docline.app import execute_fetch
from docline.app_models import FetchRequest, FetchResult
from docline.fetch.crawl import CrawlOutcome, CrawlResult
from docline.fetch.http import FetchResponse


def _page(url: str) -> CrawlResult:
    return CrawlResult(
        url=url,
        depth=0,
        response=FetchResponse(
            url=url,
            status=200,
            content_type="text/html",
            body="<html><body><h1>x</h1></body></html>",
        ),
    )


def test_progress_forwarded_and_final_staged_count_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    captured: dict[str, object] = {}

    async def _fake(start_url, config=None, progress=None):
        captured["progress"] = progress
        if progress is not None:
            # a budget-consumed event, total is the max_pages budget (an int)
            progress(1, config.max_pages if config else None, start_url)
        return CrawlOutcome(
            results=[_page(start_url), _page(start_url.rstrip("/") + "/b.html")],
            frontier_truncated=False,
        )

    monkeypatch.setattr("docline.fetch.crawl.crawl", _fake)
    monkeypatch.chdir(tmp_path)

    calls: list[tuple[int, int | None, str]] = []
    result = execute_fetch(
        FetchRequest(source="https://ex.org/docs/", output_dir="staging", max_pages=5),
        progress=lambda d, t, det: calls.append((d, t, det)),
    )

    assert result.success is True
    # progress reached crawl
    assert captured["progress"] is not None
    # a budget event arrived with the max_pages budget as total
    assert any(t == 5 for _, t, _ in calls)
    # the final event is the authoritative staged count as a count-only event
    assert calls[-1] == (2, None, "https://ex.org/docs/")


def test_progress_not_a_fetch_request_field() -> None:
    # Keeping progress off the Pydantic models preserves the MCP schema.
    assert "progress" not in FetchRequest.model_fields
    assert "progress" not in FetchResult.model_fields


def test_progress_none_default_still_stages(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    async def _fake(start_url, config=None, progress=None):
        return CrawlOutcome(results=[_page(start_url)], frontier_truncated=False)

    monkeypatch.setattr("docline.fetch.crawl.crawl", _fake)
    monkeypatch.chdir(tmp_path)
    result = execute_fetch(FetchRequest(source="https://ex.org/docs/", output_dir="staging"))
    assert result.success is True


def test_zero_page_crawl_still_emits_final_count_only_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    async def _fake(start_url, config=None, progress=None):
        if progress is not None:
            progress(1, config.max_pages if config else None, start_url)  # a budget event
        # a robots-denied/failed crawl stages nothing (no response bodies)
        return CrawlOutcome(
            results=[CrawlResult(url=start_url, depth=0, skipped=True, skip_reason="robots.txt")],
            frontier_truncated=False,
        )

    monkeypatch.setattr("docline.fetch.crawl.crawl", _fake)
    monkeypatch.chdir(tmp_path)

    calls: list[tuple[int, int | None, str]] = []
    result = execute_fetch(
        FetchRequest(source="https://ex.org/docs/", output_dir="staging", max_pages=5),
        progress=lambda d, t, det: calls.append((d, t, det)),
    )

    assert result.success is False  # nothing staged
    # the authoritative count-only 0 event still fires (before the zero-page guard)
    assert calls[-1] == (0, None, "https://ex.org/docs/")


def test_final_event_emitted_even_when_crawl_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    async def _boom(start_url, config=None, progress=None):
        raise OSError("crawl rejected")

    monkeypatch.setattr("docline.fetch.crawl.crawl", _boom)
    monkeypatch.chdir(tmp_path)

    calls: list[tuple[int, int | None, str]] = []
    result = execute_fetch(
        FetchRequest(source="https://ex.org/docs/", output_dir="staging"),
        progress=lambda d, t, det: calls.append((d, t, det)),
    )

    assert result.success is False
    # the try/finally still emits the authoritative (0) completion event
    assert calls[-1] == (0, None, "https://ex.org/docs/")


def test_fetch_url_zero_staged_raises_typed_error_with_single_callback(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A.T9 contract: `_fetch_url` raises a typed, OSError-catchable zero-staged error.

    Exercises `_fetch_url` directly (not through `execute_fetch`, which swallows
    the exception): the zero-staged path must raise `CrawlStagedNothingError`
    that is catchable as `OSError` with the exact message, carry the real
    `frontier_truncated` flag, and fire exactly one completion callback before
    the exception propagates.
    """
    from docline.elt.execute import CrawlStagedNothingError, _fetch_url
    from docline.elt.models import WebCrawlSource
    from docline.fetch.crawl import CrawlOutcome, CrawlResult

    url = "https://ex.org/docs/"

    async def _fake(start_url, config=None, progress=None):
        # A skipped result has no response body, so nothing stages.
        return CrawlOutcome(
            results=[CrawlResult(url=start_url, depth=0, skipped=True, skip_reason="dropped")],
            frontier_truncated=True,
        )

    monkeypatch.setattr("docline.fetch.crawl.crawl", _fake)
    files_dir = tmp_path / "files"
    files_dir.mkdir()

    calls: list[tuple[int, int | None, str]] = []
    with pytest.raises(CrawlStagedNothingError) as excinfo:
        _fetch_url(
            WebCrawlSource(type="web_crawl", url=url, depth=0, max_pages=5),
            files_dir,
            progress=lambda d, t, det: calls.append((d, t, det)),
        )

    err = excinfo.value
    assert isinstance(err, OSError)
    assert str(err) == f"No crawlable HTML pages were staged for {url}"
    assert err.frontier_truncated is True
    # Exactly one completion callback fires before the exception propagates.
    assert calls == [(0, None, url)]


def test_fetch_url_zero_staged_error_is_catchable_as_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The zero-staged error remains catchable via a bare `except OSError`."""
    from docline.elt.execute import _fetch_url
    from docline.elt.models import WebCrawlSource
    from docline.fetch.crawl import CrawlOutcome

    async def _fake(start_url, config=None, progress=None):
        return CrawlOutcome(results=[], frontier_truncated=False)

    monkeypatch.setattr("docline.fetch.crawl.crawl", _fake)
    files_dir = tmp_path / "files"
    files_dir.mkdir()

    caught = False
    try:
        _fetch_url(WebCrawlSource(type="web_crawl", url="https://ex.org/docs/", depth=0), files_dir)
    except OSError:
        caught = True
    assert caught is True
