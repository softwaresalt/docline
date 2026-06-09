# docline

A document to markdown ingestion and normalization pipeline CLI tool and MCP server.

## Documentation

* [docline → graphtor-docs ingestion contract](docs/design-docs/graphtor-docs-ingestion-contract.md) —
  the stable v1 contract surface that downstream consumers ingest.
* [BaseFrontmatter JSON Schema export workflow](docs/design-docs/schema-export-workflow.md) —
  how to regenerate the exported JSON Schema and how `graphtor-docs` consumes it.
* [Document ingestion and validation pipeline design](docs/design-docs/DocumentIngestion&ValidationPipelineDesign.md)

## PDF processing modes

`docline process` supports two PDF processing modes via the `--pdf-mode`
flag.

### `--pdf-mode auto` (default — recommended for technical PDFs)

Runs `docling` on every page. Best AST-aware quality (headings, tables,
code blocks, embedding-chunk-friendly section sizes) for technical
reference documents — Microsoft / AWS / Kubernetes / framework
documentation, vendor manuals, scientific papers with dense layout.

* Pros: highest structural fidelity; ideal for graph DBs, vector
  embedding stores, and LLM context windows.
* Cons: ~15-30 sec per page wall-clock; a 3,400-page reference manual
  takes ~4-9 hours.

### `--pdf-mode triage` (opt-in — for prose-dominated corpora)

Runs a heuristic baseline ([`markitdown`](https://github.com/microsoft/markitdown)
or `pypdf`) across the whole PDF, scores each page for likely fidelity
loss, and only invokes `docling` on flagged page ranges. Designed for
documents that are mostly free-form prose (novels, articles, simple
documentation, chat exports).

* Pros: ~5-10× faster than `auto` on prose corpora.
* Cons: on technical reference PDFs, triage either over-fires (large
  pages flagged, wall-clock approaches `auto`) or under-fires (table
  pages flattened to broken text). See the
  [2026-06-08 extraction strategy study](docs/decisions/2026-06-08-extraction-strategy-study.md)
  for empirical results: docling wins 14/15 sampled cosmos ranges on
  AST quality.

### Choosing a mode

* **Technical reference PDFs** (vendor docs, framework docs, scientific
  papers): use `--pdf-mode auto`.
* **Prose corpora** (novels, articles, transcripts): use `--pdf-mode triage`
  to trade some structural fidelity for speed.
* **Source markdown available** (Microsoft Learn, AWS Docs, K8s,
  React, Python, most OSS): a future shipment (026-S) will add a
  `--source-mode` flag that bypasses PDF extraction entirely; see the
  [source-MD ingestion extension](docs/decisions/2026-06-08-source-md-ingestion-extension.md).

### Calibration & QA

`docline process --pdf-mode triage --triage-report-only` emits a
per-page TSV with both fidelity-signal scores and AST-aware quality
metrics (heading count, section count, table cell count, structural
density per 1k chars, median section size). See
[`docs/compound/2026-06-08-ast-fidelity-metrics.md`](docs/compound/2026-06-08-ast-fidelity-metrics.md)
for the decision rule on interpreting these metrics.

### Triage output retention

When `--pdf-mode triage` is used, per-page baseline PDFs
(`baseline-NNNN.pdf`) and coalesced splice PDFs / outputs
(`splice-AAAA-BBBB.{pdf,md}`) are preserved by default under
`{output_dir}/splices/` for offline calibration and diagnostic
inspection. Plan accordingly for disk usage: a 3,400-page PDF produces
~3,400 per-page PDFs totaling ~150 MB.

