"""Heading hierarchy validator for graphtor-docs chunk boundary alignment.

The graphtor-docs ingestion contract chunks documents on H1/H2/H3 boundaries.
Documents that skip ancestor levels (an H2 before any H1, an H3 before any
H2) produce incoherent chunk parentage. This validator enforces that the
three structurally significant heading levels nest top-down.

H4-H6 are present in source documents but not enforced — they sit below the
chunk-boundary horizon and their ordering does not affect parentage.
"""

from __future__ import annotations

from markdown_it import MarkdownIt

from docline.schema.models import DoclineError

_ENFORCED_LEVELS = (1, 2, 3)


class HeadingHierarchyError(DoclineError):
    """Raised when an H2 or H3 heading appears without its required ancestor."""


def validate_heading_hierarchy(markdown: str) -> None:
    """Validate top-down nesting of H1 -> H2 -> H3 headings.

    Args:
        markdown: Raw Markdown source.

    Raises:
        HeadingHierarchyError: If an enforced heading level appears before
            its required ancestor (e.g. an H2 before any H1, an H3 before
            any H2).
    """
    md = MarkdownIt()
    tokens = md.parse(markdown)

    seen_h1 = False
    seen_h2 = False

    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        level = int(token.tag[1:])
        if level not in _ENFORCED_LEVELS:
            continue

        heading_text = _heading_text(tokens, index)

        if level == 1:
            seen_h1 = True
            seen_h2 = False
            continue
        if level == 2:
            if not seen_h1:
                raise HeadingHierarchyError(f"H2 heading {heading_text!r} appeared before any H1")
            seen_h2 = True
            continue
        if level == 3:
            if not seen_h1:
                raise HeadingHierarchyError(f"H3 heading {heading_text!r} appeared before any H1")
            if not seen_h2:
                raise HeadingHierarchyError(f"H3 heading {heading_text!r} appeared before any H2")


def _heading_text(tokens: list, heading_open_index: int) -> str:
    """Extract heading text from the inline token following ``heading_open``."""
    inline_index = heading_open_index + 1
    if inline_index >= len(tokens):
        return ""
    inline_token = tokens[inline_index]
    if inline_token.type != "inline":
        return ""
    return (inline_token.content or "").strip()
