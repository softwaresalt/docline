# docline

A document to markdown ingestion and normalization pipeline CLI tool and MCP server.

## Quick start: ingest a local docs repo

The fastest way to convert a cloned Microsoft Learn (or any DocFx-style)
docs repository into graphtor-ready Markdown is the `ingest local-dir`
command:

```powershell
# Clone a docs repo (one-time)
git clone https://github.com/MicrosoftDocs/powerbi-docs.git E:\Source\powerbi-docs

# Convert the whole tree in one command
docline ingest local-dir E:\Source\powerbi-docs\powerbi-docs --output .elt\output\powerbi
```

Each output file carries graphtor-ready frontmatter (`chunk_strategy`,
`content_sha256`, `doc_type`, `title`, `source_path`, `source`,
`docline.source_frontmatter`, `docline.cross_doc_links`), preserves source
directory structure, and follows TOC.yml ingest order when present.

The CLI mirrors the equivalent `.elt/config/<name>.sources.yaml` manifest
form for parity:

```yaml
# .elt/config/powerbi.sources.yaml
sources:
  - id: powerbi
    type: local
    path: E:\Source\powerbi-docs\powerbi-docs
    include: ["**/*.md", "**/TOC.yml"]
```

Both surfaces produce identical staging + processing output because they
share the same `execute_source_configs` and `execute_process` code paths.

Other Microsoft Learn docs sources that work out of the box:

| Content | Repo | Subpath |
|---|---|---|
| Power BI | `MicrosoftDocs/powerbi-docs` | `powerbi-docs/` |
| Microsoft Fabric | `MicrosoftDocs/fabric-docs` | repo root |
| DAX language reference | `MicrosoftDocs/query-docs` | `query-languages/dax/` |
| Power Query M language reference | `MicrosoftDocs/query-docs` | `query-languages/m/` |
| Analysis Services | `MicrosoftDocs/bi-shared-docs` | `docs/analysis-services/` |

Useful flags:

* `--include PATTERN` (repeatable) — glob to include, default `**/*.md` + `**/TOC.yml`
* `--exclude PATTERN` (repeatable) — glob to exclude
* `--staging-dir PATH` — keep staging artifacts under a known path (default: tempdir, removed after run)
* `--keep-staging` — retain staging directory for debugging
* `--allow-heading-disorder` — bypass strict H1→H2→H3 validation (for legacy authoring)

## Documentation

* [docline → graphtor-docs ingestion contract](docs/design-docs/graphtor-docs-ingestion-contract.md) —
  the stable v1 contract surface that downstream consumers ingest.
* [BaseFrontmatter JSON Schema export workflow](docs/design-docs/schema-export-workflow.md) —
  how to regenerate the exported JSON Schema and how `graphtor-docs` consumes it.
* [Document ingestion and validation pipeline design](docs/design-docs/DocumentIngestion&ValidationPipelineDesign.md)

## OpenAPI / Swagger source type

`docline process` ingests OpenAPI 3.x specifications as a first-class source
type. A staged `.json`, `.yaml`, or `.yml` file is recognized by content-sniff
(its root declares `openapi: 3.x` or `swagger: 2.0`), so plain config files such
as `docfx.json` are never misclassified.

Rather than flattening the spec through the PDF pipeline, docline traverses the
typed object model and renders deterministic Markdown:

* one document per **operation** at `operations/{operationId}.md`
  (`doc_type: openapi_operation`), with `Parameters`, `Request body`,
  `Responses`, and `Security` sections;
* one document per named **component schema** at `schemas/{name}.md`
  (`doc_type: openapi_schema`), with a properties table.

Each `$ref` to a component schema is emitted as a relative Markdown link, so the
existing cross-doc link harvester records every `operation → schema` reference as
a typed graph edge under the `docline.cross_doc_links` frontmatter namespace.

### v1 scope

The first release is intentionally narrow:

* OpenAPI **3.x** (Swagger 2.0 is detected but not yet rendered);
* a **single spec** (one file, or a directory for one service);
* **per-operation** granularity;
* **local** `#/components/*` `$ref` resolution only — external and split-file
  refs are left unresolved (never fetched), because resolving them is a security
  boundary deferred to a follow-up.

### Usage

Stage a spec and run the compute-bound pass:

```bash
docline ingest local-dir ./azure-rest-api-specs/specification/... \
  --output ./out --include "**/*.json"
```

The source directory is a positional argument. The MCP `process` tool produces
identical output; both surfaces share `execute_process`.

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
  React, Python, most OSS): a future feature (**026-F**) will add a
  `--source-mode` flag that bypasses PDF extraction entirely; see the
  [source-MD ingestion extension](docs/decisions/2026-06-08-source-md-ingestion-extension.md).

### Choosing a PDF engine

`--pdf-engine` selects *which* layout extractor runs and is orthogonal to
`--pdf-mode` (which selects whole-document vs. triage). Four choices: `auto`
(default), `docling`, `mistral_ocr`, and `heuristic`.

| Engine | Strengths | Trade-offs | Requirements |
|---|---|---|---|
| `auto` (default) | Prefers `docling`; transparently degrades to `heuristic` on failure so one hostile PDF can't abort a batch | Never selects `mistral_ocr` | `docline[pdf]` for docling, else heuristic |
| `docling` | Best structural fidelity on headings and dense layout; deterministic; fully local/offline | ~360 pages/hour (031-S bench) | `docline[pdf]` extra (raises if missing) |
| `mistral_ocr` | Wins decisively on tables (mean +33.9% vs. docling, 8/4/2 wins); ~3,732 pages/hour (~10× docling) | Heading depth ~8.4% weaker than docling; per-page cloud cost (~$1 / 1,000 pages); network + credentials; non-deterministic | `docline[mistral]` + `AZURE_AI_FOUNDRY_KEY`/`_ENDPOINT` or `MISTRAL_API_KEY` |
| `heuristic` | Fastest; no model download; fully local | Flattens tables and complex layout to plain text | None (built in) |

**Fidelity vs. throughput — recommended engine by corpus class:**

| Corpus class | Throughput priority | Cost sensitivity | Recommended `--pdf-engine` |
|---|---|---|---|
| Technical reference (vendor/framework docs, manuals) | Low | Any | `docling` (or `auto`) |
| Table-heavy (financial reports, spec sheets, data appendices) | Low | Low | `mistral_ocr` |
| Table-heavy at scale | High | Tolerant of cloud cost | `mistral_ocr` |
| Scientific papers (dense layout + tables) | Low | Any | `docling`; `mistral_ocr` if tables dominate |
| Forms / invoices (scanned, OCR-dependent) | Any | Tolerant | `mistral_ocr` (OCR strength) — re-validate per corpus |
| Prose (novels, articles, transcripts) | High | Any | `heuristic` (or `--pdf-mode triage`) |
| Offline / air-gapped / deterministic required | Any | Any | `docling` or `heuristic` (never cloud) |

Evidence: the
[031-S Mistral OCR spike](docs/closure/031-S-mistral-ocr-spike.md)
(PROMOTE-AS-PEER — tables mean +33.9%, ~10× throughput, headings −8.4%) and
the [2026-06-08 extraction strategy study](docs/decisions/2026-06-08-extraction-strategy-study.md)
(docling wins 14/15 sampled technical-reference ranges on AST quality).
`mistral_ocr` is opt-in only and is never auto-selected. Azure Document
Intelligence was evaluated and removed in 031-S; see
[029-S](docs/closure/029-S-adi-spike.md) for the historical record.

### Compute device (`DOCLINE_ACCELERATOR`)

The `docling` engine auto-detects an available accelerator (CUDA, MPS, or
XPU) and falls back to CPU otherwise, so GPU hosts are used without
configuration. Set `DOCLINE_ACCELERATOR` to pin the device explicitly:

| Value | Effect |
|---|---|
| unset or `auto` | docling's default auto-detection (unchanged behavior) |
| `cpu` | Force CPU — the escape hatch when an auto-detected GPU is unreliable |
| `cuda` / `mps` / `xpu` | Pin the named accelerator |

The variable applies to both the single-file CLI path and the batched
docling worker. An unrecognized value fails fast with a configuration error.

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

