"""Bounded async crawl executor with depth, robots, rate-limit, and backoff."""

import asyncio
import re
from collections import deque
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

from docline.fetch.http import FetchResponse, fetch_page
from docline.fetch.url_canonical import UrlCanonicalizationError, canonicalize_url
from docline.fetch.url_policy import CrawlUrlRejectedError, validate_crawl_url
from docline.schema.models import DoclineError


class CrawlLimitExceededError(DoclineError):
    """Raised when a crawl exceeds the configured page or time budget."""


class CrawlRobotsError(DoclineError):
    """Raised when the robots.txt policy disallows the requested URL."""


@dataclass(frozen=True)
class CrawlConfig:
    """Configuration for a bounded crawl session.

    Attributes:
        max_pages: Maximum number of pages to fetch before stopping.
        max_depth: Maximum discovery depth from the start URL.
        page_timeout_seconds: Per-page timeout in seconds.
        max_redirects: Redirect cap per page.
        respect_robots: Whether to parse and honour ``robots.txt`` rules.
        domain_lock: Whether discovered links must remain on the start URL host.
        user_agent: User-agent string sent with each request.
        max_retries: Maximum retry attempts for transient failures.
        backoff_base_seconds: Base interval for exponential backoff.
        rate_limit_ms: Delay between page fetches in milliseconds.
    """

    max_pages: int = 50
    max_depth: int = 0
    page_timeout_seconds: float = 30.0
    max_redirects: int = 5
    respect_robots: bool = True
    domain_lock: bool = True
    user_agent: str = "docline-crawler/1.0"
    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    rate_limit_ms: int = 0


@dataclass
class CrawlResult:
    """Outcome of crawling a single page.

    Attributes:
        url: The URL that was crawled.
        depth: Discovery depth relative to the start URL.
        response: The HTTP response, or ``None`` when the page was skipped.
        skipped: Whether the page was skipped (e.g. robots.txt disallow).
        skip_reason: Human-readable reason for skipping, if applicable.
    """

    url: str
    depth: int = 0
    response: FetchResponse | None = None
    skipped: bool = False
    skip_reason: str | None = None


class _LinkExtractor(HTMLParser):
    """Collect href values from HTML anchors and the first base href."""

    def __init__(self) -> None:
        super().__init__()
        self.base_href: str | None = None
        self.hrefs: list[str] = []
        self.script_srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record link targets from ``<base>`` and ``<a>`` tags."""
        attrs_map = {name.lower(): value for name, value in attrs}
        lowered = tag.lower()
        if lowered == "base" and self.base_href is None:
            href = attrs_map.get("href")
            if href:
                self.base_href = href
        if lowered == "a":
            href = attrs_map.get("href")
            if href:
                self.hrefs.append(href)
        if lowered == "script":
            src = attrs_map.get("src")
            if src:
                self.script_srcs.append(src)


async def crawl(
    start_url: str,
    config: CrawlConfig | None = None,
) -> list[CrawlResult]:
    """Crawl *start_url* within the configured page and depth budgets.

    Performs a bounded breadth-first crawl starting at *start_url*,
    optionally honouring ``robots.txt`` rules and constraining discovery to the
    start URL host. Each page fetch uses retry/backoff semantics and contributes
    one :class:`CrawlResult`.

    Args:
        start_url: The URL to fetch.
        config: Crawl configuration.  Uses default :class:`CrawlConfig` when
            ``None``.

    Returns:
        A list of :class:`CrawlResult` values, in breadth-first discovery order,
        up to ``config.max_pages`` items.

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

    start = _normalize_url(validate_crawl_url(start_url))
    start_host = urlparse(start).netloc
    section_scope = _derive_section_scope(start)
    frontier: deque[tuple[str, int]] = deque([(start, 0)])
    visited: set[str] = {_dedup_key(start)}
    emitted_urls: set[str] = set()
    robots_cache: dict[str, str | None] = {}
    results: list[CrawlResult] = []
    page_count = 0

    while frontier and page_count < crawl_config.max_pages:
        current_url, depth = frontier.popleft()

        if crawl_config.respect_robots and not await _robots_allow(
            current_url,
            crawl_config,
            robots_cache,
        ):
            results.append(
                CrawlResult(
                    url=current_url,
                    depth=depth,
                    skipped=True,
                    skip_reason="robots.txt disallows this URL",
                )
            )
            page_count += 1
            continue

        if crawl_config.rate_limit_ms > 0 and page_count > 0:
            await asyncio.sleep(crawl_config.rate_limit_ms / 1000.0)

        try:
            response = await _fetch_with_retries(current_url, crawl_config)
        except CrawlUrlRejectedError:
            raise
        except (DoclineError, OSError) as err:
            results.append(
                CrawlResult(
                    url=current_url,
                    depth=depth,
                    skipped=True,
                    skip_reason=str(err),
                )
            )
            page_count += 1
            continue

        final_url = _normalize_url(response.url)
        if crawl_config.domain_lock and urlparse(final_url).netloc != start_host:
            results.append(
                CrawlResult(
                    url=final_url,
                    depth=depth,
                    skipped=True,
                    skip_reason="redirect resolved outside locked domain",
                )
            )
            page_count += 1
            continue
        if crawl_config.domain_lock and not _url_within_section_scope(final_url, section_scope):
            continue

        if _is_print_page(final_url, response.body):
            visited.add(_dedup_key(final_url))
            if depth < crawl_config.max_depth and _is_html_response(response):
                for link in extract_links(response.body, final_url):
                    if crawl_config.domain_lock and urlparse(link).netloc != start_host:
                        continue
                    if crawl_config.domain_lock and not _url_within_section_scope(
                        link, section_scope
                    ):
                        continue
                    link_key = _dedup_key(link)
                    if link_key in visited:
                        continue
                    visited.add(link_key)
                    frontier.append((link, depth + 1))
            continue

        final_key = _dedup_key(final_url)
        if final_key in emitted_urls:
            visited.add(final_key)
            continue

        visited.add(final_key)
        emitted_urls.add(final_key)

        results.append(CrawlResult(url=final_url, depth=depth, response=response))
        page_count += 1

        if depth >= crawl_config.max_depth:
            continue
        if not _is_html_response(response):
            continue

        discovered_links = extract_links(response.body, final_url)
        if depth == 0:
            discovered_links.extend(
                await _discover_toc_links(
                    response.body,
                    final_url,
                    crawl_config,
                    start_host=start_host,
                    section_scope=section_scope,
                )
            )

        for link in discovered_links:
            if crawl_config.domain_lock and urlparse(link).netloc != start_host:
                continue
            if crawl_config.domain_lock and not _url_within_section_scope(link, section_scope):
                continue
            link_key = _dedup_key(link)
            if link_key in visited:
                continue
            visited.add(link_key)
            frontier.append((link, depth + 1))

    return results


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


def extract_links(html_text: str, page_url: str) -> list[str]:
    """Extract normalized absolute HTTP(S) links from HTML content.

    Args:
        html_text: HTML page body.
        page_url: Canonical URL of the page that produced *html_text*.

    Returns:
        Normalized absolute links discovered in document order.
    """
    parser = _LinkExtractor()
    parser.feed(html_text)
    base_url = urljoin(page_url, parser.base_href) if parser.base_href else page_url

    links: list[str] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        normalized_href = href.strip()
        if not normalized_href:
            continue
        if normalized_href.startswith(("#", "mailto:", "javascript:", "data:", "tel:")):
            continue
        try:
            absolute = _normalize_url(validate_crawl_url(urljoin(base_url, normalized_href)))
        except CrawlUrlRejectedError:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)
    return links


def extract_toc_script_urls(html_text: str, page_url: str) -> list[str]:
    """Extract mdBook-style TOC script URLs from HTML content."""
    parser = _LinkExtractor()
    parser.feed(html_text)

    script_urls: list[str] = []
    seen: set[str] = set()
    for script_src in parser.script_srcs:
        normalized_src = script_src.strip()
        if not normalized_src:
            continue
        basename = normalized_src.rsplit("/", 1)[-1].lower()
        if not (basename.startswith("toc-") and basename.endswith(".js")):
            continue
        try:
            absolute = _normalize_url(validate_crawl_url(urljoin(page_url, normalized_src)))
        except CrawlUrlRejectedError:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        script_urls.append(absolute)
    return script_urls


def extract_toc_links(script_text: str, page_url: str) -> list[str]:
    """Extract page links from an mdBook TOC script payload."""
    links: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r'href=(?P<quote>["\'])(?P<href>.*?)(?P=quote)', script_text):
        normalized_href = match.group("href").strip()
        if not normalized_href:
            continue
        if normalized_href.startswith(("#", "mailto:", "javascript:", "data:", "tel:")):
            continue
        try:
            absolute = _normalize_url(validate_crawl_url(urljoin(page_url, normalized_href)))
        except CrawlUrlRejectedError:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)
    return links


async def _fetch_with_retries(url: str, crawl_config: CrawlConfig) -> FetchResponse:
    """Fetch one page with the configured retry/backoff policy."""
    last_err: Exception | None = None
    for attempt in range(crawl_config.max_retries + 1):
        if attempt > 0:
            backoff = compute_backoff_seconds(attempt - 1, crawl_config.backoff_base_seconds)
            await asyncio.sleep(backoff)
        try:
            return await fetch_page(
                url,
                timeout_seconds=crawl_config.page_timeout_seconds,
                max_redirects=crawl_config.max_redirects,
            )
        except CrawlUrlRejectedError:
            raise
        except (DoclineError, OSError) as err:
            last_err = err
    if last_err is None:
        raise CrawlLimitExceededError(f"Unable to fetch {url!r} within retry budget")
    raise last_err


async def _robots_allow(
    url: str,
    crawl_config: CrawlConfig,
    robots_cache: dict[str, str | None],
) -> bool:
    """Return whether ``robots.txt`` permits crawling *url*."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in robots_cache:
        robots_url = f"{origin}/robots.txt"
        try:
            robots_resp = await fetch_page(
                robots_url,
                timeout_seconds=crawl_config.page_timeout_seconds,
                max_redirects=crawl_config.max_redirects,
            )
            robots_cache[origin] = robots_resp.body
        except DoclineError:
            robots_cache[origin] = None
        except OSError:
            robots_cache[origin] = None

    robots_txt = robots_cache[origin]
    if robots_txt is None:
        return True
    return check_robots_allowed(robots_txt, crawl_config.user_agent, url)


def _is_html_response(response: FetchResponse) -> bool:
    """Return True when a response appears to contain HTML content."""
    content_type = (response.content_type or "").lower()
    return "html" in content_type or "<html" in response.body.lower()


def _normalize_url(url: str) -> str:
    """Remove fragments and normalize empty paths for crawl bookkeeping."""
    without_fragment, _ = urldefrag(url)
    parsed = urlparse(without_fragment)
    normalized_path = parsed.path or "/"
    return parsed._replace(path=normalized_path, fragment="").geturl()


def _dedup_key(url: str) -> str:
    """Return a canonical dedup key for *url*.

    Wraps :func:`canonicalize_url` to collapse aliases that differ only in
    query order, tracking parameters, scheme/host case, fragments, or default
    ports. Falls back to :func:`_normalize_url` when canonicalization fails so
    dedup never raises during normal crawl iteration.
    """
    try:
        return canonicalize_url(url)
    except UrlCanonicalizationError:
        return _normalize_url(url)


async def _discover_toc_links(
    html_text: str,
    page_url: str,
    crawl_config: CrawlConfig,
    *,
    start_host: str,
    section_scope: str | None,
) -> list[str]:
    """Fetch mdBook TOC assets referenced by the root page and extract page links."""
    links: list[str] = []
    seen: set[str] = set()
    for script_url in extract_toc_script_urls(html_text, page_url):
        if crawl_config.domain_lock and urlparse(script_url).netloc != start_host:
            continue
        if crawl_config.domain_lock and not _url_within_section_scope(script_url, section_scope):
            continue
        try:
            response = await _fetch_with_retries(script_url, crawl_config)
        except CrawlUrlRejectedError:
            raise
        except (DoclineError, OSError):
            continue
        for link in extract_toc_links(response.body, page_url):
            if crawl_config.domain_lock and urlparse(link).netloc != start_host:
                continue
            if crawl_config.domain_lock and not _url_within_section_scope(link, section_scope):
                continue
            if link in seen:
                continue
            seen.add(link)
            links.append(link)
    return links


def _derive_section_scope(url: str) -> str | None:
    """Infer a section prefix that bounds a crawl to the start URL's subtree.

    Uses the **full directory prefix** of the start URL so a crawl of a
    sub-path (e.g. ``/docs/current/``) stays within that subsection and does
    not wander into sibling subsections (e.g. other ``/docs/<version>/`` trees).
    A directory URL scopes to itself; a file URL scopes to its parent
    directory. A bare-root or ambiguous extensionless path imposes no scope
    (the crawl is then bounded only by ``domain_lock``).
    """
    path = urlparse(url).path or "/"
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return None
    if path.endswith("/"):
        return path
    if "." in segments[-1]:
        parent = path.rsplit("/", 1)[0]
        return f"{parent}/" if parent else None
    return None


def _url_within_section_scope(url: str, section_scope: str | None) -> bool:
    """Return True when *url* remains inside the inferred site section."""
    if not section_scope:
        return True
    path = urlparse(url).path or "/"
    normalized_scope = section_scope.rstrip("/")
    return path == normalized_scope or path.startswith(section_scope)


def _is_print_page(url: str, body: str | None = None) -> bool:
    """Return True when a URL looks like a site-wide print page."""
    parsed = urlparse(url)
    basename = parsed.path.rstrip("/").rsplit("/", 1)[-1].lower()
    if basename in {"print", "print.html", "print.htm"}:
        return True

    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if "print" in key.lower() or "print" in value.lower():
            return True

    if body is None:
        return False

    lowered = body.lower()
    if "window.print" in lowered and "noindex" in lowered:
        return True
    if "data-r-output-format=print" in lowered and "canonical" in lowered:
        return True
    if 'data-r-output-format="print"' in lowered and "canonical" in lowered:
        return True

    return False


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
    "extract_links",
    "crawl",
]
