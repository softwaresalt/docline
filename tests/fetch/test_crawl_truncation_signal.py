"""Red harness for 068.006-T (A.T5) — truncation observability signal.

Drives real crawls (with a synthetic in-memory site) and asserts the operator
observability contract from plan decisions D1, D3, and D4:

* ``crawl()`` returns a :class:`CrawlOutcome` carrying ``results`` and
  ``frontier_truncated``;
* ``frontier_truncated`` follows the D3 "an eligible candidate was actually
  dropped" semantics, including the exactly-at-cap **link-free** page that must
  report ``False`` and emit **no** warning;
* a truncated crawl emits exactly **one** WARNING and an under-ceiling crawl
  emits none;
* the WARNING payload is the sanitized **origin** plus the admission count and
  leaks no path, query, fragment, or userinfo — even for credential-in-path,
  credential-shaped query names, userinfo, and control-character start URLs.

Red before 068.007-T (A.T6) introduces ``CrawlOutcome`` and promotes the record
to WARNING; green afterwards. No source change in this task.
"""

import asyncio
import logging

import pytest

from docline.fetch.crawl import CrawlConfig, CrawlOutcome, crawl
from docline.fetch.crawl_models import _origin_label
from docline.fetch.http import FetchResponse, RemainingByteBudget

CRAWL_LOGGER = "docline.fetch.crawl"
ORIGIN = "https://example.com"


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
        budget: RemainingByteBudget | None = None,
        **_kwargs: object,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        assert budget is not None, "crawl() must thread the request-scoped budget through"
        budget.debit_attempt()
        requested.append(url)
        if url in pages:
            return pages[url]
        return _html(url, default_body)

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)


def _ceiling_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Return WARNING-level ceiling records captured under the crawl logger."""
    return [
        record
        for record in caplog.records
        if record.name == CRAWL_LOGGER
        and record.levelno == logging.WARNING
        and "ceiling" in record.getMessage().lower()
    ]


# ---------------------------------------------------------------------------
# CrawlOutcome shape and flag semantics
# ---------------------------------------------------------------------------


def test_crawl_returns_outcome_with_results_and_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """``crawl()`` returns a ``CrawlOutcome`` exposing results and the flag."""
    start = f"{ORIGIN}/docs/"
    requested: list[str] = []
    _install_fetch(
        monkeypatch, {start: _html(start, "<html><body><h1>root</h1></body></html>")}, requested
    )

    outcome = asyncio.run(crawl(start, CrawlConfig(max_pages=5, respect_robots=False)))

    assert isinstance(outcome, CrawlOutcome)
    assert isinstance(outcome.results, list)
    assert outcome.frontier_truncated is False
    assert [result.url for result in outcome.results] == [start]


def test_truncated_crawl_flags_true_and_warns_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A fan-out beyond the cap flags truncation and warns exactly once."""
    start = f"{ORIGIN}/docs/"
    requested: list[str] = []
    _install_fetch(monkeypatch, {start: _html(start, _fan_out_body(50))}, requested)

    with caplog.at_level(logging.WARNING, logger=CRAWL_LOGGER):
        outcome = asyncio.run(
            crawl(
                start, CrawlConfig(max_pages=500, max_depth=1, max_frontier=3, respect_robots=False)
            )
        )

    assert outcome.frontier_truncated is True
    assert len(_ceiling_records(caplog)) == 1


def test_under_ceiling_crawl_flags_false_and_is_silent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A crawl staying under the ceiling flags ``False`` and emits no warning."""
    start = f"{ORIGIN}/docs/"
    requested: list[str] = []
    _install_fetch(monkeypatch, {start: _html(start, _fan_out_body(3))}, requested)

    with caplog.at_level(logging.WARNING, logger=CRAWL_LOGGER):
        outcome = asyncio.run(
            crawl(
                start,
                CrawlConfig(max_pages=500, max_depth=1, max_frontier=50, respect_robots=False),
            )
        )

    assert outcome.frontier_truncated is False
    assert _ceiling_records(caplog) == []


def test_exactly_at_cap_link_free_page_flags_false_and_is_silent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Exactly filling the cap then visiting a link-free page is not truncation.

    The cap is exactly reached by the single admitted link; the admitted page is
    link-free and TOC-free, so the depth-one short-circuit finds no eligible
    candidate. ``frontier_truncated`` stays ``False`` and **no** WARNING fires.
    """
    start = f"{ORIGIN}/docs/"
    only = f"{ORIGIN}/docs/only"
    pages = {
        start: _html(start, '<html><body><a href="/docs/only">only</a></body></html>'),
        only: _html(only, "<html><body><h1>leaf</h1></body></html>"),
    }
    requested: list[str] = []
    _install_fetch(monkeypatch, pages, requested)

    with caplog.at_level(logging.WARNING, logger=CRAWL_LOGGER):
        outcome = asyncio.run(
            crawl(
                start, CrawlConfig(max_pages=500, max_depth=2, max_frontier=1, respect_robots=False)
            )
        )

    assert outcome.frontier_truncated is False
    assert _ceiling_records(caplog) == []
    # The admitted page was actually visited, so the short-circuit was reached.
    assert only in requested


# ---------------------------------------------------------------------------
# WARNING payload: sanitized origin + count, never the URL tail (D4)
# ---------------------------------------------------------------------------


def _relative_fan_out_body(count: int) -> str:
    """Return an HTML body linking to *count* pages relative to the start dir."""
    anchors = "".join(f'<a href="child-{index}">L{index}</a>' for index in range(count))
    return f"<html><body>{anchors}</body></html>"


def _run_truncating_crawl(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, start: str
) -> str:
    """Drive a truncating crawl from *start* and return the WARNING message."""
    requested: list[str] = []
    _install_fetch(monkeypatch, {}, requested, default_body=_relative_fan_out_body(50))
    with caplog.at_level(logging.WARNING, logger=CRAWL_LOGGER):
        asyncio.run(
            crawl(
                start, CrawlConfig(max_pages=500, max_depth=1, max_frontier=7, respect_robots=False)
            )
        )
    records = _ceiling_records(caplog)
    assert len(records) == 1
    return records[0].getMessage()


def test_warning_payload_contains_origin_and_count(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The record carries the sanitized origin and the admission count."""
    message = _run_truncating_crawl(monkeypatch, caplog, f"{ORIGIN}/docs/")
    assert ORIGIN in message
    assert "7" in message


def test_warning_payload_omits_path(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A secret path segment never reaches the origin-only record."""
    message = _run_truncating_crawl(monkeypatch, caplog, f"{ORIGIN}/docs/leaksecretpath/")
    assert "leaksecretpath" not in message


def test_warning_payload_omits_credential_query_params(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Credential-shaped query names and values never reach the record."""
    start = f"{ORIGIN}/docs/?code=leakcode&jwt=leakjwt&session=leaksess"
    message = _run_truncating_crawl(monkeypatch, caplog, start)
    for secret in ("leakcode", "leakjwt", "leaksess"):
        assert secret not in message


def test_warning_payload_omits_userinfo(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """URL userinfo never reaches the origin-only record."""
    start = "https://leakuser:leakpass@example.com/docs/"
    message = _run_truncating_crawl(monkeypatch, caplog, start)
    assert "leakuser" not in message
    assert "leakpass" not in message
    assert ORIGIN in message


def test_warning_payload_has_no_fragment_or_control_chars(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A fragment and its control characters never reach the record."""
    start = f"{ORIGIN}/docs/#\x01leakfragment"
    message = _run_truncating_crawl(monkeypatch, caplog, start)
    assert "leakfragment" not in message
    assert not any(ord(char) < 32 for char in message)


# ---------------------------------------------------------------------------
# Origin label — IPv6 literals (regression: bracket-stripping ValueError)
# ---------------------------------------------------------------------------


def test_origin_label_preserves_ipv6_brackets_with_port() -> None:
    """An IPv6 origin keeps its brackets and drops path/query (no ValueError)."""
    label = _origin_label("https://[2606:4700:4700::1111]:8443/docs/?token=leak")
    assert label == "https://[2606:4700:4700::1111]:8443"
    assert "leak" not in label


def test_origin_label_ipv6_without_port_does_not_raise() -> None:
    """A bracketed IPv6 host with a letter group must not raise on port parse."""
    label = _origin_label("https://[2606:4700:4700::1a2b]/docs/")
    assert label == "https://[2606:4700:4700::1a2b]"


def test_origin_label_ipv4_and_hostname_unchanged() -> None:
    """Non-IPv6 hosts are unaffected by the bracket-preservation branch."""
    assert _origin_label("https://198.51.100.7:9000/docs/?k=v") == "https://198.51.100.7:9000"
    assert _origin_label("https://example.com/docs/") == "https://example.com"
