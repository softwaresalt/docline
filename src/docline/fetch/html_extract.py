"""HTML main-content extraction — strip DOM noise, return raw Markdown."""

from docline.schema.models import DoclineError


class HtmlExtractionError(DoclineError):
    """Raised when HTML content extraction fails."""


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
    raise NotImplementedError("stub: html_extract.extract_main_content not yet implemented")


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
    raise NotImplementedError("stub: html_extract.strip_dom_noise not yet implemented")


__all__ = [
    "HtmlExtractionError",
    "extract_main_content",
    "strip_dom_noise",
]
