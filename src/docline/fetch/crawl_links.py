"""Pure URL and HTML helpers for the bounded crawl executor.

Leaf module holding the stateless link-extraction, URL-normalisation, dedup,
section-scope, and print-page helpers used by the crawl loop. It imports only
the standard library plus the URL canonicalisation and policy helpers, and
**nothing** from :mod:`docline.fetch.crawl` or
:mod:`docline.fetch.crawl_models`, so the crawl package import graph stays
acyclic.
"""

import re
from collections.abc import Iterator
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urldefrag, urljoin, urlparse

from docline.fetch.staging import sanitize_source
from docline.fetch.url_canonical import UrlCanonicalizationError, canonicalize_url
from docline.fetch.url_policy import CrawlUrlRejectedError, validate_crawl_url


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


def _iter_eligible_links(
    links: list[str],
    *,
    domain_lock: bool,
    start_host: str,
    section_scope: str | None,
    visited: set[str],
) -> Iterator[tuple[str, str]]:
    """Yield ``(link, link_key)`` for links passing the admission filters.

    Applies the same domain-lock, section-scope, and ``visited`` dedup filters
    the crawl loop enforces before an admission. Lazy: iteration stops as soon
    as the caller stops consuming, so a refusal ``break`` skips the remaining
    parse work.
    """
    for link in links:
        if domain_lock and urlparse(link).netloc != start_host:
            continue
        if domain_lock and not _url_within_section_scope(link, section_scope):
            continue
        link_key = _dedup_key(link)
        if link_key in visited:
            continue
        yield link, link_key


def _has_eligible_link(
    links: list[str],
    *,
    domain_lock: bool,
    start_host: str,
    section_scope: str | None,
    visited: set[str],
) -> bool:
    """Return whether *links* contains at least one admissible candidate."""
    return (
        next(
            _iter_eligible_links(
                links,
                domain_lock=domain_lock,
                start_host=start_host,
                section_scope=section_scope,
                visited=visited,
            ),
            None,
        )
        is not None
    )


def _has_eligible_toc_script(
    html_text: str,
    page_url: str,
    *,
    domain_lock: bool,
    start_host: str,
    section_scope: str | None,
) -> bool:
    """Return whether the page references an eligible, in-scope TOC script.

    A pure in-memory parse with **no** TOC network fetch. It mirrors the
    domain/scope filter :func:`docline.fetch.crawl._discover_toc_links` applies
    to TOC script assets, so a depth-zero short-circuit can conservatively flag
    truncation when lifting the ceiling would have discovered TOC-derived links.
    """
    for script_url in extract_toc_script_urls(html_text, page_url):
        if domain_lock and urlparse(script_url).netloc != start_host:
            continue
        if domain_lock and not _url_within_section_scope(script_url, section_scope):
            continue
        return True
    return False


def _origin_label(url: str) -> str:
    """Return the sanitized ``scheme://host[:port]`` origin for log records.

    Strips path, query, fragment, and userinfo so a default-visible truncation
    record cannot leak URL-carried credentials.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    origin = f"{parsed.scheme}://{host}" if host else parsed.scheme
    return sanitize_source(origin)


__all__ = [
    "extract_links",
    "extract_toc_links",
    "extract_toc_script_urls",
]
