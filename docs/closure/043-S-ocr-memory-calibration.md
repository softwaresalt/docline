---
shipment: 043-S
title: "Closure record — OCR memory calibration harness + ocr_scale plumbing (040-F)"
status: verified
merge_sha: a423e1a
merged_pr: 111
---

Captures the implementation evidence for shipment `043-S` (feature `040-F`), the
first stage of the **host-relative** OCR-OOM calibration arc: the measurement +
mechanism plumbing. No new OCR limit constants ship here — the limits are
computed at runtime from a portable cost model the operator calibrates. Consumes
stash `338B788B`.

## Scope

* **`ocr_scale` render-scale knob** (`040.001-T`):
  [`src/docline/readers/pdf.py`](../../src/docline/readers/pdf.py)
  `_read_pdf_docling_pages` gains an optional `ocr_scale` overriding docling's
  `images_scale` (lower scale = lower-resolution page bitmap = less OCR peak
  memory). [`src/docline/_tools/docling_worker.py`](../../src/docline/_tools/docling_worker.py)
  exposes it as a single-chunk `--ocr-scale=N` flag and a per-chunk `ocr_scale`
  manifest field (mirrors `do_ocr`). Additive/back-compat: `None` keeps the
  `2.0` default. Non-positive values are rejected (CLI exit 2; contained
  per-chunk error in batch) — from the pre-merge adversarial review.
* **OCR memory calibration harness** (`040.002-T`):
  [`scripts/study/ocr_memory_calibration.py`](../../scripts/study/ocr_memory_calibration.py)
  fits a portable, host-independent cost model
  `peak_mb ~= base_mb + k * (megapixels * scale^2 * pages)` from measured docling
  OCR peak RSS, then recommends the per-host `max_pages_per_group` and render-scale
  schedule for a given available memory. `--run` (operator, docling+psutil) sweeps
  and measures; `--analyze` (anywhere) fits and recommends.

## Design rationale (operator clarifications 2026-06-30)

The `8→4→2→1` / `0.5/0.25` numbers were illustrative, and **OOM risk is
host-relative**. So calibration yields a portable per-bitmap cost model (the
per-bitmap OCR cost is ~hardware-independent; available memory is the per-host
variable), and docline computes the actual cap/scale at runtime from *this
host's* available memory. The provisional `OCR_MAX_BATCHED_PAGES=8` and `cap//2`
halving from 038-F are placeholders to be replaced by the runtime algorithm —
tracked follow-up stash `699FB5DC`, after the operator runs this harness.

## Files changed

| Path | Change |
|---|---|
| `src/docline/readers/pdf.py` | ADD `ocr_scale` param -> `images_scale` override |
| `src/docline/_tools/docling_worker.py` | `--ocr-scale=N` flag + per-chunk `ocr_scale`; reject non-positive |
| `scripts/study/ocr_memory_calibration.py` | NEW — cost-model fit + recommend + `--run`/`--analyze` |
| `tests/tools/test_docling_worker.py` | +7 ocr_scale forwarding / validation tests |
| `tests/test_ocr_memory_calibration.py` | NEW — 10 fit/recommend/TSV/analyze tests |
| `docs/closure/043-S-ocr-memory-calibration.md` | NEW |

## Quality gate evidence

All gates green at HEAD `7fcfd9b` (pre-merge):

| Gate | Command | Result |
|---|---|---|
| Lint | `ruff check .` | `All checks passed!` |
| Typecheck | `pyright src/` | `0 errors, 0 warnings, 0 informations` |
| Tests | `pytest` | `1358 passed, 6 skipped` |
| Format | `ruff format --check .` | `230 files already formatted` |

CI `ci.yml` is paused by design; local gates are the validation model. Merge used
`--admin` to satisfy the `REVIEW_REQUIRED` branch policy after operator approval.

## Review findings

A local tiered-persona adversarial review (`review` skill) ran pre-merge
(Constitution / Python / Correctness / Maintainability / Learnings + Security +
Architecture). No P0/P1. Dispositions:

* **P3 (Security)** — `ocr_scale <= 0` not rejected → **fixed** (`7fcfd9b`) with
  parametrized tests.
* **P2 (Correctness)** — the operator-run `_run` measurement path is untested →
  follow-up stash `A2177C87` (extract `page_megapixels` / outcome classification
  as tested helpers).
* **P3** — the `"oom"` outcome label conflates all worker failures; **P3** — peak
  RSS sampling under-measures near the OOM boundary (biases the fit
  conservatively). Both documented in the harness.

Copilot PR review of `bad2b9c` returned 0 findings; the re-review did not
retrigger on the hardening commit `7fcfd9b` (tooling limitation) — the delta was
only input validation + tests + comments.

## Runtime verification

Not applicable beyond the test suite: the `ocr_scale` reader mapping is a
docling-gated one-liner (covered when docling is installed), the worker plumbing
is fully unit-tested with the reader mocked, and the harness fit/recommend logic
is unit-tested. The `--run` measurement path is operator-supervised on a docling
host.

## Rollback

`git revert a423e1a` cleanly restores the prior behavior (`images_scale` fixed at
`2.0`, no `ocr_scale` knob, no calibration harness). No schema, CLI-contract, or
MCP surface regressed (`ocr_scale` is additive and defaulted).

## Next in the arc

1. Operator runs `ocr_memory_calibration.py --run` on a docling host to produce
   the measured coefficients + decision artifact.
2. Follow-up `699FB5DC`: the runtime host-relative cap/scale algorithm that
   replaces the provisional `OCR_MAX_BATCHED_PAGES=8`.
