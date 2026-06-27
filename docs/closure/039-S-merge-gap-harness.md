---
title: Closure — 039-S merge_gap comparison harness
date: 2026-06-27
shipment: 039-S
feature: 036-F
status: verified
merged_pr: 106
merge_sha: 08017cd
branch: feat/039-S-merge-gap-harness
---

## Readiness status

**READY** — merged to `main` (PR #106, merge commit `08017cd`, a true two-parent
merge commit per P-009).

**Feature `036-F` remains OPEN** — this shipment delivered only the
agent-shippable harness (`036.001-T`). The operator-run experiment
(`036.002-T`) is still `queued`; the feature closes after it completes.

## What shipped

Task **036.001-T** — `scripts/study/compare_merge_gap.py`, the analysis harness
for the merge_gap tuning experiment.

It ingests two or more `pa3-summary.json` files (one per `merge_gap` value),
prints a comparison table, and recommends whether to lower the triage
`merge_gap` default:

- **Verdict driven by wall-clock** (the goal), **guarded by QA**: a lower
  `merge_gap` wins only if it cuts wall-clock by ≥ `--win-threshold` (default
  5%) without raising `qa_disagreements` beyond `--qa-tolerance` (default 0).
  Reports `LOWER-DEFAULT` / `KEEP-DEFAULT` / `INCONCLUSIVE`.
- **Consumes the 038-S `docling_attribution`** section for accurate routing
  stats; raises a clear error on pre-038-S summaries.
- **No docling import** — pure JSON ingest, agent-safe and fully unit-testable.

## Verification

- Red→green TDD: 7 tests (`_extract_row` incl. missing-attribution error,
  `_verdict` win/keep/inconclusive, `main` happy-path + arg validation).
- `pytest tests/test_compare_merge_gap.py` — 7 passed.
- `ruff check` / `ruff format --check` — clean.
- `pyright scripts/study/compare_merge_gap.py` — no errors.
- Adversarial review: no findings.

## Post-merge incident (resolved)

`backlogit shipment ship 039-S` cascade-archived the parent feature `036-F`
even though the shipment contained only `036.001-T` and sibling `036.002-T`
remained queued. Restored `036-F` to `active` via an out-of-band markdown edit
(status → active, strip `archived_from`/`commit`, move `archive/` → `queue/`,
`sync`, `doctor` clean). Captured as the compound learning
`docs/compound/2026-06-27-ship-cascade-archives-parent-feature.md`.

## Next (operator-run, 036.002-T)

Run on the remote box:

```powershell
foreach ($n in 0,1,2) {
  uv run python scripts/pa3_triage_cosmos.py `
    --output-dir .elt/output/cosmos-mg$n --log-path logs/mg$n.log `
    --merge-gap $n --sample-rate 0.01 --qa-random-seed 42
}
uv run python scripts/study/compare_merge_gap.py `
  --summaries .elt/output/cosmos-mg2/pa3-summary.json `
              .elt/output/cosmos-mg1/pa3-summary.json `
              .elt/output/cosmos-mg0/pa3-summary.json
```

Bring the three summaries + verdict back; if `LOWER-DEFAULT`, ship the
`merge_gap` default change (separate small code shipment) and then close
`036-F`.
