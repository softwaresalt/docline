---
title: Decision — Triage-then-repair hybrid PDF pipeline
date: 2026-06-06
kind: deliberation
status: decided
stash: 1301B14E
related_rca: docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md
related_shipments: 018-S (runtime safety primitives), 019-S (chunking + batch)
poc_script: docs/scratch/2026-06-06-fidelity-scorer-poc.py
---

# Decision — Triage-then-repair hybrid PDF pipeline

## TL;DR

The current `process_pdf_in_chunks` path runs docling rt_detr layout
inference on every page of every PDF. On the 2026-06-04 RCA host class
(i7-4700MQ, 32 GB RAM, no usable GPU) per-page CPU inference costs
~10 sec/page. Measured wall-clock on **`azure-cosmos-db.pdf` (3,426
pages, 47 chunks)** is **~12 min/chunk and rising**, projecting **~9.5
hours total** for a single document. The all-docling path is the wrong
default for long technical reference PDFs where most pages are clean
prose that pypdf nails perfectly.

**Decision**: introduce a `triage` PDF mode (opt-in via `--pdf-mode
triage`) that runs the heuristic engine across the whole document for a
fast baseline, scores each page with deterministic fidelity signals,
coalesces flagged pages into ranges, splices just those page ranges
into temp PDFs, runs the existing `docling_worker` subprocess on each
splice, and merges per-page outputs into a final list. Default mode
behavior is unchanged; the existing `auto` / `docling` / `heuristic`
modes remain.

**Estimated impact on cosmos**: ~70–90 min total (Pass 1 heuristic ~5
min + Pass 4 docling on ~10–15 % of pages ~60–85 min) versus current
~9.5 h. **~6–8× speedup at equivalent fidelity on pages that need it.**

## Problem frame

| Symptom | Evidence |
|---|---|
| Single-document runtime > 9 hours | 2026-06-06 cosmos load test: 12 chunks completed in 2 h 25 m, 35 remaining at ~12 min/chunk avg |
| Per-chunk time trending upward | Chunks 11–12 took 16.5 m and 19 m vs 8–11 m baseline |
| Heuristic engine already produces usable output for most pages | 017-S spike found pypdf text extraction recovered usable content from the cosmos corpus when docling OOM-crashed |
| Docling output value is concentrated on layout-dense pages | Tables, figures, multi-column layouts — not paragraph prose |

The bottleneck is **CPU rt_detr inference**, not the existing orchestration
overhead (subprocess startup, reclaim pauses, throttling). Subprocess
startup is ~1.4 % of per-chunk cost; the remaining 98 % is per-page
neural network forward passes on rasterized page images. Reducing the
number of pages docling sees is the only lever that meaningfully
changes wall-clock without new hardware.

## Options considered

### Option A — Status quo: all-docling on every page

* **Pro**: Highest fidelity floor for every page; predictable
  per-engine output.
* **Pro**: Already shipped via 018-S / 019-S / 020-S.
* **Con**: ~9.5 h wall-clock for cosmos; unusable for iterative
  development and load testing.
* **Con**: Forces CPU rt_detr cost on pages where pypdf would produce
  equivalent or identical Markdown.
* **Verdict**: Keep as default behavior; reject as the only path.

### Option B — Configurable per-PDF engine routing

Operator marks specific PDFs as `heuristic-only` or `docling-only` via
manifest metadata; pipeline routes accordingly.

* **Pro**: Maximum operator control.
* **Con**: Requires per-PDF curation knowledge the operator does not
  yet have — the operator cannot predict which pages of a 3,426-page
  reference document have layout-sensitive content.
* **Con**: Single-engine-per-PDF still wastes docling on most pages of
  a doc that has *some* layout-dense sections.
* **Verdict**: Reject. Coarser than the actual page-level distribution.

### Option C — Triage-then-repair (chosen)

Run heuristic on the whole PDF, score each page with deterministic
signals to detect probable fidelity loss, route only flagged page
ranges through docling, merge into a single per-page output list.

* **Pro**: Page-granular precision — pays docling cost only where
  layout-dense content is detected.
* **Pro**: Cheap-to-compute signals (char density, non-ASCII ratio,
  multi-column gap pattern, pypdf image/form metadata) are deterministic,
  pure-Python, and microsecond-per-page.
* **Pro**: Reuses all existing infrastructure — `read_pdf_pages`,
  `split_pdf`, `docling_worker`, `process_pdf_in_chunks`.
* **Pro**: Per-page engine attribution gives downstream consumers a
  confidence signal.
* **Con**: Adds a new failure mode — false-negative undetected mangling
  (heuristic looks fine but is actually wrong). Mitigated by an
  optional `--sample-rate` QA tripwire and a `--report-only` validation
  mode for empirical threshold tuning.
* **Con**: Adds a new module trio (`fidelity_scorer.py`, `page_range.py`,
  `pdf_triage.py`) — implementation complexity.
* **Verdict**: **Selected.** The dominant runtime cost is justified
  only on layout-dense pages; the scorer's job is to identify those
  pages cheaply.

### Option D — Get a CUDA GPU

* **Pro**: 10–50× speedup on docling rt_detr inference; no design
  complexity.
* **Con**: Requires Maxwell+ hardware (~$500+ used GPU). Out of scope
  for software fix.
* **Verdict**: Not mutually exclusive with C. Document as long-term
  fix; ship C now.

### Option E — Use docling's bundled OCR/layout settings to skip pages

* **Pro**: Stays inside docling configuration surface.
* **Con**: Docling does not expose page-level skip semantics for layout
  inference. The `PdfPipelineOptions` knobs operate at the document
  level.
* **Verdict**: Reject. Wrong tool surface for the requirement.

## Chosen direction

Build **Option C** as a new pipeline mode, opt-in via `--pdf-mode triage`.
Default behavior (`--pdf-mode auto`, current) is unchanged. The new
mode is a peer of the existing `auto`/`heuristic`/`docling` selection.

## Constitution check

| Principle | Compliance |
|---|---|
| I — Safety-first Python | All new code typed, exceptions custom-typed via `DoclineError` lineage where applicable; no bare except |
| II — Test-first | RED tests for every new module before implementation; POC stays in `docs/scratch/` until promoted |
| III — Workspace isolation | All new modules under `src/docline/process/`; no out-of-workspace IO |
| IV — CLI containment | All page-splice temp PDFs go under `output_dir` or `cache_dir`, never outside the cwd tree |
| V — Structured observability | Per-page engine attribution recorded in output contract; TSV emission for `--report-only` mode |
| VI — Single responsibility | No new dependencies; uses pypdf (already required) and the existing docling extra |
| X — Context efficiency | Scorer returns a frozen `PageScore` dataclass; coalescer returns a list of tuples — small structured queries, not raw page text |

## Open questions

1. **Signal weight calibration** — the POC `_SIGNAL_WEIGHTS` constants
   are educated guesses. Resolution: implement `--report-only` first,
   run against the 12 completed cosmos chunks, tune empirically before
   locking weights. Output of the calibration becomes a small JSON
   file the scorer loads at runtime so weights can be revised without
   code changes.
2. **Buffer size** — POC uses `buffer=1` (±1 context page around each
   flagged page). May need to increase to 2 for table continuation
   cases. Tunable via signature parameter; default decided after
   calibration.
3. **Coalescer merge threshold** — POC uses `merge_gap=2`. Same as
   above: defer to calibration.
4. **Engine attribution placement in output contract** — does the
   per-page engine annotation belong in the part-level frontmatter,
   the manifest, or both? Resolution: part frontmatter (where
   downstream graphtor reads it) + manifest summary stats.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| False-negative undetected mangling | `--sample-rate FLOAT` QA tripwire re-runs that fraction of "clean" (unflagged) pages through docling and diffs the output; disagreement count emitted in summary as a regression metric |
| False-positive over-flagging slows the run unnecessarily | Low harm; only wastes ML cycles, never produces wrong output |
| Scorer thresholds drift over time as corpora change | Calibration script regenerates weights from a curated validation corpus; weights live in a JSON file outside the code |
| Reading-order artifacts at splice boundaries | Both engines emit page-separated markdown; splice boundary is a paragraph break — no special reconciliation needed unless artifacts observed |
| The `--sample-rate` tripwire could itself become slow on long docs | Cap sampled pages at e.g. 50 per run; sampling is opt-in, not default |

## Acceptance criteria

This decision is satisfied when:

1. New CLI flag `--pdf-mode triage` is available and documented.
2. Triage mode produces a final stitched markdown indistinguishable
   from the all-docling mode on the pages the scorer flagged, and from
   the all-heuristic mode on pages it did not.
3. Per-page engine attribution is recorded in the output contract
   (part frontmatter field or equivalent).
4. `--report-only` mode produces a per-page TSV
   `(page_index, signals..., aggregate, needs_docling, reason)` without
   running docling.
5. `--sample-rate FLOAT` mode re-runs that fraction of clean pages
   through docling and emits a tripwire-disagreement count.
6. Empirical wall-clock on cosmos PDF is ≤ 25 % of the all-docling
   baseline (≤ ~2.4 h vs current ~9.5 h).
7. All existing pipeline modes (`auto`, `heuristic`, `docling`) work
   unchanged — opt-in surface only.

## Notes

* POC scorer with 7 signal functions and a coalescer lives at
  `docs/scratch/2026-06-06-fidelity-scorer-poc.py` and discriminates
  correctly on synthetic samples (clean prose, garbled font, table
  artifacts, column gaps, glyph runs, near-blank pages).
* The promotion path per Constitution II is: Stage harvest → harness-architect
  produces failing `tests/process/test_fidelity_scorer.py` +
  `test_pdf_triage.py` → build-feature lifts POC into
  `src/docline/process/`.
