"""Tests for auto-applied heading-disorder tolerance on include-fragment files.

Microsoft Learn (and DocFx in general) authors content in two distinct styles:

1. Top-level documents — start with a single H1, then H2/H3 sections beneath.
   The H1->H2->H3 hierarchy MUST be enforced because the chunk-boundary
   contract relies on it.

2. Include fragments — bodies designed to be embedded under a host document's
   H1. They have NO H1 anywhere in their body and typically start with H2 or
   H3 headings that act as section headers within the host. Enforcing
   H1->H2->H3 against these files mis-flags intentional authoring as broken.

This module's contract (027-S T3 finding, 028-S T1 / 026.001-T):

    A body with NO H1 anywhere is treated as a deliberate include fragment.
    Heading-hierarchy validation is auto-bypassed for that body only.
    Files WITH an H1 still get strict validation (preserves the feedback
    loop on real authoring bugs).
"""

from __future__ import annotations

import pytest

from docline.process.assemble import assemble_markdown
from docline.process.heading_validation import (
    HeadingHierarchyError,
    body_has_no_h1,
    validate_heading_hierarchy,
)

_REQUIRED_FRONTMATTER = {
    "title": "Test",
    "source": "test",
    "ingested_at": "2026-06-10T00:00:00Z",
    "doc_type": "test",
}


# ---------------------------------------------------------------------------
# body_has_no_h1 detection contract
# ---------------------------------------------------------------------------


def test_body_has_no_h1_detects_h2_only_fragment() -> None:
    body = "## Single sign-on\n\nSome content.\n"
    assert body_has_no_h1(body) is True


def test_body_has_no_h1_detects_h3_only_fragment() -> None:
    body = "### Subsection\n\nContent.\n"
    assert body_has_no_h1(body) is True


def test_body_has_no_h1_detects_no_headings_at_all() -> None:
    body = "Just paragraph content with no headings whatsoever.\n"
    assert body_has_no_h1(body) is True


def test_body_has_no_h1_returns_false_when_h1_present_at_top() -> None:
    body = "# Top H1\n\n## A section\n"
    assert body_has_no_h1(body) is False


def test_body_has_no_h1_returns_false_when_h1_present_later() -> None:
    body = "Some preamble.\n\n# Late H1\n\n## A section\n"
    assert body_has_no_h1(body) is False


def test_body_has_no_h1_ignores_h1_inside_fenced_code_block() -> None:
    """An H1 inside ``` fences is code content, not a heading."""
    body = (
        "## A section\n\n```markdown\n# This looks like an H1 but is code\n```\n\nMore content.\n"
    )
    assert body_has_no_h1(body) is True


def test_body_has_no_h1_ignores_h1_inside_tilde_fenced_block() -> None:
    body = "## A section\n\n~~~md\n# Code\n~~~\n"
    assert body_has_no_h1(body) is True


def test_body_has_no_h1_empty_body() -> None:
    assert body_has_no_h1("") is True


# ---------------------------------------------------------------------------
# validate_heading_hierarchy still strict on normal content
# ---------------------------------------------------------------------------


def test_validate_still_rejects_h3_before_h2_in_normal_doc() -> None:
    """A body WITH an H1 but H3 before H2 is a REAL authoring bug and must still raise."""
    body = "# Real Doc\n\n### Orphan H3\n\nContent.\n"
    with pytest.raises(HeadingHierarchyError):
        validate_heading_hierarchy(body)


def test_validate_still_rejects_h2_before_h1_in_doc_with_h1_later() -> None:
    """An H2 before the H1 is still wrong even if a later H1 appears."""
    body = "## H2 first\n\n# H1 later\n"
    with pytest.raises(HeadingHierarchyError):
        validate_heading_hierarchy(body)


# ---------------------------------------------------------------------------
# assemble_markdown auto-tolerates include fragments
# ---------------------------------------------------------------------------


def test_assemble_markdown_auto_tolerates_h2_only_include_fragment() -> None:
    """An include-fragment body (no H1, starts with H2) MUST assemble without raising
    even when allow_heading_disorder is False (the default)."""
    body = "## Single sign-on\n\nThe content embeds under a host H1.\n"
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)
    assert out.startswith("---\n")
    assert "## Single sign-on" in out


def test_assemble_markdown_auto_tolerates_h3_only_include_fragment() -> None:
    body = "### Manual adjustment\n\nFragment content.\n"
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)
    assert "### Manual adjustment" in out


def test_assemble_markdown_explicit_allow_still_bypasses_real_bugs() -> None:
    """allow_heading_disorder=True still bypasses everything (existing escape hatch)."""
    body = "# Real Doc\n\n### Orphan H3 — real bug\n"
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=True)
    assert "Orphan H3" in out


# ---------------------------------------------------------------------------
# T1 extension 2 — top-level reference items (H1 + H3 before first H2)
# Microsoft Learn pattern: reference doc with an H3 callout at the top of
# the body before the formal H2 sections begin. Strict validator complained
# about H3-before-H2 even though the H3 was intentional top-level material.
# ---------------------------------------------------------------------------


def test_body_has_h3_before_first_h2_detects_reference_pattern() -> None:
    from docline.process.heading_validation import body_has_h3_before_first_h2

    body = (
        "# Doc title\n\n"
        "Intro.\n\n"
        "### Top-level reference item\n\n"
        "callout body\n\n"
        "## Formal section\n\n"
        "section body\n"
    )
    assert body_has_h3_before_first_h2(body) is True


def test_body_has_h3_before_first_h2_returns_false_for_proper_nesting() -> None:
    from docline.process.heading_validation import body_has_h3_before_first_h2

    body = "# T\n\n## Section\n\n### Subsection under section\n"
    assert body_has_h3_before_first_h2(body) is False


def test_body_has_h3_before_first_h2_returns_false_when_no_h3() -> None:
    from docline.process.heading_validation import body_has_h3_before_first_h2

    body = "# T\n\n## Section A\n\n## Section B\n"
    assert body_has_h3_before_first_h2(body) is False


def test_body_has_h3_before_first_h2_returns_false_when_no_h2() -> None:
    """The no-H2-at-all case is handled by body_has_no_h2; this predicate
    specifically detects the mixed pattern where BOTH an H3 and an H2 exist."""
    from docline.process.heading_validation import body_has_h3_before_first_h2

    body = "# T\n\n### Item A\n\n### Item B\n"
    assert body_has_h3_before_first_h2(body) is False


def test_assemble_markdown_auto_tolerates_top_level_reference_h3() -> None:
    """A doc with H1 + H3 before any H2 (the Microsoft Learn reference pattern)
    MUST assemble cleanly even when allow_heading_disorder is False."""
    body = (
        "# Query caching in Power BI Premium or Power BI Embedded\n\n"
        "Caching configuration.\n\n"
        "### ClientCacheRefreshPolicy\n\n"
        "Controls cache refresh behavior.\n\n"
        "## Considerations and limitations\n\n"
        "Limits.\n\n"
        "## Related content\n\n"
        "Links.\n"
    )
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)
    assert "Query caching" in out
    assert "### ClientCacheRefreshPolicy" in out
    assert "## Considerations" in out


def test_assemble_markdown_still_rejects_h2_before_h1() -> None:
    """The remaining catch the validator preserves: H2 that appears before any H1
    is a clear authoring bug (an orphan H2 with no parent doc title)."""
    body = "## Orphan H2 with no parent\n\n# H1 comes too late\n"
    with pytest.raises(HeadingHierarchyError):
        assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)


def test_assemble_markdown_still_rejects_h3_before_h1() -> None:
    """The remaining catch the validator preserves: H3 with no H1 OR H2 anywhere
    is auto-tolerated as include fragment, but H3 + H1-later (no H2) is currently
    classified as an include fragment by body_has_no_h2 — verify that's the chosen
    behavior."""
    # Include-fragment style: no H1 anywhere → auto-tolerated.
    body_include = "### Orphan H3 — include fragment style\n"
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body_include, allow_heading_disorder=False)
    assert "Orphan H3" in out


def test_assemble_markdown_clean_doc_unchanged() -> None:
    """A clean H1 -> H2 -> H3 body still assembles cleanly (no regression)."""
    body = "# Title\n\n## Section\n\n### Subsection\n\nContent.\n"
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)
    assert "# Title" in out
    assert "## Section" in out
    assert "### Subsection" in out


# ---------------------------------------------------------------------------
# Regression: real Power BI include fragments
# ---------------------------------------------------------------------------


def test_regression_power_bi_direct_query_sso_fragment_assembles() -> None:
    """Mirrors includes/direct-query-sso.md (H2 'Single sign-on' before any H1)."""
    body = (
        "## Single sign-on\n\n"
        "When using DirectQuery, all queries to the underlying data source\n"
        "originate from the user, so single sign-on (SSO) settings apply.\n"
    )
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)
    assert "Single sign-on" in out


def test_regression_power_bi_rls_define_roles_fragment_assembles() -> None:
    """Mirrors includes/rls-desktop-define-roles.md (H2 'Define roles' before any H1)."""
    body = (
        "## Define roles and rules in Power BI Desktop\n\n"
        "You can define security roles within Power BI Desktop.\n\n"
        "### Define roles\n\n1. Open the report.\n"
    )
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)
    assert "Define roles and rules" in out
    assert "Define roles" in out


def test_regression_power_bi_tablix_columns_resize_fragment_assembles() -> None:
    """Mirrors includes/core-visuals/tablix-columns-resize.md (H3 'Manual adjustment' before H1)."""
    body = "### Manual adjustment\n\nAdjust column widths by dragging the column divider.\n"
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)
    assert "Manual adjustment" in out


# ---------------------------------------------------------------------------
# T1 extension — sparse-hierarchy tolerance (H1 + H3 with no intermediate H2)
# Common Microsoft Learn pattern in changelogs, reference pages, tutorial
# step lists. The strict H1->H2->H3 rule is moot when no H2 appears in the
# body; auto-tolerate that case alongside include fragments.
# ---------------------------------------------------------------------------


def test_body_has_no_h2_detects_h1_h3_pattern() -> None:
    from docline.process.heading_validation import body_has_no_h2

    body = "# Title\n\n### Item 1\n\nbody\n\n### Item 2\n\nbody\n"
    assert body_has_no_h2(body) is True


def test_body_has_no_h2_returns_false_when_h2_present() -> None:
    from docline.process.heading_validation import body_has_no_h2

    body = "# Title\n\n## Section\n\n### Subsection\n"
    assert body_has_no_h2(body) is False


def test_body_has_no_h2_ignores_h2_inside_fenced_block() -> None:
    from docline.process.heading_validation import body_has_no_h2

    body = "# Title\n\n```markdown\n## Code H2\n```\n\n### Real subsection\n"
    assert body_has_no_h2(body) is True


def test_body_should_skip_validation_when_no_h1() -> None:
    """Include-fragment case: no H1 anywhere."""
    from docline.process.heading_validation import body_should_skip_heading_validation

    body = "## Single sign-on\n\nfragment content\n"
    assert body_should_skip_heading_validation(body) is True


def test_body_should_skip_validation_when_no_h2() -> None:
    """Sparse-hierarchy case: H1 + H3 only."""
    from docline.process.heading_validation import body_should_skip_heading_validation

    body = "# Doc Title\n\n### Item 1\n\nbody\n\n### Item 2\n\nbody\n"
    assert body_should_skip_heading_validation(body) is True


def test_body_should_skip_validation_false_for_complete_hierarchy() -> None:
    """A complete H1+H2+H3 doc must still be subject to strict validation."""
    from docline.process.heading_validation import body_should_skip_heading_validation

    body = "# Title\n\n## Section\n\n### Subsection\n"
    assert body_should_skip_heading_validation(body) is False


def test_assemble_markdown_auto_tolerates_sparse_h1_h3_doc() -> None:
    """A doc with H1 + H3 but no H2 (e.g. monthly changelog) MUST assemble cleanly."""
    body = (
        "# Power BI release notes\n\n"
        "Updates by month.\n\n"
        "### January 2025\n\n* feature A\n* feature B\n\n"
        "### February 2025\n\n* feature C\n"
    )
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)
    assert "Power BI release notes" in out
    assert "### January 2025" in out
    assert "### February 2025" in out


def test_assemble_markdown_top_level_reference_h3_now_tolerated() -> None:
    """T1 extension 2: A body with H1 + H3 BEFORE the first H2 is now
    auto-tolerated as a Microsoft Learn 'top-level reference item' pattern.
    Documented here so the design choice is explicit and intentional —
    this was previously rejected as a 'real authoring bug' but turned out
    to be intentional Microsoft Learn authoring."""
    body = (
        "# Title\n\n"
        "### Top-level reference — appears before the first H2\n\n"
        "## Section that comes after\n"
    )
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)
    assert "Top-level reference" in out
    assert "## Section that comes after" in out


def test_regression_changelog_pattern_assembles() -> None:
    """Mirrors fundamentals/desktop-latest-update-archive.md from Power BI corpus."""
    body = (
        "# Power BI Desktop update archive\n\n"
        "Monthly update history for Power BI Desktop.\n\n"
        "### General\n\n* fixed crash on launch\n\n"
        "### December 2024\n\n* feature foo\n"
    )
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)
    assert "Power BI Desktop update archive" in out
    assert "### General" in out


def test_regression_h1_h3_reference_pattern_assembles() -> None:
    """Mirrors connect-data/power-bi-query-caching.md from Power BI corpus."""
    body = (
        "# Query caching in Power BI\n\n"
        "Configure caching behavior.\n\n"
        "### ClientCacheRefreshPolicy\n\n"
        "Controls cache refresh.\n"
    )
    out = assemble_markdown(_REQUIRED_FRONTMATTER, body, allow_heading_disorder=False)
    assert "Query caching" in out
    assert "### ClientCacheRefreshPolicy" in out
