---
date: 2026-06-08
shipment: 023-S
category: extraction-quality-metrics
keywords: [ast, markdown, fidelity, embeddings, graph, llm, structural-density, section-count, char-count]
confidence: high
evidence: docs/decisions/2026-06-08-extraction-strategy-study.md, .elt/output/cosmos-triage-022/study/results/findings.md, src/docline/process/quality_metrics.py
supersedes: (none — extends 022-S compound learning around char-equality QA metrics)
---

# Char count is not a fidelity metric for AST-aware consumers

## Problem

Comparing extracted markdown output by raw character length (or by
naive text-equality / character-level Jaccard) **misses structural
quality differences that dominate downstream utility** for graph
databases, vector embedding stores, and LLM context windows.

A markdown document that parses to 5,500 characters of unstructured
prose-blob and one that parses to 5,500 characters with 7 headings and
8 sections look identical by char count, but produce wildly different
downstream behavior:

* The blob requires lossy re-chunking by downstream code (loses
  heading-anchored boundaries → degrades embedding-retrieval precision)
* The blob has no graphable structure (no headings to anchor nodes, no
  cross-doc edges to extract)
* The blob fills the LLM context with redundant boilerplate that the
  structured version compresses away

## Symptom

The 022-S PA4 calibration "over-fire" diagnosis identified range
1487-1490 as a scorer false positive because markitdown produced 5,498
chars and docling produced 5,564 chars (1 % char delta). The follow-on
2026-06-08 study re-examined the same range with AST-aware metrics and
found:

| Metric | markitdown | docling | ratio |
|---|---|---|---|
| char_len | 5,370 | 5,564 | 1.04 |
| heading_count | 0 | 7 | ∞ |
| section_count | 1 | 8 | **8×** |
| median_section_chars | 5,370 | 659 | docling chunks; markitdown blob |
| structural_density_per_1k | 0.186 | 3.415 | **18×** |

The scorer's flag was correct. Char count was the wrong measurement
lens.

## Root cause

Char count is a **content quantity** metric. It tells you how many
characters were extracted, not what shape they took. For consumers
that care about content quantity only (full-text search, raw archive),
char count is fine. For consumers that care about **content structure**
(graph nodes, embedding chunks, LLM-navigable headings, table cells as
graph edges), char count is silent on the dimension that matters.

The right metrics walk the AST (via `markdown-it-py` or equivalent)
and count structural elements: headings, sections, tables, table cells,
code blocks, list items. The ratio of these to total chars is
"structural density per 1k chars" — a higher number means more
semantic structure per unit of content.

## Decision rule

When evaluating whether a markdown extraction is "good enough" for
docline's downstream consumers (graph DBs, vector embeddings, LLMs):

* **Primary signals** (AST-aware): heading_count, section_count,
  table_cell_count, structural_density_per_1k, median_section_chars
* **Secondary signals**: char_len, word_count, type_token_ratio
* **Anti-pattern**: relying on char-equality or character-Jaccard
  similarity to determine whether two extractions are "equivalent" —
  they may have identical chars but unusable structure

Empirical thresholds derived from the 2026-06-08 study (cosmos
corpus, 577 sample pages):

| Quality tier | structural_density_per_1k | median_section_chars |
|---|---|---|
| Excellent (docling on technical refs) | ≥ 6 | 400-800 (good embedding chunks) |
| Acceptable (heuristic on prose) | 2-5 | 1,000-3,000 |
| Poor (heuristic on dense layout) | < 1 | > 5,000 (single blob, unchunkable) |

A markdown extraction reaches "acceptable quality for AST-aware
consumers" when `structural_density_per_1k ≥ 5` OR `section_count ≥ 30
per 50 KB content`, whichever the source material can support.

## Application in docline

* :func:`docline.process.compute_quality_metrics` is the canonical
  implementation. Use it when scoring, calibrating, or QA-ing
  extracted markdown.
* `triage_report_only --triage-report-only` emits `qm_*` columns
  alongside fidelity-signal columns so operators can calibrate against
  both lenses simultaneously.
* When designing a new QA tripwire or similarity metric, choose
  AST-aware comparison (e.g. structural-element-counts) over
  char-level comparison.

## Counterexamples

For corpora where structure is genuinely absent (chat logs, plain
prose articles, free-form notes), char-count comparison may still be
useful because there's no AST to walk. The decision rule applies
specifically to corpora where the AUTHOR'S source had structure
(headings, tables, lists, code) that any reasonable extractor should
recover.

## Generalization

This learning generalizes beyond docline: any document-processing
pipeline whose downstream consumers ingest structured content (RAG,
knowledge graphs, semantic search) should evaluate extraction quality
on AST-aware metrics, not raw char counts. Pipelines designed for
full-text storage (Elasticsearch document body, log archives) can
continue to use char-based metrics.

## References

* Decision: `docs/decisions/2026-06-08-extraction-strategy-study.md`
* Source-MD extension: `docs/decisions/2026-06-08-source-md-ingestion-extension.md`
* Implementation: `src/docline/process/quality_metrics.py`
* Evidence: `.elt/output/cosmos-triage-022/study/results/findings.md`
* Tests: `tests/process/test_quality_metrics.py`
* Reference study scripts: `scripts/study/`
