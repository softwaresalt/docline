"""DocFx tabbed content normalizer (028-S T2 / 026.002-T).

Microsoft Learn renders tab groups using ``#[#...] [Label](#tab/key)``
heading patterns. The corpus uses tabs at H1, H2, H3, AND H4 levels
(228 + 18 + 86 + 34 occurrences respectively in the Power BI corpus,
totalling 366 tab headings). Multiple consecutive tab headings form a
tab block, terminated by a ``---`` horizontal rule on its own line::

    ### [Drill enabled](#tab/drill-enabled)
    content for tab 1
    ### [Drill disabled](#tab/drill-disabled)
    content for tab 2
    ---
    content after tabs

The strict heading-hierarchy validator (and any downstream chunker
expecting clean heading text) trips on:

* the link-wrapped heading text — ``[Label](#tab/key)`` is treated as
  the heading content rather than ``Label``
* the trailing ``---`` — which, when preceded by a blank line, can be
  misread as a setext H2 underline for whatever non-blank line
  precedes it

This module flattens the pattern at every heading level: each
``[Label](#tab/key)`` wrapper is stripped to leave just ``Label``;
the level is preserved (H1 tab stays H1, etc.); the terminating
``---`` of each tab block is consumed. graphtor-docs chunkers and
embedding pipelines see a normal heading sequence.

Public API:
    :func:`normalize_docfx_tabs` — body string → body string with tabs flattened
"""

from __future__ import annotations

import re

# Module-level compiled regex per codebase convention.
# Matches a DocFx tab heading at any level H1-H4:
# ``# [Label](#tab/key)`` through ``#### [Label](#tab/key)``. The hash
# count is captured so we can preserve the heading level. The ``tab``
# keyword is matched case-insensitively to tolerate authoring variation.
_TAB_HEADING_RE = re.compile(
    r"^(#{1,4})\s+\[([^\]]+)\]\(#[Tt][Aa][Bb]/[^)]+\)\s*$",
)

# Matches a non-tab heading (H1-H4 where the heading text is NOT a tab
# link) — used as a tab-block boundary marker when no explicit ``---``
# terminator is present.
_NON_TAB_HEADING_RE = re.compile(
    r"^#{1,4}\s(?!\[[^\]]+\]\(#[Tt][Aa][Bb]/)",
)


def normalize_docfx_tabs(text: str) -> str:
    """Flatten DocFx tab blocks into plain heading sections.

    Args:
        text: Markdown body (post frontmatter-strip).

    Returns:
        Body with ``[Label](#tab/key)`` heading wrappers stripped at
        every H1-H4 level (level preserved) and the terminating ``---``
        of each tab block consumed. Documents containing no tab syntax
        are returned unchanged.
    """
    if not text or "#tab/" not in text.lower():
        return text

    lines = text.splitlines(keepends=False)
    out: list[str] = []
    in_tab_block = False

    for line in lines:
        tab_match = _TAB_HEADING_RE.match(line)
        stripped = line.strip()

        if tab_match:
            # Tab heading at any H1-H4 level — strip the #tab/ link wrapper,
            # keep label only, preserve heading level.
            level_hashes = tab_match.group(1)
            label = tab_match.group(2).strip()
            out.append(f"{level_hashes} {label}")
            in_tab_block = True
            continue

        if in_tab_block and stripped == "---":
            # Tab-block terminator — drop the line entirely.
            in_tab_block = False
            continue

        # Tab block ends when a non-tab heading appears (any H1-H4 level
        # that is NOT a tab pattern).
        if in_tab_block and _NON_TAB_HEADING_RE.match(line):
            in_tab_block = False

        out.append(line)

    # Preserve trailing newline if the input had one.
    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + trailing


__all__ = ["normalize_docfx_tabs"]
