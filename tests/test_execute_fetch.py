"""Tests for execute_fetch web-crawl orchestration (054-F / T1).

These tests exercise the real staging path (files/, metadata.json,
crawl-manifest.json) but stub the network at the crawl seam so no live HTTP
occurs. All filesystem writes are redirected under ``tmp_path``.
"""

import json

import pytest

from docline.app import execute_fetch
from docline.app_models import FetchRequest
from docline.fetch.crawl import CrawlConfig, CrawlResult
from docline.fetch.http import FetchResponse

_HTML = "<html><body><h1>Title</h1><p>Body text.</p></body></html>"


def _page(url: str, body: str = _HTML, status: int = 200) -> CrawlResult:
    """Build a successful CrawlResult with an in-memory HTML response."""
    return CrawlResult(
        url=url,
        depth=0,
        response=FetchResponse(url=url, status=status, content_type="text/html", body=body),
    )


@pytest.fixture
def fake_crawl(monkeypatch):
    """Patch the crawl seam with a deterministic two-page in-memory crawl.

    Returns a dict that captures the start URL and CrawlConfig passed to crawl.
    """
    captured: dict[str, object] = {}

    async def _fake(
        start_url: str, config: CrawlConfig | None = None, progress=None
    ) -> list[CrawlResult]:
        captured["start_url"] = start_url
        captured["config"] = config
        captured["progress"] = progress
        return [_page(start_url), _page(start_url.rstrip("/") + "/child.html")]

    monkeypatch.setattr("docline.fetch.crawl.crawl", _fake)
    return captured


def test_execute_fetch_stages_pages_and_reports_success(monkeypatch, tmp_path, fake_crawl) -> None:
    """A successful crawl stages HTML pages and returns success with a path."""
    monkeypatch.chdir(tmp_path)
    result = execute_fetch(FetchRequest(source="https://example.org/docs/", output_dir="staging"))
    assert result.success is True
    assert result.error is None
    assert result.source == "https://example.org/docs/"
    assert result.staged_path
    job_dir = tmp_path / result.staged_path
    assert (job_dir / "metadata.json").is_file()
    assert (job_dir / "crawl-manifest.json").is_file()
    staged_html = list((job_dir / "files").rglob("*.html"))
    assert len(staged_html) == 2


def test_execute_fetch_metadata_complete_and_manifest_shape(
    monkeypatch, tmp_path, fake_crawl
) -> None:
    """The staged job is marked complete and the crawl manifest is well-formed."""
    monkeypatch.chdir(tmp_path)
    result = execute_fetch(FetchRequest(source="https://example.org/docs/", output_dir="staging"))
    job_dir = tmp_path / result.staged_path
    meta = json.loads((job_dir / "metadata.json").read_text(encoding="utf-8"))
    assert meta["complete"] is True
    manifest = json.loads((job_dir / "crawl-manifest.json").read_text(encoding="utf-8"))
    assert isinstance(manifest["pages"], list)
    assert manifest["pages"]
    first = manifest["pages"][0]
    assert "relative_path" in first
    assert "crawl_order" in first


def test_execute_fetch_maps_depth_to_crawl_config(monkeypatch, tmp_path, fake_crawl) -> None:
    """FetchRequest.depth maps to the crawl's maximum discovery depth."""
    monkeypatch.chdir(tmp_path)
    execute_fetch(FetchRequest(source="https://example.org/docs/", depth=3, output_dir="staging"))
    config = fake_crawl["config"]
    assert isinstance(config, CrawlConfig)
    assert config.max_depth == 3


def test_execute_fetch_applies_bounded_max_pages_default(monkeypatch, tmp_path, fake_crawl) -> None:
    """A bounded default page budget is enforced to prevent runaway crawls."""
    monkeypatch.chdir(tmp_path)
    execute_fetch(FetchRequest(source="https://example.org/docs/", output_dir="staging"))
    config = fake_crawl["config"]
    assert isinstance(config, CrawlConfig)
    assert config.max_pages >= 1


def test_execute_fetch_rejects_non_http_scheme(monkeypatch, tmp_path) -> None:
    """A non-http(s) source is rejected without staging anything."""
    monkeypatch.chdir(tmp_path)
    result = execute_fetch(FetchRequest(source="file:///etc/passwd", output_dir="staging"))
    assert result.success is False
    assert result.staged_path == ""
    assert "http" in (result.error or "").lower()


def test_execute_fetch_reports_failure_when_no_pages_staged(monkeypatch, tmp_path) -> None:
    """When the crawl yields no pages, the fetch fails with an empty staged path."""
    monkeypatch.chdir(tmp_path)

    async def _empty(start_url: str, config: CrawlConfig | None = None) -> list[CrawlResult]:
        return []

    monkeypatch.setattr("docline.fetch.crawl.crawl", _empty)
    result = execute_fetch(FetchRequest(source="https://example.org/docs/", output_dir="staging"))
    assert result.success is False
    assert result.staged_path == ""


def test_execute_fetch_staged_output_is_processable(monkeypatch, tmp_path, fake_crawl) -> None:
    """The staged layout feeds execute_process end-to-end into Markdown."""
    from docline.app import execute_process
    from docline.app_models import ProcessRequest

    monkeypatch.chdir(tmp_path)
    fetch_result = execute_fetch(
        FetchRequest(source="https://example.org/docs/", output_dir="staging")
    )
    assert fetch_result.success is True

    process_result = execute_process(ProcessRequest(staging_dir="staging", output_dir="output"))
    assert process_result.success is True
    markdown_files = list((tmp_path / "output").rglob("*.md"))
    assert markdown_files


# --- B0A77532: max_pages passthrough + canonical_url web fallback ---


def test_execute_fetch_max_pages_overrides_default(monkeypatch, tmp_path, fake_crawl) -> None:
    """FetchRequest.max_pages overrides the bounded crawl default."""
    monkeypatch.chdir(tmp_path)
    execute_fetch(
        FetchRequest(source="https://example.org/docs/", max_pages=7, output_dir="staging")
    )
    config = fake_crawl["config"]
    assert isinstance(config, CrawlConfig)
    assert config.max_pages == 7


def test_execute_fetch_process_stamps_canonical_url_for_web_source(
    monkeypatch, tmp_path, fake_crawl
) -> None:
    """A processed web source with no Learn config gets canonical_url = fetched URL."""
    from docline.app import execute_process
    from docline.app_models import ProcessRequest

    monkeypatch.chdir(tmp_path)
    execute_fetch(FetchRequest(source="https://example.org/docs/", output_dir="staging"))
    result = execute_process(ProcessRequest(staging_dir="staging", output_dir="output"))
    assert result.success is True

    md_files = sorted((tmp_path / "output").rglob("*.md"))
    assert md_files
    text = md_files[0].read_text(encoding="utf-8")
    assert "canonical_url:" in text
    assert "example.org" in text
