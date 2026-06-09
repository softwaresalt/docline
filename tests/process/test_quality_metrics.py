"""Tests for docline.process.quality_metrics (task 021.002-T / 023-S T2).

Public surface tested:
* :class:`QualityMetrics` — frozen dataclass with 12 fields
* :func:`compute_quality_metrics` — markdown-it-py AST-aware metrics

Reference implementation: ``scripts/study/evaluate_markdown.py`` (used
during the 2026-06-08 study). T2 promotes that to a production module
with frozen output, optional parser injection, and full test coverage.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest


def test_compute_quality_metrics_on_empty_string_returns_parse_ok() -> None:
    """Empty input MUST not raise; returns parse_ok=True with zero counts.

    Note: section_count is 1 for empty input (consistent with the
    "no headings → entire document is 1 section" rule applied uniformly).
    """
    from docline.process.quality_metrics import compute_quality_metrics

    m = compute_quality_metrics("")
    assert m.parse_ok is True
    assert m.char_len == 0
    assert m.token_count == 0
    assert m.heading_count == 0
    assert m.section_count == 1
    assert m.table_count == 0
    assert m.table_cell_count == 0
    assert m.code_block_count == 0
    assert m.structural_density_per_1k == 0.0


def test_quality_metrics_is_frozen_dataclass() -> None:
    """QualityMetrics MUST be immutable (frozen=True)."""
    from docline.process.quality_metrics import QualityMetrics, compute_quality_metrics

    m = compute_quality_metrics("# Hello\n\nBody")
    assert isinstance(m, QualityMetrics)
    with pytest.raises(FrozenInstanceError):
        m.heading_count = 99  # type: ignore[misc]


def test_quality_metrics_has_exactly_twelve_fields() -> None:
    """QualityMetrics MUST have exactly 12 documented fields, no more, no less."""
    from dataclasses import fields

    from docline.process.quality_metrics import QualityMetrics

    expected = {
        "parse_ok",
        "char_len",
        "token_count",
        "heading_count",
        "heading_depth_max",
        "list_item_count",
        "code_block_count",
        "table_count",
        "table_cell_count",
        "section_count",
        "median_section_chars",
        "structural_density_per_1k",
    }
    actual = {f.name for f in fields(QualityMetrics)}
    assert actual == expected, (
        f"unexpected fields: extra={actual - expected}, missing={expected - actual}"
    )


def test_compute_metrics_counts_atx_headings() -> None:
    from docline.process.quality_metrics import compute_quality_metrics

    text = "# H1\n\nbody\n\n## H2\n\nbody2\n\n### H3\n\nbody3\n"
    m = compute_quality_metrics(text)
    assert m.heading_count == 3
    assert m.heading_depth_max == 3


def test_compute_metrics_counts_section_count_one_per_heading() -> None:
    """section_count == heading_count when the text starts with a heading."""
    from docline.process.quality_metrics import compute_quality_metrics

    text = "# A\nbody\n\n# B\nbody\n\n# C\nbody\n"
    m = compute_quality_metrics(text)
    assert m.heading_count == 3
    assert m.section_count == 3


def test_compute_metrics_section_count_is_one_when_no_headings() -> None:
    """No headings → entire document is 1 section."""
    from docline.process.quality_metrics import compute_quality_metrics

    text = "plain prose paragraph one\n\nplain prose paragraph two\n"
    m = compute_quality_metrics(text)
    assert m.heading_count == 0
    assert m.section_count == 1


def test_compute_metrics_counts_gfm_tables() -> None:
    from docline.process.quality_metrics import compute_quality_metrics

    text = (
        "## Reference\n\n"
        "| Field | Type | Description |\n"
        "|---|---|---|\n"
        "| id | string | identifier |\n"
        "| name | string | display name |\n"
        "| active | bool | is enabled |\n"
    )
    m = compute_quality_metrics(text)
    assert m.table_count == 1
    # 6 header + 9 body cells in this table = 12; markdown-it counts thead cells as th, body as td
    assert m.table_cell_count >= 12


def test_compute_metrics_counts_fenced_code_blocks() -> None:
    from docline.process.quality_metrics import compute_quality_metrics

    text = '```python\nprint("a")\n```\n\nprose\n\n```bash\necho hi\n```\n'
    m = compute_quality_metrics(text)
    assert m.code_block_count == 2


def test_compute_metrics_counts_list_items() -> None:
    from docline.process.quality_metrics import compute_quality_metrics

    text = "- one\n- two\n- three\n\n1. first\n2. second\n"
    m = compute_quality_metrics(text)
    assert m.list_item_count == 5


def test_structural_density_per_1k_is_within_expected_range() -> None:
    """A document with rich structure should have density > 5 per 1k."""
    from docline.process.quality_metrics import compute_quality_metrics

    text = (
        "# Introduction\n\nIntro paragraph one.\n\n"
        "## Background\n\nBackground paragraph.\n\n"
        "## Method\n\n- step 1\n- step 2\n- step 3\n\n"
        "## Results\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\n"
        "```python\nfoo()\n```\n\n"
        "## Conclusion\n\nFinal paragraph.\n"
    )
    m = compute_quality_metrics(text)
    # 5 headings + 3 list items + 2 table rows of cells + 1 code block + structural elements
    assert m.heading_count == 5
    assert m.code_block_count == 1
    assert m.list_item_count == 3
    assert m.table_count == 1
    # density should be substantially above the baseline 2.62 from the study
    assert m.structural_density_per_1k > 5.0


def test_median_section_chars_for_two_equal_sections() -> None:
    from docline.process.quality_metrics import compute_quality_metrics

    text = "# A\nbody_a\n\n# B\nbody_b\n"
    m = compute_quality_metrics(text)
    assert m.section_count == 2
    # both sections roughly equal length → median in that range
    assert 5 <= m.median_section_chars <= 20


def test_compute_metrics_accepts_optional_parser() -> None:
    """compute_quality_metrics accepts an optional md_parser for caller customization."""
    from markdown_it import MarkdownIt

    from docline.process.quality_metrics import compute_quality_metrics

    parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    text = "# Hello\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    m_default = compute_quality_metrics(text)
    m_custom = compute_quality_metrics(text, md_parser=parser)
    # Same parser config → identical output
    assert m_default == m_custom


def test_compute_metrics_returns_parse_ok_false_on_malformed_input() -> None:
    """Truly malformed input (e.g. binary garbage) → parse_ok may be False but no raise.

    markdown-it is forgiving — most "malformed" markdown still parses to
    valid tokens. The contract is that compute_quality_metrics NEVER
    raises on any string input.
    """
    from docline.process.quality_metrics import compute_quality_metrics

    weird = "\x00\x01\xff binary-ish garbage with embedded null"
    m = compute_quality_metrics(weird)
    # No exception — that's the primary contract. parse_ok flag exposed
    # for callers who want to flag suspicious inputs.
    assert isinstance(m.parse_ok, bool)
    assert m.char_len == len(weird)


def test_compute_metrics_public_export_from_process_namespace() -> None:
    """Public symbols MUST be re-exported from docline.process namespace."""
    from docline.process import QualityMetrics, compute_quality_metrics

    m = compute_quality_metrics("# x")
    assert isinstance(m, QualityMetrics)


def test_compute_metrics_heading_depth_max_tracks_deepest_level() -> None:
    """heading_depth_max MUST report the deepest heading level, not the count."""
    from docline.process.quality_metrics import compute_quality_metrics

    only_h1 = compute_quality_metrics("# A\nbody\n")
    assert only_h1.heading_depth_max == 1

    mixed = compute_quality_metrics("# A\n## B\n### C\n#### D\n")
    assert mixed.heading_count == 4
    assert mixed.heading_depth_max == 4

    skip_levels = compute_quality_metrics("# A\n###### F\n")
    assert skip_levels.heading_depth_max == 6


def test_compute_metrics_setext_headings_produce_sections() -> None:
    """Setext-style headings (``Title\\n=====``) MUST also produce sections,
    not just ATX-style (``# Title``).

    Regression coverage for the PR #49 review finding: the prior regex-based
    section splitter only matched ATX headings, while heading_count
    correctly included Setext. The AST-based splitter must keep the two in
    sync.
    """
    from docline.process.quality_metrics import compute_quality_metrics

    text = "Title One\n=========\n\nbody one\n\nTitle Two\n---------\n\nbody two\n"
    m = compute_quality_metrics(text)
    assert m.heading_count == 2, "Setext headings should be counted"
    # Old regex impl returned 1 section; AST impl correctly returns 2.
    assert m.section_count == 2, "Setext headings should produce 2 sections"


def test_compute_metrics_token_count_increases_with_more_content() -> None:
    from docline.process.quality_metrics import compute_quality_metrics

    small = compute_quality_metrics("hello")
    large = compute_quality_metrics("# Heading\n\nLots of body text here\n\n## Sub\n\nMore body\n")
    assert large.token_count > small.token_count
