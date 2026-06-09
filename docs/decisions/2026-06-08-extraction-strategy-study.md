---
title: Extraction strategy study — markitdown vs docling for graph/embedding/LLM use cases
date: 2026-06-08
status: decided
related_closures:
  - docs/closure/021-S-triage-then-repair.md
  - docs/closure/022-S-pa4-closure.md
related_stashes:
  - 79F23BDE
  - 0AF15C3D
study_artifacts:
  - scripts/study/build_comparison_dataset.py
  - scripts/study/evaluate_markdown.py
  - scripts/study/analyze_study.py
  - .elt/output/cosmos-triage-022/study/results/findings.md
  - .elt/output/cosmos-triage-022/study/results/findings.json
  - .elt/output/cosmos-triage-022/study/results/per-range-metrics.tsv
---

## Question

Given docline's downstream consumers are **graph databases, vector
embedding stores, and LLM context windows**, which PDF-to-markdown
extraction strategy is most effective and most efficient: pypdf,
markitdown, docling, or a hybrid? The 022-S design assumption was
"markitdown as cheap baseline + docling as targeted repair" — does
that assumption hold up under AST-aware quality measurement?

## Constraints

* Output must be AST-parseable (markdown-it-py compatible)
* "Fidelity" is operationally defined as: graphability + embedding
  chunk friendliness + LLM semantic density — NOT raw text recall
* Cosmos PA3+PA4 evidence already exists (84 docling splices + 3,426
  per-page baselines under `.elt/output/cosmos-triage-022/`)
* No fresh full-document docling runs (RCA-documented OOM risk when
  docling rt_detr runs co-hosted with the agent process)

## Method

Stratified sample of 15 flagged ranges from the cosmos PA3+PA4 run
(5 small ≤5 pages, 5 medium 6-30 pages, 5 large >30 pages), totaling
**577 pages** of evidence. For each range:

1. Reuse existing `splice-AAAA-BBBB.md` (docling output, untouched)
2. Regenerate per-page markitdown from `baseline-NNNN.pdf` files
3. Parse both with markdown-it-py (commonmark + tables enabled)
4. Compute 25 AST-aware metrics per output

Decision rule for per-range classification:

* **docling clearly wins** if ANY of: ≥5 extra table cells; ≥1.0/1000
  structural density gain; ≥30 % more total chars
* **markitdown wins** if ≥2 fewer table cells, OR equal-or-more
  headings AND ≤95 % char ratio (shorter equivalent)
* **tied** otherwise

## Headline result

| Bucket | Count | % |
|---|---|---|
| docling clearly wins | **14 / 15** | 93 % |
| tied | 0 | 0 % |
| markitdown wins | 1 | 7 % |

Across all 577 sample pages:

| Metric | markitdown (mean) | docling (mean) | docling / markitdown |
|---|---|---|---|
| chars | 50,700 | 41,358 | 0.82 (docling is **leaner**) |
| **heading count** | 0.93 | 66.2 | **70.95×** |
| **section count** | 1.8 | 66.8 | **37.11×** |
| **table count** | 0.53 | 3.47 | **6.5×** |
| table cell count | 39.1 | 64.8 | 1.66× |
| list item count | 29.3 | 94.9 | 3.24× |
| code block count | 3.33 | 15.7 | 4.72× |
| **structural density per 1k chars** | 2.62 | 6.80 | **2.59×** |
| median section length (chars) | 29,161 | **571** | 0.02× |
| type-token ratio | 0.249 | 0.252 | ~1.0 |

## Interpretation against the stated use cases

### Vector embeddings (semantic search)

Most embedding models (OpenAI ada-002, Cohere embed-multilingual, all
sentence-transformers) target chunks of **256-512 tokens (~1k-2k
chars)** for best retrieval quality. Chunks larger than that get
truncated or averaged, losing precision.

* markitdown median section: **29,161 chars** — must be lossily
  re-chunked by downstream code (loses heading-anchored boundaries)
* docling median section: **571 chars** — **already near-optimal**
  for direct ingestion; each heading-anchored section becomes one
  semantically coherent embedding

**Docling wins decisively.**

### Graph databases (linkable nodes + edges)

Graph extraction relies on identifying named entities, hierarchical
relationships, and cross-references. Markdown headings, list
hierarchies, tables, and code-block identifiers are all node/edge
candidates.

* markitdown produces **0.93 headings per range average** — no
  hierarchy to graph
* docling produces **66.2 headings per range** with multi-level
  nesting — rich hierarchy
* docling extracts **6.5× more tables** and **3.2× more list items**
  — far more graphable structure

**Docling wins decisively.**

### LLM semantic density (per-token information)

LLM context windows are expensive (cost ∝ token count). Output that
delivers more semantic information per token is more efficient.

* docling produces **18 % fewer chars overall** while delivering
  **2.6× more structural elements per 1k chars**
* docling output IS more semantically dense by both axes (less
  redundant boilerplate, more navigable structure)

**Docling wins.**

### Where markitdown might still be preferred

Only 1 of 15 ranges (3110-3112, a 3-page slice) classified as
markitdown-wins, and even there docling gave +15 headings. No range
showed markitdown producing genuinely better output by these AST
metrics. The remaining markitdown advantages are:

* **Speed**: ~1-2 s/page vs docling's ~15-30 s/page
* **No subprocess overhead**: pure in-process
* **Deterministic**: pdfminer.six produces same output run-to-run

## Why the earlier "over-fire" diagnosis was wrong

The 022-S PA3+PA4 closure assessment treated 53 % flag rate as a
scorer regression because **char-count delta was small on many flagged
ranges**. The motivating example — range 1487-1490 — looked like a
1 % char delta (5,498 vs 5,564 chars), suggesting wasted docling work.

This study re-examined that exact range:

| Metric | markitdown | docling | ratio |
|---|---|---|---|
| chars | 5,370 | 5,564 | 1.04 |
| heading_count | 0 | 7 | **∞** |
| section_count | 1 | 8 | **8×** |
| median section chars | 5,370 | 659 | 0.12 |
| structural_density_per_1k | 0.186 | 3.415 | **18×** |

**The scorer was right.** Char count was the wrong measurement lens.
Docling produced 8 properly-sized embedding chunks where markitdown
produced 1 unstructured 5.4k-char blob. For all three goal use cases
(embeddings, graphs, LLMs) docling's output is dramatically better
despite identical char count.

## Verdict on stashes 79F23BDE and 0AF15C3D

* **`79F23BDE` (interim mitigation — revert default to pypdf, lower
  layout signal weight)**: **REJECT.** It would optimize for the
  wrong metric (raw chars / wall-clock) and regress on the actual
  downstream-effectiveness metrics that matter.
* **`0AF15C3D` (proper PA4 calibration against markitdown baseline)**:
  **PIVOT.** The underlying intent (tuning the scorer empirically)
  is sound, but the target metric must change from "land flag rate
  in [5 %, 15 %]" to "maximize structural density and section count
  in the merged output, conditional on per-page cost budget".

Both stashes should be archived as superseded; new stashes captured
below replace them.

## Decision

**Docling is the right primary extraction engine for docline's stated
downstream uses.** Markitdown's role narrows from "default baseline"
to "fast cheap fallback for prose-only documents where docling is
unavailable or budget-prohibitive".

The triage-then-repair pattern (021-S architecture) is still valuable
but its **role inverts**:

* **Old framing**: heuristic baseline + docling repair for the
  minority of problematic pages
* **New framing**: docling primary + heuristic shortcut only for
  pages where AST-quality predictors show heuristic will suffice

In practice this means rewriting the scorer to predict
*structural complexity* of the source page (not heuristic-output
quality). A page with rich structure (tables, multi-column,
hierarchical headings in the source PDF) routes to docling; a flat
prose page routes to the cheap heuristic.

## Recommended docline strategy

### Short term (1-2 shipments)

1. **Capture this study's findings as compound learning** —
   "char-count is not a fidelity metric for AST-aware consumers"
   plus "structural density + section count + heading density are
   the right metrics".
2. **Add an AST-aware QA mode** to the triage pipeline. When
   `--triage-report-only` is run, emit per-range structural density
   and section count delta alongside char-length. Operators
   can then calibrate against goal-aligned metrics.
3. **Default mode recommendation update** in docs — for cosmos-class
   technical reference PDFs, recommend `--pdf-mode auto` (all-docling)
   over `--pdf-mode triage`. Triage retains value only for
   prose-dominated corpora.
4. **Preserve the per-page baseline PDFs** option — the cosmos run's
   3,426 `baseline-NNNN.pdf` files are valuable diagnostic
   artifacts; the orchestrator should optionally retain them under
   a `--keep-page-pdfs` flag so future studies don't need to
   re-split.

### Medium term (3-5 shipments)

5. **Invert the scoring model**. Replace the 8-signal heuristic-
   output scorer with a **source-PDF structural-complexity scorer**:
   * X-cluster count (already implemented in `signal_layout_complexity`)
   * Image / figure presence
   * Font diversity (many fonts → likely figure / table)
   * Cross-page text-flow consistency (low → likely multi-column)

   A page scores HIGH → routes to docling. LOW → routes to
   markitdown/pypdf shortcut. The decision is made BEFORE running
   either heuristic, eliminating the wasted markitdown work on
   pages destined for docling.

6. **Speed up docling itself** where possible:
   * Larger per-subprocess page batches (current: ~per-range, often
     few pages — overhead amortizes poorly)
   * Profile and tune `docling_worker`
   * Investigate GPU acceleration for rt_detr layout model

### Long term (research direction)

7. **Hybrid output protocol**: docling's structural skeleton +
   markitdown's body text for prose sections. Requires
   per-page or per-section engine choice and stitching — non-trivial.
   Likely only worth doing if docling speed-up (#6) hits a ceiling.
8. **Per-corpus calibration**: different document classes (scientific
   papers, legal contracts, technical manuals, novels) have different
   optimal extraction strategies. A small calibration pass per new
   corpus could choose engine defaults automatically.

## Risks and limits

1. **Cosmos may not generalize.** The study used one corpus (Azure
   Cosmos DB reference manual). A small-sample re-study against 2-3
   other corpus classes (scientific paper, contract, novel) would
   confirm or refute the universal docling-wins finding.
2. **Study uses regenerated markitdown.** The output should be
   deterministic (`enable_plugins=False`), but if any non-deterministic
   pdfminer behavior leaks in, the comparison drifts from what the
   PA3+PA4 scorer originally saw. Spot-check via re-runs.
3. **No throughput / cost dimension in the metric.** Decision rule
   currently treats quality as binary. A pareto-optimal scorer
   might weight per-page docling cost ($) against quality gain (Δ
   sections, Δ headings) and route only when ROI clears a threshold.

## Follow-up work captured

New stashes created in this session (priority + kind in parentheses):

| Stash | Priority | Kind | Description |
|---|---|---|---|
| `13F608BA` | high | task | Compound learning: char-count is not a fidelity metric for AST-aware consumers; structural density + section count + heading count are the right metrics |
| `378C8BC0` | high | feature | Add AST-aware QA mode to `--triage-report-only`: emit structural density / section count / heading count alongside char counts; promote `scripts/study/evaluate_markdown.py` to `src/docline/process/quality_metrics.py` |
| `EFC6C84E` | high | feature | INVERT scoring model: score source-PDF structural complexity (BEFORE running extractors), not heuristic-output quality. Supersedes the earlier interim-mitigation thinking |
| `A39C3704` | medium | task | Update docs: recommend `--pdf-mode auto` for technical reference PDFs; `--pdf-mode triage` only for prose corpora |
| `5A622B72` | medium | feature | Add `--keep-page-pdfs` flag to preserve `baseline-NNNN.pdf` artifacts for future diagnostic studies |
| `51332802` | medium | task | Profile and tune `docling_worker` for larger per-subprocess batches; investigate GPU acceleration |
| `4CB606D5` | low | task | Re-study with 2-3 additional corpus classes to verify generalization beyond cosmos |

Plus the two stashes from the prior session (79F23BDE, 0AF15C3D) which
this study **supersedes** — they exist in the git stash `stash@{0}` on
the `fix/silence-pdfminer-warnings` branch context. When recovering
that stash for the next shipment, archive 79F23BDE + 0AF15C3D rather
than harvesting them (their stated interventions are now rejected).
