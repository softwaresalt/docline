---
shipment: 044-S
title: "Closure record — runtime host-relative OCR memory cap + scale recovery (041-F)"
status: verified
merge_sha: ac1c9c8
merged_pr: 115
---

## Scope delivered

Feature `041-F` applies the calibrated OCR peak-memory cost model (from the
040.002-T calibration run) at runtime so the batched docling worker OCR cap is
host-relative instead of the provisional fixed `OCR_MAX_BATCHED_PAGES = 8`.

| Task | Delivered |
|---|---|
| `041.002-T` (T1) | `src/docline/runtime/ocr_budget.py` — calibrated coefficients, `max_ocr_pages_per_group` (min of bitmap-area and per-page-floor caps), `recover_render_scale` / `recover_scale_for_single_page` |
| `041.001-T` (T2) | `src/docline/process/ocr_cap.py` bridges probe + model; `pdf_batch` / `pdf_triage` pass a memory-derived `ocr_max_pages` (fallback 8 when degraded) |
| `041.003-T` (T3) | `dispatch_batched_groups_with_retry` recomputes the OOM retry cap from the model at a shrunk budget instead of blind `cap // 2`, preserving termination |
| `041.004-T` (T4) | single-page `ocr_scale` step-down retry (`2.0 -> 1.0 -> 0.5 -> 0.25`) emitting the manifest knob before heuristic |

## Verification

* `ruff check .` — clean
* `pyright src/` — 0 errors
* `pytest -m "not integration"` — 1373 passed, 2 skipped
* `ruff format --check .` — clean
* Copilot review — 3 fix cycles, 4 findings resolved (all-pages mpx scan;
  group-page-count scale recovery; `ocr_scale` gated on `do_ocr`; `MB_PER_GB`
  single source of truth). Fresh review clean, 0 unresolved threads.

## Merge

Merge commit `ac1c9c8` (PR #115, merge-commit strategy per P-009). Branch
`feat/041-runtime-ocr-cap` deleted.

## Follow-ups

* Stash `A3E6D72C` — re-calibrate coefficients on a scanned / high-mpx corpus to
  exercise the bitmap-area `k` term and the scale schedule (the digital-corpus
  fit had R^2 = 0.148).

## Notes

* backlogit MCP was down (`Transport closed`) during the session; status
  transitions and the shipment archive were completed via the backlogit CLI
  (see `docs/compound/2026-07-03-backlogit-mcp-down-fall-back-to-cli.md`).
