---
title: Closure — 037-S Bounded sub-batching for docling batched worker
date: 2026-06-23
shipment: 037-S
feature: 032-F
status: verified
merged_pr: 96
merge_sha: c325b30
branch: feat/037-S-bounded-sub-batching
---

## Readiness status

**READY** — merged to `main` (PR #96, merge commit `c325b30`, a true two-parent
merge commit per P-009). Closes feature **032-F** (Docling batched-worker perf
recovery).

## What shipped

Task **032.003-T** — bounded sub-batching for the docling batched worker.
Recovers the batched model-load amortization win that 033-S surrendered
(per-chunk default for memory safety) **without** reintroducing the 032-S
1,818-page OOM. Implements Option A from the 2026-06-23 deliberation.

| File | Change |
|---|---|
| `page_range.py` | New `group_by_page_count()` (greedy bin-pack by cumulative page count) + `MAX_BATCHED_PAGES = 40` |
| `pdf_triage.py` | Batched splice dispatch splits ranges into bounded groups; one `--batch` worker per group |
| `pdf_batch.py` | `_run_chunks_batched` splits chunks into bounded groups; per-chunk returncode tracking |

A fresh subprocess **per group** reclaims torch memory between groups (avoids
the OOM) while amortizing the docling model load **within** a group. cosmos
1,818 / 40 ≈ 46 subprocesses vs 86 per-chunk vs 1 unsafe-giant.

### MAX_BATCHED_PAGES = 40

Calibrated from the `032.001-T` probe: a single 30-page conversion peaks ~2 GB
RSS; batched mode accumulates → the OOM. 40 sits in the deliberated 32–48 band.

### Preserved invariants

- **036-S `do_ocr`** carried into every group's manifest (per-range / per-chunk).
- **032.002-T envelope gating** unchanged — each chunk/range consumed from its
  own envelope, so a mid-group crash preserves the group's written envelopes.
- **Opt-in / default False** — engages only when `use_batched_worker=True` and
  N≥2; the production per-chunk default path is untouched.

## 032-F scope summary

| Task | Disposition |
|---|---|
| `032.001-T` (batch-size probe) | Already satisfied by committed 033-S work (decision doc `2026-06-14-docling-batch-size-probe.md`); closed during 037-S staging |
| `032.002-T` (partial-crash recovery) | Shipped in 034-S |
| `032.003-T` (bounded sub-batching) | Shipped here |

## Verification

- Red→green TDD. New `test_page_range.py` grouping tests (7) +
  `test_bounded_subbatching.py` (5).
- **Full suite: 1294 passed, 4 skipped.**
- `ruff check` / `ruff format --check`: clean on changed files.
- `pyright`: no new errors (2 pre-existing in `pdf_triage`, out of scope).
- Adversarial review run before merge: no P0/P1/P2.

## ⚠️ Outstanding — deferred runtime-verification gate

This shipment is validated by **unit tests with fake runners** — it proves the
dispatch splits into bounded groups correctly. It does **NOT** yet prove the
actual memory-bounding on the real cosmos corpus. The cosmos re-validation
(peak RSS bounded, docling actually runs, wall-clock vs per-chunk) remains a
**deferred manual runtime-verification** step. `use_batched_worker` stays
default-False; promoting bounded-batched to default is a separate decision
gated on those numbers.

## Follow-ups

- **Cosmos runtime verification** (manual, heavy docling inference; runnable
  here with the full `azure-cosmos-db.pdf` + docling `.venv`) — required before
  any future default flip to bounded-batched mode.
- `C04896E1` — maintainability dedup; now also covers the `_chunk_page_count` /
  `_chunk_needs_ocr` double-open of chunk PDFs surfaced in this review.
- Env-var / budget-derived override for `MAX_BATCHED_PAGES` (deliberation
  follow-up) if hosts vary widely.
