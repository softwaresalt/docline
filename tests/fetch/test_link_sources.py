"""Harness for 070.002-T (T2a) — discovery-source seam protocol + registry.

Pins the :class:`~docline.fetch.link_sources.DiscoverySource` protocol and the
minimal first-match registry (:func:`~docline.fetch.link_sources.register` /
:func:`~docline.fetch.link_sources.find_source`) against a stub source, with
**no network I/O and no concrete provider adapter** — the Terraform Registry
adapter (070.005-T/070.006-T) is tested separately in
``test_tf_registry_source.py``.

Red before 070.003-T: the structural stub's ``register``/``find_source`` both
raise ``NotImplementedError``. Green once 070.003-T implements the registry.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from docline.fetch import link_sources
from docline.fetch.crawl_models import CrawlConfig


@pytest.fixture(autouse=True)
def _reset_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level source registry before every test.

    Uses ``raising=False`` because the 070.002-T structural stub does not yet
    expose a ``_sources`` list (``register``/``find_source`` both raise
    ``NotImplementedError``); once 070.003-T lands, this actually resets the
    registry between tests so no test's registration leaks into another.
    """
    monkeypatch.setattr(link_sources, "_sources", [], raising=False)


class _StubSource:
    """A minimal ``DiscoverySource`` recognizing exactly one URL prefix."""

    def __init__(self, prefix: str, doc_urls: list[str]) -> None:
        self.prefix = prefix
        self.doc_urls = doc_urls
        self.yielded_count = 0

    def recognizes(self, start_url: str) -> bool:
        return start_url.startswith(self.prefix)

    async def discover_doc_urls(
        self, start_url: str, config: CrawlConfig, budget: object
    ) -> AsyncIterator[str]:
        del start_url, config, budget
        for url in self.doc_urls:
            self.yielded_count += 1
            yield url


def test_find_source_returns_none_for_unrecognized_url() -> None:
    """No registered source recognizes an unrelated URL: ``find_source`` is None."""
    stub = _StubSource("https://example.com/docs", ["https://example.com/docs/a"])
    link_sources.register(stub)

    assert link_sources.find_source("https://other.example.org/docs") is None


def test_find_source_returns_registered_stub_for_matching_url() -> None:
    """A registered source recognizing the start URL is returned by identity."""
    stub = _StubSource("https://example.com/docs", ["https://example.com/docs/a"])
    link_sources.register(stub)

    found = link_sources.find_source("https://example.com/docs/anything")

    assert found is stub


def test_find_source_uses_first_match_registration_order() -> None:
    """When multiple sources are registered, the first match wins."""
    first = _StubSource("https://example.com/docs", ["https://example.com/docs/a"])
    second = _StubSource("https://example.com/docs", ["https://example.com/docs/b"])
    link_sources.register(first)
    link_sources.register(second)

    found = link_sources.find_source("https://example.com/docs/x")

    assert found is first


async def _collect_up_to(iterator: AsyncIterator[str], limit: int) -> list[str]:
    """Pull at most *limit* items from *iterator*, then stop early."""
    collected: list[str] = []
    async for item in iterator:
        collected.append(item)
        if len(collected) >= limit:
            break
    return collected


def test_discover_doc_urls_is_consumed_lazily() -> None:
    """Stopping consumption early stops the producer from yielding further items.

    A stub with 5 doc URLs, consumed only 2 deep, must show ``yielded_count``
    of exactly 2 — proving ``discover_doc_urls`` is a genuine async generator
    (not an eagerly-materialized list wrapped in an async iterator).
    """
    import asyncio

    stub = _StubSource(
        "https://example.com/docs",
        [f"https://example.com/docs/{i}" for i in range(5)],
    )
    link_sources.register(stub)

    iterator = stub.discover_doc_urls("https://example.com/docs", CrawlConfig(), None)
    collected = asyncio.run(_collect_up_to(iterator, 2))

    assert collected == [
        "https://example.com/docs/0",
        "https://example.com/docs/1",
    ]
    assert stub.yielded_count == 2, (
        "the producer must stop after the consumer stops pulling, not "
        "eagerly yield the whole collection"
    )
