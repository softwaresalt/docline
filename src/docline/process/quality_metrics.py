"""AST-aware quality metrics for extracted markdown.

This module computes structural and embedding-chunk-friendliness metrics
on markdown text via :mod:`markdown_it` parsing. The metrics are designed
to predict downstream utility for:

* **Graph databases** — heading hierarchy, code blocks, table structure
  produce node and edge candidates.
* **Vector embedding stores** — heading-anchored section length signals
  whether the output is naturally chunkable.
* **LLM context** — structural density measures information per token.

See ``docs/compound/2026-06-08-ast-fidelity-metrics.md`` for the decision
rule and the empirical study (``docs/decisions/2026-06-08-extraction-
strategy-study.md``) that motivated this metric set.

Public API:
    :class:`QualityMetrics` — frozen dataclass with 12 fields
    :func:`compute_quality_metrics` — computes metrics from a markdown string

Implementation note:
    The pure-text reference implementation lived in
    ``scripts/study/evaluate_markdown.py`` during the 2026-06-08 study.
    This module is the production promotion (021.002-T / 023-S T2).
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Any

from markdown_it import MarkdownIt

_HEADING_LINE_RE = re.compile(r"^#{1,6}\s")


def _default_parser() -> MarkdownIt:
    """Construct the default commonmark + tables parser used by the module."""
    return MarkdownIt("commonmark", {"html": True}).enable("table")


@dataclass(frozen=True)
class QualityMetrics:
    """AST-aware quality metrics for one markdown document.

    All fields are computed by :func:`compute_quality_metrics`.

    Attributes:
        parse_ok: True when the markdown parser produced at least one
            token, or the input was empty. False signals an unparseable
            input (rare — markdown-it is forgiving).
        char_len: Length of the input string in characters.
        token_count: Total number of markdown-it tokens emitted.
        heading_count: Number of ATX or Setext heading tokens.
        heading_depth_max: Deepest heading level present (1-6, 0 if no
            headings).
        list_item_count: Total list items across bullet and ordered lists.
        code_block_count: Number of fenced or indented code blocks.
        table_count: Number of tables (GFM table extension).
        table_cell_count: Total ``<td>`` + ``<th>`` cells across all tables.
        section_count: Number of heading-anchored sections. When the
            document has no headings, this is 1 (the entire document is
            one section).
        median_section_chars: Median section length in characters. Used
            to estimate embedding-chunk friendliness.
        structural_density_per_1k: Structural elements per 1000 characters,
            where "structural" = headings + list items + code blocks +
            blockquotes + table cells + links. Higher = richer structure
            per unit of content.
    """

    parse_ok: bool
    char_len: int
    token_count: int
    heading_count: int
    heading_depth_max: int
    list_item_count: int
    code_block_count: int
    table_count: int
    table_cell_count: int
    section_count: int
    median_section_chars: int
    structural_density_per_1k: float


def _parse_tokens(parser: MarkdownIt, text: str) -> list[Any]:
    """Parse text via the supplied parser, swallowing any parser exceptions.

    Broad-except is intentional here: markdown-it is forgiving and rarely
    raises, but the public ``compute_quality_metrics`` contract promises
    to never raise on any string input. Any parser exception degrades
    to an empty token list (which the caller surfaces as ``parse_ok=False``
    while still returning valid zero-or-best-effort metrics).
    """
    try:
        return parser.parse(text)
    except Exception:  # noqa: BLE001 — public API guarantees no raise
        return []


def _section_lengths(text: str, heading_count: int, char_len: int) -> list[int]:
    """Split text on heading lines and return the char length of each section.

    When the document has no headings (``heading_count == 0``), returns
    a single-element list ``[char_len]`` representing the whole document
    as one section.
    """
    if heading_count == 0:
        return [char_len]

    lines = text.split("\n")
    sections: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        if _HEADING_LINE_RE.match(line):
            if cur:
                sections.append(cur)
            cur = [line]
        else:
            cur.append(line)
    if cur:
        sections.append(cur)
    return [len("\n".join(s)) for s in sections]


def compute_quality_metrics(text: str, *, md_parser: MarkdownIt | None = None) -> QualityMetrics:
    """Compute AST-aware quality metrics for a markdown string.

    Args:
        text: The markdown source to analyze. May be empty.
        md_parser: Optional pre-configured :class:`markdown_it.MarkdownIt`
            parser. When ``None``, a default commonmark + tables parser
            is constructed. Provided primarily so callers can inject a
            singleton parser to avoid construction overhead in tight
            loops.

    Returns:
        A :class:`QualityMetrics` instance populated with all 12 metrics.

    Raises:
        Never raises on any string input. Malformed markdown is handled
        by the parser's recovery logic; truly unparseable input yields
        ``parse_ok=False`` but still returns a valid metrics object with
        zero-or-best-effort counts.
    """
    parser = md_parser if md_parser is not None else _default_parser()
    char_len = len(text)
    tokens = _parse_tokens(parser, text)
    parse_ok = bool(tokens) or char_len == 0

    type_counter: Counter[str] = Counter(t.type for t in tokens)

    headings_open = [t for t in tokens if t.type == "heading_open"]
    heading_count = len(headings_open)
    heading_levels = Counter(
        int(t.tag[1]) for t in headings_open if t.tag.startswith("h") and len(t.tag) >= 2
    )
    heading_depth_max = max(heading_levels) if heading_levels else 0

    list_item_count = type_counter.get("list_item_open", 0)
    code_block_count = type_counter.get("code_block", 0) + type_counter.get("fence", 0)
    blockquote_count = type_counter.get("blockquote_open", 0)

    table_count = type_counter.get("table_open", 0)
    table_cell_count = type_counter.get("td_open", 0) + type_counter.get("th_open", 0)

    # Inline-level: walk inline tokens for link_open
    inline_link_count = 0
    for t in tokens:
        if t.type == "inline" and t.children:
            for c in t.children:
                if c.type == "link_open":
                    inline_link_count += 1

    structural_total = (
        heading_count
        + list_item_count
        + code_block_count
        + blockquote_count
        + table_cell_count
        + inline_link_count
    )
    structural_density_per_1k = (structural_total / char_len * 1000) if char_len else 0.0

    section_lengths = _section_lengths(text, heading_count, char_len)
    section_count = len(section_lengths)
    median_section_chars = int(statistics.median(section_lengths)) if section_lengths else 0

    return QualityMetrics(
        parse_ok=parse_ok,
        char_len=char_len,
        token_count=len(tokens),
        heading_count=heading_count,
        heading_depth_max=heading_depth_max,
        list_item_count=list_item_count,
        code_block_count=code_block_count,
        table_count=table_count,
        table_cell_count=table_cell_count,
        section_count=section_count,
        median_section_chars=median_section_chars,
        structural_density_per_1k=round(structural_density_per_1k, 3),
    )


__all__ = ["QualityMetrics", "compute_quality_metrics"]
