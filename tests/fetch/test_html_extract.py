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


# --- 054-F / T3: PostgreSQL / DocBook structural fidelity ---


def test_pre_block_renders_as_fenced_code() -> None:
    """A <pre> block renders as a fenced code block preserving newlines."""
    html = (
        "<article><div class='refsynopsisdiv'>"
        "<pre class='synopsis'>SELECT *\n  FROM t\n  WHERE x = 1;</pre>"
        "</div></article>"
    )
    result = extract_main_content(html)
    assert "```" in result
    assert "SELECT *\n  FROM t\n  WHERE x = 1;" in result


def test_table_renders_as_markdown_table() -> None:
    """A content <table> renders as a GitHub-flavored Markdown table."""
    html = (
        "<article><table class='table'>"
        "<thead><tr><th>Name</th><th>Type</th></tr></thead>"
        "<tbody><tr><td>id</td><td>integer</td></tr>"
        "<tr><td>label</td><td>text</td></tr></tbody>"
        "</table></article>"
    )
    result = extract_main_content(html)
    assert "| Name | Type |" in result
    assert "| --- | --- |" in result
    assert "| id | integer |" in result
    assert "| label | text |" in result


def test_table_cell_pipe_is_escaped() -> None:
    """A pipe character inside a table cell is escaped to keep the table valid."""
    html = "<article><table><tr><th>a | b</th></tr><tr><td>c</td></tr></table></article>"
    result = extract_main_content(html)
    assert r"a \| b" in result


def test_note_div_renders_as_blockquote() -> None:
    """A DocBook note admonition renders as a labeled blockquote."""
    html = (
        "<article><div class='note'><h3 class='title'>Note</h3><p>Mind the gap.</p></div></article>"
    )
    result = extract_main_content(html)
    assert "> **Note**" in result
    assert "Mind the gap." in result
    # The redundant DocBook title node must not duplicate the label.
    assert result.count("Note") == 1


def test_caution_div_renders_as_blockquote() -> None:
    """A DocBook caution admonition renders with its own label."""
    html = "<article><div class='caution'><p>Be careful.</p></div></article>"
    result = extract_main_content(html)
    assert "> **Caution**" in result
    assert "Be careful." in result


def test_strip_dom_noise_removes_navheader_and_navfooter() -> None:
    """DocBook navigation chrome (navheader/navfooter) is stripped as noise."""
    html = (
        "<div class='navheader'><table summary='Navigation header'>"
        "<tr><td>18</td><td>17</td></tr></table></div>"
        "<article><p>Real content.</p></article>"
        "<div class='navfooter'><table summary='Navigation footer'>"
        "<tr><td>Prev</td><td>Next</td></tr></table></div>"
    )
    cleaned = strip_dom_noise(html)
    assert "navheader" not in cleaned
    assert "navfooter" not in cleaned
    assert "Navigation header" not in cleaned


def test_extract_main_content_strips_nav_leaves_content() -> None:
    """End-to-end: nav chrome is removed while synopsis/content survive."""
    html = (
        "<html><body>"
        "<div class='navheader'><table summary='Navigation header'>"
        "<tr><td>18</td><td>17</td><td>16</td></tr></table></div>"
        "<div class='refsect1'><h2>Synopsis</h2>"
        "<pre class='synopsis'>SELECT 1;</pre></div>"
        "<div class='navfooter'><table summary='Navigation footer'>"
        "<tr><td>Prev</td></tr></table></div>"
        "</body></html>"
    )
    result = extract_main_content(html)
    assert "```\nSELECT 1;\n```" in result
    assert "Prev" not in result
    assert "16" not in result


# --- B0A77532: HTML fidelity follow-ups ---


def test_definition_list_renders_terms_and_descriptions() -> None:
    """A <dl> renders each <dt> as a bold term with its <dd> description."""
    html = (
        "<article><dl>"
        "<dt>alpha</dt><dd><p>First param.</p></dd>"
        "<dt>beta</dt><dd><p>Second param.</p></dd>"
        "</dl></article>"
    )
    result = extract_main_content(html)
    assert "**alpha**" in result
    assert "First param." in result
    assert "**beta**" in result
    assert "Second param." in result


def test_table_colspan_repeats_cell_across_columns() -> None:
    """A colspan cell is expanded into each covered column."""
    html = (
        "<article><table>"
        "<tr><th colspan='2'>Header</th></tr>"
        "<tr><td>a</td><td>b</td></tr>"
        "</table></article>"
    )
    result = extract_main_content(html)
    assert "| Header | Header |" in result
    assert "| a | b |" in result


def test_table_rowspan_repeats_cell_down_rows() -> None:
    """A rowspan cell is expanded into each covered row."""
    html = (
        "<article><table>"
        "<tr><td rowspan='2'>X</td><td>a</td></tr>"
        "<tr><td>b</td></tr>"
        "</table></article>"
    )
    result = extract_main_content(html)
    assert "| X | a |" in result
    assert "| X | b |" in result


def test_pre_language_hint_from_code_class() -> None:
    """A <code class='language-sql'> inside <pre> yields a language-tagged fence."""
    html = "<article><pre><code class='language-sql'>SELECT 1;</code></pre></article>"
    result = extract_main_content(html)
    assert "```sql" in result
    assert "SELECT 1;" in result


def test_pre_without_language_hint_uses_plain_fence() -> None:
    """A <pre> without a recognized language class uses a plain fence."""
    html = "<article><pre class='synopsis'>SELECT 1;</pre></article>"
    result = extract_main_content(html)
    assert "```\nSELECT 1;\n```" in result
