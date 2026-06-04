---
title: "Heading-aware semantic segmentation for output parts (G3a)"
stash_ids: ["90695245"]
shipment: "012-S"
status: approved
requires_plan_hardening: no
---

# Heading-aware semantic segmentation for output parts (G3a)

**Date**: 2026-06-03
**Source stash**: `90695245` (high, feature) — `[G3a]`
**Target shipment**: `012-S`
**Author**: Stage agent

## Problem

`src/docline/process/output_contract.py` currently splits processed output by
physical-layout boundaries that ignore document structure:

- **PDF**: `read_pdf_pages()` yields one segment per physical PDF page. PDF
  pages routinely cut mid-section, mid-paragraph, and even mid-sentence.
- **DOCX**: `_chunk_text_blocks(blocks, 6000)` performs greedy character
  binning over paragraph blocks. The 6000-char cap is arbitrary and ignores
  H1/H2 chapter and section starts.
- **HTML / web crawl**: already one-page-per-file. No change required.

Downstream graphtor-docs / AST and Tree-sitter graphing rely on H1/H2
boundaries to derive parent-child chunk relationships. Splitting mid-section
destroys that continuity even before chunk anchors are inspected.

## Goal

Replace the page-based and char-bin segmentation paths with a single
heading-aware segmenter that:

1. Parses rendered markdown via `markdown-it-py` (already in `pyproject.toml`
   as `markdown-it-py>=4,<5`, used by `ast_lint.py` and
   `heading_validation.py`).
2. **Splits hard at every H1 boundary.** Every H1 begins a new output part.
3. **Sub-splits at H2** when a single H1-bounded part exceeds `max_chars`
   (default 12_000). Sub-splitting uses the same H2 token-position scan; the
   first sub-part keeps the H1 heading.
4. **Falls through to char-bin behavior** as the final safety net when:
   - no H1 headings exist in the markdown (the case for the current `pypdf`
     extractor against real seed PDFs — confirmed to yield 0 headings), or
   - a single H1+H2-bounded sub-part is still over `max_chars` (very long
     prose with no further sub-headings).

The schema contract is preserved: filenames remain `part-NNNN.md`, the
`OutputDocumentPart` dataclass is unchanged, no frontmatter field is added
or removed (G3b's frontmatter referentiality lands separately).

## Scope (G3a only)

- New module: `src/docline/process/segment.py`
- Modify: `src/docline/process/output_contract.py` (PDF and DOCX paths)
- New tests: `tests/process/test_segment.py`
- Existing tests that exercise `build_output_document_parts` may need
  fixture adjustment in `tests/elt/test_process_regression.py` if observed
  part counts change.

**Out of scope (deferred to G3b stash `C5CA1740` and G3c stash `351170C9`)**:

- Frontmatter referentiality fields (`prev_part`, `next_part`,
  `parent_doc`).
- Flipping `emit_chunk_anchors=True`.
- Adding `docling` engine or `[pdf]` optional extra.
- Image sidecar extraction.
- Graphtor-docs schema snapshot refresh.

## Constitution check

| Principle | Compliance |
|---|---|
| I. Safety-first Python | Python 3.12 only; typed signatures; no `Any` |
| II. TDD (NON-NEGOTIABLE) | Tests written and verified red before implementation |
| III. Workspace isolation | No filesystem changes outside repo |
| V. Structured observability | Existing `_log` patterns reused if logging is added |
| VI. Single responsibility | Zero new dependencies; reuses existing `markdown-it-py` |
| X. Context efficiency | One new module, one modified module, one new test file |
| XI. Merge commit history | Standard PR flow via Ship |

No new dependencies. No schema break. No CLI surface change. No MCP tool
change. No new optional extras.

## Design

### `src/docline/process/segment.py`

```python
"""Heading-aware semantic segmentation for processed markdown output.

Splits rendered markdown at H1 boundaries, sub-splits at H2 when a single
H1-bounded part exceeds ``max_chars``, and falls back to deterministic
char-binning when no headings are present or sub-splitting cannot reach
the target size. The contract is the same for PDF (post-extraction) and
DOCX (post `read_docx_blocks` join). Web/HTML inputs are unaffected
because the existing output_contract path keeps them single-file.
"""

from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.token import Token

_DEFAULT_MAX_CHARS = 12_000


def segment_markdown(markdown: str, *, max_chars: int = _DEFAULT_MAX_CHARS) -> list[str]:
    """Return ordered semantic segments of *markdown*.

    The result is non-empty for any non-empty input. Empty input returns
    ``[""]`` to preserve the single-part contract used by callers.
    """
    ...


def _split_at_level(markdown: str, level: int) -> list[str]:
    """Return ordered segments split at every ATX heading of the given level.

    A segment starts at a heading_open token of *level* and runs until the
    next heading_open token of the same level (or end-of-document).
    """
    ...


def _char_bin(text: str, max_chars: int) -> list[str]:
    """Final-safety-net char binner reused from output_contract semantics.

    Splits on paragraph boundaries (\\n\\n) greedily, never exceeding
    *max_chars* per bin where possible. A single paragraph longer than
    *max_chars* is emitted as its own bin (no mid-paragraph cut).
    """
    ...
```

**Algorithm:**

1. Parse `markdown` with `MarkdownIt().parse()`.
2. Locate every `heading_open` token; record `(level, token_index)` pairs.
3. **No H1 present** → call `_char_bin(markdown, max_chars)` and return.
4. **H1 present** → use `_split_at_level(markdown, 1)` to produce H1 parts.
5. For each H1 part:
   - If `len(part) <= max_chars`: emit as-is.
   - Else: call `_split_at_level(part, 2)` → H2 sub-parts.
     - If sub-split produced exactly one sub-part (no H2 in this H1 part)
       OR any sub-part still exceeds `max_chars`: fall back to
       `_char_bin(part, max_chars)`.
     - Else: emit the H2 sub-parts in order.
6. Strip leading/trailing whitespace per emitted segment; drop empty
   segments; if the final list is empty, return `[""]`.

**Token-to-character mapping:** `markdown-it-py` tokens expose `map: [start_line, end_line]` for block-level tokens. We split by slicing the original markdown on line boundaries using token `map` values, which preserves source whitespace and code-fence integrity.

### `src/docline/process/output_contract.py` integration

Replace the PDF branch:

```python
if suffix == ".pdf":
    rendered = read_pdf(file_path)
    segment_bodies = segment_markdown(rendered)
```

Replace the DOCX branch:

```python
elif suffix == ".docx":
    blocks = read_docx_blocks(file_path)
    joined = "\n\n".join(block.strip() for block in blocks if block.strip())
    segment_bodies = segment_markdown(joined) if joined else [""]
```

Remove `_chunk_text_blocks` and `_DOCX_SEGMENT_CHAR_LIMIT` once no other
callers exist (`grep` confirms none).

Keep `_relative_output_path` and `build_output_document_parts` signature
unchanged. HTML, MD, TXT branches are untouched. Empty-segment safety:
if `segment_markdown` returns `[""]`, `build_output_document_parts` still
returns a single `OutputDocumentPart` with empty body (same as today).

## Test plan (TDD red phase first)

`tests/process/test_segment.py` covers:

| Test | Input | Expected |
|---|---|---|
| `test_no_heading_fallback_single_segment` | Plain prose under 12k, no headings | 1 segment equal to input |
| `test_no_heading_fallback_char_binned` | Plain prose 30k chars, no headings | Multiple segments, each `<= 12_000`, no mid-paragraph cuts |
| `test_h1_split_two_chapters` | Two H1 sections, each under 12k | 2 segments, each starts with `# ` |
| `test_h1_split_three_chapters_one_oversize` | Three H1 sections; middle one is 20k | 5+ segments, middle H1 expanded into H2 sub-parts |
| `test_h2_subsplit_under_max_chars` | One H1 with H2 sub-parts; total 18k | Segments split at H2 boundaries; first segment retains H1 |
| `test_h2_subsplit_when_h1_oversize_no_h2` | One H1, no H2, 25k chars | Falls back to char-bin; each segment under 12k |
| `test_h2_subsplit_when_h2_subpart_still_oversize` | One H1, two H2, one H2 still 20k | Char-bin fallback for that H1 part |
| `test_empty_input_returns_single_empty` | `""` | `[""]` |
| `test_whitespace_only_input_returns_single_empty` | `"\n\n   \n"` | `[""]` |
| `test_deterministic_idempotent` | Run twice with same input | Identical output (no random ordering) |
| `test_preserves_code_fences` | Markdown with fenced code blocks under H1 | Fences not split mid-block |
| `test_preserves_tables` | GFM table under an H1 | Tables not split mid-row |
| `test_max_chars_parameter_honored` | Custom `max_chars=5_000` | Segments respect override |

All tests MUST fail before `segment.py` is implemented (RED phase confirmed
in 012.001-T). Implementation in 012.002-T turns them green.

## Risk and rollback

| Risk | Mitigation |
|---|---|
| Existing `pypdf` extractor produces 0 headings on real PDFs (smoke-tested) | Char-bin fallback engages; output is at worst equal to current single-segment behavior |
| Existing `test_process_regression.py` may observe different DOCX part counts | Update fixture expectations in 012.003-T; verify all 5 quality gates green before merge |
| Code-fence or table mid-split corrupts markdown | Token `map` slicing operates on block boundaries; explicit test coverage in `test_preserves_code_fences` and `test_preserves_tables` |
| Schema break via unexpected filename change | `_relative_output_path` signature and behavior unchanged; tests assert no rename |
| Performance regression on large DOCX | `markdown-it-py` parse cost is O(n) and runs once per file; no measurable impact vs current per-page PDF iteration |

**Rollback**: revert the shipment merge commit. No data migration needed
(output is regenerated each `docline process` run).

## ProposedAction / ActionRisk (strict-safety)

| Action | Risk | Approval |
|---|---|---|
| Add `src/docline/process/segment.py` | `low` | None — net-new module |
| Modify `src/docline/process/output_contract.py` PDF and DOCX branches | `moderate` | None — covered by test gate; behavior change is intentional and reversible |
| Update `tests/elt/test_process_regression.py` fixture expectations (if needed) | `low` | None |

No destructive actions. No high-blast-radius surfaces. `plan-harden` not
invoked.

## Sequencing (TDD-ordered)

1. **012.001-T** — Write failing tests for `segment_markdown` (RED).
2. **012.002-T** — Implement `src/docline/process/segment.py` (GREEN).
3. **012.003-T** — Wire `segment_markdown` into
   `build_output_document_parts`; update regression fixtures; run all five
   quality gates.
4. **012.004-T** — Closure document at
   `docs/closure/012-S-heading-aware-segmentation.md`.

## Acceptance criteria

- `src/docline/process/segment.py` exists and exposes `segment_markdown`.
- `tests/process/test_segment.py` covers all scenarios in the test plan
  above and is green.
- `src/docline/process/output_contract.py` no longer calls `read_pdf_pages`
  or `_chunk_text_blocks`; the PDF and DOCX branches route through
  `segment_markdown`.
- All five CI gates pass on the PR: `ruff format --check`, `ruff check .`,
  `pyright src/`, `pytest`, `python -m build`.
- The closure document records the part-count delta observed against the
  existing seed PDFs and DOCX fixtures.
- No change to JSON Schema export (`docline export-schema` output
  unchanged).

## Files touched (summary)

| Path | Change |
|---|---|
| `src/docline/process/segment.py` | NEW |
| `src/docline/process/output_contract.py` | MODIFY (PDF and DOCX branches; remove `_chunk_text_blocks` and `_DOCX_SEGMENT_CHAR_LIMIT`) |
| `tests/process/test_segment.py` | NEW |
| `tests/elt/test_process_regression.py` | MODIFY only if observed counts change |
| `docs/closure/012-S-heading-aware-segmentation.md` | NEW |
