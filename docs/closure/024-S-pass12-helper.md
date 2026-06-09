---
title: Closure — 024-S extract shared Pass 1-2 helper
date: 2026-06-09
shipment: 024-S
feature: 022-F
status: verified
merged_pr: 52
merge_sha: a7f1ed8
branch: feat/024-S-pass12-helper
harvested_stashes: DE3E7346
parent_closures:
  - docs/closure/021-S-triage-then-repair.md
  - docs/closure/022-S-pa4-closure.md
  - docs/closure/023-S-strategy-alignment.md
---

## Readiness status

**READY** — merge complete (PR #52, merge commit `a7f1ed8`).

Small bounded refactor. No behavior change in any public API or CLI
surface. Eliminates duplication between `process_pdf_triaged` and
`triage_report_only` by introducing a private shared Pass 1+2 helper.

## Scope

Stash `DE3E7346` (review follow-up from 019-F). Single-task shipment.

## Changes

| Path | Action |
|---|---|
| `src/docline/process/pdf_triage.py` | MODIFY — new `_Pass12Result` frozen dataclass + `_heuristic_and_score_pass` helper; `process_pdf_triaged` and `triage_report_only` refactored to use it |
| `tests/process/test_pdf_triage_pass12_helper.py` | NEW — 5 unit tests for the helper (page count, splice cache, scorer indexing, missing-PDF error, tuple immutability of returned heuristic_pages/scores) |

## Implementation note

Before the refactor, the two functions duplicated the reader-init +
splice-cache-mkdir + per-page heuristic extraction + per-page scoring
blocks (~15 lines each). The two implementations were slightly
divergent:

* `process_pdf_triaged` used two separate loops (extract all, then
  score all) with defensive page-metadata access
  (`page_idx < len(reader.pages)`)
* `triage_report_only` used one interleaved loop without the
  defensive guard

The new helper uses the interleaved single-loop form WITH the
defensive guard — the most conservative behavior of the two callers.
This unification is verified to produce identical observable output
by the 1029 pre-existing tests passing unchanged.

## Verification

| Gate | Result |
|---|---|
| pytest (full suite) | **1034 passed / 3 skipped / 0 failed** (was 1029; +5 new helper tests) |
| ruff check | clean |
| ruff format --check | clean |
| pyright (touched files) | 0 new errors |
| CI on PR #52 | all 7 jobs green |
| Copilot Review | clean (zero comments raised) |

## Adversarial self-review

3 considerations evaluated pre-PR:

1. The defensive `page_idx < len(reader.pages)` conditional inside the
   helper is technically dead code (since `total_pages = len(reader.pages)`),
   but retained to match the conservative style of the original
   `process_pdf_triaged` implementation. The conditional cost is
   negligible.
2. `_Pass12Result.reader` is a non-frozen object inside a frozen
   dataclass. Per Python's frozen semantics, this only blocks field
   rebinding (not mutation of held objects). The helper guarantees the
   reader is fresh per call so no shared-state bug is possible.
3. `splice_cache` is created in BOTH callers even though
   `triage_report_only` never writes docling splice PDFs. The cache is
   still needed for the per-page baseline-NNNN.pdf artifacts that
   markitdown produces (and which the 2026-06-08 study script reuses
   for diagnostic comparisons). Verified by the existing markitdown
   baseline tests passing unchanged.

## Invariants preserved

| Invariant | Verification |
|---|---|
| `process_pdf_triaged` output unchanged | All 12 pre-existing `test_pdf_triage_*` tests pass |
| `triage_report_only` output unchanged | All `test_pdf_triage_qm_integration` + `test_pdf_triage_baseline_engine` tests pass |
| `_Pass12Result.heuristic_pages` is a tuple (immutable) | `test_pass12_result_heuristic_pages_is_immutable` |
| `_Pass12Result.scores` is a tuple (immutable) | same test |
| Helper raises `FileNotFoundError` on missing PDF | `test_pass12_helper_raises_on_missing_pdf` |
| Helper creates `output_dir/splices/` | `test_pass12_helper_splice_cache_created` |
| Scorer receives correct per-page index | `test_pass12_helper_scorer_sees_correct_page_index` |

## Risk

**Low.** Pure internal refactor:

* No public API change
* No CLI surface change
* No new dependencies
* All pre-existing tests pass unchanged
* New helper has dedicated test coverage

## Deployment / rollback

Merge-only. No service deploy.

Rollback: `git revert -m 1 a7f1ed8` then push. Removes the helper and
restores both callers to their pre-refactor inline form. Existing
tests would continue to pass because the refactor preserves
observable behavior.

## Follow-up

None directly from 024-S. Roadmap continuation remains:

* `EFC6C84E` → 025-S (scoring inversion — the architecturally important
  pending work; not safe for overnight unsupervised execution because
  it changes scoring algorithm semantics and requires empirical
  validation against the cosmos corpus)
* `6A4E8059` → 026-F (source-MD ingestion pathway — multi-week feature
  per the decomposition guidance)
* `51332802` → 027-S (docling speedup — needs spike first)
* `4CB606D5` → research spike (generalization study)
* `5CFE4481` → medium-priority improvement (per-page docling output)

## Recommendation

**READY** — refactor complete; main is cleaner; future scoring/triage
changes can modify the shared helper once instead of two divergent
sites.
