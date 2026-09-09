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
    _link_in_scope,
    _normalize_url,
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
    _origin_label,
)
from docline.fetch.http import (
    MAX_FETCH_ATTEMPTS,
    MAX_TOTAL_FETCH_BYTES,
    AggregateBudgetExceededError,
    FetchResponse,
    RemainingByteBudget,
    fetch_page,
)
from docline.fetch.link_sources import DiscoverySource, find_source, register
from docline.fetch.tf_registry_source import TfRegistrySource
from docline.fetch.url_policy import CrawlUrlRejectedError, validate_crawl_url
from docline.schema.models import DoclineError

logger = logging.getLogger(__name__)

# Composition point (070.010-T): the concrete Terraform Registry adapter
# registers itself here, at import time, exactly once per process -- the
# generic seam (link_sources.py) never imports a concrete provider adapter,
# so a future site adapter only ever needs a new registration line here.
register(TfRegistrySource())


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
        A :class:`CrawlOutcome`: ``results`` are the :class:`CrawlResult` values
        in breadth-first discovery order (up to ``config.max_pages`` items), and
        ``frontier_truncated`` reports whether the ceiling cost the crawl an
        eligible link — deliberately conservative per :class:`CrawlOutcome`.

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

    if crawl_config.enable_api_discovery and crawl_config.max_frontier > 0:
        # max_frontier == 0 means "disable link discovery entirely" (see
        # CrawlConfig's own docstring) -- skip the seed call outright rather
        # than entering _seed_from_discovery_source only to have its first
        # ceiling check immediately report a false-positive truncation before
        # ever asking the source for a single item.
        source = find_source(start)
        if source is not None:
            await _seed_from_discovery_source(
                source,
                start,
                crawl_config,
                frontier=frontier,
                visited=visited,
                start_host=start_host,
                section_scope=section_scope,
                budget=budget,
            )

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
                    # Cap full: parse in memory, record truncation only on a real drop.
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
            # Ceiling exhausted: skip TOC *network* discovery but still parse
            # links (and depth-zero TOC scripts) to record a real drop only.
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


async def _seed_from_discovery_source(
    source: DiscoverySource,
    start_url: str,
    crawl_config: CrawlConfig,
    *,
    frontier: _Frontier,
    visited: set[str],
    start_host: str,
    section_scope: str | None,
    budget: "RemainingByteBudget | None",
) -> None:
    """Seed the frontier from a recognized discovery source, once, at crawl start.

    Lazily drains *source*'s async generator, admitting each in-scope,
    not-yet-visited URL through the SAME frontier ceiling, domain-lock/section
    -scope filter, and dedup rules static links go through (I5/I6
    defense-in-depth at this composition layer, independent of whatever the
    concrete adapter itself already guarantees).

    Checks the frontier ceiling *before* pulling each item (not after, unlike
    the existing admit-then-check pattern used for already-parsed in-memory
    anchor links) so a paginated, network-backed source is never driven to
    fetch one further page just to have it refused -- this is what keeps a
    1,620-document provider's enumeration bounded by ``max_frontier`` rather
    than by the provider's own document count. Caller guarantees
    ``crawl_config.max_frontier > 0`` before invoking this function, so its
    ceiling check is never the *first* check performed (which would otherwise
    report truncation without ever having asked the source for an item).

    This check-before-pull ordering trades a small conservative-over-report
    risk for that efficiency: if the source's remaining item count happens to
    exactly equal the remaining frontier capacity, this reports
    ``frontier_truncated=True`` even though nothing was actually dropped,
    because confirming otherwise would require pulling one further item --
    exactly the network cost this ordering exists to avoid. This mirrors the
    already-documented depth-zero ``toc-*.js`` conservative case (D3):
    over-reporting is tolerated, under-reporting is not.

    A narrow adapter failure (any other :class:`DoclineError`) is logged once
    and degrades to static-only extraction for the rest of the crawl.
    :class:`AggregateBudgetExceededError` and
    :class:`~docline.fetch.url_policy.CrawlUrlRejectedError` are never masked
    here (I4 carve-out): they propagate uncaught out of ``crawl()``.

    On any non-error completion (the source exhausts naturally, or the
    frontier ceiling stops it), a single INFO record reports the sanitized
    crawl origin plus the number of URLs actually seeded -- observability for
    what is potentially a large, silent admission of many URLs from a single
    third-party API response.
    """
    seeded_count = 0
    iterator = source.discover_doc_urls(start_url, crawl_config, budget).__aiter__()
    while True:
        if frontier.exhausted:
            # This early check-before-pull path never calls frontier.admit()
            # while exhausted, so it must record the drop itself -- admit()'s
            # own refusal branch is never reached from this loop.
            frontier.refused_any = True
            frontier.report_ceiling()
            _log_seed_summary(start_url, seeded_count)
            return
        try:
            discovered_url = await iterator.__anext__()
        except StopAsyncIteration:
            _log_seed_summary(start_url, seeded_count)
            return
        except (AggregateBudgetExceededError, CrawlUrlRejectedError):
            raise
        except DoclineError:
            logger.warning(
                "Discovery source failed for crawl origin %s; falling back to "
                "static link extraction.",
                _origin_label(start_url),
            )
            return

        try:
            normalized = _normalize_url(validate_crawl_url(discovered_url))
        except CrawlUrlRejectedError:
            # A malformed/invalid discovered URL is skipped, not fatal --
            # mirrors how an ineligible static anchor is silently dropped.
            continue
        if not _link_in_scope(
            normalized,
            domain_lock=crawl_config.domain_lock,
            start_host=start_host,
            section_scope=section_scope,
        ):
            continue
        link_key = _dedup_key(normalized)
        if link_key in visited:
            continue
        if frontier.admit(normalized, link_key, 1, visited):
            seeded_count += 1


def _log_seed_summary(start_url: str, seeded_count: int) -> None:
    """Log one INFO record summarizing a completed discovery-source seed.

    Payload is the sanitized crawl origin plus the admitted-URL count -- never
    the raw start URL or any discovered URL -- matching the same
    credential-safe logging posture as :meth:`_Frontier.report_ceiling`.
    """
    logger.info(
        "Discovery source seeded %d URL(s) for crawl origin %s.",
        seeded_count,
        _origin_label(start_url),
    )


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

    def _in_scope(candidate: str) -> bool:
        return _link_in_scope(
            candidate,
            domain_lock=crawl_config.domain_lock,
            start_host=start_host,
            section_scope=section_scope,
        )

    links: list[str] = []
    seen: set[str] = set()
    for script_url in extract_toc_script_urls(html_text, page_url):
        if not _in_scope(script_url):
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
            if not _in_scope(link):
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
