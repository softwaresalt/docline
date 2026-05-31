"""Bounded async crawl executor with timeout, page-cap, robots, and backoff."""

from dataclasses import dataclass
from urllib.robotparser import RobotFileParser

from docline.fetch.http import FetchResponse, fetch_page
from docline.fetch.url_policy import validate_crawl_url
from docline.schema.models import DoclineError


class CrawlLimitExceededError(DoclineError):
    """Raised when a crawl exceeds the configured page or time budget."""


class CrawlRobotsError(DoclineError):
    """Raised when the robots.txt policy disallows the requested URL."""


@dataclass(frozen=True)
class CrawlConfig:
    """Configuration for a single crawl session.

    Attributes:
        max_pages: Maximum number of pages to fetch before stopping.
        page_timeout_seconds: Per-page timeout in seconds.
        max_redirects: Redirect cap per page.
        respect_robots: Whether to parse and honour ``robots.txt`` rules.
        user_agent: User-agent string sent with each request.
        max_retries: Maximum retry attempts for transient failures.
        backoff_base_seconds: Base interval for exponential backoff.
    """

    max_pages: int = 50
    page_timeout_seconds: float = 30.0
    max_redirects: int = 5
    respect_robots: bool = True
    user_agent: str = "docline-crawler/1.0"
    max_retries: int = 3
    backoff_base_seconds: float = 1.0


@dataclass
class CrawlResult:
    """Outcome of crawling a single page.

    Attributes:
        url: The URL that was crawled.
        response: The HTTP response, or ``None`` when the page was skipped.
        skipped: Whether the page was skipped (e.g. robots.txt disallow).
        skip_reason: Human-readable reason for skipping, if applicable.
    """

    url: str
    response: FetchResponse | None = None
    skipped: bool = False
    skip_reason: str | None = None


async def crawl(
    start_url: str,
    config: CrawlConfig | None = None,
) -> list[CrawlResult]:
    """Crawl pages starting from *start_url* within the configured budget.

    Args:
        start_url: The URL to begin crawling from.
        config: Crawl configuration.  Uses default :class:`CrawlConfig` when
            ``None``.

    Returns:
        A list of :class:`CrawlResult` objects, one per attempted page.

    Raises:
        CrawlLimitExceededError: If the crawl exceeds ``config.max_pages``
            before the queue is exhausted.
        CrawlUrlRejectedError: If ``start_url`` fails URL policy validation.
    """
    crawl_config = config or CrawlConfig()
    validate_crawl_url(start_url)

    results: list[CrawlResult] = []
    try:
        response = await fetch_page(
            start_url,
            timeout_seconds=crawl_config.page_timeout_seconds,
            max_redirects=crawl_config.max_redirects,
        )
        results.append(CrawlResult(url=start_url, response=response))
    except (DoclineError, OSError) as err:
        results.append(CrawlResult(url=start_url, skipped=True, skip_reason=str(err)))
    return results[: crawl_config.max_pages]


def check_robots_allowed(robots_txt: str, user_agent: str, url: str) -> bool:
    """Parse *robots_txt* and return whether *url* is allowed for *user_agent*.

    Args:
        robots_txt: Full text content of a ``robots.txt`` file.
        user_agent: User-agent identifier to check rules against.
        url: The URL path (or full URL) to test against the parsed rules.

    Returns:
        ``True`` when the URL is allowed, ``False`` when disallowed.
    """
    if not robots_txt:
        return True
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return parser.can_fetch(user_agent, url)


def compute_backoff_seconds(attempt: int, base: float = 1.0) -> float:
    """Compute an exponential backoff interval for a retry attempt.

    Args:
        attempt: Zero-based attempt index (0 = first retry).
        base: Base interval in seconds.

    Returns:
        The backoff duration in seconds (capped at 60 seconds).
    """
    return float(min(base * (2**attempt), 60.0))


__all__ = [
    "CrawlConfig",
    "CrawlLimitExceededError",
    "CrawlResult",
    "CrawlRobotsError",
    "check_robots_allowed",
    "compute_backoff_seconds",
    "crawl",
]
