---
title: Bounded sub-batching for the docling batched worker
date: 2026-06-23
status: decided
kind: deliberation
task: 032.003-T
feature: 032-F
references:
  - docs/decisions/2026-06-14-docling-batch-size-probe.md
  - docs/closure/033-S-worker-observability-and-batched-revert.md
  - docs/closure/034-S-batched-crash-recovery.md
  - src/docline/process/pdf_triage.py
  - src/docline/process/pdf_batch.py
  - src/docline/_tools/docling_worker.py
---

# Bounded sub-batching for the docling batched worker (032.003-T)

## Problem frame

032-S shipped `use_batched_worker` running **all** flagged ranges in **one**
long-lived subprocess. On the cosmos corpus (86 ranges / 1,818 pages) that
process accumulated torch working set until it was OOM-killed → 86/86 docling
fallback (zero docling output). 033-S reverted the default to per-chunk
(memory-safe: one subprocess per chunk, reclaimed between chunks) but
surrendered the batched model-load amortization win.

The goal is to recover the batched win **safely**: amortize docling's
~5-10s cold-start across several chunks while keeping peak RSS bounded so the
OOM cannot recur.

## Empirical grounding (from 032.001-T probe)

`docs/decisions/2026-06-14-docling-batch-size-probe.md`:

- A **single** 30-page conversion peaks at ~2 GB RSS (`layout_batch_size=4`,
  OCR off).
- Batched mode **accumulates** working set across conversions in one process —
  this is the mechanism behind the 1,818-page OOM.
- Output is identical across batch sizes; batch size affects only speed/memory.

So the safe unit is a **bounded group** of pages, sized so a fresh subprocess
per group keeps peak RSS within host headroom.

## Options

- **A — Bounded sub-batching (group-by-cumulative-page-count).** Walk the
  ordered splice/chunk list, greedily accumulate items into a group until
  adding the next would exceed `MAX_BATCHED_PAGES`, then start a new group.
  Spawn **one fresh `--batch` worker per group** (reclaims torch memory between
  groups) while amortizing model load **within** a group. Combines with the
  032.002-T per-chunk envelope gating so a mid-group crash preserves the
  group's already-written chunk envelopes.
- **B — Keep per-chunk default (033-S status quo).** Safe but gives up the
  model-load amortization entirely.
- **C — Adaptive cap from live RSS probing.** Monitor subprocess RSS and split
  dynamically. Most precise but adds cross-platform memory-probing complexity
  and non-determinism; over-engineered for the current need.

## Chosen direction — Option A

Implement bounded sub-batching with a calibrated static page cap.

### MAX_BATCHED_PAGES

Choose **40** as the default cap. Rationale: a single 30-page conversion peaks
at ~2 GB; batched mode accumulates, so a group of ~40 pages keeps a fresh
per-group process within a conservative working-set envelope on the
8-core/host-class machines in the probe, with margin below the point where the
1,818-page run died. 40 sits in the middle of the stash-suggested 32-48 band:
cosmos 1,818 pages / 40 ≈ 46 subprocesses (vs 86 per-chunk vs 1 unsafe-giant) —
roughly halves the cold-start count while bounding memory. Expose it as a
named module constant so it is tunable without code archaeology.

### Grouping algorithm

Greedy bin-pack by cumulative page count over the **existing** range/chunk
ordering (preserve document order for splice-back). A single range/chunk that
already exceeds the cap forms its own group (cannot split below existing
granularity). Each group maps 1:1 to a `--batch` manifest + worker invocation.

### Per-group dispatch

- `pdf_triage`: replace the single all-ranges `--batch` manifest with one
  manifest+invocation per group; per-range `do_ocr` (036-S) is carried into
  each group's manifest unchanged.
- `pdf_batch`: same grouping over `chunks`/`chunk_outputs`; per-chunk `do_ocr`
  (036-S) preserved.
- Reuse the 032.002-T envelope-gating splice-back: each chunk is consumed from
  its own envelope regardless of which group's subprocess produced it.

### Engagement condition

Sub-batching only engages when batched mode is active
(`use_batched_worker=True`, N>=2 items, `not serialize_docling`). The
per-chunk default path (033-S) is unchanged. This keeps the change opt-in and
low-blast-radius until cosmos re-validation promotes it.

## Open questions / follow-ups

1. **Cosmos re-validation (runtime verification, not a build blocker).** Peak
   RSS bounded + docling actually runs (not fallback) + wall-clock vs per-chunk
   baseline. Heavy docling inference (~1,818 pages); the full
   `azure-cosmos-db.pdf` and a working docling `.venv` are present, so this is
   runnable but slow — schedule as a `manual` runtime-verification gate after
   the unit-tested code lands, before flipping any default.
2. **Default flip is out of scope.** This shipment keeps `use_batched_worker`
   default False; promoting bounded-batched to default is a separate decision
   gated on the cosmos re-validation numbers.
3. **Cap tunability.** `MAX_BATCHED_PAGES` ships as a constant; an env-var or
   budget-derived override can follow if hosts vary widely.

## Scope

Single skill domain: the batched-worker dispatch in `pdf_triage` + `pdf_batch`
(grouping helper + per-group invocation). No worker-contract change (reuses the
existing `--batch` manifest and 032.002-T envelope gating). Unit-testable with
the existing fake-runner harness; cosmos re-validation deferred to runtime
verification.
