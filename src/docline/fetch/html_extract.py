"""HTML main-content extraction — strip DOM noise, return raw Markdown."""

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from docline.schema.models import DoclineError


class HtmlExtractionError(DoclineError):
    """Raised when HTML content extraction fails."""


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
    if name in {"ul", "ol"}:
        items = [
            f"* {item.get_text(' ', strip=True)}"
            for item in el.find_all("li", recursive=False)
            if item.get_text(" ", strip=True)
        ]
        return "\n".join(items)
    if name in {"div", "section", "article", "main", "body", "[document]"}:
        parts = [
            _element_to_markdown(child)
            for child in el.children
            if isinstance(child, (Tag, NavigableString))
        ]
        return "\n\n".join(part for part in parts if part)
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
    root = soup.find(["article", "main", "body"]) or soup
    markdown = _element_to_markdown(root).strip()
    if not markdown:
        raise HtmlExtractionError(
            f"HTML extraction failed for {source_url or '<unknown source>'}: no content"
        )
    return markdown


def strip_dom_noise(html: str) -> str:
    """Remove known noise elements from an HTML document.

    Removes ``<nav>``, ``<header>``, ``<footer>``, ``<aside>``,
    ``<script>``, ``<style>``, and common ad/cookie banner selectors before
    content extraction.

    Args:
        html: Raw HTML document text.

    Returns:
        HTML text with noise elements removed.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["nav", "header", "footer", "aside", "script", "style"]):
        tag.decompose()
    return str(soup)


__all__ = [
    "HtmlExtractionError",
    "extract_main_content",
    "strip_dom_noise",
]
