"""Bounded async crawl executor with depth, robots, rate-limit, and backoff."""

import asyncio
import logging
from collections.abc import Callable
from urllib.parse import urlparse

from docline.fetch.crawl_discovery import check_robots_allowed, compute_backoff_seconds
from docline.fetch.crawl_links import (
    _dedup_key,
    _derive_section_scope,
    _has_eligible_link,
    _has_eligible_toc_script,
    _is_print_page,
    _iter_eligible_links,
    _normalize_url,
    _origin_label,
    _url_within_section_scope,
    extract_links,
    extract_toc_links,
    extract_toc_script_urls,
)
from docline.fetch.crawl_models import (
    MAX_FRONTIER,
    CrawlConfig,
    CrawlLimitExceededError,
    CrawlOutcome,
    CrawlResult,
    CrawlRobotsError,
    _Frontier,
)
from docline.fetch.http import (
    MAX_FETCH_ATTEMPTS,
    MAX_TOTAL_FETCH_BYTES,
    AggregateBudgetExceededError,
    FetchResponse,
    RemainingByteBudget,
    fetch_page,
)
from docline.fetch.url_policy import CrawlUrlRejectedError, validate_crawl_url
from docline.schema.models import DoclineError

logger = logging.getLogger(__name__)


async def crawl(
    start_url: str,
    config: CrawlConfig | None = None,
    progress: Callable[[int, int | None, str], None] | None = None,
) -> CrawlOutcome:
    """Crawl *start_url* within the configured page and depth budgets.

    Performs a bounded breadth-first crawl starting at *start_url*,
    optionally honouring ``robots.txt`` rules and constraining discovery to the
    start URL host. Each page fetch uses retry/backoff semantics and contributes
    one :class:`CrawlResult`.

    Args:
        start_url: The URL to fetch.
        config: Crawl configuration.  Uses default :class:`CrawlConfig` when
            ``None``.
        progress: Optional callback invoked once per *budget-consuming* page as
            ``progress(page_count, config.max_pages, url)``. It fires on each
            ``page_count`` increment (fetched pages plus robots-denied, failed,
            and domain-rejected URLs) and is a budget-consumed signal, not a
            staged-page count. URLs that skip without consuming the budget (out
            of section scope, print pages, duplicate finals) do not fire it.

    Returns:
        A :class:`CrawlOutcome` whose ``results`` are the :class:`CrawlResult`
        values in breadth-first discovery order (up to ``config.max_pages``
        items) and whose ``frontier_truncated`` flag is ``True`` when the
        admission ceiling actually refused an eligible discovered link.

    Note:
        Discovered-link admissions to the frontier are capped at
        ``config.max_frontier`` for the whole crawl, independently of
        ``config.max_pages`` and ``config.max_depth``. The start URL is never
        subject to the cap, and breadth-first order is preserved for admitted
        links.

    Raises:
        CrawlLimitExceededError: If ``config.max_pages`` is less than 1
            (zero-page budget cannot accommodate a single page), or if
            ``config.max_frontier`` is negative.
        CrawlUrlRejectedError: If ``start_url`` fails URL policy validation.
    """
    crawl_config = config or CrawlConfig()

    if crawl_config.max_pages < 1:
        raise CrawlLimitExceededError(
            f"Page budget of {crawl_config.max_pages} cannot accommodate a single page."
        )

    if crawl_config.max_frontier < 0:
        raise CrawlLimitExceededError(
            f"Frontier ceiling of {crawl_config.max_frontier} is negative; "
            "use 0 to disable link discovery."
        )

    start = _normalize_url(validate_crawl_url(start_url))
    start_host = urlparse(start).netloc
    section_scope = _derive_section_scope(start)
    frontier = _Frontier(
        max_frontier=crawl_config.max_frontier,
        start_label=_origin_label(start),
    )
    frontier.queue.append((start, 0))
    visited: set[str] = {_dedup_key(start)}
    emitted_urls: set[str] = set()
    robots_cache: dict[str, str | None] = {}
    results: list[CrawlResult] = []
    page_count = 0
    # Request-scoped aggregate byte + fetch-attempt budget threaded through every
    # fetch_page call so no auxiliary/retry/redirect traffic bypasses the bound.
    budget = RemainingByteBudget(MAX_TOTAL_FETCH_BYTES, max_attempts=MAX_FETCH_ATTEMPTS)

    while frontier.queue and page_count < crawl_config.max_pages:
        current_url, depth = frontier.queue.popleft()

        if crawl_config.respect_robots and not await _robots_allow(
            current_url,
            crawl_config,
            robots_cache,
            budget,
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
            if progress is not None:
                progress(page_count, crawl_config.max_pages, current_url)
            continue

        if crawl_config.rate_limit_ms > 0 and page_count > 0:
            await asyncio.sleep(crawl_config.rate_limit_ms / 1000.0)

        try:
            response = await _fetch_with_retries(current_url, crawl_config, budget)
        except CrawlUrlRejectedError:
            raise
        except AggregateBudgetExceededError:
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
            if progress is not None:
                progress(page_count, crawl_config.max_pages, current_url)
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
            if progress is not None:
                progress(page_count, crawl_config.max_pages, current_url)
            continue
        if crawl_config.domain_lock and not _url_within_section_scope(final_url, section_scope):
            continue

        if _is_print_page(final_url, response.body):
            visited.add(_dedup_key(final_url))
            if depth < crawl_config.max_depth and _is_html_response(response):
                page_links = extract_links(response.body, final_url)
                if frontier.exhausted:
                    # Cap already full: skip admission but still parse links in
                    # memory to record a truncation only when an eligible
                    # candidate was actually dropped.
                    if _has_eligible_link(
                        page_links,
                        domain_lock=crawl_config.domain_lock,
                        start_host=start_host,
                        section_scope=section_scope,
                        visited=visited,
                    ):
                        frontier.refused_any = True
                        frontier.report_ceiling()
                else:
                    for link, link_key in _iter_eligible_links(
                        page_links,
                        domain_lock=crawl_config.domain_lock,
                        start_host=start_host,
                        section_scope=section_scope,
                        visited=visited,
                    ):
                        if not frontier.admit(link, link_key, depth + 1, visited):
                            break
            continue

        final_key = _dedup_key(final_url)
        if final_key in emitted_urls:
            visited.add(final_key)
            continue

        visited.add(final_key)
        emitted_urls.add(final_key)

        results.append(CrawlResult(url=final_url, depth=depth, response=response))
        page_count += 1
        if progress is not None:
            progress(page_count, crawl_config.max_pages, current_url)

        if depth >= crawl_config.max_depth:
            continue
        if not _is_html_response(response):
            continue

        anchor_links = extract_links(response.body, final_url)
        if frontier.exhausted:
            # The ceiling is exhausted, so every discovered link would be
            # refused. Skip the TOC *network* discovery, but still parse links
            # (and, at depth zero, TOC script references) in memory to record a
            # truncation only when an eligible candidate was actually dropped.
            if _has_eligible_link(
                anchor_links,
                domain_lock=crawl_config.domain_lock,
                start_host=start_host,
                section_scope=section_scope,
                visited=visited,
            ):
                frontier.refused_any = True
                frontier.report_ceiling()
            elif depth == 0 and _has_eligible_toc_script(
                response.body,
                final_url,
                domain_lock=crawl_config.domain_lock,
                start_host=start_host,
                section_scope=section_scope,
            ):
                frontier.refused_any = True
                frontier.report_ceiling()
            continue

        discovered_links = anchor_links
        if depth == 0:
            # TOC-derived navigation is ordered ahead of in-page anchors so an
            # admission-competition drop sheds anchors, not authoritative TOC (D6).
            discovered_links = (
                await _discover_toc_links(
                    response.body,
                    final_url,
                    crawl_config,
                    start_host=start_host,
                    section_scope=section_scope,
                    budget=budget,
                )
                + anchor_links
            )

        for link, link_key in _iter_eligible_links(
            discovered_links,
            domain_lock=crawl_config.domain_lock,
            start_host=start_host,
            section_scope=section_scope,
            visited=visited,
        ):
            if not frontier.admit(link, link_key, depth + 1, visited):
                break

    return CrawlOutcome(results=results, frontier_truncated=frontier.truncated)


async def _fetch_with_retries(
    url: str,
    crawl_config: CrawlConfig,
    budget: "RemainingByteBudget | None" = None,
) -> FetchResponse:
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
                budget=budget,
            )
        except CrawlUrlRejectedError:
            raise
        except AggregateBudgetExceededError:
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
    budget: "RemainingByteBudget | None" = None,
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
                budget=budget,
            )
            robots_cache[origin] = robots_resp.body
        except AggregateBudgetExceededError:
            raise
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


async def _discover_toc_links(
    html_text: str,
    page_url: str,
    crawl_config: CrawlConfig,
    *,
    start_host: str,
    section_scope: str | None,
    budget: "RemainingByteBudget | None" = None,
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
            response = await _fetch_with_retries(script_url, crawl_config, budget)
        except CrawlUrlRejectedError:
            raise
        except AggregateBudgetExceededError:
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


__all__ = [
    "MAX_FRONTIER",
    "CrawlConfig",
    "CrawlLimitExceededError",
    "CrawlOutcome",
    "CrawlResult",
    "CrawlRobotsError",
    "check_robots_allowed",
    "compute_backoff_seconds",
    "extract_links",
    "crawl",
]
