"""Heading-aware semantic segmentation for processed markdown output.

Splits rendered markdown at H1 boundaries, sub-splits at H2 when a single
H1-bounded part exceeds ``max_chars``, and falls back to deterministic
char-binning when no H1 headings are present or when sub-splitting cannot
reach the target size. The contract is identical for PDF (post-extraction)
and DOCX (post ``read_docx_blocks`` join). Web/HTML inputs are unaffected
because the existing ``output_contract`` path keeps them single-file.
"""

from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.token import Token

_DEFAULT_MAX_CHARS = 12_000


def segment_markdown(markdown: str, *, max_chars: int = _DEFAULT_MAX_CHARS) -> list[str]:
    """Return ordered semantic segments of ``markdown``.

    The algorithm:

    1. If the input is empty or whitespace-only, return ``[""]``.
    2. If no H1 heading is present, fall back to ``_char_bin``.
    3. Otherwise split at every H1 boundary.
    4. For each H1 segment over ``max_chars``, attempt an H2 sub-split.
       If sub-splitting yields a single sub-segment (no H2 present), or
       any sub-segment is still over ``max_chars``, fall back to
       ``_char_bin`` for that H1 part.
    5. Strip leading/trailing whitespace per segment; drop empty
       segments; return ``[""]`` if the final list is empty.

    Args:
        markdown: Rendered markdown text from an upstream extractor.
        max_chars: Soft upper bound for emitted segment length. Defaults
            to 12_000.

    Returns:
        Non-empty ordered list of markdown segments. Always returns at
        least one element. ``[""]`` for empty or whitespace-only input.
    """
    if not markdown or not markdown.strip():
        return [""]

    tokens = _parse(markdown)
    has_h1 = any(_is_heading(token, level=1) for token in tokens)
    if not has_h1:
        return _finalize(_char_bin(markdown, max_chars))

    h1_parts = _split_at_level(markdown, 1)
    output: list[str] = []
    for part in h1_parts:
        if len(part) <= max_chars:
            output.append(part)
            continue
        sub_parts = _split_at_level(part, 2)
        if len(sub_parts) <= 1 or any(len(sub) > max_chars for sub in sub_parts):
            output.extend(_char_bin(part, max_chars))
        else:
            output.extend(sub_parts)

    return _finalize(output)


def _split_at_level(markdown: str, level: int) -> list[str]:
    """Return ordered segments split at every ATX heading of ``level``.

    A segment starts at a ``heading_open`` token of ``level`` and runs
    until the next ``heading_open`` token of the same level (or the end
    of the document). Any prelude text before the first heading at this
    level is emitted as the leading segment.

    Splitting operates on line boundaries (``token.map``), preserving
    fenced code blocks, GFM tables, and source whitespace.

    Args:
        markdown: Markdown text to split.
        level: Heading level to split on (1 for H1, 2 for H2).

    Returns:
        Ordered non-overlapping segments covering the entire input. The
        list always has at least one element (the input itself when no
        heading at ``level`` is present).
    """
    tokens = _parse(markdown)
    heading_lines: list[int] = []
    for token in tokens:
        if _is_heading(token, level=level) and token.map is not None:
            heading_lines.append(token.map[0])

    if not heading_lines:
        return [markdown]

    lines = markdown.splitlines(keepends=True)
    boundaries = [0, *heading_lines, len(lines)]
    seen: set[int] = set()
    ordered: list[int] = []
    for boundary in boundaries:
        if boundary not in seen:
            seen.add(boundary)
            ordered.append(boundary)
    ordered.sort()

    segments: list[str] = []
    for start, end in zip(ordered, ordered[1:]):
        segments.append("".join(lines[start:end]))
    return segments


def _char_bin(text: str, max_chars: int) -> list[str]:
    """Final-safety-net char binner that splits on paragraph boundaries.

    Splits ``text`` on blank-line paragraph boundaries (``\\n\\n``)
    greedily, never exceeding ``max_chars`` per bin when possible. A
    single paragraph longer than ``max_chars`` is emitted as its own bin
    (no mid-paragraph cut). Empty paragraphs are dropped.

    Args:
        text: Text to bin.
        max_chars: Soft upper bound per bin.

    Returns:
        Ordered list of bins. Empty input yields ``[""]``.
    """
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n")]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    if not paragraphs:
        return [""]

    bins: list[str] = []
    current: list[str] = []
    current_length = 0
    for paragraph in paragraphs:
        projected = current_length + len(paragraph) + (2 if current else 0)
        if current and projected > max_chars:
            bins.append("\n\n".join(current))
            current = [paragraph]
            current_length = len(paragraph)
            continue
        current.append(paragraph)
        current_length = projected
    if current:
        bins.append("\n\n".join(current))
    return bins


def _parse(markdown: str) -> list[Token]:
    """Tokenize ``markdown`` with GFM tables enabled.

    Tables are enabled per the plan-review P2 finding so GFM table tokens
    stay at the block level for clean ``token.map``-based slicing rather
    than degrading to inline interpretation.

    Args:
        markdown: Source markdown.

    Returns:
        Flat token list as returned by ``MarkdownIt.parse``.
    """
    parser = MarkdownIt().enable("table")
    return parser.parse(markdown)


def _is_heading(token: Token, *, level: int) -> bool:
    """Return True when ``token`` is an ATX ``heading_open`` of ``level``."""
    return token.type == "heading_open" and token.tag == f"h{level}"


def _finalize(segments: list[str]) -> list[str]:
    """Strip per-segment whitespace, drop empties, and return ``[""]`` if all empty."""
    cleaned = [segment.strip() for segment in segments]
    cleaned = [segment for segment in cleaned if segment]
    if not cleaned:
        return [""]
    return cleaned


def extract_section_title(segment: str) -> str | None:
    """Return the first H1 heading text from ``segment`` or ``None`` if absent.

    The returned text is stripped of the leading ``"# "`` marker and any
    trailing whitespace. Returns ``None`` for segments produced by the
    char-bin fallback (no H1 heading present).

    Args:
        segment: A single semantic markdown segment as produced by
            ``segment_markdown``.

    Returns:
        The H1 heading text or ``None``.
    """
    if not segment or not segment.strip():
        return None
    tokens = _parse(segment)
    for index, token in enumerate(tokens):
        if _is_heading(token, level=1) and index + 1 < len(tokens):
            inline = tokens[index + 1]
            if inline.type == "inline" and inline.content:
                return inline.content.strip()
    return None


__all__ = ["segment_markdown", "extract_section_title"]
