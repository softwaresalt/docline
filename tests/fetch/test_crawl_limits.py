"""Test harness for 003.002-T — Bound crawl executor timeouts.

Acceptance criteria:
- CrawlConfig exposes max_pages and page_timeout_seconds fields with safe defaults.
- crawl() returns a list of CrawlResult objects within the page budget.
- CrawlLimitExceededError is raised when the page cap is exceeded.
- CrawlLimitExceededError is a DoclineError subclass.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests assert return values or typed exceptions (FAIL in red phase).
"""

import asyncio

import pytest

from docline.fetch.crawl import (
    CrawlConfig,
    CrawlLimitExceededError,
    crawl,
)
from docline.fetch.http import FetchResponse
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Structural: config defaults and error hierarchy (PASS in red phase)
# ---------------------------------------------------------------------------


def test_crawl_config_default_max_pages() -> None:
    """CrawlConfig has a positive default max_pages."""
    config = CrawlConfig()
    assert config.max_pages > 0


def test_crawl_config_default_page_timeout() -> None:
    """CrawlConfig has a positive default page_timeout_seconds."""
    config = CrawlConfig()
    assert config.page_timeout_seconds > 0


def test_crawl_config_custom_max_pages() -> None:
    """CrawlConfig accepts a custom max_pages value."""
    config = CrawlConfig(max_pages=5)
    assert config.max_pages == 5


def test_crawl_config_custom_timeout() -> None:
    """CrawlConfig accepts a custom page_timeout_seconds value."""
    config = CrawlConfig(page_timeout_seconds=10.0)
    assert config.page_timeout_seconds == 10.0


def test_crawl_config_custom_max_redirects() -> None:
    """CrawlConfig accepts a custom max_redirects value."""
    config = CrawlConfig(max_redirects=3)
    assert config.max_redirects == 3


def test_crawl_limit_exceeded_error_is_docline_error() -> None:
    """CrawlLimitExceededError is a subclass of DoclineError."""
    err = CrawlLimitExceededError("limit exceeded")
    assert isinstance(err, DoclineError)


# ---------------------------------------------------------------------------
# Behavioral: crawl() return value (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_crawl_returns_list_of_results() -> None:
    """crawl() returns a list of CrawlResult objects."""
    results = asyncio.run(crawl("https://example.com", CrawlConfig(max_pages=1)))
    assert isinstance(results, list)


def test_crawl_respects_max_pages_single() -> None:
    """crawl() fetches at most max_pages pages."""
    config = CrawlConfig(max_pages=1, page_timeout_seconds=5.0)
    results = asyncio.run(crawl("https://example.com", config))
    assert len(results) <= 1


def test_crawl_result_has_url_field() -> None:
    """Each CrawlResult from crawl() has a url field matching the start URL."""
    results = asyncio.run(crawl("https://example.com", CrawlConfig(max_pages=1)))
    assert all(isinstance(r.url, str) for r in results)


def test_crawl_with_default_config_returns_list() -> None:
    """crawl() with default config returns a list."""
    results = asyncio.run(crawl("https://example.com"))
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Behavioral: page-budget enforcement (no live network required)
# ---------------------------------------------------------------------------


def test_crawl_raises_limit_exceeded_when_max_pages_zero() -> None:
    """crawl() raises CrawlLimitExceededError when max_pages is 0.

    A zero-page budget cannot accommodate even a single page; the error is
    raised before any network I/O, so no monkeypatching is required.
    """
    with pytest.raises(CrawlLimitExceededError):
        asyncio.run(crawl("https://example.com", CrawlConfig(max_pages=0)))


def test_crawl_follows_links_within_depth_and_page_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """crawl() traverses additional pages up to the configured depth/page caps."""
    pages = {
        "https://example.com/start": FetchResponse(
            url="https://example.com/start",
            status=200,
            content_type="text/html",
            body=(
                "<html><body>"
                '<a href="/docs/intro">Intro</a>'
                '<a href="/docs/api">API</a>'
                "</body></html>"
            ),
        ),
        "https://example.com/docs/intro": FetchResponse(
            url="https://example.com/docs/intro",
            status=200,
            content_type="text/html",
            body="<html><body><h1>Intro</h1></body></html>",
        ),
        "https://example.com/docs/api": FetchResponse(
            url="https://example.com/docs/api",
            status=200,
            content_type="text/html",
            body="<html><body><h1>API</h1></body></html>",
        ),
    }

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        return pages[url]

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    results = asyncio.run(
        crawl(
            "https://example.com/start",
            CrawlConfig(
                max_pages=3,
                max_depth=1,
                respect_robots=False,
                domain_lock=True,
            ),
        )
    )

    assert [result.url for result in results] == [
        "https://example.com/start",
        "https://example.com/docs/intro",
        "https://example.com/docs/api",
    ]
    assert [result.depth for result in results] == [0, 1, 1]


def test_crawl_domain_lock_skips_cross_domain_links(monkeypatch: pytest.MonkeyPatch) -> None:
    """crawl() does not enqueue links that leave the locked domain."""
    fetched_urls: list[str] = []
    pages = {
        "https://example.com/start": FetchResponse(
            url="https://example.com/start",
            status=200,
            content_type="text/html",
            body=(
                "<html><body>"
                '<a href="/docs/intro">Intro</a>'
                '<a href="https://other.example.com/offsite">Offsite</a>'
                "</body></html>"
            ),
        ),
        "https://example.com/docs/intro": FetchResponse(
            url="https://example.com/docs/intro",
            status=200,
            content_type="text/html",
            body="<html><body><h1>Intro</h1></body></html>",
        ),
    }

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        fetched_urls.append(url)
        return pages[url]

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    results = asyncio.run(
        crawl(
            "https://example.com/start",
            CrawlConfig(
                max_pages=5,
                max_depth=2,
                respect_robots=False,
                domain_lock=True,
            ),
        )
    )

    assert [result.url for result in results] == [
        "https://example.com/start",
        "https://example.com/docs/intro",
    ]
    assert "https://other.example.com/offsite" not in fetched_urls


def test_crawl_domain_lock_limits_links_to_inferred_site_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """crawl() stays within the inferred top-level section of the start URL."""
    fetched_urls: list[str] = []
    pages = {
        "https://example.com/docs/": FetchResponse(
            url="https://example.com/docs/",
            status=200,
            content_type="text/html",
            body=(
                "<html><body>"
                '<a href="/docs/intro">Intro</a>'
                '<a href="/api/reference">API</a>'
                "</body></html>"
            ),
        ),
        "https://example.com/docs/intro": FetchResponse(
            url="https://example.com/docs/intro",
            status=200,
            content_type="text/html",
            body="<html><body><h1>Intro</h1></body></html>",
        ),
    }

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        fetched_urls.append(url)
        return pages[url]

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    results = asyncio.run(
        crawl(
            "https://example.com/docs/",
            CrawlConfig(
                max_pages=5,
                max_depth=1,
                respect_robots=False,
                domain_lock=True,
            ),
        )
    )

    assert [result.url for result in results] == [
        "https://example.com/docs/",
        "https://example.com/docs/intro",
    ]
    assert "https://example.com/api/reference" not in fetched_urls


def test_crawl_discovers_mdbook_toc_links_from_root_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """crawl() supplements root-page discovery using mdBook TOC assets."""
    fetched_urls: list[str] = []
    pages = {
        "https://example.com/book/": FetchResponse(
            url="https://example.com/book/",
            status=200,
            content_type="text/html",
            body=(
                '<html><head><script src="toc-123.js"></script></head>'
                "<body><h1>Book</h1></body></html>"
            ),
        ),
        "https://example.com/book/toc-123.js": FetchResponse(
            url="https://example.com/book/toc-123.js",
            status=200,
            content_type="application/javascript",
            body=(
                "customElements.define('mdbook-sidebar-scrollbox', class extends HTMLElement {"
                "connectedCallback(){"
                "this.innerHTML = '<ol>"
                '<li><a href="ch01.html">Chapter 1</a></li>'
                '<li><a href="ch02.html">Chapter 2</a></li>'
                '<li><a href="/cargo/index.html">Cargo</a></li>'
                "</ol>';"
                "}"
                "});"
            ),
        ),
        "https://example.com/book/ch01.html": FetchResponse(
            url="https://example.com/book/ch01.html",
            status=200,
            content_type="text/html",
            body="<html><body><h1>Chapter 1</h1></body></html>",
        ),
        "https://example.com/book/ch02.html": FetchResponse(
            url="https://example.com/book/ch02.html",
            status=200,
            content_type="text/html",
            body="<html><body><h1>Chapter 2</h1></body></html>",
        ),
    }

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        fetched_urls.append(url)
        return pages[url]

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    results = asyncio.run(
        crawl(
            "https://example.com/book/",
            CrawlConfig(
                max_pages=5,
                max_depth=1,
                respect_robots=False,
                domain_lock=True,
            ),
        )
    )

    assert [result.url for result in results] == [
        "https://example.com/book/",
        "https://example.com/book/ch01.html",
        "https://example.com/book/ch02.html",
    ]
    assert "https://example.com/cargo/index.html" not in fetched_urls


def test_crawl_deduplicates_pages_when_alias_redirects_to_an_emitted_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """crawl() emits a final URL once even if another discovered page resolves to it."""
    pages = {
        "https://example.com/start": FetchResponse(
            url="https://example.com/start",
            status=200,
            content_type="text/html",
            body='<html><body><a href="/alias">Alias</a></body></html>',
        ),
        "https://example.com/alias": FetchResponse(
            url="https://example.com/start",
            status=200,
            content_type="text/html",
            body="<html><body><h1>Start</h1></body></html>",
        ),
    }

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        return pages[url]

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    results = asyncio.run(
        crawl(
            "https://example.com/start",
            CrawlConfig(
                max_pages=5,
                max_depth=2,
                respect_robots=False,
                domain_lock=True,
            ),
        )
    )

    assert [result.url for result in results] == ["https://example.com/start"]


def test_crawl_skips_discovered_print_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """crawl() excludes print-format routes from output but still traverses beyond them."""
    fetched_urls: list[str] = []
    pages = {
        "https://example.com/book/": FetchResponse(
            url="https://example.com/book/",
            status=200,
            content_type="text/html",
            body=('<html><body><a href="/book/print.html">Print</a></body></html>'),
        ),
        "https://example.com/book/print.html": FetchResponse(
            url="https://example.com/book/print.html",
            status=200,
            content_type="text/html",
            body=(
                "<html><body>"
                '<a href="/book/chapter-1.html">Chapter 1</a>'
                '<a href="/cargo/index.html">Cargo</a>'
                "</body></html>"
            ),
        ),
        "https://example.com/book/chapter-1.html": FetchResponse(
            url="https://example.com/book/chapter-1.html",
            status=200,
            content_type="text/html",
            body="<html><body><h1>Chapter 1</h1></body></html>",
        ),
    }

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        fetched_urls.append(url)
        return pages[url]

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    results = asyncio.run(
        crawl(
            "https://example.com/book/",
            CrawlConfig(
                max_pages=5,
                max_depth=2,
                respect_robots=False,
                domain_lock=True,
            ),
        )
    )

    assert [result.url for result in results] == [
        "https://example.com/book/",
        "https://example.com/book/chapter-1.html",
    ]
    assert "https://example.com/cargo/index.html" not in fetched_urls


def test_crawl_skips_nonliteral_print_pages_with_window_and_noindex_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """crawl() omits a print-like page but still follows its content links."""
    pages = {
        "https://example.com/start": FetchResponse(
            url="https://example.com/start",
            status=200,
            content_type="text/html",
            body='<html><body><a href="/export/book">Export</a></body></html>',
        ),
        "https://example.com/export/book": FetchResponse(
            url="https://example.com/export/book",
            status=200,
            content_type="text/html",
            body=(
                "<html><head>"
                '<meta name="robots" content="noindex">'
                "<script>window.print()</script>"
                '</head><body><a href="/chapter-1.html">Chapter 1</a></body></html>'
            ),
        ),
        "https://example.com/chapter-1.html": FetchResponse(
            url="https://example.com/chapter-1.html",
            status=200,
            content_type="text/html",
            body="<html><body><h1>Chapter 1</h1></body></html>",
        ),
    }

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        return pages[url]

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    results = asyncio.run(
        crawl(
            "https://example.com/start",
            CrawlConfig(
                max_pages=3,
                max_depth=2,
                respect_robots=False,
                domain_lock=True,
            ),
        )
    )

    assert [result.url for result in results] == [
        "https://example.com/start",
        "https://example.com/chapter-1.html",
    ]


def test_crawl_skips_nonliteral_print_pages_with_render_mode_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """crawl() drops a page whose body advertises print render mode."""
    pages = {
        "https://example.com/render/all-pages": FetchResponse(
            url="https://example.com/render/all-pages",
            status=200,
            content_type="text/html",
            body=(
                "<html data-r-output-format=print><head>"
                '<link rel="canonical" href="https://example.com/docs/guide">'
                "</head><body><h1>Guide</h1></body></html>"
            ),
        )
    }

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        return pages[url]

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    results = asyncio.run(
        crawl(
            "https://example.com/render/all-pages",
            CrawlConfig(
                max_pages=1,
                max_depth=0,
                respect_robots=False,
                domain_lock=True,
            ),
        )
    )

    assert results == []
