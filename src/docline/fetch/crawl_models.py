"""Crawl data models and admission-state primitives.

Leaf module for the bounded crawl executor: it defines the configuration, the
per-page result record, the whole-crawl frontier ceiling constant and errors,
and the ``_Frontier`` admission-state dataclass. It imports nothing from
:mod:`docline.fetch.crawl` or :mod:`docline.fetch.crawl_links`, keeping the
crawl package import graph strictly one-way.
"""

import logging
from collections import deque
from dataclasses import dataclass, field

from docline.fetch.http import FetchResponse
from docline.schema.models import DoclineError

# Ceiling records are a crawl-level observability event: emit them under the
# crawl loop's logger so operators watch a single, stable logger name regardless
# of which internal module owns the admission state.
logger = logging.getLogger("docline.fetch.crawl")

MAX_FRONTIER: int = 10_000
"""Absolute ceiling on discovered-link admissions for a single crawl.

Independent of ``max_pages`` and ``max_depth``: it bounds how many links a
crawl may admit to the frontier, so an adversarial link fan-out cannot grow
the resident ``frontier``/``visited`` structures without bound.
"""


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
        max_frontier: Ceiling on discovered-link admissions to the frontier.
            ``0`` disables link discovery entirely; negative values are rejected.
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
    max_frontier: int = MAX_FRONTIER


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


@dataclass(slots=True)
class CrawlOutcome:
    """Result of a bounded crawl: the ordered pages and the truncation signal.

    Attributes:
        results: The per-page :class:`CrawlResult` values in breadth-first
            discovery order, up to ``config.max_pages`` items.
        frontier_truncated: ``True`` when the whole-crawl admission ceiling
            actually refused at least one eligible candidate (an operator-visible
            "the crawl may be incomplete" signal), ``False`` otherwise. Reaching
            the cap without dropping an eligible link is **not** truncation.
    """

    results: list[CrawlResult]
    frontier_truncated: bool


@dataclass(slots=True)
class _Frontier:
    """Whole-crawl admission-state owner for the discovered-link ceiling.

    Encapsulates the breadth-first work queue and the admission counters that
    bound how many discovered links a single crawl may enqueue. The crawl loop
    reads :attr:`queue` directly for ``popleft`` and emptiness checks — queue
    ordering is the loop's concern — while admission accounting stays here so
    the 058-S ceiling invariants are testable without driving a full crawl.

    The emitted-page ``visited`` set is deliberately **not** a field: it is
    mutated at non-admission sites and serves emitted-page dedup, a separate
    responsibility. :meth:`admit` takes it as an argument and records an
    admitted link's dedup key on success only.

    Attributes:
        max_frontier: Whole-crawl ceiling on discovered-link admissions.
        start_label: Sanitized crawl label used in the ceiling log record.
        queue: Breadth-first queue of ``(url, depth)`` pairs awaiting a fetch.
        admitted: Count of discovered links admitted to :attr:`queue` so far.
        ceiling_reported: Whether the once-per-crawl ceiling record has fired.
        refused_any: Whether the ceiling refused at least one eligible
            candidate — the sole basis for :attr:`truncated`.
    """

    max_frontier: int
    start_label: str
    queue: deque[tuple[str, int]] = field(default_factory=deque)
    admitted: int = 0
    ceiling_reported: bool = False
    refused_any: bool = False

    @property
    def exhausted(self) -> bool:
        """Return ``True`` when the admission ceiling is full."""
        return self.admitted >= self.max_frontier

    @property
    def truncated(self) -> bool:
        """Return ``True`` when the ceiling actually refused an eligible link."""
        return self.refused_any

    def report_ceiling(self) -> None:
        """Log the frontier truncation once per crawl at WARNING level.

        Emitted only when the ceiling actually refuses an eligible candidate.
        The payload is the sanitized crawl **origin** (scheme + host) plus the
        admission count — never the full start URL, whose path, query,
        fragment, or userinfo could carry credentials once the record is
        default-visible.
        """
        if self.ceiling_reported:
            return
        self.ceiling_reported = True
        logger.warning(
            "Frontier admission ceiling of %d reached for crawl origin %s after "
            "%d admission(s); dropping further discovered links.",
            self.max_frontier,
            self.start_label,
            self.admitted,
        )

    def admit(self, link: str, link_key: str, next_depth: int, visited: set[str]) -> bool:
        """Admit a discovered link to the queue unless the ceiling refuses it.

        Args:
            link: The absolute discovered URL.
            link_key: The canonical dedup key for *link*.
            next_depth: Discovery depth to record for *link*.
            visited: Emitted/queued dedup set. *link_key* is added on a
                successful admission and never on a refusal (the 058-S
                invariant).

        Returns:
            ``True`` when the link was admitted, ``False`` when the whole-crawl
            frontier ceiling refused it. A refusal records :attr:`refused_any`
            and emits the truncation record.
        """
        if self.exhausted:
            self.refused_any = True
            self.report_ceiling()
            return False
        self.admitted += 1
        visited.add(link_key)
        self.queue.append((link, next_depth))
        return True


__all__ = [
    "MAX_FRONTIER",
    "CrawlConfig",
    "CrawlLimitExceededError",
    "CrawlOutcome",
    "CrawlResult",
    "CrawlRobotsError",
]
