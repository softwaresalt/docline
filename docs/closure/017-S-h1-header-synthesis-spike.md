---
shipment: 017-S
title: "Closure record — H1 header synthesis spike"
status: verified
merge_sha: TBD
merged_pr: TBD
---

# Closure — 017-S: H1 header synthesis spike

## Outcome

A time-boxed spike (~2.5 h target, ~1.5 h actual) characterized the
headerless-part population in the 2026-06-04 load test corpus
(`.elt/output/`), evaluated four deterministic and one SLM-based
synthesis approach, and produced a measured recommendation.

**Headline numbers** (965 parts across 5 source jobs):

* 458 parts (47.5 %) have `docline.section_title == null`
* A hybrid deterministic synthesizer (Tier A title-promotion → Tier B
  first-H2-to-H1 → Tier C first-paragraph fallback) rescues **379 / 458
  = 82.8 %** of those headerless parts
* 79 parts (17.2 %) remain unrescued by deterministic tiers, concentrated
  in heuristic-engine PDF output (root PDFs 53/55, cosmos 26/365)

## Recommendation

Build the deterministic hybrid as the next shipment. Defer the SLM tier
behind an explicit opt-in extra (`docline[h1-slm]`) — the residue is
more likely to shrink once stash `4B913619` (docling threshold spike) and
`F64683BC` (PDF splitter) ship and let docling extract real headings
from PDFs that currently OOM.

## Tasks

| Task | Title | Outcome |
|---|---|---|
| 018.001-T | Build corpus analysis script and run against `.elt/output/` | `scripts/spike_h1_corpus_analysis.py`; precise rescue intersection rates |
| 018.002-T | Author decision artifact with measured tier rescue rates | `docs/decisions/2026-06-04-spike-h1-header-synthesis.md` |
| 018.003-T | Author follow-on shipment plan stub | `docs/plans/2026-06-04-h1-synthesis-implementation-stub.md` |
| 018.004-T | Author closure document for 017-S | This file |

## Quality Gate Evidence

This shipment is documentation + a throwaway analysis script under
`scripts/`. No production code change, no test change.

### Local (Windows, pre-PR)

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | All files clean |
| `pyright src/` | Unchanged (no `src/` change) |
| `pytest` | Unchanged (no test change) |
| `python -m build` | Unchanged (no packaging change) |

### CI

To be populated after the PR runs through the cross-OS matrix.

## Spike Budget

* Target: ~2.5 hours of agent work
* Hard ceiling: 4 hours
* Actual: ~1.5 hours (corpus script + analysis ~45 min, decision
  artifact ~30 min, plan stub ~15 min, closure ~10 min)

**Inside budget by ~40 %.**

## Handoff to next Stage cycle

The follow-on implementation work is captured at
`docs/plans/2026-06-04-h1-synthesis-implementation-stub.md`. The next
Stage cycle should hydrate that stub, write a complete implementation
plan, route through plan-review, and harvest into a new feature +
shipment. The stub already lists module placement, API sketch,
integration point, RED-test scaffold, hard constraints, and estimated
task decomposition (~5 hours total).

## Stash impact

* Harvested: `CD9F1913` (archived as part of staging 017-S)
* Adjacent (still open, will benefit from the spike's findings):
  * `4B913619` (docling OOM threshold spike) — likely reduces the
    unrescued residue without touching the synthesizer
  * `F64683BC` (PDF splitter) — same
  * `D885CE79` (PDF batch + stitching) — same
* **New, created during spike RCA analysis** (2026-06-05, riding along
  on this PR for context):
  * `1D945AB5` — adaptive resource probe (RAM / pagefile / GPU
    detection) that becomes the single source of truth for throttling
  * `15ADD215` — broaden `read_pdf_pages` auto-fallback exception net
    (catches `RuntimeError` / `MemoryError` / `OSError`)
  * `C1EB2C6A` — cap docling/PyTorch thread fan-out via probe-derived
    `OMP_NUM_THREADS`
  * `A2A78AEE` — `scripts/load_test.py` harness with subprocess-per-PDF
    isolation, probe-driven serialization, and TSV instrumentation

## RCA bundle riding along

This PR also ships the root-cause analysis for the 2026-06-04 hard
reboot that occurred during the spike's load-test corpus generation
(the corpus this spike then analyzed). The RCA documents:

* Why the system OOM'd (docling rt_detr layout model on the
  109 MB cosmos PDF triggered a Windows paging spiral; verified via
  the `report.20260604.223541.24064.0.001.json` V8 crash dump)
* Why a "local model for synthetic header generation" was *not* the
  cause (project-wide grep confirms no torch / transformers / SLM
  code anywhere in `src/` or `scripts/`)
* A 7-remediation design pivot from "detect OOM and fall back" to
  "split and throttle proactively so OOM cannot happen"
* A 2026-06-05 GPU evaluation addendum documenting why the host's
  GTX 770M (sm_30, 3 GB VRAM) cannot accelerate docling

RCA path: `docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md`.
The RCA is informational — it does not change `src/` and does not
gate this spike's merge. Shipment A/B/C in the RCA's open-items table
captures the implementation work for the next Stage cycle.

## References

* Decision artifact: `docs/decisions/2026-06-04-spike-h1-header-synthesis.md`
* Plan: `docs/plans/2026-06-04-h1-header-synthesis-spike.md`
* Plan-review: `docs/decisions/2026-06-04-plan-review-h1-header-synthesis-spike.md`
* Follow-on stub: `docs/plans/2026-06-04-h1-synthesis-implementation-stub.md`
* Deliberation: `docs/decisions/2026-06-04-deliberation-h1-header-synthesis.md`
* Spike script: `scripts/spike_h1_corpus_analysis.py`
* Corpus: `.elt/output/` (2026-06-04 load test, 965 parts)
