---
date: 2026-06-06
shipment: 021-S
category: pipeline-architecture
keywords: [triage, selective-ml, splice-back, docline, pdf, fidelity-scoring, hybrid-pipeline]
confidence: high
evidence: src/docline/process/pdf_triage.py, src/docline/process/fidelity_scorer.py, src/docline/process/page_range.py, docs/decisions/2026-06-06-triage-then-repair-pdf-pipeline.md, docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md
---

# Triage-then-repair pattern for selective ML invocation in document pipelines

## Problem

A document-processing pipeline has two extraction engines for the same
input class:

* a **cheap deterministic engine** that produces good-enough output
  for the majority of inputs (e.g. `pypdf` text extraction for paragraph
  prose), and
* an **expensive ML engine** that produces materially better output for
  a minority of inputs (e.g. docling `rt_detr` layout for tables,
  multi-column pages, figure-heavy pages).

Running the expensive engine on every input wastes massive compute on
inputs where it produces no real improvement. Running only the cheap
engine loses fidelity on the inputs where the expensive engine matters.
Picking per-input (manifest-level routing) is too coarse — within a
single long document, most pages benefit from the cheap path and only
a minority benefit from the ML path.

Concrete docline example (2026-06-06): the 3,426-page
`azure-cosmos-db.pdf` runs in ~9.5 hours under the all-docling path
(~10 sec/page CPU `rt_detr` inference × 3,426 pages). Most pages are
clean paragraph prose that `pypdf` extracts perfectly. The ML cost is
justified only on a minority of layout-dense pages.

## Pattern: triage-then-repair

Replace "ML on every input" with a 5-pass orchestrator:

1. **Cheap baseline** — run the deterministic engine across the whole
   input. Preserve per-unit-of-work index alignment (per-page for PDFs,
   per-block for DOCX, etc.) — do not filter empty units, because they
   may be the very ones the ML engine would catch.
2. **Per-unit fidelity scoring** — pure-function deterministic signals
   that detect probable fidelity loss in the cheap output. For
   docline's PDF case: char density, non-ASCII / private-use codepoint
   ratio, long-line-no-whitespace anomalies, multi-column whitespace
   gaps, table-grid character density, embedded-image count, form-field
   annotations. Signals are weighted importance multipliers and stack
   into a single `aggregate` score; weights are externalized to JSON
   so they're tunable without code changes.
3. **Flag coalescing** — convert flagged single units into ranges with
   a context buffer (the ML engine needs neighboring context for
   things like table-continuation detection) and merge adjacent /
   near-adjacent ranges per a gap threshold.
4. **Surgical re-extraction** — splice each range into a temp input
   (e.g. `pypdf.PdfWriter`) and run the expensive engine on JUST
   those splices.
5. **Splice-back** — merge the ML outputs into the cheap baseline at
   the per-unit level; record per-unit engine attribution as
   downstream confidence metadata.

Expected wall-clock impact: `O(cheap × N + expensive × M)` where M is
the flagged-unit count, typically 10–30 % of N for prose-heavy corpora.
Speedup vs. all-ML is `~N / (cheap_cost + M × expensive_cost)` — for
docline's case: ~6–8× on the cosmos PDF.

## Required safety nets

The pattern only works if these three safety nets are wired in from
day one:

### 1. Calibration mode (`--report-only`)

A mode that runs Passes 1 + 2 only, emits a per-unit TSV
`(unit_index, signals..., aggregate, needs_ml, reason)`, and never
invokes the expensive engine. Used to tune signal weights against a
curated corpus where ML output already exists for comparison. **Without
this, signal thresholds are guesses and the speedup is non-deterministic.**

### 2. QA tripwire (`--sample-rate FLOAT`)

A mode that randomly re-runs that fraction of *unflagged* units
through the ML engine and diffs against the cheap output. Increments
a `qa_disagreements` counter recorded in run metadata. Captures
false-negative under-flagging — the scorer said "no ML needed" but
the ML output materially differs. **Disagreement count becomes a
regression-detection metric for production runs.**

### 3. Per-unit fallback on ML failure

When the ML subprocess fails for a flagged range (allocator OOM, segfault,
timeout), fall back to the cheap output for that range and increment
a fallback counter. Batch never aborts on a single failure. **Without
this, one hostile input kills the entire batch run** (the
2026-06-04 RCA failure mode that motivated docline's whole runtime-safety
shipment).

## Where the implementation lives in docline

| Module | Role |
|---|---|
| `src/docline/process/fidelity_scorer.py` | Per-unit signals + `score_page()` combiner + `load_weights()` JSON loader |
| `src/docline/process/page_range.py` | `coalesce_ranges()` — flagged indices → range tuples with buffer + merge gap |
| `src/docline/process/pdf_triage.py` | `process_pdf_triaged()` 5-pass orchestrator + `triage_report_only()` calibration sibling + `QASampling` tripwire dataclass + `dispatch_pdf_mode()` CLI router |
| `src/docline/process/output_contract.py` | `apply_triage_attribution()`, `build_triage_part_payloads()`, `build_triage_manifest_stats()` for per-unit engine attribution + manifest summary |

## Likely future applications in docline

The pattern generalizes beyond PDF + docling:

* **Scanned PDF subset → OCR**: detect image-only pages from pypdf
  metadata; run OCR only on those.
* **Malformed DOCX tables → docling**: detect DOCX paragraphs with
  ASCII table-art and re-extract just those via docling.
* **Stale web content → re-fetch**: detect cached HTML where
  freshness signals (Last-Modified, Cache-Control) indicate staleness;
  re-fetch only the affected pages.

For each: the pattern is the same. The variation is in (a) what signals
score "needs re-extraction" and (b) what expensive engine handles the
re-extraction.

## Pattern non-goals

* **Not** a replacement for the all-ML path when the corpus is
  uniformly layout-dense. If `>50 %` of inputs flag, the orchestration
  overhead exceeds the savings — just run all-ML.
* **Not** a way to skip expensive processing entirely — the safety
  nets exist precisely because the scorer is heuristic and can be
  wrong; the QA tripwire makes wrongness visible.
* **Not** a fit when per-unit indexing is unavailable in the cheap
  engine (e.g., the cheap engine returns a single concatenated string
  with no boundaries). Splice-back requires per-unit alignment.

## Risks that recur with this pattern

* **Scorer threshold drift** across corpora — calibrate per corpus
  class. Externalize weights to a JSON file the scorer loads at
  runtime so weights can be revised without code changes.
* **ML output granularity mismatch** — if the ML engine returns one
  blob per range but downstream needs per-unit content, splice-back
  is lossy. (Docline's current limitation per stash `5CFE4481` —
  flagged for follow-on.)
* **First-time integration cost** — wiring the new orchestrator into
  the production pipeline (CLI flag → request model → execute path) is
  easy to forget. Docline's PR #42 Copilot review caught exactly this
  gap: `--pdf-mode triage` was a silent no-op until the wiring fix in
  commit `603f3cd`. **Compound learning**: an opt-in CLI flag is not
  wired until an end-to-end test verifies a real production code path
  responds to it.
