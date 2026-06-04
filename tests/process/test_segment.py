"""Failing-first tests for heading-aware semantic segmentation.

These tests are written before ``src/docline/process/segment.py`` exists
(TDD RED phase for task 012.001-T). The implementation in task 012.002-T
turns them green.
"""

from __future__ import annotations

import pytest

from docline.process.segment import segment_markdown

_MAX = 12_000


def _para(seed: str, target_chars: int) -> str:
    """Return a paragraph of roughly ``target_chars`` length, no headings.

    Uses repeated sentence-like text so the result is plain prose without
    any markdown structural tokens (no '#', no '|', no fenced code).
    """
    sentence = f"This is a sentence about {seed} that contains enough words to fill space. "
    return (sentence * ((target_chars // len(sentence)) + 1))[:target_chars]


def _multi_para(seed: str, paragraphs: int, chars_per_para: int) -> str:
    """Return multiple paragraphs separated by blank lines (no headings)."""
    return "\n\n".join(_para(f"{seed}-{i}", chars_per_para) for i in range(paragraphs))


def test_no_heading_fallback_single_segment() -> None:
    """Plain prose under max_chars and no headings returns a single segment."""
    text = _para("alpha", 5_000)
    result = segment_markdown(text)
    assert len(result) == 1
    assert result[0].strip() == text.strip()


def test_no_heading_fallback_char_binned() -> None:
    """Plain prose of ~30k chars with no headings is char-binned under the limit.

    Each emitted segment must be at or below ``max_chars``, and no paragraph
    is cut mid-paragraph.
    """
    text = _multi_para("beta", paragraphs=12, chars_per_para=2_800)
    result = segment_markdown(text)
    assert len(result) > 1
    for segment in result:
        assert len(segment) <= _MAX, f"segment length {len(segment)} exceeds max {_MAX}"
    rejoined = "\n\n".join(segment.strip() for segment in result)
    for paragraph in text.split("\n\n"):
        if paragraph.strip():
            assert paragraph.strip() in rejoined


def test_h1_split_two_chapters() -> None:
    """Two H1 sections under max_chars each yield two segments, each starting with '# '."""
    text = "# Chapter One\n\n" + _para("c1", 2_000) + "\n\n# Chapter Two\n\n" + _para("c2", 2_000)
    result = segment_markdown(text)
    assert len(result) == 2
    assert result[0].lstrip().startswith("# Chapter One")
    assert result[1].lstrip().startswith("# Chapter Two")


def test_h1_split_three_chapters_one_oversize() -> None:
    """Three H1 sections with an oversize middle yield more than three segments.

    The middle H1 is expanded into multiple H2 sub-parts (or char-bin
    fallback if no H2). The first and third H1 sections remain intact.
    """
    middle_body = (
        _para("middle-a", 7_000)
        + "\n\n## Sub Alpha\n\n"
        + _para("middle-b", 7_000)
        + "\n\n## Sub Beta\n\n"
        + _para("middle-c", 7_000)
    )
    text = (
        "# First\n\n"
        + _para("first", 1_500)
        + "\n\n# Middle\n\n"
        + middle_body
        + "\n\n# Last\n\n"
        + _para("last", 1_500)
    )
    result = segment_markdown(text)
    assert len(result) >= 5
    assert result[0].lstrip().startswith("# First")
    assert result[-1].lstrip().startswith("# Last")
    for segment in result:
        assert len(segment) <= _MAX


def test_h2_subsplit_under_max_chars() -> None:
    """An oversize H1 with H2 sub-headings sub-splits at H2 boundaries.

    The first emitted segment retains the H1 heading line.
    """
    text = (
        "# Big Chapter\n\n"
        + _para("intro", 5_000)
        + "\n\n## Section A\n\n"
        + _para("a", 5_000)
        + "\n\n## Section B\n\n"
        + _para("b", 5_000)
    )
    result = segment_markdown(text)
    assert len(result) >= 2
    assert result[0].lstrip().startswith("# Big Chapter")
    joined = "\n\n".join(result)
    assert "## Section A" in joined
    assert "## Section B" in joined
    for segment in result:
        assert len(segment) <= _MAX


def test_h2_subsplit_when_h1_oversize_no_h2() -> None:
    """An oversize H1 with no H2 falls back to char-bin; each segment <= max_chars."""
    text = "# Solo\n\n" + _multi_para("solo", paragraphs=10, chars_per_para=2_800)
    result = segment_markdown(text)
    assert len(result) > 1
    for segment in result:
        assert len(segment) <= _MAX


def test_h2_subsplit_when_h2_subpart_still_oversize() -> None:
    """When an H2 sub-part still exceeds max_chars, char-bin fallback engages.

    Every emitted segment must remain under the limit.
    """
    text = (
        "# H1\n\n"
        + "## A\n\n"
        + _multi_para("a", paragraphs=8, chars_per_para=2_800)
        + "\n\n## B\n\n"
        + _para("b", 1_000)
    )
    result = segment_markdown(text)
    assert len(result) > 1
    for segment in result:
        assert len(segment) <= _MAX


def test_empty_input_returns_single_empty() -> None:
    """Empty string input returns the single-empty-segment contract ['']."""
    assert segment_markdown("") == [""]


def test_whitespace_only_input_returns_single_empty() -> None:
    """Whitespace-only input returns ['']."""
    assert segment_markdown("\n\n   \n") == [""]


def test_deterministic_idempotent() -> None:
    """Calling segment_markdown twice on identical input yields identical output."""
    text = "# A\n\n" + _para("a", 3_000) + "\n\n# B\n\n" + _para("b", 3_000)
    assert segment_markdown(text) == segment_markdown(text)


def test_preserves_code_fences() -> None:
    """A fenced code block under an H1 is emitted whole, not split mid-fence."""
    fence = "```python\n" + "\n".join(f"x_{i} = {i}" for i in range(60)) + "\n```"
    text = "# Code\n\n" + fence + "\n\n" + _para("after", 1_000)
    result = segment_markdown(text)
    joined = "\n\n".join(result)
    assert fence in joined
    for segment in result:
        opens = segment.count("```")
        assert opens % 2 == 0, (
            "fenced code block boundaries must remain balanced inside each segment"
        )


def test_preserves_tables() -> None:
    """A GFM table under an H1 is emitted whole, not split mid-row."""
    table = "| col1 | col2 | col3 |\n|------|------|------|\n" + "\n".join(
        f"| a{i} | b{i} | c{i} |" for i in range(40)
    )
    text = "# Table\n\n" + table + "\n\n" + _para("trailing", 1_000)
    result = segment_markdown(text)
    joined = "\n\n".join(result)
    assert table in joined


def test_max_chars_parameter_honored() -> None:
    """Passing a custom max_chars produces correspondingly smaller segments."""
    text = _multi_para("gamma", paragraphs=10, chars_per_para=900)
    result = segment_markdown(text, max_chars=5_000)
    assert len(result) > 1
    for segment in result:
        assert len(segment) <= 5_000


@pytest.mark.parametrize("max_chars", [3_000, 8_000, 15_000])
def test_max_chars_no_oversize_segments(max_chars: int) -> None:
    """For varied max_chars values, no emitted segment exceeds the configured limit."""
    text = "# Chapter\n\n" + _multi_para("delta", paragraphs=15, chars_per_para=1_200)
    result = segment_markdown(text, max_chars=max_chars)
    for segment in result:
        assert len(segment) <= max_chars
