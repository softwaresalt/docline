"""Red harness for 068.013-T (A.T10) — CLI/MCP truncation-signal parity.

Runs an equivalent truncating web-crawl request through the CLI serialization
seam (``StagingJob.model_dump(mode="json")``, as ``cli.py`` emits it) and the
MCP tool surface (``DoclineMcpServer.fetch`` → ``FetchResult``), and asserts
both report the **same** ``frontier_truncated`` value against their *actual
serialized payloads* — not internal objects (plan decision D7).

Cases: a truncated staged crawl (both ``True``), an under-ceiling crawl (both
``False``), a zero-staged truncated crawl (both ``True`` and agreeing with the
persisted ``crawl-manifest.json``, per D8), and a crawl failure where no crawl
output was produced (both ``False``).

Red before 068.015-T (A.T11b) adds ``frontier_truncated`` to ``FetchResult``;
green afterwards.
"""

import json

import pytest

from docline.app_models import FetchRequest
from docline.elt.execute import execute_source_configs
from docline.elt.models import WebCrawlSource
from docline.fetch.crawl import CrawlOutcome, CrawlResult
from docline.fetch.http import FetchResponse
from docline.mcp.server import DoclineMcpServer

SOURCE = "https://example.com/docs/"


def _staged_page(url: str) -> CrawlResult:
    """Return a CrawlResult carrying a stageable HTML response."""
    return CrawlResult(
        url=url,
        depth=0,
        response=FetchResponse(
            url=url,
            status=200,
            content_type="text/html",
            body="<html><body><h1>page</h1></body></html>",
        ),
    )


def _install_crawl(monkeypatch: pytest.MonkeyPatch, outcome_factory) -> None:
    """Patch the crawl seam shared by the CLI and MCP fetch paths."""

    async def _fake(start_url, config=None, progress=None):
        del config, progress
        return outcome_factory(start_url)

    monkeypatch.setattr("docline.fetch.crawl.crawl", _fake)


def _cli_payload(tmp_path, source_url: str) -> dict:
    """Return the CLI-serialized StagingJob payload for *source_url*."""
    jobs = execute_source_configs(
        [WebCrawlSource(type="web_crawl", url=source_url, depth=0, max_pages=5)],
        "staging",
        workspace_root=tmp_path,
    )
    return jobs[0].model_dump(mode="json")


def _mcp_payload(monkeypatch, tmp_path, source_url: str) -> dict:
    """Return the MCP-serialized FetchResult payload for *source_url*."""
    monkeypatch.chdir(tmp_path)
    result = DoclineMcpServer().fetch(
        FetchRequest(source=source_url, output_dir="staging", max_pages=5)
    )
    return result.model_dump()


def test_truncated_staged_crawl_matches_across_cli_and_mcp(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A truncated crawl that staged pages reports True on both surfaces."""
    _install_crawl(
        monkeypatch, lambda url: CrawlOutcome(results=[_staged_page(url)], frontier_truncated=True)
    )
    cli = _cli_payload(tmp_path, SOURCE)
    mcp = _mcp_payload(monkeypatch, tmp_path, SOURCE)

    assert cli["frontier_truncated"] is True
    assert mcp["frontier_truncated"] is True
    assert cli["frontier_truncated"] == mcp["frontier_truncated"]


def test_untruncated_crawl_matches_across_cli_and_mcp(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """An under-ceiling crawl reports False on both surfaces."""
    _install_crawl(
        monkeypatch, lambda url: CrawlOutcome(results=[_staged_page(url)], frontier_truncated=False)
    )
    cli = _cli_payload(tmp_path, SOURCE)
    mcp = _mcp_payload(monkeypatch, tmp_path, SOURCE)

    assert cli["frontier_truncated"] is False
    assert mcp["frontier_truncated"] is False
    assert cli["frontier_truncated"] == mcp["frontier_truncated"]


def test_zero_staged_truncated_crawl_matches_and_agrees_with_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A zero-staged truncated crawl reports True on both surfaces and on disk."""
    _install_crawl(
        monkeypatch,
        lambda url: CrawlOutcome(
            results=[CrawlResult(url=url, depth=0, skipped=True, skip_reason="dropped")],
            frontier_truncated=True,
        ),
    )
    cli = _cli_payload(tmp_path, SOURCE)
    manifest = json.loads(
        (tmp_path / cli["cache_path"] / "crawl-manifest.json").read_text(encoding="utf-8")
    )
    mcp = _mcp_payload(monkeypatch, tmp_path, SOURCE)

    assert cli["frontier_truncated"] is True
    assert mcp["frontier_truncated"] is True
    assert manifest["frontier_truncated"] is True
    assert cli["frontier_truncated"] == mcp["frontier_truncated"]


def test_crawl_failure_reports_false_on_both_surfaces(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A crawl that raised (no output) reports False on both surfaces."""

    async def _boom(start_url, config=None, progress=None):
        del start_url, config, progress
        raise OSError("network down")

    monkeypatch.setattr("docline.fetch.crawl.crawl", _boom)
    cli = _cli_payload(tmp_path, SOURCE)
    mcp = _mcp_payload(monkeypatch, tmp_path, SOURCE)

    assert cli["frontier_truncated"] is False
    assert mcp["frontier_truncated"] is False
    assert cli["complete"] is False
    assert mcp["success"] is False
