---
title: Closure — 036-S Conditional docling OCR
date: 2026-06-23
shipment: 036-S
feature: 034-F
status: verified
merged_pr: 93
merge_sha: d97b114
branch: feat/036-S-conditional-docling-ocr
---

## Readiness status

**READY** — merged to `main` (PR #93, merge commit `d97b114`, a true two-parent
merge commit per P-009).

## What shipped

Feature **034-F** — make docling OCR conditional so RapidOCR runs only on
image-only/scanned pages, not on native-text pages that already carry an
extractable text layer. Implements Option A from deliberation `002-DL`.

| Task | Commit | Change |
|---|---|---|
| `034.004-T` | `6e6a805` | `_read_pdf_docling_pages` gains keyword-only `do_ocr` (default True) set on `PdfPipelineOptions` |
| `034.005-T` | `307c9e9` | `docling_worker` accepts `do_ocr` — single-chunk `--no-ocr` flag + optional per-chunk manifest field |
| `034.006-T` | `94d34e1` | `pdf_triage`/`pdf_batch` compute per-range/per-chunk `do_ocr` from a new `fidelity_scorer.page_needs_ocr` signal and thread it through every dispatch site |

### Decision rule

`page_needs_ocr` reuses `signal_char_density`: a page needs OCR when it has
sparse text **and** embedded images (the image-only/scanned signature). A
coalesced range/chunk gets `do_ocr=False` only when every page has a text
layer; any image-only page forces OCR on (conservative — no scanned-PDF
fidelity regression). The `--no-ocr` flag is placed before the positional
input/output args so the worker cmd contract (`args[-2]`/`args[-1]`) is
preserved.

## Verification

- Strict red→green TDD per task; red phases observed failing before
  implementation.
- **Full suite: 1279 passed, 4 skipped** (before the review fix); the
  conditional-OCR suite is 12 passing tests including real image-only PDF
  fixtures (Pillow-built, skip-gated on PIL).
- `ruff check` / `ruff format --check`: clean on all changed files.
- `pyright`: no new errors (3 pre-existing errors in `signal_font_diversity`
  and `pdf_triage` are unchanged and out of scope).
- CI is paused by design; local gates are the validation substitute.

## Adversarial review

Full multi-persona review run before merge. No P0/P1 findings.

- **F1 (P2) — fixed in `c537479`:** added a real image-only PDF fixture and
  three end-to-end tests covering the `do_ocr=True` path (signal + triage +
  batch). Closes the `034.006-T` acceptance criterion.
- **F4 (advisory) — filed:** stash `C04896E1` to unify `_range_needs_ocr` and
  `_chunk_needs_ocr`.
- **F2 / F3 (advisory) — accepted:** F2 inherits `signal_char_density`'s image
  detection blind spot (no regression); F3 threads `do_ocr` into the QA
  tripwire (deliberate, perf-consistent).

## What did NOT ship (scope boundary)

- **Option B** (per-page splitting of mixed text/image ranges) — deferred; the
  conservative per-range rule covers the common native-text case.
- Quantified throughput measurement — gated on stash `032.001-T` (docling
  batch-size probe), which now depends on `034-F` so OCR cost no longer
  confounds the measurement.

## Recommended follow-ups

- **Runtime verification** on a real native-text PDF (docling runs without OCR,
  fidelity preserved) and a real scanned PDF (OCR still runs) — the test
  doubles cannot validate actual OCR runtime behavior.
- Run `032.001-T` (batch-size probe) + a cosmos re-run to quantify the OCR
  removal speedup against the ~247-min baseline.
- `C04896E1` — maintainability dedup of the two OCR-gate helpers.
