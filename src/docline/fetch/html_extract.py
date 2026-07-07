"""HTML main-content extraction — strip DOM noise, return raw Markdown."""

import re

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from docline.schema.models import DoclineError


class HtmlExtractionError(DoclineError):
    """Raised when HTML content extraction fails."""


# DocBook-style admonition div classes rendered as labeled blockquotes.
_ADMONITION_CLASSES = ("note", "caution", "warning", "tip", "important")
# DocBook navigation chrome stripped as noise (version switcher, prev/next nav).
_NOISE_CLASSES = ("navheader", "navfooter")


def _element_classes(el: Tag) -> list[str]:
    """Return an element's CSS classes as a list, tolerating missing/str values."""
    class_attr = el.get("class")
    if isinstance(class_attr, list):
        return [str(cls) for cls in class_attr]
    if isinstance(class_attr, str):
        return class_attr.split()
    return []


def _int_attr(el: Tag, name: str, default: int) -> int:
    """Return a positive integer HTML attribute value, or ``default``."""
    raw = el.get(name)
    if isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
        if value >= 1:
            return value
    return default


def _render_table(el: Tag) -> str:
    """Render an HTML ``<table>`` as a GitHub-flavored Markdown table.

    ``colspan`` and ``rowspan`` are expanded by repeating the spanning cell's
    text into each covered column/row (Markdown tables have no native spans),
    so no data is lost. The first row supplies the header; pipe characters are
    escaped and rows are normalized to a common width. Returns ``""`` for a
    table with no rows.
    """
    trs = el.find_all("tr")
    if not trs:
        return ""

    grid: list[list[str]] = []
    carry: dict[int, tuple[int, str]] = {}  # column -> (rows_remaining, value)
    for tr in trs:
        cells = tr.find_all(["th", "td"], recursive=False)
        row: list[str] = []
        col = 0
        ci = 0
        while ci < len(cells) or any(c >= col for c in carry):
            if col in carry:
                remaining, value = carry[col]
                row.append(value)
                if remaining - 1 > 0:
                    carry[col] = (remaining - 1, value)
                else:
                    del carry[col]
                col += 1
            elif ci < len(cells):
                cell = cells[ci]
                ci += 1
                value = cell.get_text(" ", strip=True).replace("|", r"\|")
                colspan = _int_attr(cell, "colspan", 1)
                rowspan = _int_attr(cell, "rowspan", 1)
                for _ in range(colspan):
                    row.append(value)
                    if rowspan > 1:
                        carry[col] = (rowspan - 1, value)
                    col += 1
            else:
                # A carried span sits in a later column than this short row fills.
                row.append("")
                col += 1
        grid.append(row)

    width = max((len(r) for r in grid), default=0)
    if width == 0:
        return ""

    def _fmt(cells: list[str]) -> str:
        return "| " + " | ".join((cells + [""] * width)[:width]) + " |"

    lines = [_fmt(grid[0]), "| " + " | ".join(["---"] * width) + " |"]
    lines.extend(_fmt(r) for r in grid[1:])
    return "\n".join(lines)


def _render_admonition(el: Tag, label: str) -> str:
    """Render a DocBook-style admonition ``<div>`` as a labeled blockquote.

    A redundant DocBook ``.title`` node (e.g. ``<h3 class="title">Note</h3>``)
    is removed so the label is not duplicated in the body.
    """
    title = el.find(class_="title")
    if isinstance(title, Tag):
        title.extract()
    body = el.get_text(" ", strip=True)
    inner = [f"**{label.capitalize()}**"]
    if body:
        inner.append("")
        inner.append(body)
    return "\n".join(f"> {line}" if line else ">" for line in inner)


def _render_children(el: Tag) -> str:
    """Render an element's children to Markdown, joined by blank lines."""
    parts = [
        _element_to_markdown(child)
        for child in el.children
        if isinstance(child, (Tag, NavigableString))
    ]
    return "\n\n".join(part for part in parts if part)


_LANG_CLASS_RE = re.compile(r"^(?:language|lang|highlight-source|sourceCode)-([\w+#.-]+)$")


def _pre_language(el: Tag) -> str:
    """Extract a fenced-code language hint from a ``<pre>`` or its ``<code>``.

    Recognizes the common ``language-<lang>`` / ``lang-<lang>`` /
    ``highlight-source-<lang>`` / ``sourceCode-<lang>`` class conventions on the
    ``<pre>`` element or a nested ``<code>``. Returns ``""`` when no hint is found.
    """
    candidates = list(_element_classes(el))
    code = el.find("code")
    if isinstance(code, Tag):
        candidates.extend(_element_classes(code))
    for cls in candidates:
        match = _LANG_CLASS_RE.match(cls)
        if match:
            return match.group(1).lower()
    return ""


def _render_definition_list(el: Tag) -> str:
    """Render a ``<dl>`` as bold terms followed by their descriptions.

    Each ``<dt>`` becomes a bold term line and each ``<dd>`` renders its child
    content beneath it. Used for DocBook ``variablelist`` output (e.g.
    PostgreSQL parameter lists) so terms and descriptions are not flattened
    into a single run of text.
    """
    parts: list[str] = []
    for child in el.find_all(["dt", "dd"], recursive=False):
        if (child.name or "").lower() == "dt":
            term = child.get_text(" ", strip=True)
            if term:
                parts.append(f"**{term}**")
        else:
            desc = _render_children(child).strip()
            if desc:
                parts.append(desc)
    return "\n\n".join(parts)


def _element_to_markdown(el: Tag | NavigableString) -> str:
    """Convert a BeautifulSoup element tree into simple Markdown."""
    if isinstance(el, NavigableString):
        return str(el).strip()

    name = (el.name or "").lower()
    text = el.get_text(" ", strip=True)

    if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        if not text:
            return ""
        return f"{'#' * int(name[1])} {text}"
    if name == "p":
        return text
    if name == "pre":
        code = el.get_text().strip("\n")
        if not code.strip():
            return ""
        return f"```{_pre_language(el)}\n{code}\n```"
    if name == "table":
        return _render_table(el)
    if name == "dl":
        return _render_definition_list(el)
    if name == "img":
        # F6.T2 image preservation: render every <img> as Markdown image so
        # downstream readers and accessibility linters can see it. Missing
        # ``alt`` becomes ``![](src)`` rather than being silently dropped.
        src = el.get("src", "")
        alt_attr = el.get("alt")
        alt_text = alt_attr if isinstance(alt_attr, str) else ""
        if not src:
            return ""
        return f"![{alt_text}]({src})"
    if name == "figcaption":
        # Plain caption text on its own line; rendered after the figure's
        # <img> by the containing <figure> recursion.
        return text
    if name in {"ul", "ol"}:
        items = [
            f"* {item.get_text(' ', strip=True)}"
            for item in el.find_all("li", recursive=False)
            if item.get_text(" ", strip=True)
        ]
        return "\n".join(items)
    if name == "div":
        admonition = next((cls for cls in _element_classes(el) if cls in _ADMONITION_CLASSES), None)
        if admonition is not None:
            return _render_admonition(el, admonition)
    if name in {"figure", "div", "section", "article", "main", "body", "[document]"}:
        return _render_children(el)
    return text


def extract_main_content(html: str, *, source_url: str = "") -> str:
    """Extract main article content from an HTML page and return raw Markdown.

    Strips navigation, headers, footers, ads, and other DOM noise, then
    converts the remaining semantic content to Markdown.

    Args:
        html: Raw HTML document text.
        source_url: Optional origin URL, used to improve extraction heuristics
            and for error messages.

    Returns:
        Markdown text containing the main content.

    Raises:
        HtmlExtractionError: If extraction fails or produces empty output.
    """
    if not html.strip():
        raise HtmlExtractionError(
            f"HTML extraction failed for {source_url or '<unknown source>'}: empty input"
        )

    cleaned_html = strip_dom_noise(html)
    soup = BeautifulSoup(cleaned_html, "html.parser")
    # Prefer a whole-content DocBook container (standard DocBook output classes)
    # so surrounding site chrome — version switchers, search, breadcrumbs — is
    # excluded. Document order yields the outermost container first (a
    # ``.chapter`` wrapping its ``.sect1`` children is selected whole). DocBook
    # emits one top-level component per page, so this does not truncate content.
    # Non-DocBook pages fall back to the usual article/main/body root.
    root = soup.select_one(".book, .chapter, .refentry, .sect1") or soup.find(
        ["article", "main", "body"]
    )
    if root is None:
        root = soup
    markdown = _element_to_markdown(root).strip()
    if not markdown:
        raise HtmlExtractionError(
            f"HTML extraction failed for {source_url or '<unknown source>'}: no content"
        )
    return markdown


def strip_dom_noise(html: str) -> str:
    """Remove known noise elements from an HTML document.

    Removes ``<nav>``, ``<header>``, ``<footer>``, ``<aside>``, ``<script>``,
    ``<style>``, and DocBook navigation chrome (``.navheader`` / ``.navfooter``,
    which carry the prev/next and version-switcher links) before content
    extraction.

    Args:
        html: Raw HTML document text.

    Returns:
        HTML text with noise elements removed.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["nav", "header", "footer", "aside", "script", "style"]):
        tag.decompose()
    for tag in soup.select(", ".join(f".{cls}" for cls in _NOISE_CLASSES)):
        tag.decompose()
    return str(soup)


__all__ = [
    "HtmlExtractionError",
    "extract_main_content",
    "strip_dom_noise",
]
