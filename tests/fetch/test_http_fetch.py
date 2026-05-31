"""Tests for http.py — Finding 1: CrawlUrlRejectedError must not be wrapped.

Acceptance criteria:
- CrawlUrlRejectedError raised inside _fetch() propagates unchanged from
  fetch_page(), rather than being swallowed and re-raised as a FetchError.
- Preserving the original typed exception lets callers (e.g. crawl()) distinguish
  permanent URL-policy rejections from transient network failures.
"""

import asyncio

import pytest

from docline.fetch.http import FetchError, fetch_page
from docline.fetch.url_policy import CrawlUrlRejectedError


def _make_raising_opener(exc: Exception) -> object:
    """Return a minimal fake opener whose open() immediately raises *exc*."""

    class _FakeOpener:
        def open(self, req: object, timeout: float = 30.0) -> object:  # noqa: ARG002
            raise exc

    return _FakeOpener()


def test_crawl_url_rejected_error_propagates_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CrawlUrlRejectedError from inside _fetch propagates as-is from fetch_page.

    When the redirect handler (or final-URL check) raises CrawlUrlRejectedError,
    fetch_page must NOT wrap it in FetchError.
    """
    policy_err = CrawlUrlRejectedError("redirect to private address detected")
    fake_opener = _make_raising_opener(policy_err)

    import urllib.request

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_a, **_kw: fake_opener)

    with pytest.raises(CrawlUrlRejectedError):
        asyncio.run(fetch_page("https://example.com"))


def test_crawl_url_rejected_error_is_not_wrapped_as_fetch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fetch_page raises CrawlUrlRejectedError exactly — never FetchError — for SSRF blocks.

    This is the regression guard: the original bug wrapped CrawlUrlRejectedError
    inside FetchError, losing the typed signal callers depend on.
    """
    policy_err = CrawlUrlRejectedError("SSRF redirect to 169.254.169.254 blocked")
    fake_opener = _make_raising_opener(policy_err)

    import urllib.request

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_a, **_kw: fake_opener)

    caught: BaseException | None = None
    try:
        asyncio.run(fetch_page("https://example.com"))
    except BaseException as exc:
        caught = exc

    assert caught is not None, "fetch_page should have raised"
    assert type(caught) is CrawlUrlRejectedError, (
        f"Expected CrawlUrlRejectedError but got {type(caught).__name__}: {caught!r}. "
        "CrawlUrlRejectedError must not be wrapped as FetchError."
    )
    assert not isinstance(caught, FetchError), (
        "CrawlUrlRejectedError must never be an instance of FetchError."
    )
