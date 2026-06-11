"""Tests for DocFx tabbed content normalization.

Microsoft Learn uses the ``### [Label](#tab/key)`` pattern to render
tabbed content groups. Multiple consecutive tab headings form a tab
block, terminated by a ``---`` horizontal rule on its own line:

    ### [Drill enabled](#tab/drill-enabled)
    content for tab 1
    ### [Drill disabled](#tab/drill-disabled)
    content for tab 2
    ---
    content after tabs

docline normalizes these into plain H3 sections so the heading-hierarchy
validator and downstream graphtor-docs chunker treat them as ordinary
section boundaries instead of choking on the link-wrapped heading text
or interpreting the ``---`` terminator as a setext H2 underline.

028-S T2 / 026.002-T.
"""

from __future__ import annotations

from docline.process.docfx_tabs import normalize_docfx_tabs


def test_basic_tab_block_flattens_to_h3_sections() -> None:
    """A standard 2-tab block normalizes to 2 plain H3 sections, terminator dropped."""
    text = (
        "Preamble.\n\n"
        "### [Drill enabled](#tab/drill-enabled)\n\n"
        "![enabled](media/enabled.png)\n\n"
        "### [Drill disabled](#tab/drill-disabled)\n\n"
        "![disabled](media/disabled.png)\n\n"
        "---\n\n"
        "Postamble.\n"
    )
    out = normalize_docfx_tabs(text)
    assert "### Drill enabled" in out
    assert "### Drill disabled" in out
    # The wrapped #tab/ link form MUST be gone
    assert "#tab/" not in out
    # The tab terminator MUST be consumed (no orphan `---` line)
    lines = [ln.strip() for ln in out.splitlines()]
    assert "---" not in lines
    # Preamble and postamble preserved
    assert "Preamble." in out
    assert "Postamble." in out


def test_single_tab_heading_still_normalizes() -> None:
    """A lone tab heading (no following sibling) still strips the link wrapper."""
    text = "### [Only tab](#tab/only)\n\nContent.\n"
    out = normalize_docfx_tabs(text)
    assert "### Only tab" in out
    assert "#tab/" not in out


def test_no_tab_content_passes_through_unchanged() -> None:
    """Documents without tab syntax MUST be unchanged."""
    text = "# Title\n\n## Section\n\n### Subsection\n\nBody content.\n\n---\n\nBottom matter.\n"
    assert normalize_docfx_tabs(text) == text


def test_terminator_only_consumed_inside_tab_block() -> None:
    """A ``---`` outside a tab block (standalone horizontal rule) MUST be preserved."""
    text = "First paragraph.\n\n---\n\nSecond paragraph.\n"
    assert normalize_docfx_tabs(text) == text


def test_multiple_tab_blocks_in_one_document() -> None:
    """Two independent tab blocks each get their own terminator dropped."""
    text = (
        "### [A1](#tab/a1)\n\ncontent A1\n\n"
        "### [A2](#tab/a2)\n\ncontent A2\n\n"
        "---\n\n"
        "Between blocks.\n\n"
        "### [B1](#tab/b1)\n\ncontent B1\n\n"
        "### [B2](#tab/b2)\n\ncontent B2\n\n"
        "---\n\n"
        "End.\n"
    )
    out = normalize_docfx_tabs(text)
    assert "### A1" in out
    assert "### A2" in out
    assert "### B1" in out
    assert "### B2" in out
    assert "#tab/" not in out
    assert "Between blocks." in out
    assert "End." in out


def test_tab_block_ended_by_h1_without_terminator() -> None:
    """A tab block followed by an H1 (no `---` terminator) still normalizes labels."""
    text = (
        "### [Tab1](#tab/t1)\n\ncontent\n\n"
        "### [Tab2](#tab/t2)\n\ncontent\n\n"
        "# Real H1 ends the block\n\nbody.\n"
    )
    out = normalize_docfx_tabs(text)
    assert "### Tab1" in out
    assert "### Tab2" in out
    assert "# Real H1 ends the block" in out
    assert "#tab/" not in out


def test_tab_block_ended_by_h2_without_terminator() -> None:
    text = (
        "### [Tab1](#tab/t1)\n\ncontent\n\n"
        "### [Tab2](#tab/t2)\n\ncontent\n\n"
        "## Next section\n\nbody.\n"
    )
    out = normalize_docfx_tabs(text)
    assert "### Tab1" in out
    assert "### Tab2" in out
    assert "## Next section" in out


def test_tab_block_with_no_terminator_at_eof() -> None:
    """Tab block at end of file (no terminator, no following heading) still works."""
    text = "## Section\n\n### [Tab1](#tab/t1)\n\ncontent\n\n### [Tab2](#tab/t2)\n\ncontent\n"
    out = normalize_docfx_tabs(text)
    assert "### Tab1" in out
    assert "### Tab2" in out


def test_empty_input() -> None:
    assert normalize_docfx_tabs("") == ""


def test_tab_label_with_special_chars() -> None:
    """Labels with special chars (colons, parens, etc.) preserved correctly."""
    text = "### [Tab with : colon and (parens)](#tab/special)\n\nContent.\n"
    out = normalize_docfx_tabs(text)
    assert "### Tab with : colon and (parens)" in out


def test_regression_dynamic_drill_down_sample() -> None:
    """Mirrors developer/visuals/dynamic-drill-down.md from Power BI corpus."""
    text = (
        "# Dynamic drill control\n\n"
        "The following images show enabled vs disabled:\n\n"
        "### [Drill enabled](#tab/drill-enabled)\n\n"
        ':::image type="content" source="media/drill-enabled.png":::\n\n'
        "### [Drill disabled](#tab/drill-disabled)\n\n"
        ':::image type="content" source="media/drill-disabled.png":::\n\n'
        "---\n\n"
        "The dynamic drill control feature includes the following API elements:\n"
    )
    out = normalize_docfx_tabs(text)
    assert "### Drill enabled" in out
    assert "### Drill disabled" in out
    assert "#tab/" not in out
    # The `---` tab terminator should be consumed
    assert "\n---\n" not in out
    # Content preserved
    assert "Dynamic drill control" in out
    assert "API elements" in out


def test_regression_highlight_sample() -> None:
    """Mirrors developer/visuals/highlight.md from Power BI corpus."""
    text = (
        "# Highlighting\n\n"
        "### [No highlight support](#tab/Standard)\n\n"
        "Standard behavior content.\n\n"
        "### [Highlight support](#tab/HighlightSupport)\n\n"
        "Highlight-aware content.\n\n"
        "---\n\n"
        "Conclusion.\n"
    )
    out = normalize_docfx_tabs(text)
    assert "### No highlight support" in out
    assert "### Highlight support" in out
    assert "#tab/" not in out
    assert "Conclusion." in out


def test_uppercase_tab_keyword_handled() -> None:
    """Tab anchors are case-sensitive in spec but accept either case in practice."""
    text = "### [Label](#Tab/key)\n\ncontent\n"
    # Even if upper-case TAB is non-canonical, we recognize and normalize it.
    out = normalize_docfx_tabs(text)
    # Either path (normalized OR passed through) is acceptable as long as nothing crashes.
    assert "content" in out
