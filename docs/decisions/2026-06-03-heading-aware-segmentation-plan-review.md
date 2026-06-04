# Plan review — heading-aware semantic segmentation (012-S / G3a)

**Date**: 2026-06-03
**Plan**: `docs/plans/2026-06-03-heading-aware-segmentation-plan.md`
**Reviewer**: Stage agent (plan-review skill)
**Verdict**: **APPROVED**

## Personas consulted

| Persona | Verdict | Notes |
|---|---|---|
| Architect | APPROVED | New module follows existing `process/` package conventions. Reuses `markdown-it-py` already wired by `ast_lint.py` and `heading_validation.py`. No layering inversion. |
| Coding-standards | APPROVED | Plan declares typed signatures, `from __future__ import annotations`, Google-style docstrings, no `Any`. Matches existing `process/` modules. |
| Test-discipline | APPROVED | TDD red phase declared as the first task (012.001-T). 13 test scenarios cover every algorithmic branch including code-fence/table preservation and idempotency. |
| Scope-boundary | APPROVED | G3b (frontmatter referentiality) and G3c (docling + sidecars) are explicitly out of scope. Stash text is honored; no scope creep. |
| Risk-assessment | APPROVED | Blast radius is moderate: one new module, one modified module, no dependency change, no schema break. Rollback is a single revert. |
| Security | APPROVED | No new I/O surface. `markdown-it-py` is already a vetted, version-pinned dependency. No new untrusted input parsing. |

## Findings

### Confirmed (no change required)

1. **Char-bin fallback semantics differ subtly from existing `_chunk_text_blocks`.**
   The existing function operates on a `list[str]` of paragraph blocks; the
   plan's `_char_bin(text, max_chars)` operates on a joined markdown string
   and splits on `\n\n`. The output should be equivalent for the DOCX path
   because `read_docx_blocks` already emits paragraph-delimited blocks
   joined with blank lines. Implementation MUST verify this equivalence in
   012.003-T; if a regression test in `tests/elt/test_process_regression.py`
   observes a different part count, the plan permits updating the fixture
   expectation.

2. **PDF path will produce a single segment in practice today** because the
   current `pypdf` extractor yields 0 markdown headings on real seed PDFs.
   That is the intended graceful-degradation behavior. Once G3c lands the
   docling engine (~112 headings on the same seed), this path engages
   naturally without further code change.

### P2 — accepted as planned

1. **Test counts assume implementation parses tables and code fences
   correctly.** `markdown-it-py` default config recognizes fenced code and
   GFM-style separators (when `enable("table")` is called). The plan's
   `MarkdownIt()` invocation uses defaults, which DOES handle fenced code
   but does NOT enable `table` by default. The implementation in 012.002-T
   should call `MarkdownIt().enable("table")` to keep table tokens at the
   block level so token `map` slicing does not cut mid-table.

   **Resolution**: Documented as an implementation note for 012.002-T; not
   a plan-level defect.

### P3 — informational

1. **Closure document should record observed part-count deltas** against
   the existing seed PDFs and DOCX fixtures (e.g., a 20-page PDF that
   previously produced 20 parts should now produce 1 — the char-bin
   fallback joins the whole text). This is already listed in the
   plan's acceptance criteria; included here for clarity.

## Constitution alignment

| Principle | Status |
|---|---|
| I — Safety-First Python | OK |
| II — Test-First (NON-NEGOTIABLE) | OK — RED phase is task 1 |
| III — Workspace isolation | OK — repo-local edits only |
| V — Structured observability | N/A — no new logging proposed |
| VI — Single responsibility | OK — no new deps |
| X — Context efficiency | OK — small surface |
| XI — Merge commit history | OK — Ship will merge via merge commit |

## Decision

**APPROVED for harvest.** Proceed to 012-F decomposition and shipment
012-S assembly. Implementation note from P2-1 should be carried forward
into 012.002-T's acceptance criteria.
