---
type: decided-plan
source_plan: 2026-06-10-local-dir-ingest-plan.md
consolidated_at: 2026-08-29
status: shipped
---

## Decision Summary

The shipped local-directory ingest work added a one-shot CLI path for already-cloned documentation repositories: `docline ingest local-dir <path> --output <dir>`. The command binds the existing local manifest fetch and process primitives into a product surface while improving TOC ordering and frontmatter robustness for Microsoft Learn style source-MD corpora.

The plan deliberately kept v1 local-only and file-output-only. Git cloning, multi-repo orchestration, remote sinks, tabbed content, cross-product absolute-path link extraction, and OpenAPI sources remained follow-on work.

## Implementation Units

* T1: implement `docline ingest local-dir` command and pipeline dispatch with include, exclude, staging, keep-staging, and heading-disorder options
* T2: make `_fetch_manifest_local` emit TOC.yml-aware `crawl-manifest.json` ordering with alphabetical fallback and `toc_referenced` markers
* T3: harden `_parse_md_frontmatter` for uniformly indented YAML and regex key/value fallback
* T4: add end-to-end fixture tests and opt-in Power BI corpus parity coverage
* T5: document the quick start and align CLI help with examples

## Key Constraints

* Reuse `ManifestLocalSource`, `execute_elt_fetch`, and `execute_process` rather than inventing a second pipeline
* Require the operator to choose `--output` for safety
* Preserve source directory structure in output
* Keep all filesystem operations within the workspace and staging/output roots
* Preserve existing fetch and process workflows; the new command is additive
* Feature is shippable only when AC1 through AC6 pass, including quality gates and corpus thresholds

## Rejected Alternatives

* Require operators to keep authoring YAML source manifests — rejected as too much friction for ad-hoc local clone ingestion
* Use the study staging script as the product surface — rejected because it is developer tooling
* Auto-detect `docline ingest <path>` source type — rejected in favor of explicit `ingest local-dir` extensibility
* Default output location under `./output` — rejected because explicit `--output` is safer
* Support remote sinks or git cloning in v1 — rejected as separate concerns
* Treat DocFx tabs and cross-product absolute links in this shipment — deferred to dedicated follow-ups

## Review Outcome

No substantive appended plan-review findings were present in the source; it still recommended plan review before harvest. Final shipped scope followed the bounded five-task decomposition and deferred the named non-goals.

## Traceability

Full deliberation history archived at docs/archive/plans/2026-06-10-local-dir-ingest-plan.md

