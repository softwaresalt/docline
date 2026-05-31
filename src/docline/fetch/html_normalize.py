"""Extracted heading hierarchy normalization for HTML-sourced Markdown."""

from docline.schema.models import DoclineError


class HeadingNormalizationError(DoclineError):
    """Raised when heading normalization cannot produce a valid hierarchy."""


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
    raise NotImplementedError(
        "stub: html_normalize.normalize_heading_hierarchy not yet implemented"
    )


def extract_headings(markdown: str) -> list[tuple[int, str]]:
    """Return a list of (level, text) pairs for all ATX headings in *markdown*.

    Args:
        markdown: Markdown text to scan.

    Returns:
        A list of ``(heading_level, heading_text)`` tuples in document order.
        Heading level is the count of leading ``#`` characters (1–6).
    """
    raise NotImplementedError("stub: html_normalize.extract_headings not yet implemented")


__all__ = [
    "HeadingNormalizationError",
    "extract_headings",
    "normalize_heading_hierarchy",
]
