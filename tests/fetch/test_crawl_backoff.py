"""Test harness for 003.003-T — Add robots and backoff controls.

Acceptance criteria:
- check_robots_allowed() returns True when URL is allowed, False when disallowed.
- compute_backoff_seconds() returns exponentially increasing float intervals.
- CrawlRobotsError is a DoclineError subclass.
- CrawlConfig exposes respect_robots, max_retries, and backoff_base_seconds.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests assert return values (FAIL in red phase).
"""

import asyncio

import pytest

from docline.fetch.crawl import (
    CrawlConfig,
    CrawlRobotsError,
    check_robots_allowed,
    compute_backoff_seconds,
    crawl,
)
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Structural: error hierarchy and config fields (PASS in red phase)
# ---------------------------------------------------------------------------


def test_crawl_robots_error_is_docline_error() -> None:
    """CrawlRobotsError is a subclass of DoclineError."""
    err = CrawlRobotsError("disallowed by robots.txt")
    assert isinstance(err, DoclineError)


def test_crawl_config_default_respect_robots_is_true() -> None:
    """CrawlConfig defaults respect_robots to True."""
    config = CrawlConfig()
    assert config.respect_robots is True


def test_crawl_config_default_max_retries_non_negative() -> None:
    """CrawlConfig has a non-negative default max_retries."""
    config = CrawlConfig()
    assert config.max_retries >= 0


def test_crawl_config_default_backoff_base_positive() -> None:
    """CrawlConfig has a positive default backoff_base_seconds."""
    config = CrawlConfig()
    assert config.backoff_base_seconds > 0


def test_crawl_config_custom_respect_robots_false() -> None:
    """CrawlConfig accepts respect_robots=False."""
    config = CrawlConfig(respect_robots=False)
    assert config.respect_robots is False


def test_crawl_config_custom_max_retries() -> None:
    """CrawlConfig accepts custom max_retries."""
    config = CrawlConfig(max_retries=5)
    assert config.max_retries == 5


# ---------------------------------------------------------------------------
# Behavioral: check_robots_allowed (FAIL in red phase)
# ---------------------------------------------------------------------------

_ALLOW_ALL_ROBOTS = "User-agent: *\nAllow: /\n"
_DISALLOW_PRIVATE_ROBOTS = "User-agent: *\nDisallow: /private/\n"


def test_check_robots_allowed_returns_true_for_allow_all() -> None:
    """check_robots_allowed returns True when all paths are allowed."""
    result = check_robots_allowed(_ALLOW_ALL_ROBOTS, "*", "https://example.com/page")
    assert result is True


def test_check_robots_allowed_returns_false_for_disallowed_path() -> None:
    """check_robots_allowed returns False for a Disallow-matched path."""
    result = check_robots_allowed(_DISALLOW_PRIVATE_ROBOTS, "*", "https://example.com/private/doc")
    assert result is False


def test_check_robots_allowed_returns_true_for_non_disallowed_path() -> None:
    """check_robots_allowed returns True for a path not covered by Disallow."""
    result = check_robots_allowed(_DISALLOW_PRIVATE_ROBOTS, "*", "https://example.com/public/doc")
    assert result is True


def test_check_robots_allowed_empty_robots_allows_all() -> None:
    """check_robots_allowed returns True for an empty robots.txt."""
    result = check_robots_allowed("", "*", "https://example.com/page")
    assert result is True


# ---------------------------------------------------------------------------
# Behavioral: compute_backoff_seconds (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_compute_backoff_first_attempt_returns_positive_float() -> None:
    """compute_backoff_seconds returns a positive float for attempt 0."""
    result = compute_backoff_seconds(0)
    assert isinstance(result, float)
    assert result > 0


def test_compute_backoff_increases_with_attempts() -> None:
    """compute_backoff_seconds returns a larger value for higher attempt numbers."""
    first = compute_backoff_seconds(0)
    second = compute_backoff_seconds(1)
    assert second > first


def test_compute_backoff_is_capped_at_sixty_seconds() -> None:
    """compute_backoff_seconds does not exceed 60 seconds."""
    result = compute_backoff_seconds(100)
    assert result <= 60.0


def test_compute_backoff_custom_base_scales_output() -> None:
    """compute_backoff_seconds with base=2.0 is larger than base=1.0."""
    default = compute_backoff_seconds(1, base=1.0)
    doubled = compute_backoff_seconds(1, base=2.0)
    assert doubled > default


# ---------------------------------------------------------------------------
# Behavioral: crawl() wires retry/backoff and robots (no live network)
# ---------------------------------------------------------------------------


def test_crawl_retries_transient_fetch_failure_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """crawl() retries a transient FetchError and returns the successful result.

    Verifies that the retry/backoff loop around fetch_page is wired: the first
    attempt raises FetchError; the second attempt succeeds.  backoff_base_seconds
    is set to 0.0 so the test does not sleep.
    """
    from docline.fetch.http import FetchError, FetchResponse

    attempt_count = 0
    success_response = FetchResponse(
        url="https://example.com",
        status=200,
        content_type="text/html",
        body="<html>ok</html>",
    )

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
    ) -> FetchResponse:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            raise FetchError("transient connection error")
        return success_response

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    config = CrawlConfig(
        respect_robots=False,
        max_retries=2,
        backoff_base_seconds=0.0,
    )
    results = asyncio.run(crawl("https://example.com", config))

    assert len(results) == 1
    assert results[0].skipped is False
    assert results[0].response is not None
    assert attempt_count == 2, (
        f"Expected 2 fetch attempts (1 fail + 1 success), got {attempt_count}"
    )


def test_crawl_returns_skipped_result_when_robots_txt_disallows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """crawl() returns a skipped CrawlResult when robots.txt disallows the URL.

    Verifies that the respect_robots config knob is wired: when robots.txt
    contains a Disallow rule matching start_url, the page is skipped without
    being fetched.
    """
    from docline.fetch.http import FetchResponse

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
    ) -> FetchResponse:
        if "robots.txt" in url:
            return FetchResponse(
                url=url,
                status=200,
                content_type="text/plain",
                body="User-agent: *\nDisallow: /\n",
            )
        raise AssertionError(f"Should not fetch page URL when robots disallows: {url!r}")

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)

    config = CrawlConfig(respect_robots=True, max_retries=0)
    results = asyncio.run(crawl("https://example.com/page", config))

    assert len(results) == 1
    assert results[0].skipped is True, "Result must be marked skipped when robots.txt disallows"
    assert results[0].skip_reason is not None
    assert "robots" in results[0].skip_reason.lower(), (
        f"skip_reason should mention robots, got: {results[0].skip_reason!r}"
    )
