"""Section-scope derivation must use the full start-path prefix (5A27C137).

Regression tests for the bug where ``_derive_section_scope`` scoped to only the
first path segment (``/docs/``) instead of the full directory prefix
(``/docs/current/``), causing a crawl of a sub-path to wander into sibling
subsections (e.g. other documentation versions).
"""

import asyncio

import pytest

from docline.fetch.crawl import (
    CrawlConfig,
    _derive_section_scope,
    _url_within_section_scope,
    crawl,
)
from docline.fetch.http import FetchResponse


def test_section_scope_uses_full_prefix_for_trailing_slash() -> None:
    """A directory start URL scopes to that full directory, not the first segment."""
    assert _derive_section_scope("https://www.postgresql.org/docs/current/") == "/docs/current/"


def test_section_scope_uses_parent_dir_for_file_url() -> None:
    """A file start URL scopes to its parent directory (full prefix)."""
    assert (
        _derive_section_scope("https://www.postgresql.org/docs/current/index.html")
        == "/docs/current/"
    )


def test_section_scope_excludes_sibling_subsections() -> None:
    """Scope derived from /docs/current/ admits current pages and rejects siblings."""
    scope = _derive_section_scope("https://www.postgresql.org/docs/current/")
    assert (
        _url_within_section_scope(
            "https://www.postgresql.org/docs/current/sql-select.html", scope
        )
        is True
    )
    assert (
        _url_within_section_scope("https://www.postgresql.org/docs/10/sql-select.html", scope)
        is False
    )
    assert (
        _url_within_section_scope("https://www.postgresql.org/docs/release/", scope) is False
    )


def test_section_scope_none_for_site_root() -> None:
    """A bare-root start URL imposes no section scope."""
    assert _derive_section_scope("https://example.com/") is None


def test_section_scope_none_for_extensionless_no_slash() -> None:
    """An ambiguous extensionless path with no trailing slash imposes no scope."""
    assert _derive_section_scope("https://example.com/start") is None


def test_crawl_from_subsection_does_not_follow_sibling_version_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crawl of /docs/current/ must not follow version-switcher links to /docs/10/."""
    pages = {
        "https://ex.org/docs/current/": FetchResponse(
            url="https://ex.org/docs/current/",
            status=200,
            content_type="text/html",
            body=(
                "<html><body>"
                '<a href="/docs/current/page.html">Current page</a>'
                '<a href="/docs/10/page.html">v10 page</a>'
                "</body></html>"
            ),
        ),
        "https://ex.org/docs/current/page.html": FetchResponse(
            url="https://ex.org/docs/current/page.html",
            status=200,
            content_type="text/html",
            body="<html><body><h1>Current</h1></body></html>",
        ),
        "https://ex.org/docs/10/page.html": FetchResponse(
            url="https://ex.org/docs/10/page.html",
            status=200,
            content_type="text/html",
            body="<html><body><h1>v10</h1></body></html>",
        ),
    }

    async def fake_fetch_page(
        url: str, *, timeout_seconds: float = 30.0, max_redirects: int = 5
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        return pages[url]

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    results = asyncio.run(
        crawl(
            "https://ex.org/docs/current/",
            CrawlConfig(max_pages=10, max_depth=2, respect_robots=False, domain_lock=True),
        )
    )
    fetched = {r.url for r in results if r.response is not None}
    assert "https://ex.org/docs/current/page.html" in fetched
    assert "https://ex.org/docs/10/page.html" not in fetched
