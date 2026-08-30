"""Test harness for 067.001-T — Bound crawl frontier growth independently of depth/max_pages.

Acceptance criteria:
- ``CrawlConfig`` exposes a ``max_frontier`` knob defaulting to ``MAX_FRONTIER`` (10_000).
- A page advertising a fan-out far larger than ``max_frontier`` admits no more than the cap,
  while ``max_pages`` and ``max_depth`` remain independently honoured.
- A small ``max_frontier`` bounds admissions even when ``max_pages``/``max_depth`` are large.
- A crawl that stays under the cap produces identical results at the default cap.
- Non-page-counting branches (redirect/duplicate-final aliases) do not circumvent the bound:
  total resident identity keys stay within ``MAX_FETCH_ATTEMPTS + max_frontier``.

Harness pattern: structural tests verify scaffold shape (PASS); behavioural tests assert
admission bounds (FAIL in red phase, before the cap is enforced in ``crawl()``).
"""

import asyncio

import pytest

from docline.fetch.crawl import (
    MAX_FRONTIER,
    CrawlConfig,
    crawl,
)
from docline.fetch.http import MAX_FETCH_ATTEMPTS, FetchResponse

SITE = "https://example.com/docs/"


def _fan_out_body(count: int, *, prefix: str = "page") -> str:
    """Return an HTML body linking to *count* distinct in-scope pages."""
    anchors = "".join(f'<a href="/docs/{prefix}-{index}">L{index}</a>' for index in range(count))
    return f"<html><body>{anchors}</body></html>"


def _html(url: str, body: str) -> FetchResponse:
    """Return a synthetic HTML :class:`FetchResponse` for *url*."""
    return FetchResponse(url=url, status=200, content_type="text/html", body=body)


def _install_fetch(
    monkeypatch: pytest.MonkeyPatch,
    pages: dict[str, FetchResponse],
    requested: list[str],
    *,
    default_body: str = "<html><body><h1>leaf</h1></body></html>",
) -> None:
    """Monkeypatch ``crawl.fetch_page`` with a synthetic in-memory site."""

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
        **_kwargs: object,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        requested.append(url)
        if url in pages:
            return pages[url]
        return _html(url, default_body)

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)


# ---------------------------------------------------------------------------
# Structural: config surface (PASS in red phase)
# ---------------------------------------------------------------------------


def test_max_frontier_default_constant_is_ten_thousand() -> None:
    """The module-level frontier ceiling is an explicit 10_000."""
    assert MAX_FRONTIER == 10_000


def test_crawl_config_default_max_frontier_matches_constant() -> None:
    """CrawlConfig defaults max_frontier to the module-level constant."""
    assert CrawlConfig().max_frontier == MAX_FRONTIER


def test_crawl_config_custom_max_frontier() -> None:
    """CrawlConfig accepts an explicit max_frontier override."""
    assert CrawlConfig(max_frontier=7).max_frontier == 7


def test_max_frontier_is_independent_of_page_and_depth_defaults() -> None:
    """The frontier ceiling is not derived from max_pages or max_depth."""
    config = CrawlConfig()
    assert config.max_frontier != config.max_pages
    assert config.max_frontier != config.max_depth


# ---------------------------------------------------------------------------
# Scenario 1: adversarial fan-out is capped; max_pages/max_depth still honoured
# ---------------------------------------------------------------------------


def test_fan_out_beyond_cap_admits_at_most_max_frontier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fan-out far larger than max_frontier admits no more than the cap."""
    requested: list[str] = []
    _install_fetch(monkeypatch, {SITE: _html(SITE, _fan_out_body(200))}, requested)

    results = asyncio.run(
        crawl(
            SITE,
            CrawlConfig(
                max_pages=500,
                max_depth=1,
                max_frontier=5,
                respect_robots=False,
            ),
        )
    )

    # start URL plus at most `max_frontier` admitted discoveries
    assert len(requested) == 6
    assert len(results) == 6


def test_fan_out_cap_still_honours_max_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_pages remains the binding budget when it is smaller than the cap."""
    requested: list[str] = []
    _install_fetch(monkeypatch, {SITE: _html(SITE, _fan_out_body(200))}, requested)

    results = asyncio.run(
        crawl(
            SITE,
            CrawlConfig(
                max_pages=3,
                max_depth=1,
                max_frontier=50,
                respect_robots=False,
            ),
        )
    )

    assert len(results) == 3
    assert len(requested) == 3


def test_fan_out_cap_still_honours_max_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_depth=0 suppresses discovery entirely, regardless of the cap."""
    requested: list[str] = []
    _install_fetch(monkeypatch, {SITE: _html(SITE, _fan_out_body(200))}, requested)

    results = asyncio.run(
        crawl(
            SITE,
            CrawlConfig(
                max_pages=500,
                max_depth=0,
                max_frontier=50,
                respect_robots=False,
            ),
        )
    )

    assert [result.url for result in results] == [SITE]
    assert requested == [SITE]


def test_start_url_is_never_dropped_by_a_tiny_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A max_frontier of 0 still crawls the start URL and terminates."""
    requested: list[str] = []
    _install_fetch(monkeypatch, {SITE: _html(SITE, _fan_out_body(200))}, requested)

    results = asyncio.run(
        crawl(
            SITE,
            CrawlConfig(
                max_pages=500,
                max_depth=3,
                max_frontier=0,
                respect_robots=False,
            ),
        )
    )

    assert [result.url for result in results] == [SITE]


# ---------------------------------------------------------------------------
# Scenario 2: independence from max_pages / max_depth
# ---------------------------------------------------------------------------


def test_small_cap_bounds_admissions_under_large_page_and_depth_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A small cap bounds a deep multi-level crawl with a very large page budget."""
    requested: list[str] = []
    # Every synthetic page fans out again, so growth is unbounded without the cap.
    _install_fetch(
        monkeypatch,
        {SITE: _html(SITE, _fan_out_body(10))},
        requested,
        default_body=_fan_out_body(10, prefix="deep"),
    )

    results = asyncio.run(
        crawl(
            SITE,
            CrawlConfig(
                max_pages=500,
                max_depth=8,
                max_frontier=3,
                respect_robots=False,
            ),
        )
    )

    assert len(requested) == 4
    assert len(results) == 4


def test_breadth_first_order_is_preserved_for_admitted_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admitted links keep breadth-first discovery order; the cap truncates the tail."""
    requested: list[str] = []
    _install_fetch(monkeypatch, {SITE: _html(SITE, _fan_out_body(20))}, requested)

    results = asyncio.run(
        crawl(
            SITE,
            CrawlConfig(
                max_pages=500,
                max_depth=1,
                max_frontier=4,
                respect_robots=False,
            ),
        )
    )

    assert [result.url for result in results] == [
        SITE,
        "https://example.com/docs/page-0",
        "https://example.com/docs/page-1",
        "https://example.com/docs/page-2",
        "https://example.com/docs/page-3",
    ]


# ---------------------------------------------------------------------------
# Scenario 3: under-cap regression at the exact default
# ---------------------------------------------------------------------------


def test_under_cap_crawl_is_unchanged_at_the_default_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crawl staying under the ceiling yields identical results at the default cap."""
    pages = {SITE: _html(SITE, _fan_out_body(4))}

    default_requested: list[str] = []
    _install_fetch(monkeypatch, pages, default_requested)
    default_results = asyncio.run(
        crawl(
            SITE,
            CrawlConfig(max_pages=50, max_depth=1, respect_robots=False),
        )
    )

    raised_requested: list[str] = []
    _install_fetch(monkeypatch, pages, raised_requested)
    raised_results = asyncio.run(
        crawl(
            SITE,
            CrawlConfig(
                max_pages=50,
                max_depth=1,
                max_frontier=MAX_FRONTIER * 1000,
                respect_robots=False,
            ),
        )
    )

    assert default_requested == raised_requested
    assert [(r.url, r.depth) for r in default_results] == [(r.url, r.depth) for r in raised_results]
    assert len(default_results) == 5


# ---------------------------------------------------------------------------
# Scenario 4: non-page-counting branches do not circumvent the bound
# ---------------------------------------------------------------------------


def test_redirect_alias_branches_stay_within_the_bounded_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redirect/duplicate-final aliases do not bypass the discovered-link cap.

    ``/docs/alias-*`` all resolve to one canonical final URL. Only the first
    increments ``page_count``; the rest take the duplicate-final branch, which
    does not count a page. The canonical page then advertises a large fan-out.
    Admissions across both discovery sites stay within ``max_frontier``, and
    total outbound attempts stay inside ``MAX_FETCH_ATTEMPTS``.
    """
    canonical = "https://example.com/docs/canonical"
    alias_body = (
        "<html><body>"
        '<a href="/docs/alias-0">A0</a>'
        '<a href="/docs/alias-1">A1</a>'
        '<a href="/docs/alias-2">A2</a>'
        "</body></html>"
    )
    pages = {
        SITE: _html(SITE, alias_body),
        # Each alias request resolves (redirects) to the same canonical final URL.
        "https://example.com/docs/alias-0": _html(canonical, _fan_out_body(200)),
        "https://example.com/docs/alias-1": _html(canonical, _fan_out_body(200)),
        "https://example.com/docs/alias-2": _html(canonical, _fan_out_body(200)),
    }
    requested: list[str] = []
    _install_fetch(monkeypatch, pages, requested)

    max_frontier = 6
    results = asyncio.run(
        crawl(
            SITE,
            CrawlConfig(
                max_pages=500,
                max_depth=2,
                max_frontier=max_frontier,
                respect_robots=False,
            ),
        )
    )

    # Three alias admissions plus three fan-out admissions exhaust the cap.
    assert len(requested) == 1 + max_frontier
    assert requested[:4] == [
        SITE,
        "https://example.com/docs/alias-0",
        "https://example.com/docs/alias-1",
        "https://example.com/docs/alias-2",
    ]

    # The duplicate-final branch was exercised: canonical is emitted exactly once
    # even though three distinct alias URLs resolved to it.
    emitted = [result.url for result in results]
    assert emitted.count(canonical) == 1
    assert emitted[0] == SITE

    # Total resident identity keys are bounded by MAX_FETCH_ATTEMPTS + max_frontier.
    assert len(requested) <= MAX_FETCH_ATTEMPTS + max_frontier
