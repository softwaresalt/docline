---
type: session-memory
date: 2026-06-29
feature: 038-F
shipment: 041-S
pr: 109
branch: fix/038-F-ocr-oom-blast-radius
status: awaiting-operator-merge-approval
---

# Session memory — 038-F batched docling OCR OOM fix (stage + ship 041-S)

## Outcome
Staged and built shipment **041-S** (feature **038-F**) end-to-end; PR
**#109** open and merge-ready, **awaiting explicit operator merge approval
(P-014)**. Not merged.

## Tasks completed
- **038.001-T** (`ac258e7`) — `group_by_page_count_ocr_aware` + `OCR_MAX_BATCHED_PAGES=8`
  in `page_range.py`; OCR items never share a group with OCR-free items. +11 unit tests.
- **038.002-T** (`2b44126`) — wired OCR-aware grouping into both batched dispatch
  paths (`pdf_triage`, `pdf_batch`); per-chunk `do_ocr` computed once. +2 crash
  isolation regressions.
- **038.003-T** (`c631b74`) — adaptive OCR-group downsizing retry (operator
  follow-up): new `batch_dispatch.dispatch_batched_groups_with_retry` re-splits a
  crashed OCR group at half cap and retries 8→4→2→1 before conceding to heuristic.
  +5 unit + 1 e2e recovery test.
- `fade7a6` — 2 pre-existing pyright fixes (`fidelity_scorer.py`, `pdf_triage.py`)
  to unblock the typecheck gate (zero behavior change).

## Files modified / added
- `src/docline/process/page_range.py` (new function + OCR_MAX_BATCHED_PAGES)
- `src/docline/process/batch_dispatch.py` (NEW — adaptive retry dispatcher)
- `src/docline/process/pdf_triage.py` (wiring + envelope-init pyright fix)
- `src/docline/process/pdf_batch.py` (wiring; do_ocr computed once)
- `src/docline/process/fidelity_scorer.py` (pyright type-narrowing)
- `tests/process/test_page_range.py`, `test_bounded_subbatching.py`,
  `test_batch_dispatch.py` (NEW)

## Root-cause decision
Conditional-OCR gating was already correct on both batched paths (036-S). The
real defect was that `group_by_page_count` bounded page count, not OCR bitmap
memory, and a hard OCR `bad_alloc` killed the whole batched group. Fix =
OCR-aware grouping (isolation + tighter cap) + adaptive downsizing retry.

## Quality gates (final state, HEAD c631b74)
- `ruff check .` ✅ · `pyright src/` ✅ 0 errors · `pytest` ✅ 1336 passed, 6 skipped
  · `ruff format --check .` ✅
- CI workflow `ci.yml` is PAUSED by design (release-tag/manual triggers only;
  operator validates locally) — no PR checks run.

## Open issues / next steps
- **BLOCKER:** operator must approve the PR #109 merge (P-014). On approval:
  merge with a merge commit (P-009), then post-merge closure — `backlogit_ship_shipment`
  for 041-S, shipment-reconcile, closure doc in `docs/closure/`, archive
  038-F/tasks, compound-refresh, compact-context.
- **Copilot review caveat:** the re-review did NOT trigger on the new HEAD
  `c631b74` after 3 re-request methods (~15 min). Last Copilot review is stale at
  `fade7a6` and was clean (0 findings, 0 threads). Tooling limitation, not a code
  finding.
- **Follow-up stashed `338B788B`** (low): per-page OCR DPI/bitmap downscale for
  the single-page-too-large OOM case that group-halving cannot fix.

## Failed approaches (avoid repeating)
- Pyright `hasattr(obj, "get")` narrowing on an `object`-typed param did NOT
  satisfy pyright; `getattr`+`callable` cascaded the error. The working fix was
  aliasing the metadata to `Any` (`meta: Any = page_metadata`).
- `gh pr edit --add-reviewer copilot` returns "'' not found"; use
  `gh api -X POST .../requested_reviewers -f "reviewers[]=Copilot"` instead.
- Re-requesting Copilot (POST, and DELETE+POST) did not retrigger a fresh review
  on a new push within budget.
