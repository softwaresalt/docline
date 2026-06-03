"""Sitemap discovery and parsing stub — staged scaffolding for F6.T6 (010.030-T).

This module exists so the red-first contract tests in
``tests/fetch/test_sitemap.py`` collect cleanly. All public callables raise
:class:`NotImplementedError` until F6.T6 lands the real sitemap parser and
SSRF-resistant host validation.
"""

from __future__ import annotations

from dataclasses import dataclass

from docline.schema.models import DoclineError


class SitemapError(DoclineError):
    """Raised when sitemap discovery, parsing, or SSRF validation fails."""


@dataclass(frozen=True)
class SitemapEntry:
    """A single ``<url>`` entry inside a ``<urlset>`` sitemap.

    Attributes:
        loc: The ``<loc>`` URL.
        lastmod: Optional ISO-8601 ``<lastmod>`` value.
    """

    loc: str
    lastmod: str | None = None


def parse_sitemap_urlset(content: str) -> tuple[SitemapEntry, ...]:  # noqa: ARG001
    """Stub — F6.T6 implements ``<urlset>`` parsing."""
    raise NotImplementedError("parse_sitemap_urlset is implemented by F6.T6 (010.030-T).")


def parse_sitemap_index(content: str) -> tuple[str, ...]:  # noqa: ARG001
    """Stub — F6.T6 implements ``<sitemapindex>`` parsing."""
    raise NotImplementedError("parse_sitemap_index is implemented by F6.T6 (010.030-T).")


def discover_sitemaps_from_robots(robots_txt: str) -> tuple[str, ...]:  # noqa: ARG001
    """Stub — F6.T6 extracts ``Sitemap:`` directives from robots.txt."""
    raise NotImplementedError("discover_sitemaps_from_robots is implemented by F6.T6 (010.030-T).")


def validate_sitemap_url(url: str) -> str:  # noqa: ARG001
    """Stub — F6.T6 implements DNS-rebinding-resistant SSRF validation."""
    raise NotImplementedError("validate_sitemap_url is implemented by F6.T6 (010.030-T).")


__all__ = [
    "SitemapEntry",
    "SitemapError",
    "discover_sitemaps_from_robots",
    "parse_sitemap_index",
    "parse_sitemap_urlset",
    "validate_sitemap_url",
]
