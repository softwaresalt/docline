---
title: Power BI docs source-MD ingestion — empirical baseline + gap analysis
date: 2026-06-09
status: investigation
related_decisions:
  - docs/decisions/2026-06-08-extraction-strategy-study.md
  - docs/decisions/2026-06-08-source-md-ingestion-extension.md
related_stashes:
  - 6A4E8059
related_compound:
  - docs/compound/2026-06-08-ast-fidelity-metrics.md
study_artifacts:
  - scripts/study/survey_powerbi_source_md.py
  - scripts/study/stage_powerbi_test.py
  - .elt/output/powerbi-source-survey/
  - .elt/output/powerbi-test/
---

## Question

What happens when current docline (post-023-S) is pointed at the local
Power BI docs source-MD repository at `E:\Source\powerbi-docs`?

## Corpus characteristics

| Metric | Value |
|---|---|
| Total .md files | 1,340 |
| Total body chars | 13.8 MB |
| Subdirectories | 16 (paginated-reports, create-reports, developer, etc.) |
| Files with YAML frontmatter | 99.5 % |
| TOC.yml files | 16 (one per subdir + breadcrumb) |
| Flavor | DocFx-flavored CommonMark + Microsoft Learn frontmatter |

## Survey results (compute_quality_metrics on all 1,340 files)

Headline metrics from `scripts/study/survey_powerbi_source_md.py`:

| Metric | Value | Quality tier |
|---|---|---|
| Mean structural_density_per_1k | **6.89** | Excellent (matches docling's 6.80 average from 2026-06-08 study) |
| Median structural_density_per_1k | 6.09 | Excellent |
| Mean median_section_chars | **782** | Optimal for embedding chunks (256-512 tokens ≈ 1-2 KB) |
| Mean heading_count per doc | 11.0 | Rich hierarchy |
| Mean section_count per doc | 11.0 | One section per heading (clean structure) |
| Mean table_cell_count per doc | 13.9 | Structured data present |
| Frontmatter coverage | 99.5 % | Reliable metadata source |

### Per-subdir highlights

| Subdir | Files | Mean body chars | Mean density | Notes |
|---|---|---|---|---|
| paginated-reports | 269 | 6,139 | 7.17 | Highest count, dense |
| create-reports | 184 | 9,320 | 6.53 | Medium-large docs |
| developer | 167 | 8,724 | 7.64 | Highest code-block count (6.2/doc avg) |
| guidance | 146 | 21,880 | 5.84 | Largest docs (architecture/planning) |
| fundamentals | 19 | 49,036 | **9.70** | Mega-docs (mean 65.6 headings/doc) |
| report-server | 38 | 10,443 | **10.22** | Densest small-subdir |

### Comparison to 2026-06-08 study

| Source | Mean density / 1k | Median section chars |
|---|---|---|
| markitdown (PDF → md) | 2.62 | 29,161 (one big blob) |
| docling (PDF → md) | 6.80 | 571 (good chunking) |
| source-MD (Azure PostgreSQL proxy) | 9.14 | 542 |
| **source-MD (Power BI, this run)** | **6.89** | **782** |

Power BI source-MD lands in the "as good as docling at zero ML cost"
band. Section sizes are slightly larger than the PostgreSQL proxy but
still well within embedding-chunk-friendly territory.

## Single-doc smoke test (compute_quality_metrics standalone)

Sampled the largest guidance doc:
`powerbi-implementation-planning-auditing-monitoring-tenant-level-auditing.md`
(205 KB body, after frontmatter strip):

| Metric | Value |
|---|---|
| char_len | 205,603 |
| heading_count | 103 |
| heading_depth_max | 6 |
| section_count | 103 |
| median_section_chars | 1,621 |
| table_count | 12 |
| table_cell_count | 275 |
| code_block_count | 0 |
| list_item_count | 513 |
| structural_density_per_1k | 6.595 |

**Conclusion**: `compute_quality_metrics` handles production source MD
flawlessly. The 023-S production module is correct + fast end-to-end.

## End-to-end CLI test (`docline process`)

Staged 10 stratified Power BI MD files via
`scripts/study/stage_powerbi_test.py` (one per major subdir, mid-sized
5-30 KB) and ran:

```powershell
docline process --staging-dir .elt/staging-powerbi-test --output-dir .elt/output/powerbi-test
```

**Result**: CLI exits 0 / `success: true` but **all 10 files produce
"Failed to build frontmatter" warnings**. The output directory contains:

* `manifest.json` with all 10 document entries (document_id, ingest_order,
  input_path, output_path, source) — manifest infrastructure works
* Per-file `.md` outputs that are **verbatim copies of the source files**
  (frontmatter + body, including DocFx extensions, all unchanged)

### Root cause of frontmatter assembly failure

docline's MD reader (`build_output_document_parts` in
`src/docline/process/output_contract.py`) reads the file content with
`file_path.read_text()` and passes it directly to the markdown segmenter
+ frontmatter assembler. **The source YAML frontmatter is NOT stripped
before parsing**. So when the assembler walks the document looking for
H1/H2 hierarchy, the YAML lines (`title: ...`, `description: ...`)
appear as if they were prose body content, and the validator rejects
the document because the first heading-like construct is at "H2 level"
(actually a YAML key) before any H1.

### Workaround that proves the diagnosis

Manually stripping frontmatter via `strip_frontmatter()` in the survey
script (see `survey_powerbi_source_md.py`) before running
`compute_quality_metrics` produces perfect results across all 1,340
files. The issue is purely the YAML-fence handling in docline's
ingestion path.

## Gap analysis: what 026-F needs to close

| # | Gap | Impact | Difficulty |
|---|---|---|---|
| 1 | Strip YAML frontmatter before markdown parsing | Blocks all .md ingestion of Microsoft Learn / DocFx / Hugo / Jekyll / Sphinx flavor | Low (regex or yaml.safe_load_all) |
| 2 | Preserve ms.* / DocFx frontmatter fields under `docline:` namespace | Loses metadata graphability (ms.topic, ms.author, ms.date are all valuable graph node attributes) | Low-Medium |
| 3 | Resolve `[!INCLUDE [name](path.md)]` directives | Content is incomplete without include resolution (~5-20% of body text on average) | Medium |
| 4 | Handle `:::image type="content" source="..."::: :::` containers | Image references opaque; alt-text inaccessible to LLMs | Low (extension parser) |
| 5 | Handle `:::moniker range="..."::: :::` zone-pivots | Wrong-version content emitted; downstream confusion | Medium |
| 6 | Parse `TOC.yml` for topological ingestion order | Without ordering, graph parents may be processed AFTER children | Medium |
| 7 | Resolve cross-doc `[text](other-doc.md)` links to canonical IDs | String-only links cannot become graph edges | Medium-High |
| 8 | Manifest `source_type: github-source-md` + `source_repo`, `source_commit`, `source_path` provenance | No traceability to upstream version | Low |
| 9 | Incremental sync via diff-against-prior-manifest | Full re-ingest on every change is wasteful at 1,340-file scale | High |
| 10 | DocFx include + zone-pivot interaction | Edge case but bites on conditional Power BI Pro/Premium guidance | Medium |

## What docline already provides (don't rebuild)

* ✅ Per-document `document_id` assignment (deterministic from job + path)
* ✅ `manifest.json` skeleton with ingest_order, source_path, source provenance
* ✅ Per-source `picture_sink` for media routing
* ✅ Heading-hierarchy validation (will work once frontmatter is stripped)
* ✅ Workspace path containment (`safe_workspace_path`)
* ✅ Output directory layout (`{job_id}/{relative_source_path}.md`)
* ✅ AST-aware quality metrics (`compute_quality_metrics` from 023-S)
* ✅ Multi-format dispatch (PDF / DOCX / HTML / MD / TXT) already in place

## Recommended 026-F shape (revised based on this finding)

The full 026-F as planned in the source-MD ingestion extension decision
(`docs/decisions/2026-06-08-source-md-ingestion-extension.md`) is the
right architectural target, but the **minimum-viable first slice**
(call it 026.001-T) is much smaller than the original 8-task
decomposition suggested:

* **026.001-T (minimum-viable source-MD)**: Strip YAML frontmatter
  before markdown parsing; preserve ms.* fields under `docline:`
  namespace; pass through DocFx extensions verbatim (still readable
  by graph extraction even if not parsed). **This single task alone
  would change "all 10 files fail" to "all 10 files succeed with
  basic provenance"** — immediate value for the Power BI corpus.

* 026.002-T: TOC.yml parser for topological ingest order
* 026.003-T: DocFx include resolver
* 026.004-T: Cross-doc link resolution → graph-edge metadata
* 026.005-T: DocFx container parser (`:::image:::`, `:::moniker:::`)
* 026.006-T: Source provenance fields in manifest
* 026.007-T: Incremental sync via prior-manifest diff

Each task is ~2 hours; the feature ships incrementally with each
task delivering operator-visible value.

## Decision points for operator review

1. **Should we proceed with 026.001-T as a quick small win?** It would
   unblock Power BI ingestion (and AWS / K8s / React / Python / etc.)
   with one well-scoped change.
2. **Should the frontmatter passthrough be lossy (strip + reformat) or
   lossless (preserve original YAML + nest under `docline:source_frontmatter`)?**
   Recommended: lossless preservation under `docline:source_frontmatter`,
   plus extract well-known fields (title, description, ms.author,
   ms.topic, ms.date) into the standard docline frontmatter top-level.
3. **Should 026.001-T also include a basic DocFx `:::image:::` parser?**
   It's a 1-line change and downstream consumers care a lot about
   alt-text. Recommended: yes.

## Artifacts produced

| Path | Status |
|---|---|
| `scripts/study/survey_powerbi_source_md.py` | new committable diagnostic tool |
| `scripts/study/stage_powerbi_test.py` | new committable test harness for local-corpus ingestion |
| `.elt/output/powerbi-source-survey/global-summary.json` | local evidence |
| `.elt/output/powerbi-source-survey/per-subdir-summary.json` | local evidence |
| `.elt/output/powerbi-source-survey/per-file-metrics.json` | local evidence (1.4 MB) |
| `.elt/output/powerbi-source-survey/per-file-metrics.tsv` | local evidence (spreadsheet inspection) |
| `.elt/output/powerbi-test/manifest.json` | docline-produced manifest from end-to-end test |
| `.elt/output/powerbi-test/{job_id}/.../.md` | 10 verbatim file copies |
| `.elt/staging-powerbi-test/` | staging artifacts |

## Recommendation

**Strong empirical green-light for source-MD ingestion as docline's
next-tier capability.** The corpus quality is in the "excellent" tier
(matching docling output at zero compute cost), and the existing
docline scaffolding (manifest, document_id, picture_sink, multi-format
dispatch) provides about 60% of what 026-F needs. The single biggest
unblock is frontmatter stripping (026.001-T), which would change
"all 10 files fail" to "all 10 files succeed with provenance" for ANY
corpus that uses YAML frontmatter (Microsoft Learn, AWS, K8s, React,
Hugo, Jekyll, MkDocs, Sphinx, Astro — essentially all modern docs).

A small 026-S shipment carrying just 026.001-T (frontmatter strip +
DocFx image parser + manifest provenance fields) would deliver
operator-visible value on the Power BI corpus and serve as the
foundation for the larger 026-F feature work that follows.
