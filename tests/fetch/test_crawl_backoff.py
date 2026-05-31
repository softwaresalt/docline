"""Test harness for 003.003-T — Add robots and backoff controls.

Acceptance criteria:
- check_robots_allowed() returns True when URL is allowed, False when disallowed.
- compute_backoff_seconds() returns exponentially increasing float intervals.
- CrawlRobotsError is a DoclineError subclass.
- CrawlConfig exposes respect_robots, max_retries, and backoff_base_seconds.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests assert return values (FAIL in red phase).
"""

from docline.fetch.crawl import (
    CrawlConfig,
    CrawlRobotsError,
    check_robots_allowed,
    compute_backoff_seconds,
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
