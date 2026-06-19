---
title: Closure — 034-S Docling batched-worker perf recovery (032.002-T partial-crash recovery)
date: 2026-06-19
shipment: 034-S
feature: 032-F
status: verified
merged_pr: 89
merge_sha: d1362bd
branch: feat/034-S-batched-crash-recovery
---

## Readiness status

**READY** — merge to `main` is complete (PR #89, merge commit `d1362bd`, a true
two-parent merge commit per P-009).

## What shipped

Task **032.002-T** — batched-mode partial-crash recovery.

In batched docling-worker mode, both `pdf_triage.process_pdf_triaged` (splice
post-pass) and `pdf_batch._run_chunks_batched` gated each chunk's usability on
the **whole-batch** subprocess return code. When the batched worker was killed
partway after writing `K` valid chunk envelopes, every chunk was marked
fallback — discarding the `K` successfully-written envelopes.

The fix gates each chunk/range on its **own** output envelope (existence plus
the existing error-envelope check). The batch is treated as fully failed only
when no chunk produced an envelope.

- `src/docline/process/pdf_triage.py` — post-pass loop sets `subprocess_ok =
  True` in batched mode; per-range gating is handled by `splice_md.exists()`
  plus error-envelope detection.
- `src/docline/process/pdf_batch.py` — `_run_chunks_batched` gates on
  `chunk_out.exists()` regardless of `batch_subprocess_failed`.

## Verification

- Two TDD regression tests written first and confirmed RED before the fix:
  `test_batched_mode_partial_crash_recovers_written_envelopes` and
  `test_triage_batched_partial_crash_recovers_written_ranges`.
- `pytest tests/process/test_pdf_batch.py tests/process/test_pdf_triage.py` — 13
  batched/partial cases pass; full files green. The existing "subprocess
  failure routes all to heuristic" tests still pass (they write no envelopes,
  preserving the all-fallback-when-no-envelopes contract).
- `ruff check`, `ruff format --check` — pass.
- `pyright` — no new errors. Two pre-existing errors in `pdf_triage.py` (line
  177 `enable_plugins`; an `envelope` possibly-unbound false positive) exist
  identically on `main` and are out of scope.
- Docline CI is paused by design (`ci.yml` triggers commented out for
  Actions-minute conservation); local gates are the validation substitute.
- Copilot review: clean, fresh on merged HEAD, zero unresolved threads.

## What did NOT ship (returned blocked)

The shipment was re-scoped from the original three-task cluster because two
tasks require inputs the agent cannot produce. Both remain in the queue as
`blocked` tasks under the still-open feature **032-F**:

- **032.001-T** — docling batch-size probe. Requires operator-run docling
  inference; docling is not importable in the agent environment.
- **032.003-T** — bounded sub-batching. Carries `needs-deliberation` and
  depends on the 032.001-T probe data plus cosmos docling re-validation.

Feature 032-F is intentionally left `active` (not archived) because these two
tasks are still open.

## Follow-ups

- Operator runs `scripts/study/docling_batch_size_probe.py` and commits results
  to unblock 032.001-T.
- Run the deliberate skill on 032.003-T before building bounded sub-batching.
- Stash entries `D771B78E` (per-page fidelity) and `E32FAF6F` (hybrid routing)
  remain active — separate concerns excluded from this cluster.
