"""Discovery-source seam: pluggable per-site link enumeration for ``crawl()``.

Defines the :class:`DiscoverySource` protocol and a minimal first-match
registry (:func:`register` / :func:`find_source`) that ``crawl()`` (070.010-T)
consults at the start of a crawl to decide whether a recognized site can be
enumerated through an API-backed adapter instead of relying solely on static
HTML link extraction.

This module is deliberately generic: it imports only leaf dependencies
(:mod:`docline.fetch.crawl_models`, :mod:`docline.fetch.http`) and never
imports a concrete provider adapter (e.g. the Terraform Registry adapter in
:mod:`docline.fetch.tf_registry_source`). The concrete adapter registers
itself at the ``crawl.py`` composition point, so this seam never needs to
change when a new site adapter is added.

Named ``link_sources`` (not ``crawl_discovery*``) to avoid colliding with the
existing robots/backoff module :mod:`docline.fetch.crawl_discovery`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from docline.fetch.crawl_models import CrawlConfig
from docline.fetch.http import RemainingByteBudget


@runtime_checkable
class DiscoverySource(Protocol):
    """A pluggable, per-site link-enumeration source consulted by ``crawl()``.

    Implementations recognize a start URL by pattern (no network I/O) and, if
    recognized, lazily enumerate every discoverable document URL for that
    site through whatever API or protocol the site exposes.
    """

    def recognizes(self, start_url: str) -> bool:
        """Return ``True`` when this source can enumerate docs for *start_url*.

        Args:
            start_url: The crawl's start URL.

        Returns:
            ``True`` when this source recognizes *start_url*'s shape. Must be
            pure and synchronous — no network I/O.
        """
        ...

    def discover_doc_urls(
        self,
        start_url: str,
        config: CrawlConfig,
        budget: RemainingByteBudget | None,
    ) -> AsyncIterator[str]:
        """Lazily yield every doc URL discoverable from *start_url*.

        Args:
            start_url: The crawl's start URL (already confirmed recognized).
            config: The active crawl configuration.
            budget: The request-scoped byte/attempt budget threaded through
                every outbound fetch the source performs.

        Yields:
            Absolute, policy-validated document URLs. Consumption is lazy: a
            consumer that stops pulling stops the source's own I/O (e.g. API
            pagination) rather than eagerly enumerating everything upfront.

        Raises:
            DoclineError: Implementations MUST wrap any failure specific to
                their own enumeration (a fetch error, a schema-drift/parsing
                failure, an unsupported input shape, etc.) in a
                :class:`~docline.schema.models.DoclineError` subclass, never
                let it escape as a bare/builtin exception. ``crawl()``'s
                composition point catches exactly this base type to degrade to
                static-only extraction on any adapter failure — an
                implementation that raises something else breaks that
                fail-open guarantee and aborts the whole crawl instead of
                degrading gracefully. Genuinely aggregate-budget or
                SSRF-policy failures the implementation's own outbound fetches
                raise (`AggregateBudgetExceededError` /
                `CrawlUrlRejectedError`, both themselves `DoclineError`
                subclasses) MUST be re-raised unwrapped rather than caught and
                rewrapped, so a budget/SSRF stop is never masked as an
                ordinary adapter failure.
        """
        ...


_sources: list[DiscoverySource] = []
"""Module-level first-match registry. Populated by concrete adapters at their
composition point (``crawl.py``), never by this generic seam module."""


def register(source: DiscoverySource) -> None:
    """Register a discovery source.

    Registration order is first-match precedence: :func:`find_source` returns
    the first registered source whose :meth:`DiscoverySource.recognizes`
    returns ``True`` for a given start URL.

    Args:
        source: The discovery source to register.
    """
    _sources.append(source)


def find_source(start_url: str) -> DiscoverySource | None:
    """Return the first registered source that recognizes *start_url*.

    Args:
        start_url: The crawl's start URL.

    Returns:
        The first matching :class:`DiscoverySource`, or ``None`` when no
        registered source recognizes *start_url*.
    """
    for source in _sources:
        if source.recognizes(start_url):
            return source
    return None


__all__ = ["DiscoverySource", "find_source", "register"]
