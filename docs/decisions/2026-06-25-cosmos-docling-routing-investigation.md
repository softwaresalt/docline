---
title: Investigation — cosmos 82% docling-routing breakdown
date: 2026-06-25
kind: investigation
status: complete
references:
  - docs/closure/037-S-runtime-verification-cosmos.md
  - .elt/output/cosmos-batched/pa3-engine-attribution.tsv
  - .elt/output/cosmos-batched/pa3-summary.json
  - src/docline/process/fidelity_scorer.py
  - src/docline/process/page_range.py
  - src/docline/process/pdf_triage.py
---

# Investigation — why 82% of cosmos pages "route to docling"

The 037-S runtime verification reported `engine_distribution = docling-collapsed
2799 / heuristic 627` — 82% of the 3,426-page corpus apparently routed to
docling. This investigation decomposes that number.

## Finding 1 — "82% docling" is largely an attribution artifact

The 2,799 "docling" pages are **not** 2,799 richly-extracted pages. Per the
per-page TSV:

- **2,713 of 2,799 (96.9%) docling page-slots hold 0 characters.**
- Only **86 docling pages hold content** — exactly one per flagged range.
- **86 / 86 ranges** have all their content on the range's **first page**.

This is the known `docling-collapsed` behavior (030-F T2): a multi-page splice
returns one concatenated markdown blob, which splice-back assigns to the range's
first page; the remaining pages become empty `docling-collapsed` placeholders.
**No content is lost** — each range's blob contains everything — but the
per-page `engine_distribution` metric counts the empty placeholders as "docling
pages," overstating per-page coverage. The honest framing: **86 ranges → 86
concatenated docling blobs**, covering 2,799 source pages.

## Finding 2 — routing decomposition

| Stage | Pages | % of corpus |
|---|---:|---:|
| Scorer raw flags | 1,818 | 53% |
| After coalescing (buffer=1, merge_gap=2) | 2,799 | 82% |
| **Coalescing expansion** | **+981** | **+29pp** |
| Stayed heuristic | 627 | 18% |

Coalescing **absorbed 981 pages (+54% over the raw flag count)** — gaps of ≤2
heuristic pages between flagged ranges get merged into docling ranges. This is
the single largest "over-routing" contributor.

## Finding 3 — content reality is appropriate

- docling produced **3.44M chars** across 86 ranges; heuristic **0.99M chars**
  across 627 pages. docling handles ~78% of character content.
- 17 ranges ≥50 pages cover 1,888 pages (the table/layout-heavy technical
  sections that genuinely benefit from docling).
- The QA tripwire sampled 6 heuristic pages: **0 disagreements**, all ≥0.9
  similarity to docling — the pages kept on heuristic are correctly kept there.

For a table- and layout-heavy technical corpus like the Cosmos DB docs, heavy
docling routing is expected and largely correct.

## Tuning levers (in order of leverage)

1. **`merge_gap`** — the big one. `merge_gap=2` absorbed 981 pages. Lowering to
   1 or 0 keeps more in-gap pages on heuristic, cutting docling wall-clock —
   *if* those gap pages are heuristic-quality. 037-S bounded sub-batching now
   amortizes docling model-load across a group, so the cold-start penalty that
   motivated aggressive merging is smaller; more/smaller ranges are cheaper than
   before. **Recommended: a controlled merge_gap experiment (0/1/2) measuring
   wall-clock + QA disagreement, to quantify whether tighter coalescing saves
   docling time without fidelity loss.**
2. **Scorer threshold** — the 53% raw flag rate. A deeper lever requiring
   pre-triage score-distribution analysis; defer unless merge_gap tuning is
   insufficient.
3. **`buffer`** — minor (±1 page of context per flagged page).

## Separate (known) issue surfaced

The `docling-collapsed` attribution makes the per-page metrics misleading. Two
independent follow-ups:

- **Metric clarity:** report range-level docling stats (86 ranges) rather than
  letting collapsed placeholders inflate the per-page "docling" count, so future
  runtime-verification numbers are not misread as "82% richly extracted."
- **Per-page fidelity restoration** (existing follow-up, stash `D771B78E`):
  `page_range=(i,i)` looping inside the batched worker would give true per-page
  attribution, but the 032.001-T probe measured 2.22× overhead — deferred.

## Conclusion

The "82% docling" figure is not a red flag: ~most of it is the collapsed-
attribution artifact plus appropriate routing of a table-heavy corpus. The one
concrete optimization worth pursuing is **`merge_gap` tuning**, now cheaper to
exploit thanks to 037-S. The misleading per-page metric is worth a small
reporting fix.
