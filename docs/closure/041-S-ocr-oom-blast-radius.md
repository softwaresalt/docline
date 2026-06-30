---
shipment: 041-S
title: "Closure record — batched docling OCR OOM isolation + adaptive downsizing (038-F)"
status: verified
merge_sha: 41bcb47
merged_pr: 109
---

Captures the implementation evidence for shipment `041-S` (feature `038-F`),
which hardens the batched docling worker against the OCR out-of-memory crash
observed during the 036.002-T cosmos sweep (mg1, 2026-06-27): a batched group
hard-crashed (`exit=3221225477` = `0xC0000005` access violation) while RapidOCR
ran (`std::bad_alloc` on the onnxruntime Clip node, numpy `_ArrayMemoryError`),
and the **whole group** fell back to heuristic. Source stash `D44A61E4`.

## Scope

* **OCR-aware grouping** (`038.001-T`): [`src/docline/process/page_range.py`](../../src/docline/process/page_range.py) — new `group_by_page_count_ocr_aware` plus `OCR_MAX_BATCHED_PAGES=8`. OCR-flagged items never share a batched group with OCR-free items, and OCR groups bin under the tighter cap. With all-OCR-free input the grouping is identical to `group_by_page_count`.
* **Dispatch wiring + isolation** (`038.002-T`): [`src/docline/process/pdf_triage.py`](../../src/docline/process/pdf_triage.py) and [`src/docline/process/pdf_batch.py`](../../src/docline/process/pdf_batch.py) — both batched paths use the OCR-aware grouping so an OCR worker OOM only forces OCR ranges/chunks to heuristic; OCR-free docling ranges in neighbouring groups survive. Per-chunk `do_ocr` is computed once and reused.
* **Adaptive downsizing retry** (`038.003-T`): [`src/docline/process/batch_dispatch.py`](../../src/docline/process/batch_dispatch.py) (NEW) — `dispatch_batched_groups_with_retry` re-splits a crashed OCR group at half the cap and retries `8 → 4 → 2 → 1`; successful smaller retries write per-item envelopes the post-pass splices back as docling. Only concedes to heuristic at a single page / cap 1. Wired into both dispatch paths.
* **Pre-existing pyright fixes**: [`src/docline/process/fidelity_scorer.py`](../../src/docline/process/fidelity_scorer.py) (alias pypdf metadata to `Any`) and `pdf_triage.py` (init `envelope` before `try`) — zero behaviour change, needed to keep the typecheck gate green.

## Root-cause finding

Conditional-OCR gating was **already correct** on both batched paths (036-S;
`_range_needs_ocr` / `_chunk_needs_ocr` forward per-item `do_ocr`). A native-text
Azure page that is mostly a screenshot with a short caption legitimately trips
`page_needs_ocr` (<200 chars + embedded images). The real defect was that
`group_by_page_count` bounded **page count, not OCR bitmap memory**, and a hard
OCR `bad_alloc` killed the whole worker subprocess. Fix = OCR-aware grouping
(isolation + tighter cap) + adaptive downsizing retry.

## Files changed

| Path | Change |
|---|---|
| `src/docline/process/page_range.py` | MODIFY — `group_by_page_count_ocr_aware` + `OCR_MAX_BATCHED_PAGES` |
| `src/docline/process/batch_dispatch.py` | NEW — adaptive retry dispatcher |
| `src/docline/process/pdf_triage.py` | MODIFY — OCR-aware grouping + retry dispatch wiring; envelope-init pyright fix |
| `src/docline/process/pdf_batch.py` | MODIFY — OCR-aware grouping + retry dispatch wiring; `do_ocr` computed once |
| `src/docline/process/fidelity_scorer.py` | MODIFY (small) — `Any` alias for pypdf metadata (pyright) |
| `tests/process/test_page_range.py` | MODIFY — 11 OCR-aware grouping unit tests |
| `tests/process/test_batch_dispatch.py` | NEW — 5 adaptive-downsizing unit tests |
| `tests/process/test_bounded_subbatching.py` | MODIFY — 2 crash-isolation + 1 end-to-end recovery regression |
| `docs/closure/041-S-ocr-oom-blast-radius.md` | NEW |

## Quality gate evidence

All gates green at HEAD `9566c84` (pre-merge):

| Gate | Command | Result |
|---|---|---|
| Lint | `ruff check .` | `All checks passed!` |
| Typecheck | `pyright src/` | `0 errors, 0 warnings, 0 informations` |
| Tests | `pytest` | `1336 passed, 6 skipped` |
| Format | `ruff format --check .` | `228 files already formatted` |

CI workflow `ci.yml` is intentionally **paused** (release-tag / manual-dispatch
triggers only, to conserve GitHub Actions minutes); local gates are the
validation model. The merge used `--admin` to satisfy the `REVIEW_REQUIRED`
branch policy after explicit operator approval.

## Adaptive downsizing algorithm

`dispatch_batched_groups_with_retry` walks a worklist of `(indices, cap)`. On a
non-zero exit of a group containing OCR work, it re-splits the group's items
with `group_by_page_count` at `cap // 2` and re-enqueues each subgroup. The loop
**terminates** because the cap halves at every retry level and single-item
groups never recurse. OCR-free groups never retry — their failure is a real
docling error, not memory pressure. Items left without an envelope fall back to
heuristic in the caller's existing post-pass, so the recovery is transparent.

## Review findings

Copilot review (covering commits `ac258e7`/`2b44126`/`fade7a6`) returned **0
findings / 0 threads**. The re-review did not retrigger on the final HEAD
`c631b74` after three re-request methods (~15 min) — a tooling limitation, not a
code finding; the final commit is additive and fully covered by 6 new tests.

## Runtime verification

A real docling OCR OOM is impractical to reproduce deterministically. Coverage
instead exercises the production dispatch paths (`process_pdf_triaged`,
`process_pdf_in_chunks`) with injected runners: crash-isolation regressions
prove OCR-free ranges survive an OCR group crash, and an end-to-end recovery
test proves OCR ranges return as docling (`subprocess_fallback_count == 0`) after
adaptive downsizing. A real-interpreter sanity check confirmed grouping
behaviour and clean imports of both dispatch modules.

## Rollback

`git revert 41bcb47` cleanly restores the prior behaviour (single-cap
`group_by_page_count` grouping, one-shot heuristic fallback on OCR crash, no
retry). No schema, CLI, or MCP surface changed.

## Stash follow-up

`338B788B` (low): per-page OCR DPI / bitmap downscale for the single-page-too-large
OOM case that group-halving cannot fix — when a single page at cap 1 still OOMs,
retry it at a reduced OCR rendering resolution before conceding to heuristic.
