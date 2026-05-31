"""Bounded async crawl executor with timeout, page-cap, robots, and backoff."""

import asyncio
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from docline.fetch.http import FetchResponse, fetch_page
from docline.fetch.url_policy import CrawlUrlRejectedError, validate_crawl_url
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
    """Crawl a single page at *start_url* within the configured budget.

    Fetches *start_url* once, optionally honouring ``robots.txt`` rules and
    retrying transient failures with exponential backoff.  This is a
    single-page crawler; it does not follow links to additional pages.

    Args:
        start_url: The URL to fetch.
        config: Crawl configuration.  Uses default :class:`CrawlConfig` when
            ``None``.

    Returns:
        A list containing exactly one :class:`CrawlResult` for *start_url*:
        a successful result, or a skipped result when the page cannot be
        fetched (robots.txt disallow, retries exhausted, etc.).

    Raises:
        CrawlLimitExceededError: If ``config.max_pages`` is less than 1
            (zero-page budget cannot accommodate a single page).
        CrawlUrlRejectedError: If ``start_url`` fails URL policy validation.
    """
    crawl_config = config or CrawlConfig()

    if crawl_config.max_pages < 1:
        raise CrawlLimitExceededError(
            f"Page budget of {crawl_config.max_pages} cannot accommodate a single page."
        )

    validate_crawl_url(start_url)

    # --- Optional robots.txt check ---
    if crawl_config.respect_robots:
        parsed = urlparse(start_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            robots_resp = await fetch_page(
                robots_url,
                timeout_seconds=crawl_config.page_timeout_seconds,
                max_redirects=crawl_config.max_redirects,
            )
            if not check_robots_allowed(robots_resp.body, crawl_config.user_agent, start_url):
                return [
                    CrawlResult(
                        url=start_url,
                        skipped=True,
                        skip_reason="robots.txt disallows this URL",
                    )
                ]
        except DoclineError:
            pass  # robots.txt unreachable — proceed permissively
        except OSError:
            pass  # network error fetching robots.txt — proceed permissively

    # --- Fetch with retry / exponential backoff ---
    last_err: Exception | None = None
    for attempt in range(crawl_config.max_retries + 1):
        if attempt > 0:
            backoff = compute_backoff_seconds(attempt - 1, crawl_config.backoff_base_seconds)
            await asyncio.sleep(backoff)
        try:
            response = await fetch_page(
                start_url,
                timeout_seconds=crawl_config.page_timeout_seconds,
                max_redirects=crawl_config.max_redirects,
            )
            return [CrawlResult(url=start_url, response=response)]
        except CrawlUrlRejectedError:
            raise  # permanent policy rejection — do not retry
        except (DoclineError, OSError) as err:
            last_err = err

    return [CrawlResult(url=start_url, skipped=True, skip_reason=str(last_err))]


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
