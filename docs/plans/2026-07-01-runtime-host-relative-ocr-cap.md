---
title: Runtime host-relative OCR memory cap and scale recovery
date: 2026-07-01
status: planned
stash: 699FB5DC
feature: 041-F
shipment: 044-S
origin_feature: 040-F
references:
  - docs/decisions/2026-06-30-ocr-memory-calibration.md
  - src/docline/runtime/resource_probe.py
  - src/docline/process/page_range.py
  - src/docline/process/batch_dispatch.py
  - src/docline/process/pdf_batch.py
  - src/docline/process/pdf_triage.py
---

## Problem

`OCR_MAX_BATCHED_PAGES = 8` (`page_range.py`) is a provisional, host-blind
constant. The batched docling worker OOM risk is relative to the *host's*
available memory: 8 pages that fit a 128 GB box can OOM an 8 GB box, and 8 is
needlessly small on a large box. The calibration run (040.002-T) produced a
portable cost model; this feature applies it at runtime so the same binary caps
per host.

## Calibrated inputs (from the decision doc)

`peak_mb ~= base_mb + k_mb_per_mpx * (page_megapixels * scale^2 * pages_per_group)`

* `base_mb = 1412.84` — fixed OCR runtime working set.
* `k_mb_per_mpx = 15.4942` — marginal per `mpx * scale^2 * page`.
* `per_page_mb ~= 207` — empirical fixed per-page floor (digital corpora; the
  fit R^2 was 0.148 because per-page cost was scale/mpx-insensitive). The
  runtime guard MUST also apply this floor and take the smaller cap.
* `safe_fraction = 0.6` default.

## Approach

Add a pure, unit-tested budget module that turns
`(available_mb, page_megapixels, scale, coefficients)` into a
max-pages-per-group cap and a single-page recovery scale, then wire it through
the existing grouping + retry seams:

1. `group_by_page_count_ocr_aware` already accepts `ocr_max_pages`; callers
   pass a runtime-derived cap instead of relying on the fixed default.
2. `dispatch_batched_groups_with_retry` replaces the blind `cap // 2` halving
   with a memory-derived downsizing, and adds a single-page `ocr_scale`
   step-down retry (the 040.001-T manifest knob) before conceding to heuristic.

`OCR_MAX_BATCHED_PAGES = 8` stays as the ceiling / degraded-probe fallback.

## Constitution check

* Test-first: every task writes red tests first; the cap/scale math and the
  retry are unit-testable with synthetic inputs and a fake runner.
* Single responsibility: no new runtime deps; reuses `resource_probe` and the
  existing `ocr_scale` worker knob.
* Workspace isolation / typed errors preserved.

## Task decomposition

* **T1 — Calibrated OCR budget module (pure).** New
  `src/docline/runtime/ocr_budget.py` with the coefficients, `predict_peak_mb`,
  `max_ocr_pages_per_group` (min of bitmap-area cap and per-page-floor cap,
  never < 1), and `recover_scale_for_single_page`. Red-first synthetic tests.
* **T2 — Derive the cap at runtime and wire into grouping.** Compute
  `ocr_max_pages` from `probe()` + `ocr_budget` (representative page
  megapixels; conservative default when unavailable) and pass it to
  `group_by_page_count_ocr_aware` / `dispatch_batched_groups_with_retry` in
  `pdf_batch.py` and `pdf_triage.py`. Fall back to `OCR_MAX_BATCHED_PAGES` when
  the probe is degraded. Depends on T1.
* **T3 — Memory-derived downsizing replaces `cap // 2`.** In
  `dispatch_batched_groups_with_retry`, recompute the retry cap from the cost
  model against a reduced budget instead of halving; preserve the strictly
  decreasing, terminating, `>= 1` guarantee. Fake-runner tests. Depends on T1.
* **T4 — Single-page scale-step retry.** When a single OCR item at `cap == 1`
  still OOMs, walk `recover_scale_for_single_page` (2.0 -> 1.0 -> 0.5 -> 0.25),
  emitting `ocr_scale` into the manifest chunk, before conceding to heuristic.
  Fake-runner scale-step tests. Depends on T3.

## Follow-ups (not in this feature)

* Stash `A3E6D72C` — re-calibrate coefficients on a scanned / high-mpx corpus
  to exercise `k` and the scale schedule; may update the constants in T1.

## Verification

`ruff check .`, `pyright src/`, `pytest`, `ruff format --check .`. New unit
tests for the budget math, caller wiring, memory-derived downsizing, and the
scale-step retry.
