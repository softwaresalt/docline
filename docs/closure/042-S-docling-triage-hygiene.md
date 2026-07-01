---
shipment: 042-S
title: "Closure record — docling triage internals hygiene (039-F)"
status: verified
merge_sha: 0a713e4
merged_pr: 110
---

Captures the implementation evidence for shipment `042-S` (feature `039-F`),
two low-risk docling-triage hygiene fixes with **no change to assembled markdown,
AST, heading hierarchy, or node referentiality** — internal maintainability and
observability only. Consumes stash `C04896E1` and `C0F3B979`; archives the
superseded stash `D771B78E`.

## Scope

* **OCR-gate dedup** (`039.002-T`, stash `C04896E1`, 036-S review F4):
  [`src/docline/process/fidelity_scorer.py`](../../src/docline/process/fidelity_scorer.py)
  gains `any_page_needs_ocr(pairs)`, a shared primitive that reduces an iterable
  of `(text, page_metadata)` pairs to "does any page need OCR?".
  `pdf_triage._range_needs_ocr` and `pdf_batch._chunk_needs_ocr` now build lazy
  generators and delegate. Short-circuit and conservative "unreadable → OCR on"
  defaults preserved. No behavior change.
* **Collapsed-range attribution** (`039.001-T`, stash `C0F3B979`):
  [`src/docline/process/pdf_triage.py`](../../src/docline/process/pdf_triage.py)
  splice-back now treats a single-entry envelope (or a legacy flat blob) for an
  N-page range as the **expected** coherent whole-range docling render: it is
  attributed `"docling-range"` with **no** warning. The "envelope length
  mismatch" WARNING and the `"docling-collapsed"` label are retained only for a
  genuinely unexpected multi-entry, wrong-count envelope (where envelope pages
  would be silently dropped).
  [`scripts/pa3_triage_cosmos.py`](../../scripts/pa3_triage_cosmos.py)
  `_docling_attribution` docstring updated (it already reports ranges, and its
  `engine.startswith("docling")` counting covers the new label).

## Root-cause / rationale

Per the 2026-06-28 merge-gap verdict, the assembled markdown joins page slots
(`output_contract.py:264`) and runs whole-body heading/AST validation
(`assemble.py:141-144`), so a docling range collapsed onto one slot ingests
identically to a per-page layout. A per-page `export_to_markdown` split would
*fragment* headings/tables across page breaks and worsen AST/heading/lint —
therefore it is explicitly **not** done. The single-entry whole-range envelope
is correct; only the misleading log line and pejorative label needed fixing.
This is why the medium stash `D771B78E` (which proposed the per-page split) was
archived as superseded during staging.

## Files changed

| Path | Change |
|---|---|
| `src/docline/process/fidelity_scorer.py` | ADD `any_page_needs_ocr`; `Iterable` import |
| `src/docline/process/pdf_triage.py` | `_range_needs_ocr` delegates; splice-back relabel + conditional warning; `Iterator` import; `any_page_needs_ocr` import |
| `src/docline/process/pdf_batch.py` | `_chunk_needs_ocr` delegates; import swap to `any_page_needs_ocr`; `Iterator` import |
| `scripts/pa3_triage_cosmos.py` | `_docling_attribution` docstring updated |
| `tests/process/test_conditional_ocr.py` | +4 `any_page_needs_ocr` unit tests |
| `tests/process/test_pdf_triage.py` | 2 splice-back tests updated to `docling-range`+no-warning; +1 unexpected-multientry regression |
| `docs/closure/042-S-docling-triage-hygiene.md` | NEW |

## Quality gate evidence

All gates green at HEAD `c32b388` (pre-merge):

| Gate | Command | Result |
|---|---|---|
| Lint | `ruff check .` | `All checks passed!` |
| Typecheck | `pyright src/` | `0 errors, 0 warnings, 0 informations` |
| Tests | `pytest` | `1341 passed, 6 skipped` |
| Format | `ruff format --check .` | `228 files already formatted` |

CI workflow `ci.yml` is intentionally paused (release-tag / manual triggers
only); local gates are the validation model. Merge used `--admin` to satisfy the
`REVIEW_REQUIRED` branch policy after explicit operator approval.

## Review findings

Copilot review returned **0 findings / 0 threads**, fresh on HEAD `c32b388`
(pre-merge readiness Checks 1–3 all passed).

## Runtime verification

Not required beyond the test suite: both changes are internal (a refactor with
no behavior change, and a logging/attribution relabel). The splice-back
behavior is exercised end-to-end by the updated `test_pdf_triage.py` cases
(single-entry → `docling-range`+no-warning; legacy flat → `docling-range`;
unexpected multi-entry → warning + `docling-collapsed`).

## Rollback

`git revert 0a713e4` cleanly restores the prior behavior (duplicated OCR-gate
loops; `docling-collapsed` label + "length mismatch" warning for whole-range
renders). No schema, CLI, or MCP surface changed.
