"""Test harness for 003.005-T — Normalize extracted heading hierarchy.

Acceptance criteria:
- normalize_heading_hierarchy() returns Markdown starting at H1.
- Promotes the highest heading when no H1 is present.
- Fills contiguous gaps when heading levels are skipped.
- Operation is idempotent on already-normalized input.
- extract_headings() returns (level, text) pairs in document order.

Harness pattern: structural tests verify scaffold shape (PASS); behavioral
tests assert return values or typed exceptions (FAIL in red phase).
"""

from docline.fetch.html_normalize import (
    HeadingNormalizationError,
    extract_headings,
    normalize_heading_hierarchy,
)
from docline.schema.models import DoclineError

# ---------------------------------------------------------------------------
# Structural: error hierarchy (PASS in red phase)
# ---------------------------------------------------------------------------


def test_heading_normalization_error_is_docline_error() -> None:
    """HeadingNormalizationError is a subclass of DoclineError."""
    err = HeadingNormalizationError("cannot normalize")
    assert isinstance(err, DoclineError)


# ---------------------------------------------------------------------------
# Behavioral: extract_headings (FAIL in red phase)
# ---------------------------------------------------------------------------


def test_extract_headings_returns_list() -> None:
    """extract_headings returns a list."""
    result = extract_headings("# Title\n\n## Section\n\nContent.")
    assert isinstance(result, list)


def test_extract_headings_finds_h1() -> None:
    """extract_headings returns (1, 'Title') for an H1 heading."""
    result = extract_headings("# Title\n\nBody text.")
    assert (1, "Title") in result


def test_extract_headings_finds_h2() -> None:
    """extract_headings returns (2, 'Section') for an H2 heading."""
    result = extract_headings("# Title\n\n## Section\n\nContent.")
    assert (2, "Section") in result


def test_extract_headings_returns_empty_for_no_headings() -> None:
    """extract_headings returns an empty list when no headings are present."""
    result = extract_headings("Just some text with no headings.")
    assert result == []


def test_extract_headings_preserves_document_order() -> None:
    """extract_headings returns headings in the order they appear."""
    md = "# First\n\n## Second\n\n### Third\n"
    result = extract_headings(md)
    levels = [lvl for lvl, _ in result]
    assert levels == [1, 2, 3]


def test_extract_headings_returns_empty_for_empty_input() -> None:
    """extract_headings returns an empty list for empty Markdown."""
    result = extract_headings("")
    assert result == []


# ---------------------------------------------------------------------------
# Behavioral: normalize_heading_hierarchy (FAIL in red phase)
# ---------------------------------------------------------------------------

_ALREADY_VALID = "# Title\n\n## Section\n\n### Subsection\n\nContent."
_NO_H1 = "## Section\n\n### Subsection\n\nContent without H1."
_SKIPPED_LEVEL = "# Title\n\n### Jump to H3\n\nContent."


def test_normalize_heading_hierarchy_returns_string_from_valid() -> None:
    """normalize_heading_hierarchy returns a string for already-valid input."""
    result = normalize_heading_hierarchy(_ALREADY_VALID)
    assert isinstance(result, str)


def test_normalize_heading_hierarchy_idempotent_on_valid_input() -> None:
    """normalize_heading_hierarchy is idempotent on already-valid Markdown."""
    first = normalize_heading_hierarchy(_ALREADY_VALID)
    second = normalize_heading_hierarchy(first)
    assert first == second


def test_normalize_heading_hierarchy_produces_h1_from_no_h1() -> None:
    """normalize_heading_hierarchy produces an H1 heading when none is present."""
    result = normalize_heading_hierarchy(_NO_H1)
    assert result.startswith("# ")


def test_normalize_heading_hierarchy_fills_skipped_level() -> None:
    """normalize_heading_hierarchy produces no skipped levels."""
    result = normalize_heading_hierarchy(_SKIPPED_LEVEL)
    headings = extract_headings(result)
    levels = [lvl for lvl, _ in headings]
    for i in range(len(levels) - 1):
        assert levels[i + 1] - levels[i] <= 1


def test_normalize_heading_hierarchy_returns_string_for_body_only() -> None:
    """normalize_heading_hierarchy returns a string for body-only Markdown."""
    result = normalize_heading_hierarchy("Just paragraph text.\n\nNo headings.")
    assert isinstance(result, str)
