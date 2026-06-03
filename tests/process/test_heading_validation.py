"""Red-first tests for heading hierarchy validator (010-S F3.T1).

Validates that ``validate_heading_hierarchy`` enforces top-down nesting
for H1→H2→H3 (the structurally significant levels) and raises
``HeadingHierarchyError`` when a heading skips an ancestor level
(e.g. H2 before any H1, H3 before any H2). H4-H6 are present in the
document but not enforced — only the top three levels matter for the
graphtor-docs chunk boundary strategy ``h1-h2-h3``.
"""

from __future__ import annotations

import pytest

from docline.process.heading_validation import (
    HeadingHierarchyError,
    validate_heading_hierarchy,
)
from docline.schema.models import DoclineError


def test_valid_hierarchy_passes() -> None:
    """A canonical H1 → H2 → H3 nest validates cleanly."""
    markdown = (
        "# Top\n\n"
        "## Section A\n\n"
        "### Subsection 1\n\n"
        "Body text.\n\n"
        "### Subsection 2\n\n"
        "## Section B\n\n"
        "### Subsection 3\n"
    )
    validate_heading_hierarchy(markdown)


def test_h2_before_h1_raises() -> None:
    """An H2 appearing before any H1 must be rejected."""
    markdown = "## Stray H2\n\nBody\n\n# Top\n"
    with pytest.raises(HeadingHierarchyError):
        validate_heading_hierarchy(markdown)


def test_h3_before_h2_raises() -> None:
    """An H3 appearing before any H2 must be rejected even if H1 exists."""
    markdown = "# Top\n\n### Premature subsection\n\nBody\n"
    with pytest.raises(HeadingHierarchyError):
        validate_heading_hierarchy(markdown)


def test_h4_through_h6_do_not_affect_validation() -> None:
    """H4, H5, H6 are not enforced; their presence/order does not raise."""
    markdown = (
        "# Top\n\n"
        "## Section\n\n"
        "### Sub\n\n"
        "##### Skips H4\n\n"
        "###### Skips H4 and H5\n\n"
        "#### Out of order H4 after H5/H6\n"
    )
    validate_heading_hierarchy(markdown)


def test_deeply_nested_document_passes() -> None:
    """A document with many sibling H2/H3 sections under one H1 validates."""
    parts = ["# Root\n"]
    for section_index in range(3):
        parts.append(f"\n## Section {section_index}\n")
        for sub_index in range(4):
            parts.append(f"\n### Subsection {section_index}.{sub_index}\n")
            parts.append(f"Body for {section_index}.{sub_index}\n")
    validate_heading_hierarchy("".join(parts))


def test_no_headings_passes() -> None:
    """A document with no headings must validate (no hierarchy to enforce)."""
    validate_heading_hierarchy("Just a body with no headings.\n")


def test_multiple_h1_allowed() -> None:
    """Two H1 root sections with their own H2/H3 children must validate.

    The validator enforces ancestor presence, not single-H1 uniqueness.
    """
    markdown = "# First Root\n\n## Section A\n\n# Second Root\n\n## Section B\n\n### Subsection 1\n"
    validate_heading_hierarchy(markdown)


def test_heading_hierarchy_error_is_docline_error() -> None:
    """``HeadingHierarchyError`` must be a ``DoclineError`` subclass."""
    assert issubclass(HeadingHierarchyError, DoclineError)


def test_error_message_identifies_offending_heading() -> None:
    """Raised error should mention the offending heading level and text."""
    markdown = "# Top\n\n### Orphan\n"
    with pytest.raises(HeadingHierarchyError) as exc_info:
        validate_heading_hierarchy(markdown)
    message = str(exc_info.value)
    assert "Orphan" in message
    assert "h3" in message.lower() or "H3" in message
