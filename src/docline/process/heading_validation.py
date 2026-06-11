"""Heading hierarchy validator for graphtor-docs chunk boundary alignment.

The graphtor-docs ingestion contract chunks documents on H1/H2/H3 boundaries.
Documents that skip ancestor levels (an H2 before any H1, an H3 before any
H2) produce incoherent chunk parentage. This validator enforces that the
three structurally significant heading levels nest top-down.

H4-H6 are present in source documents but not enforced — they sit below the
chunk-boundary horizon and their ordering does not affect parentage.

Auto-tolerance for known-good sparse-hierarchy patterns (028-S T1 / 026.001-T)
-----------------------------------------------------------------------------
Microsoft Learn (and DocFx generally) authors content in two patterns that
trip the strict H1→H2→H3 validator without representing real authoring
bugs:

1. **Include fragments** — bodies designed to be embedded under a host
   document's H1. They have NO H1 anywhere and start with H2 or H3
   headings that act as section headers within the host.
2. **Sparse hierarchies** — top-level documents that use H1 + H3 only,
   skipping H2 entirely. This is common in changelogs (H1 doc title +
   H3 per release), reference pages (H1 title + H3 per item), and
   tutorial steps (H1 + H3 sub-steps).

Both patterns share the property that NO H2 appears in the body, which
means the strict "H3 must follow H2" rule is moot. The auto-tolerance
predicate is:

    skip validation when no H1 OR no H2 anywhere in the body

Documents WITH an H2 still get strict validation, preserving the
quality-signal feedback loop on real H3-before-H2 authoring bugs.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

from docline.schema.models import DoclineError

_ENFORCED_LEVELS = (1, 2, 3)

# Module-level compiled regex per codebase convention. Matches an ATX H1
# heading (``# `` at line start, exactly one ``#``, then space + content).
_H1_LINE_RE = re.compile(r"^# [^\n]+$", re.MULTILINE)

# Matches an ATX H2 heading (exactly two ``#`` + space + content).
_H2_LINE_RE = re.compile(r"^## [^\n]+$", re.MULTILINE)

# Matches an ATX H3 heading (exactly three ``#`` + space + content).
_H3_LINE_RE = re.compile(r"^### [^\n]+$", re.MULTILINE)

# Matches a fenced code block opener (``` or ~~~ with optional info string).
_FENCE_RE = re.compile(r"^(```+|~~~+)[^\n]*$", re.MULTILINE)


class HeadingHierarchyError(DoclineError):
    """Raised when an H2 or H3 heading appears without its required ancestor."""


def _fence_spans(markdown: str) -> list[tuple[int, int]]:
    """Build a list of fenced-code-block spans (start, end) within ``markdown``.

    Matches opener/closer fence pairs by first fence character (``` or ~~~)
    so different fence types nest without confusing each other. An unclosed
    fence treats everything from its opener to end-of-document as code.
    """
    spans: list[tuple[int, int]] = []
    opener: re.Match[str] | None = None
    opener_fence: str | None = None
    for match in _FENCE_RE.finditer(markdown):
        if opener is None:
            opener = match
            opener_fence = match.group(1)[0]
            continue
        if match.group(1)[0] == opener_fence:
            spans.append((opener.start(), match.end()))
            opener = None
            opener_fence = None
    if opener is not None:
        spans.append((opener.start(), len(markdown)))
    return spans


def _has_atx_heading_outside_code(
    markdown: str, pattern: re.Pattern[str], fence_spans: list[tuple[int, int]]
) -> bool:
    """Return True when ``pattern`` matches at a position outside every fenced span."""
    for match in pattern.finditer(markdown):
        pos = match.start()
        if not any(start <= pos < end for start, end in fence_spans):
            return True
    return False


def body_has_no_h1(markdown: str) -> bool:
    """Return ``True`` when ``markdown`` contains no ATX H1 heading.

    Used to detect Microsoft Learn include fragments. ATX H1s inside fenced
    code blocks (``` or ~~~) are treated as code, not headings.
    """
    if not markdown:
        return True
    fence_spans = _fence_spans(markdown)
    return not _has_atx_heading_outside_code(markdown, _H1_LINE_RE, fence_spans)


def body_has_no_h2(markdown: str) -> bool:
    """Return ``True`` when ``markdown`` contains no ATX H2 heading.

    Used to detect sparse-hierarchy documents (H1 + H3 with no intermediate
    H2). ATX H2s inside fenced code blocks are treated as code.
    """
    if not markdown:
        return True
    fence_spans = _fence_spans(markdown)
    return not _has_atx_heading_outside_code(markdown, _H2_LINE_RE, fence_spans)


def body_has_h3_before_first_h2(markdown: str) -> bool:
    """Return ``True`` when an ATX H3 appears before any ATX H2 in the body.

    This is the Microsoft Learn "top-level reference item" authoring
    pattern: a doc starts with an H1 title, then has H3 reference items
    BEFORE the first formal H2 section. The strict H1→H2→H3 rule rejects
    this even though it's intentional authoring (the H3 acts as a
    sibling of H2 at the top level, with formal H2 sections following).

    Headings inside fenced code blocks (``` or ~~~) are ignored.
    """
    if not markdown:
        return False
    fence_spans = _fence_spans(markdown)
    h2_positions = [
        m.start()
        for m in _H2_LINE_RE.finditer(markdown)
        if not any(start <= m.start() < end for start, end in fence_spans)
    ]
    h3_positions = [
        m.start()
        for m in _H3_LINE_RE.finditer(markdown)
        if not any(start <= m.start() < end for start, end in fence_spans)
    ]
    if not h3_positions:
        return False
    if not h2_positions:
        # No H2 anywhere — that's a different case (sparse hierarchy);
        # body_has_no_h2 already handles it.
        return False
    return h3_positions[0] < h2_positions[0]


def body_should_skip_heading_validation(markdown: str) -> bool:
    """Return ``True`` when ``markdown`` uses a known-good sparse-hierarchy pattern.

    Auto-tolerance covers three intentional Microsoft Learn authoring
    patterns where the strict H1→H2→H3 rule false-positives:

    * **include fragments** (no H1 anywhere; designed to be embedded under
      a host doc's H1)
    * **sparse hierarchies** (no H2 anywhere; H1 + H3 directly, common in
      changelogs, reference pages, tutorial steps)
    * **top-level reference items** (H1 + one or more H3s BEFORE the first
      H2; common in Microsoft Learn product reference docs where a
      top-level reference item appears before formal sections)

    Documents that exhibit none of these patterns still get strict
    validation. The validator's primary remaining catch is the
    H2-before-any-H1 case (a clearer authoring bug than ordering H3
    relative to H2).
    """
    return (
        body_has_no_h1(markdown)
        or body_has_no_h2(markdown)
        or body_has_h3_before_first_h2(markdown)
    )


def validate_heading_hierarchy(markdown: str) -> None:
    """Validate top-down nesting of H1 -> H2 -> H3 headings.

    The state machine tracks whether an H1 and an H2 have been seen
    anywhere in the document, then checks H3 occurrences against those
    flags. Subsequent H1s (which appear in Microsoft Learn tab-variant
    docs with multiple top-level alternatives, in long reference docs
    with section-marker H1s, or in docs that were assembled from
    multiple sources) do NOT reset ``seen_h2`` because the existence of
    a prior H2 establishes the doc's hierarchy convention; later H3s
    can validly follow under the established parentage even after a
    new H1 appears.

    Args:
        markdown: Raw Markdown source.

    Raises:
        HeadingHierarchyError: If an enforced heading level appears
            before its required ancestor (an H2 before any H1, an H3
            before any H1, or an H3 before any H2 in the entire doc).
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
            # Intentionally do NOT reset seen_h2 here — see docstring.
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
