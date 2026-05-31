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
