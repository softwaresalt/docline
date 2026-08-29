---
title: Spike — H1 header synthesis for graphtor parentage
date: 2026-06-04
shipment: 017-S
feature: 018-F
deliberation: docs/decisions/2026-06-04-deliberation-h1-header-synthesis.md
plan: docs/plans/2026-06-04-h1-header-synthesis-spike.md
status: complete
verdict: hybrid-deterministic-recommended
---

# Spike — H1 header synthesis for graphtor parentage

## TL;DR

A hybrid deterministic synthesis pass — Tier A (`title` promotion when not
a placeholder) → Tier B (first H2 promoted to H1 when the document has no
H1) → Tier C (first paragraph fallback when usable) — rescues **379 of 458
headerless parts (82.8 %)** in the current load-test corpus. The remaining
**79 parts (17.2 %)** are dominated by content-sparse PDFs that need
either docling layout (currently OOM-blocked for the cosmos corpus) or
SLM-based synthesis. **Recommendation: build the deterministic hybrid in
the next shipment; defer the SLM tier behind an explicit opt-in extra
pending a corpus expansion that captures more headerless content.**

## Spike scope and corpus

Corpus: `.elt/output/` from the 2026-06-04 full-load test. 965 markdown
parts across 5 source jobs (Rust book, Bicep AVM, PartTableAndIndexStrat
DOCX, cosmos-db.pdf, root PDFs). The cosmos PDF was processed via the
heuristic engine because docling OOM-crashed during the load test
(captured separately as stash `4B913619`). Script: `scripts/spike_h1_corpus_analysis.py`.

## Measured corpus shape

| Job | Source kind | Parts | sect=null | H2/H3-first | title usable | first-para usable | parse fail |
|---|---|---:|---:|---:|---:|---:|---:|
| `08551bba0aca94b0` | web (Bicep AVM) | 198 | 8 | 0 | 198 | 95 | 0 |
| `4801fedf764b782f` | web (Rust book) | 112 | 0 | 0 | 112 | 112 | 0 |
| `9e16ad54288349a8` | DOCX (PartTableAndIndexStrat) | 46 | 30 | 30 | 0 | 10 | 0 |
| `ab1de93c608fc438` | PDF heuristic (cosmos-db) | 554 | 365 | 1 | 0 | 495 | 0 |
| `dc851847b2d85d5a` | PDF heuristic (root PDFs) | 55 | 55 | 0 | 0 | 2 | 0 |
| **TOTAL** | | **965** | **458** | **31** | **310** | **714** | **0** |

Definitions used by the script:

* **sect=null**: `docline.section_title` is null or missing in part frontmatter
* **H2/H3-first**: the body's first ATX heading has level ≥ 2 (no H1)
* **title usable**: frontmatter `title` is non-empty, ≤ 100 chars, NOT a
  placeholder of shape `"X Part N"` or `"Untitled"`
* **first-para usable**: first non-empty/non-anchor/non-heading line is
  10–120 chars and is not a bare markdown image or URL

## Tier rescue rates (measured, not estimated)

Applied to the **sect=null subset** (458 parts). Each tier's count is the
number of headerless parts where that tier alone produces a usable H1.
The hybrid column is the union: how many distinct headerless parts are
rescued when tiers are tried in order A → B → C.

| Job | sect=null | Tier A (title) | Tier B (H2->H1) | Tier C (1st para) | Hybrid | Unrescued |
|---|---:|---:|---:|---:|---:|---:|
| `08551bba0aca94b0` | 8 | 8 | 0 | 1 | 8 | 0 |
| `4801fedf764b782f` | 0 | 0 | 0 | 0 | 0 | 0 |
| `9e16ad54288349a8` | 30 | 0 | 30 | 4 | 30 | 0 |
| `ab1de93c608fc438` | 365 | 0 | 1 | 339 | 339 | 26 |
| `dc851847b2d85d5a` | 55 | 0 | 0 | 2 | 2 | 53 |
| **TOTAL** | **458** | **8** | **31** | **346** | **379** | **79** |

Headline numbers:

* **Hybrid rescues 379 / 458 = 82.8 %** of all headerless parts.
* **Unrescued: 79 / 458 = 17.2 %** — concentrated in root PDFs (53 / 55)
  and a residue of cosmos parts (26).
* Tier C alone is the workhorse (346 rescues); Tiers A and B fill the
  PDF-failure and DOCX-H2-first cases respectively.

## Approach comparison

| Approach | Rescue rate | Determinism | Runtime cost | New dependency | Notes |
|---|---:|---|---|---|---|
| A — Title promotion | 1.7 % alone, 8 / 458 | Deterministic | O(1) per part | None | Useful for web pages with real `<title>` tags; useless for PDF/DOCX where `title` is auto-generated `"X Part N"` placeholder. |
| B — First H2 → H1 | 6.8 % alone, 31 / 458 | Deterministic | O(parts) scan | None | Targets the DOCX H2/H3-first case (and 1 PDF case). Removes the need for `--allow-heading-disorder` for documents that have any heading at all. |
| C — First paragraph fallback | 75.5 % alone, 346 / 458 | Deterministic with filters | O(parts) scan | None | Broad PDF rescue. Quality is variable — depends on the first paragraph being a semantic intro line, not a footnote or page header. |
| D — SLM (e.g. Phi-3.5-mini CPU) | unmeasured | Non-deterministic | Seconds per part on CPU; model load is several hundred MB | Yes (SLM weights + transformers entry point shared with docling) | Targets the 79 unrescued parts. Would also improve quality of Tier C rescues by replacing "first paragraph" heuristic with a generated summary. |
| **E — Hybrid A → B → C** | **82.8 %, 379 / 458** | **Deterministic** | **O(parts) scan** | **None** | **Recommended.** Each tier targets a distinct pathology; their union is much stronger than any tier in isolation. |
| F — Hybrid A → B → C → D | likely > 95 % | Hybrid | Slower (SLM only invoked for unrescued residue) | Yes (SLM) | Future option, gated behind opt-in extra `docline[h1-slm]`. Not in scope of the immediate follow-on shipment. |

## Where the unrescued parts live

The 79 unrescued parts cluster in the heuristic-engine PDF outputs:

* **53 of 55 root-PDF parts** (`dc851847b2d85d5a`). Root PDFs are
  `AzureFabric.ebook.pdf` (5 parts) and `performance-tuning-with-dmvs.pdf`
  (50 parts). All have `title` set to placeholder `"<name> Part N"`,
  almost no body H2/H3, and the first paragraph fails the
  10–120-character filter (probably full-page paragraphs without clean
  newline breaks).
* **26 of 365 cosmos headerless parts** (`ab1de93c608fc438`). Same
  pathology as root PDFs but a smaller fraction because cosmos has
  more text overall.

Two follow-up paths for the unrescued residue, in priority order:

1. **Re-run with docling on un-OOM-able chunks** (depends on stash
   `F64683BC` PDF splitter + `D885CE79` batch processor). Docling would
   extract real headings the heuristic engine misses, eliminating most
   of the residue without an SLM dependency.
2. **SLM tier D** (deferred). Only become attractive once (1) has been
   tried and the residue is still meaningful.

## Recommendation

**Build the deterministic hybrid (Tier A → B → C) as the next shipment.**

* Module: `src/docline/process/header_synthesis.py` (new), invoked at
  assemble time after segmentation but before frontmatter rendering.
* API sketch: `synthesize_section_title(part_body: str, fm: dict) -> str | None`
  — returns the synthesized title or `None` if nothing rescues; the
  caller writes the result into `docline.section_title` and, when
  appropriate, prepends a synthetic `# {title}` line to the body so
  downstream chunk-parentage checks pass.
* Provenance: tag synthesized titles in frontmatter with
  `docline.section_title_synthesized: true` (and which tier produced
  them) so graphtor and downstream consumers can distinguish synthetic
  from author-supplied headings.
* Backwards compatibility: when `docline.section_title` is already
  non-null, synthesis is a no-op.
* Replaces `--allow-heading-disorder`: after this shipment, the strict
  parentage check in `assemble.py` no longer needs the escape-hatch
  flag for documents that have at least one heading or one usable first
  paragraph. The flag can stay as a fallback for the residual ~8 % of
  pathological cases.
* Tests: parameterized RED tests covering each tier in isolation, the
  hybrid escalation, the no-op-when-already-titled path, the
  synthetic-flag emission, and integration through `assemble.py`.

**Defer SLM tier D.** It targets a real ~17 % residue, but introducing
torch/transformers SLM weights as a mandatory dependency for ingestion
contradicts Principle VI (single responsibility / minimize dependencies).
Two cleaner paths exist for the residue: (a) the PDF splitter +
batch-processor shipments will let docling extract real headings the
heuristic engine misses, and (b) if SLM is eventually needed, gate it
behind an opt-in `docline[h1-slm]` extra so contributors who don't need
it don't carry the weights.

## Risks (called out, with mitigations)

| Risk | Severity | Mitigation |
|---|---|---|
| 5-source corpus too small for confidence | Medium | Re-run the analysis script on a wider corpus when more sources are ingested. Decision artifact's numbers are reproducible from `scripts/spike_h1_corpus_analysis.py`. |
| Tier C produces low-quality H1s (footnote, page-header lines pass the filter) | Medium | Add quality post-filters: reject paragraphs that match Roman numerals only, page-number patterns, or are < 3 words. Add a synthesis-quality regression test set during the follow-on shipment. |
| Synthesized H1s confuse graphtor's anchor extraction | Low | The `docline.section_title_synthesized` flag is explicit; graphtor can treat synthetic anchors as soft hints rather than authoritative. |
| `--allow-heading-disorder` removal breaks contributor muscle memory | Low | Keep the flag as a no-op for one release after synthesis lands; emit deprecation warning. |
| Cosmos heuristic output has 26 residue parts that look like real failures | Low | The residue overlaps with the broader docling-fallback problem (stash `4B913619`). Solving that will likely shrink the residue without touching the synthesizer. |

## Spike budget consumption

* Plan target: ~2.5 h. Hard ceiling: 4 h.
* Actual: ~45 min for the script, ~30 min for this artifact, plus follow-on
  stub and closure. **Well within budget.**

## Follow-on

See `docs/plans/2026-06-04-h1-synthesis-implementation-stub.md` for the
plan stub the next Stage cycle picks up.

## References

* Stash: `CD9F1913` (this spike's input)
* Script: `scripts/spike_h1_corpus_analysis.py`
* Corpus: `.elt/output/` from 2026-06-04 load test (965 parts)
* Related stash: `4B913619` (docling OOM threshold), `F64683BC`
  (PDF splitter), `D885CE79` (batch + stitching)
* Closure context: `docs/closure/012-S-heading-aware-segmentation.md`,
  `docs/closure/013-S-referentiality.md`, `docs/closure/015-S-post-g3-hygiene.md`
* `src/docline/process/assemble.py` (current strict parentage check)
* `src/docline/process/segment.py` (heading-aware segmenter)
