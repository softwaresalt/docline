"""Test harness for 003.004-T — Extract main HTML content.

Acceptance criteria:
- extract_main_content() returns non-empty Markdown from article HTML.
- Strips navigation, footer, header, and script elements.
- HtmlExtractionError raised for empty or unparseable input.
- strip_dom_noise() removes known noise elements from HTML.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests assert return values or typed exceptions (FAIL in red phase).
"""

import pytest

from docline.fetch.html_extract import (
    HtmlExtractionError,
    extract_main_content,
    strip_dom_noise,
)
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Structural: error hierarchy (PASS in red phase)
# ---------------------------------------------------------------------------


def test_html_extraction_error_is_docline_error() -> None:
    """HtmlExtractionError is a subclass of DoclineError."""
    err = HtmlExtractionError("extraction failed")
    assert isinstance(err, DoclineError)


# ---------------------------------------------------------------------------
# Behavioral: extract_main_content (FAIL in red phase)
# ---------------------------------------------------------------------------

_ARTICLE_HTML = (
    "<html><body>"
    "<nav>Site menu</nav>"
    "<article><h1>Title</h1><p>Body text with enough content.</p></article>"
    "<footer>Copyright</footer>"
    "</body></html>"
)

_MAIN_HTML = (
    "<html><body>"
    "<header>Logo</header>"
    "<main><h1>Article</h1><p>Content paragraph.</p></main>"
    "<aside>Related links</aside>"
    "</body></html>"
)

_SCRIPT_HEAVY_HTML = (
    "<html><body>"
    "<script>trackAds()</script>"
    "<div id='content'><h2>Topic</h2><p>Detail paragraph.</p></div>"
    "<script>moreTracking()</script>"
    "</body></html>"
)


def test_extract_main_content_returns_string_from_article() -> None:
    """extract_main_content returns a non-empty string from article HTML."""
    result = extract_main_content(_ARTICLE_HTML)
    assert isinstance(result, str)
    assert len(result) > 0


def test_extract_main_content_includes_title_text() -> None:
    """extract_main_content preserves the main heading text."""
    result = extract_main_content(_ARTICLE_HTML)
    assert "Title" in result


def test_extract_main_content_excludes_nav_text() -> None:
    """extract_main_content strips navigation element text."""
    result = extract_main_content(_ARTICLE_HTML)
    assert "Site menu" not in result


def test_extract_main_content_excludes_footer_text() -> None:
    """extract_main_content strips footer element text."""
    result = extract_main_content(_ARTICLE_HTML)
    assert "Copyright" not in result


def test_extract_main_content_handles_main_element() -> None:
    """extract_main_content extracts content from <main> element."""
    result = extract_main_content(_MAIN_HTML)
    assert "Content paragraph" in result


def test_extract_main_content_raises_for_empty_html() -> None:
    """extract_main_content raises HtmlExtractionError for empty HTML."""
    with pytest.raises(HtmlExtractionError):
        extract_main_content("")


def test_extract_main_content_accepts_source_url() -> None:
    """extract_main_content accepts an optional source_url argument."""
    result = extract_main_content(_ARTICLE_HTML, source_url="https://example.com/article")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Behavioral: strip_dom_noise (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_strip_dom_noise_returns_string() -> None:
    """strip_dom_noise returns a string."""
    result = strip_dom_noise(_ARTICLE_HTML)
    assert isinstance(result, str)


def test_strip_dom_noise_removes_nav_element() -> None:
    """strip_dom_noise removes <nav> elements from HTML."""
    result = strip_dom_noise("<html><body><nav>Menu</nav><main>Content</main></body></html>")
    assert "<nav>" not in result
    assert "Menu" not in result


def test_strip_dom_noise_removes_script_elements() -> None:
    """strip_dom_noise removes <script> elements."""
    result = strip_dom_noise(_SCRIPT_HEAVY_HTML)
    assert "<script>" not in result
    assert "trackAds" not in result
