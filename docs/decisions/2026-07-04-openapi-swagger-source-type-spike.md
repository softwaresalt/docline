---
title: "OpenAPI / Swagger source type — ingestion design and decomposition"
type: spike
date: 2026-07-04
time_box: "3h"
conclusion: "proceed"
confidence: "medium-high"
linked_parent_work_item: "049-F"
promoted_to: ["build-feature-decomposition"]
tags:
  - "openapi"
  - "swagger"
  - "source-type"
  - "rest-api"
  - "ingestion"
---

## Problem frame

Stash `F8E142A1` (low, epic): docline has no first-class ingestion path for REST
API reference content. The canonical source for such content is a set of
**OpenAPI / Swagger** specifications (for example, the Azure/`azure-rest-api-specs`
repository), not a prose document. Today an operator who wants the
1,686-page `rest-api-power-bi.pdf` equivalent must run the PDF through the layout
pipeline, which flattens a precise, machine-readable API contract into lossy
prose. This spike frames the ingestion model, confirms feasibility against
docline's current architecture, and decomposes the work into a build-ready
feature so a future dedicated shipment can execute it.

Out of scope for this spike: writing the reader. This is investigation +
design + decomposition only.

## Investigation — how docline ingests today

Grounded in the current code (2026-07-04, `main`):

* **Source classification** — `router.classify_source` maps a raw string to
  `SourceKind` (`URL` / `TRANSCRIPT` / `FILE`); everything non-URL, non-`.vtt/.srt`
  is `FILE`. `readers/documents.read_document` is still a stub; the live dispatch
  is extension-driven in `app.py` via
  `_SUPPORTED_EXTENSIONS = {.docx, .pdf, .html, .htm, .md, .txt}`.
* **Readers** — one adapter per format under `src/docline/readers/`
  (`pdf.py`, `docx.py`, `text.py`, `transcripts.py`, `github.py`). Each returns
  Markdown text. Layout formats (PDF/DOCX) do heavy extraction; `.md` is a
  near-passthrough (the 2026-06-09 corpus study measured ~1,800x more chunks per
  unit time for already-structured Markdown than for PDF layout analysis).
* **Output contract** — every document is a `BaseDocument` = Markdown `body` +
  `BaseFrontmatter` (`title`, `source`, `ingested_at`, `doc_type`, `description`,
  `content_sha256`, `source_path`, `chunk_strategy="h1-h2-h3"`, `schema_version`,
  and a `docline` namespace for tool-only metadata). Downstream consumers are a
  graphtor graph DB (typed edges harvested from cross-document links) and RAG
  chunking on `h1/h2/h3` boundaries.
* **Two-phase pipeline** — `docline fetch` (I/O-bound staging) then
  `docline process` (compute-bound normalization). `.json` staged files are
  deliberately **skipped** in the process pass (they are config/`docfx.json`
  sidecars), so an OpenAPI `.json` cannot ride the existing FILE path.
* **Dependencies** — `PyYAML>=6,<7` and `pydantic>=2,<3` are already present, so
  parsing OpenAPI in either JSON or YAML needs **no new dependency** (Principle VI).

## Key finding — OpenAPI is a *structured-render*, not a *layout-extract*, source

Unlike PDF/DOCX (rasterized or styled prose that must be reverse-engineered into
structure), an OpenAPI/Swagger spec is already a typed object model. The correct
ingestion model **traverses** the model and **renders** deterministic Markdown,
much closer to the `.md` passthrough than to the PDF pipeline:

```text
spec (openapi.json / swagger.yaml)
  → parse (json/yaml)  → resolve $ref  → walk paths/operations + components/schemas
  → render one Markdown document per operation (H1 = METHOD path)
      H2 sections: Summary/Description, Parameters, Request body, Responses, Security
      $ref to a component schema  → a typed cross-document link (operation → schema)
  → BaseFrontmatter(doc_type="openapi_operation", source=<spec URI + operationId>)
```

Rendering per **operation** (rather than per file) yields RAG-sized chunks and
clean graph nodes, and turns each `$ref` into a referential edge — the same
referentiality value docline already harvests from Markdown cross-links.

### Design decisions (recommended defaults for the build feature)

| Decision | Recommendation | Rationale |
|---|---|---|
| Detection | **Content-sniff**, not extension. A source is OpenAPI when the parsed root has an `openapi:` (3.x) or `swagger:` (2.0) key. | `.json`/`.yaml` are overloaded; extension alone misclassifies config/sidecars (which the process pass already skips). |
| Source kind | Add `SourceKind.OPENAPI` and route it to a new `readers/openapi.py`. | Keeps the FILE path untouched; makes the new pipeline explicit and testable. |
| Granularity | One document **per operation**; one document **per named component schema**. | Best RAG chunking + graph-node shape; mirrors how the rendered PDF is navigated. |
| `$ref` resolution | Local (`#/components/...`) in v1; **defer** external/split-file refs. | `azure-rest-api-specs` splits across files; full resolution is a large sub-problem. Local refs cover single-spec ingestion and de-risk v1. |
| Spec version | OpenAPI **3.0/3.1** first; **defer** Swagger 2.0. | 3.x is the modern majority; 2.0 differs enough (definitions vs components, body params) to warrant its own task. |
| Cross-refs | Emit `operation → schema` links as Markdown links so graphtor harvests typed edges. | Reuses existing referentiality harvesting; no new contract surface. |
| Scale | v1 ingests a **single spec (file or directory of one service)**; corpus-wide `azure-rest-api-specs` sweep is a separate concern. | Prevents an unbounded first cut; matches the 2-hour task rule per unit. |

## Options considered

1. **Render-from-OpenAPI (recommended).** Parse the authoritative spec and
   render Markdown per operation/schema. Pros: lossless, referential, fast,
   reuses the output contract. Cons: new reader + `$ref` resolver.
2. **Keep using the PDF pipeline on `rest-api-*.pdf`.** Pros: zero new code.
   Cons: lossy (tables/schemas flattened), slow, non-authoritative, no typed
   edges. Rejected — it is the very gap this stash names.
3. **Third-party OpenAPI→Markdown generator (e.g. widdershins).** Pros: fast to
   wire. Cons: new heavy dependency (Principle VI), output does not match
   `BaseFrontmatter`/`chunk_strategy`, no graphtor edge emission, template lock-in.
   Rejected for the core path; may inform the renderer's section layout.

## Decomposition (build feature — future dedicated shipment)

Each task is scoped to roughly two hours, single-domain, with a verifiable
milestone, per the constitution's Task Granularity rule.

| Task | Scope | Verifiable milestone |
|---|---|---|
| T1 — detection | Content-sniff `openapi:`/`swagger:`; add `SourceKind.OPENAPI`; wire routing. | Unit tests: an OpenAPI 3.x doc classifies OPENAPI; a plain config `.json` does not. |
| T2 — loader + local `$ref` | Load JSON/YAML (PyYAML); resolve `#/components/*` refs with cycle guard. | Unit tests: nested + circular local refs resolve without infinite loop. |
| T3 — operation renderer | Render one doc per operation: summary, parameters table, request/response bodies, security. | Golden-file test on a small hand-written 3.1 spec. |
| T4 — schema renderer + edges | Render component schemas; emit `operation → schema` Markdown links. | Test: link targets resolve to the schema docs; graphtor edge shape asserted. |
| T5 — frontmatter + assembly | `doc_type="openapi_operation"`/`"openapi_schema"`, `source` = spec URI + `operationId`; `content_sha256`. | Schema-validation test: emitted docs pass `BaseDocument` validation. |
| T6 — CLI/MCP parity + docs | Surface the path through `docline process` and the MCP tool; README section; dual-interface parity test. | `--manifest` advertises it; parity test: CLI and MCP produce identical output for one spec. |

Deferred beyond v1 (record as follow-up stash on harvest): external/split `$ref`
resolution across `azure-rest-api-specs`; Swagger 2.0; API versioning/monikers;
pagination/long-running-operation conventions; auth/security scheme deep render.

## Risks

* **`$ref` sprawl.** `azure-rest-api-specs` splits a service across many files;
  local-only resolution in v1 mitigates this but limits v1 to self-contained
  specs. Flagged as the top follow-up.
* **External-`$ref` resolution is a security boundary (deferred).** When the
  external/split-file resolver is built, file refs MUST resolve within the
  workspace root (Principle III — reject `..`/absolute/symlink escapes) and any
  URL-valued `$ref` MUST be treated as an SSRF vector and gated, not fetched
  blindly. v1's local-only scope deliberately sidesteps both; this note carries
  the requirement forward so the deferred task does not reintroduce the risk.
* **Spec-version drift** (2.0 vs 3.0 vs 3.1) — contained by scoping v1 to 3.x.
* **Scale** — a corpus-wide sweep is explicitly out of v1 scope; without that
  guard the first cut is unbounded.
* **Granularity churn** — per-operation vs per-tag is a product decision; the
  recommendation (per-operation) should be confirmed by the operator before T3.

## Recommendation

**PROCEED** as a dedicated build feature (not a slice-in). The ingestion model is
a structured render that fits docline's existing output contract cleanly, needs
no new dependency, and delivers a referential, lossless alternative to the PDF
path. Start narrow: OpenAPI 3.x, single-spec scope, per-operation rendering,
local `$ref` only. The build should run as its own shipment after the operator
confirms the per-operation granularity and the v1 scope boundary.

Feature `049-F` tracks this spike; the build work above is ready to harvest into
a sibling feature when the operator green-lights the granularity decision.
