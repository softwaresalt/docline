---
title: Decision — merge_gap tuning verdict (KEEP-DEFAULT=2)
date: 2026-06-28
kind: decision
status: complete
feature: 036-F
references:
  - docs/closure/039-S-merge-gap-harness.md
  - docs/decisions/2026-06-25-cosmos-docling-routing-investigation.md
  - scripts/study/compare_merge_gap.py
  - scripts/pa3_triage_cosmos.py
  - src/docline/process/page_range.py
  - src/docline/process/pdf_triage.py
  - .elt/output/cosmos-mg0/pa3-summary.json
  - .elt/output/cosmos-mg1/pa3-summary.json
  - .elt/output/cosmos-mg2/pa3-summary.json
---

# Decision — merge_gap tuning verdict

## Verdict

**KEEP-DEFAULT (`merge_gap=2`).** No lower `merge_gap` delivered a wall-clock
win. The production default in `page_range.py` and `pdf_triage.py` is already
`merge_gap=2`, so **no code change is required**. Feature `036-F` closes with
this decision.

## Question

The 2026-06-25 routing investigation found that triage coalescing
(`buffer=1`, `merge_gap=2`) absorbed +981 pages (+54% over the 1818 raw-flagged
pages) into docling ranges — routing ~82% of the corpus to docling. After 037-S
bounded sub-batching amortized docling model-load across a group, the cold-start
penalty that motivated aggressive merging was reduced. The hypothesis: a
**tighter** coalescing (lower `merge_gap`) might cut docling wall-clock without
fidelity loss.

## Method

Operator-run sweep on the remote dev box (task `036.002-T`) over
`merge_gap ∈ {0, 1, 2}` on the cosmos corpus (3426 pages, 1818 flagged),
`--sample-rate 0.01 --qa-random-seed 42`, batched worker at library default
(now `True`). The agent-shippable harness `scripts/study/compare_merge_gap.py`
(task `036.001-T`, shipped in 039-S) ingested the three `pa3-summary.json`
files and emitted the verdict.

## Results

| merge_gap | wall-clock (s) | flagged ranges | docling pages | docling chars | fallback | qa_disagree |
|----------:|---------------:|---------------:|--------------:|--------------:|---------:|------------:|
| **2** (default) | **4189.7** | 86 | 2799 | 3,464,062 | 0 | 0 |
| 1 | 4541.8 | 143 | 2669 | 3,625,807 | 1 | 0 |
| 0 | 5368.7 | 275 | 2742 | 3,986,679 | 0 | 0 |

The hypothesis is **refuted**: lowering `merge_gap` made the run **slower**, not
faster (28% spread, monotonic). Tighter coalescing splits docling work into more,
smaller ranges (275 ranges at `mg0` vs 86 at `mg2`), and per-subprocess overhead
dominates any savings from smaller ranges. The highest `merge_gap` (fewest,
largest ranges) is the fastest. QA disagreements were 0 across all three.

## Caveats (do not affect the verdict)

Two operational issues surfaced during the sweep. Neither changes the
KEEP-DEFAULT conclusion (the wall-clock trend is large and monotonic, and QA
stayed clean), and — after analysis — neither degrades the product outcome.

1. **Docling whole-range render flagged as a "collapse"** (low; stash
   `C0F3B979`). The docling worker returns a single coherent markdown render per
   N-page range (`readers/pdf.py::_read_pdf_docling_pages` exports the whole
   document and returns a one-element list), so `pdf_triage.py` logs an
   "envelope length mismatch" and labels the range `docling-collapsed`. This is
   **not** a quality regression and is **not** a default-flip regression: the
   splice-back and worker envelope are shared by both batched and non-batched
   paths. Per-page fidelity does not affect the downstream outcome — the final
   markdown is `"\n\n".join(pages if p.strip())` (`output_contract.py:264`,
   page boundaries erased) and heading/AST validation runs on the whole joined
   body (`assemble.py:141-142`). A per-page split would *fragment* tables, lists,
   and sections at page boundaries and make AST/heading quality *worse*. The only
   real costs are WARNING log noise and an inaccurate internal routing metric
   (`content_pages`/`docling-collapsed`). The fix direction is to treat the
   whole-range render as expected (silence the warning, relabel attribution) —
   not a per-page split.
2. **Batched-worker OCR OOM crash** (medium; stash `D44A61E4`). The `mg1` run
   hit a hard crash (`exit=3221225477`, `0xC0000005` access violation) in a
   batched group while RapidOCR ran on image pages (`std::bad_alloc`, onnxruntime
   "bad allocation"). That group fell back to heuristic (`fallback=1`). OCR ran
   on a native-text PDF, suggesting 036-S conditional-OCR may not apply in the
   batched path, and per-group memory is unbounded.

The concern that actually gates graphtor-docs ingestion — whether the assembled
output lints clean with a valid heading hierarchy across the heuristic↔docling
seams — is filed separately as a verification spike (stash `6ED7FFD4`).

## Decision and follow-ups

* **Keep `merge_gap=2`.** Close feature `036-F`. No code change.
* Stash items filed for separate handling:
  * `C0F3B979` (low) — silence the docling whole-range "collapse" warning and fix
    the internal attribution metric; **not** a per-page split.
  * `D44A61E4` (medium) — batched-worker OCR OOM; verify 036-S conditional-OCR in
    the batched path and bound per-group memory.
  * `6ED7FFD4` (medium, spike) — verify cosmos output lints clean with a valid
    heading hierarchy across the heuristic↔docling seams (the real ingestion gate).
