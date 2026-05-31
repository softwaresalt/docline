"""Extracted heading hierarchy normalization for HTML-sourced Markdown."""

import re

from docline.schema.models import DoclineError


class HeadingNormalizationError(DoclineError):
    """Raised when heading normalization cannot produce a valid hierarchy."""


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)$")


def normalize_heading_hierarchy(markdown: str) -> str:
    """Normalize heading levels in Markdown to a valid root hierarchy.

    Rules applied:

    1. If no ``#`` (H1) heading is present, promote the highest heading
       level found to H1 and shift all others proportionally.
    2. If heading levels skip (e.g. H1 → H3), insert the missing level
       so the cascade is contiguous.
    3. The operation is idempotent: already-normalized input is returned
       unchanged.

    Args:
        markdown: Markdown text with potentially un-normalized headings.

    Returns:
        Markdown text with a valid root heading hierarchy.

    Raises:
        HeadingNormalizationError: If the heading structure cannot be
            normalized to a valid root hierarchy.
    """
    headings = extract_headings(markdown)
    if not headings:
        return markdown

    min_level = min(level for level, _ in headings)
    shift = min_level - 1
    shifted_levels = [level - shift for level, _ in headings]

    normalized_levels: list[int] = []
    prev_level = 0
    for level in shifted_levels:
        normalized_level = level
        if normalized_level > prev_level + 1:
            normalized_level = prev_level + 1
        normalized_levels.append(normalized_level)
        prev_level = normalized_level

    result_lines: list[str] = []
    heading_index = 0
    for line in markdown.split("\n"):
        match = _HEADING_RE.match(line)
        if match:
            text = match.group(2).strip()
            result_lines.append(f"{'#' * normalized_levels[heading_index]} {text}")
            heading_index += 1
        else:
            result_lines.append(line)
    return "\n".join(result_lines)


def extract_headings(markdown: str) -> list[tuple[int, str]]:
    """Return a list of (level, text) pairs for all ATX headings in *markdown*.

    Args:
        markdown: Markdown text to scan.

    Returns:
        A list of ``(heading_level, heading_text)`` tuples in document order.
        Heading level is the count of leading ``#`` characters (1–6).
    """
    if not markdown:
        return []

    headings: list[tuple[int, str]] = []
    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            headings.append((len(match.group(1)), match.group(2).strip()))
    return headings


__all__ = [
    "HeadingNormalizationError",
    "extract_headings",
    "normalize_heading_hierarchy",
]
