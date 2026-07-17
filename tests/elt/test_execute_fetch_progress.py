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
from docline.fetch.crawl import CrawlResult
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
        return [_page(start_url), _page(start_url.rstrip("/") + "/b.html")]

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
        return [_page(start_url)]

    monkeypatch.setattr("docline.fetch.crawl.crawl", _fake)
    monkeypatch.chdir(tmp_path)
    result = execute_fetch(FetchRequest(source="https://ex.org/docs/", output_dir="staging"))
    assert result.success is True
