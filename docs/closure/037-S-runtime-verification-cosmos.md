---
title: Runtime verification — 037-S bounded sub-batching (cosmos corpus)
date: 2026-06-25
kind: runtime-verification
shipment: 037-S
feature: 032-F
status: verified
verdict: PASS
references:
  - docs/closure/037-S-bounded-sub-batching.md
  - docs/decisions/2026-06-23-bounded-sub-batching-deliberation.md
  - scripts/pa3_triage_cosmos.py
  - .elt/output/cosmos-perchunk/pa3-summary.json
  - .elt/output/cosmos-batched/pa3-summary.json
---

# Runtime verification — 037-S bounded sub-batching

Operator ran both modes on a remote dev box against the full
`azure-cosmos-db.pdf` (3,426 pages, 109.55 MB) using the `--use-batched-worker`
flag added for this verification. Both runs used identical settings
(`buffer=1`, `merge_gap=2`, `baseline_engine=markitdown`, `--sample-rate 0.01`,
`--qa-random-seed 42`).

## Results

| Metric | Per-chunk (default) | Batched (037-S) | Delta |
|---|---|---|---|
| Wall-clock | 4767.3s (1h19m27s) | 4312.4s (1h11m52s) | −454.9s (**~9.5% faster**) |
| `subprocess_fallback_count` | 0 / 86 | 0 / 86 | identical (**0%**) |
| Engine distribution | docling-collapsed 2799 / heuristic 627 | docling-collapsed 2799 / heuristic 627 | identical |
| QA disagreements | 0 / 6 (all ≥0.9) | 0 / 6 (all ≥0.9) | identical |
| Pages → docling | 2799 / 3426 (82%) | 2799 / 3426 (82%) | identical |
| Flagged ranges | 86 | 86 | identical |

## Verdict: PASS

1. **The OOM is gone (primary 037-S claim).** The original `6E6754D4` failure
   was 86/86 (100%) docling fallback when all 1,818 flagged pages ran in one
   long-lived subprocess. Bounded sub-batching (40-page groups → ~46
   subprocesses) runs the full corpus with **0/86 fallback**. Because an
   OOM-killed worker yields fallback, zero fallback across all groups is the
   functional proof that peak memory stayed bounded.

2. **Batched perf win recovered: ~9.5% faster** (4767s → 4312s) — the
   docling model-load amortization within groups. Batched also returns
   wall-clock to **under the 75-minute 022-S threshold** (per-chunk is slightly
   over at 1h19m).

3. **No fidelity regression.** Engine distribution is byte-for-byte identical
   between modes, and all 6 QA-sampled pages scored ≥0.9 similarity with 0
   disagreements.

## Caveats / not measured

- **Peak RSS was not captured** in `pa3-summary.json` (no such field). The 0%
  fallback is a strong functional proxy for bounded memory on this host, but
  there is no absolute RSS figure. A future probe could record peak RSS to make
  the memory claim quantitative.
- **036-S conditional OCR is not isolated** by these two runs — both have it
  active, so they validate 037-S (batched vs per-chunk) but do not *quantify*
  the OCR win. The ~72–79 min times vs the historical ~247-min OCR-on-everything
  baseline are suggestive but not a controlled comparison.

## Orthogonal observation (triage tuning, not 037-S)

82% of pages (2799/3426) route to docling: the scorer flags 53% raw
(1818 pages), and coalescing with `merge_gap=2` expands that to 2799 by
absorbing small heuristic gaps. Identical in both modes. Whether the triage
scorer over-routes is a separate tuning question; it does not affect the
batching verdict.

## Recommendation on the default

The data justifies promoting bounded-batched mode: faster, zero fallback,
identical output, and inherently safer than the old all-in-one batched mode
(which OOM'd). The remaining gate before flipping `use_batched_worker` to
default is confirming memory headroom is representative across target hosts
(the RSS number was not captured here). Promotion should ship as its own small,
test-covered change.
