---
title: Deliberation — Spike H1 header synthesis for graphtor parentage
date: 2026-06-04
stash: CD9F1913
shipment: 017-S
status: framed
---

# Deliberation — H1 header synthesis for graphtor parentage

## Problem frame

The graphtor-docs ingestion contract requires every chunk to have a parent
heading anchor. Two real failure modes appeared in the 2026-06-04 load test:

1. **DOCX H2/H3 before H1**: `PartTableAndIndexStrat.docx` opens with H2/H3
   structure. The strict chunk-boundary parentage check in
   `process/assemble.py` rejects every part with
   `H2 heading 'X' appeared before any H1` and refuses to emit the part.
   Today the only escape hatch is the runtime flag
   `--allow-heading-disorder`, which silences the warning but does not
   produce a valid H1 — every "headerless" part comes out with
   `section_title: null`.
2. **PDF chunk-internal H1 gaps**: the cosmos-db.pdf heuristic output has
   554 parts; many parts have `section_title: null` because the
   heading-aware segmenter (012-S) only opens a new part on H1/H2 boundaries
   and parts between boundaries inherit no heading.

Both cases leave graphtor without a parent anchor for those chunks.

## Why this is a spike, not a direct build

Multiple plausible approaches exist with different trade-offs across
determinism, runtime cost, quality, and dependency surface. The spike's job
is to surface those trade-offs with measured corpus data so a follow-on
shipment can build the right thing the first time.

## Options under consideration

| Option | Determinism | Quality | Cost | New dep |
|---|---|---|---|---|
| A. Promote frontmatter `title` to H1 when missing | high | medium | trivial | none |
| B. Promote first H2 → H1 when document has no H1 | high | high (when applicable) | trivial | none |
| C. First non-empty paragraph as H1 fallback | high | low (often garbage) | trivial | none |
| D. SLM summarization → H1 (Phi-3.5-mini / gemma-2-2b, CPU) | low (non-deterministic) | high | high (model load, per-part inference) | docling-already-loads-torch but adds an SLM weight |
| E. Hybrid: A → B → C → D escalation, only invoke D when A–C all fail | high (for A–C path) | high overall | low average | optional SLM |

The likely recommendation is E (hybrid), but the spike needs to validate by
counting how many parts each tier rescues on the load-test corpus.

## Out of scope for this shipment

* Implementing any synthesizer.
* Wiring synthesis into the production pipeline.
* Adding any new runtime dependency.

The spike produces a **decision artifact** and a **follow-on shipment plan
stub**. A subsequent shipment will implement whichever tier(s) the spike
recommends.

## Risks

* The spike could conclude "SLM is the only acceptable option" — that would
  introduce a heavier dependency and the operator should approve before the
  follow-on shipment plans for it.
* The corpus could be too small to be representative; the spike must call
  this out and recommend a corpus-expansion follow-up if so.

## Chosen direction

Run a tightly-bounded spike that:

1. Quantifies the headerless-part population on the existing load-test
   corpus at `.elt/output/` (no new fetch).
2. Estimates each deterministic tier's rescue rate.
3. Recommends a deterministic-first hybrid (likely option E) **without
   committing** to SLM until the operator approves the dependency.
4. Outputs a follow-on shipment plan stub the next Stage cycle can pick up.

## References

* Stash `CD9F1913` (this spike's input)
* `docs/closure/012-S-heading-aware-segmentation.md`
* `docs/closure/013-S-referentiality.md`
* `docs/closure/015-S-post-g3-hygiene.md`
* `.elt/output/` (2026-06-04 load test artifacts, 965 parts across 5 sources)
* `src/docline/process/assemble.py` (current parentage enforcement)
* `src/docline/process/segment.py` (heading-aware segmenter)
