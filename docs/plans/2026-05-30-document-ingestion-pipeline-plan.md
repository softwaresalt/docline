---
title: "Document ingestion and validation pipeline plan"
description: "Implementation plan for the full design-doc-defined ingestion, validation, CLI, and MCP program."
source_documents:
  - "docs/decisions/2026-05-30-document-ingestion-pipeline-deliberation.md"
  - "docs/design-docs/DocumentIngestion&ValidationPipelineDesign.md"
tags:
  - "ingestion"
  - "schema"
  - "cli"
  - "mcp"
---

# Document ingestion and validation pipeline plan

## Problem Frame

We need to build `docline` as a dual CLI and MCP ingestion system that converts heterogeneous sources into schema-validated Markdown. The design requires a decoupled fetch/process pipeline, deterministic document identity, manifest generation, transcript-specialized handling, AST validation with structural correction, and full CLI/MCP parity. The repository is greenfield, so the plan must establish the initial module boundaries under `src/docline/` and the first complete execution flow.

This plan is gated by the backlog-persistence prerequisite in `docs/plans/2026-05-30-backlog-persistence-prerequisite-plan.md`. No implementation shipment for this feature should be claimed until Shipment 0 from that companion plan is complete.

## Requirements Trace

* Route inputs by source type and signature
  * Create router and reader abstractions for files, transcripts, and recursive HTML
* Support two-stage execution
  * Separate fetch-side staging from process-side validation and correction
* Enforce schema contracts
  * Define Pydantic frontmatter models and translate structural requirements into AST assertions
* Preserve CLI/MCP parity
  * Share operation schemas and expose equivalent fetch, process, and manifest contracts
* Protect ingestion quality
  * Add header normalization, crawler limits, deterministic UUIDs, manifest SSOT rules, and quarantine handling
* Support operator review of quarantined outputs
  * Provide a lightweight local-only viewer for quarantine artifacts and failure reasons

## Implementation Units

### Unit 1: Establish package boundaries and source router contracts

* Changes needed: create the top-level package layout and the input classification contracts for fetch/process orchestration
* Affected files: `src/docline/__init__.py`, `src/docline/router.py`, `src/docline/types.py`
* Tests/verification: router tests covering file-path, MIME, transcript, and URL classification
* Execution posture: test-first

### Unit 2: Define base schema core models

* Changes needed: implement shared Pydantic frontmatter and body contract primitives with no document-family specialization yet
* Affected files: `src/docline/schema/models.py`, `src/docline/schema/library.py`, `tests/schema/test_models.py`
* Tests/verification: schema validation tests for shared required fields and JSON Schema core snapshots
* Execution posture: test-first

### Unit 3: Add wiki and ADR schema families

* Changes needed: implement wiki and ADR document-type schemas on top of the shared schema core
* Affected files: `src/docline/schema/library.py`, `tests/schema/test_wiki_adr_schemas.py`
* Tests/verification: schema-family tests for required sections and metadata constraints
* Execution posture: test-first

### Unit 4: Add transcript and web-document schema families

* Changes needed: implement transcript and web-document schemas on top of the shared schema core
* Affected files: `src/docline/schema/library.py`, `tests/schema/test_transcript_web_schemas.py`
* Tests/verification: schema-family tests for transcript/web-specific constraints
* Execution posture: test-first

### Unit 5: Define shared operation models for fetch, process, and manifest flows

* Changes needed: create the shared application service contracts before any interface wiring so CLI and MCP depend on the same operation schema source
* Affected files: `src/docline/app_models.py`, `src/docline/app.py`, `tests/parity/test_operation_models.py`
* Tests/verification: contract tests proving one shared model set drives both interfaces
* Execution posture: test-first

### Unit 6: Implement CLI and MCP manifest export from the shared schema source

* Changes needed: expose CLI `--manifest` and MCP manifest discovery/resource export from the same operation model source
* Affected files: `src/docline/cli.py`, `src/docline/mcp/server.py`, `tests/parity/test_manifest_parity.py`
* Tests/verification: parity snapshot test proving CLI and MCP manifest contents match
* Execution posture: test-first

### Unit 7: Define dependency-selection and guarded-import policy

* Changes needed: select optional reader/crawler dependencies early, define guarded-import behavior, and document which adapters degrade cleanly when extras are absent
* Affected files: `pyproject.toml`, `src/docline/dependencies.py`, `tests/build/test_optional_dependencies.py`
* Tests/verification: tests proving missing optional extras fail with typed, user-facing guidance instead of import crashes
* Execution posture: test-first

### Unit 8: Build staging job records and deterministic cache layout

* Changes needed: define the fetch-stage job model, cache directory contract, and source metadata written to staging while stripping embedded credentials, signed query parameters, and machine-local absolute paths before persistence
* Affected files: `src/docline/fetch/staging.py`, `src/docline/fetch/models.py`, `tests/fetch/test_staging.py`
* Tests/verification: staging record tests covering timestamps, sanitized source metadata, and deterministic layout
* Execution posture: test-first

### Unit 9: Enforce workspace-contained path resolution for inputs and outputs

* Changes needed: implement canonical path resolution, traversal rejection, symlink refusal, and output-root containment guards
* Affected files: `src/docline/paths.py`, `src/docline/fetch/staging.py`, `tests/security/test_path_containment.py`
* Tests/verification: containment tests covering traversal, symlink, and out-of-root path cases
* Execution posture: test-first

### Unit 10: Define crawler URL policy and SSRF protections

* Changes needed: enforce allowed schemes, private-address denial after resolution, redirect caps, and loopback/metadata-service blocking
* Affected files: `src/docline/fetch/url_policy.py`, `src/docline/fetch/http.py`, `tests/security/test_url_policy.py`
* Tests/verification: policy tests for localhost, RFC1918, link-local, redirect, and scheme rejection cases
* Execution posture: test-first

### Unit 11: Implement bounded async crawl execution

* Changes needed: add recursive crawl orchestration with per-page timeout and total-page limit controls
* Affected files: `src/docline/fetch/crawl.py`, `src/docline/fetch/http.py`, `tests/fetch/test_crawl_limits.py`
* Tests/verification: crawler timeout and page-cap tests
* Execution posture: test-first

### Unit 11A: Add robots and backoff crawl controls

* Changes needed: add robots handling and bounded backoff behavior to the crawl executor without broadening the core executor task
* Affected files: `src/docline/fetch/crawl.py`, `src/docline/fetch/http.py`, `tests/fetch/test_crawl_backoff.py`
* Tests/verification: robots-policy and retry/backoff behavior tests
* Execution posture: test-first

### Unit 12: Implement HTML main-content extraction

* Changes needed: strip DOM noise and convert semantic HTML to raw Markdown
* Affected files: `src/docline/fetch/html_extract.py`, `tests/fetch/test_html_extract.py`
* Tests/verification: HTML fixture tests proving noise removal and content preservation
* Execution posture: test-first

### Unit 13: Implement extracted-header normalization

* Changes needed: normalize extracted headers to a valid root hierarchy without corrupting document structure
* Affected files: `src/docline/fetch/html_normalize.py`, `tests/fetch/test_header_normalization.py`
* Tests/verification: fixture tests proving normalized H1/H2 cascades and idempotent re-normalization
* Execution posture: test-first

### Unit 14: Enforce file-ingest safety limits before reader execution

* Changes needed: validate MIME/signature, size, page-count, and timeout ceilings before reader execution, and explicitly restrict PDF/DOCX parsing in v1 to trusted-local inputs only until isolated parser execution is separately approved
* Affected files: `src/docline/readers/limits.py`, `src/docline/readers/documents.py`, `tests/security/test_reader_limits.py`
* Tests/verification: oversize, malformed, wrong-signature, and trusted-local-only refusal tests with reject-or-quarantine outcomes
* Execution posture: test-first

### Unit 15: Implement PDF reader adapter

* Changes needed: add the PDF extraction adapter behind the guarded dependency contract
* Affected files: `src/docline/readers/pdf.py`, `src/docline/readers/documents.py`, `tests/readers/test_pdf_reader.py`
* Tests/verification: PDF adapter selection and typed-failure tests
* Execution posture: test-first

### Unit 16: Implement DOCX reader adapter

* Changes needed: add the DOCX extraction adapter behind the guarded dependency contract
* Affected files: `src/docline/readers/docx.py`, `src/docline/readers/documents.py`, `tests/readers/test_docx_reader.py`
* Tests/verification: DOCX adapter selection and typed-failure tests
* Execution posture: test-first

### Unit 17: Implement text and VTT reader adapters

* Changes needed: add plain-text and VTT ingestion paths with normalized transcript segment output
* Affected files: `src/docline/readers/text.py`, `src/docline/readers/transcripts.py`, `tests/readers/test_text_vtt_readers.py`
* Tests/verification: fixture tests for text and VTT normalization
* Execution posture: test-first

### Unit 18: Implement transcript pre-processing hooks

* Changes needed: add transcript-only pre-processing hooks that prepare speaker/time metadata for later semantic restructuring
* Affected files: `src/docline/readers/transcripts.py`, `tests/readers/test_transcript_preprocess.py`
* Tests/verification: transcript hook tests preserving chronology and raw utterance boundaries
* Execution posture: test-first

### Unit 19: Implement deterministic document identity

* Changes needed: derive stable canonical source keys and deterministic UUIDs from staged inputs
* Affected files: `src/docline/process/identity.py`, `tests/process/test_identity.py`
* Tests/verification: UUID determinism tests across repeated ingests and canonical-source variations
* Execution posture: test-first

### Unit 20: Implement document-type resolution

* Changes needed: map staged inputs onto the correct built-in schema family before assembly
* Affected files: `src/docline/process/metadata.py`, `tests/process/test_doc_type_resolution.py`
* Tests/verification: resolution tests for wiki, ADR, transcript, and web-document cases
* Execution posture: test-first

### Unit 21: Assemble validated frontmatter payloads

* Changes needed: build the final frontmatter payload from resolved schema plus staged metadata
* Affected files: `src/docline/process/metadata.py`, `tests/process/test_frontmatter_payload.py`
* Tests/verification: frontmatter assembly tests for required metadata and schema-compliant shape
* Execution posture: test-first

### Unit 22: Normalize transcript structure

* Changes needed: reshape transcript content into required speaker/time/topic section scaffolding before linting
* Affected files: `src/docline/process/transcripts.py`, `tests/process/test_transcript_structure.py`
* Tests/verification: structure tests covering required headings and chronology preservation
* Execution posture: test-first

### Unit 23: Add transcript topic segmentation

* Changes needed: add topic-boundary grouping for transcript sections without adding extra summary features beyond the design requirement
* Affected files: `src/docline/process/transcripts.py`, `tests/process/test_transcript_topics.py`
* Tests/verification: topic segmentation tests on representative transcript fixtures
* Execution posture: test-first

### Unit 24: Implement Markdown assembly

* Changes needed: prepend validated YAML and construct the assembled Markdown body before AST linting
* Affected files: `src/docline/process/assemble.py`, `tests/process/test_assemble.py`
* Tests/verification: assembly tests for YAML placement and stable Markdown composition
* Execution posture: test-first

### Unit 25: Implement AST lint engine

* Changes needed: parse Markdown with `markdown-it-py` and enforce structural rules derived from schema contracts
* Affected files: `src/docline/process/ast_lint.py`, `tests/process/test_ast_lint.py`
* Tests/verification: AST rule tests for heading depth, required sections, table headers, and schema-derived assertions
* Execution posture: test-first

### Unit 26: Define correction-provider enablement and credential rules

* Changes needed: make external model use explicit and default-off, define credential source and revocation rules, and document the approved provider operating modes
* Affected files: `src/docline/process/prompts.py`, `src/docline/config.py`, `tests/security/test_correction_policy.py`
* Tests/verification: tests proving default-off behavior, secret-source enforcement, and explicit enablement requirements
* Execution posture: test-first

### Unit 26A: Define correction payload minimization and non-persistence rules

* Changes needed: minimize and redact provider payloads and forbid tokens or raw provider payloads from logs, manifest, quarantine artifacts, and other persisted outputs
* Affected files: `src/docline/process/prompts.py`, `src/docline/process/quarantine.py`, `tests/security/test_correction_redaction.py`
* Tests/verification: tests proving payload minimization, redaction, and non-persistence of provider data
* Execution posture: test-first

### Unit 27: Implement correction-loop orchestration

* Changes needed: generate precise lint error payloads and invoke structure correction with bounded retries
* Affected files: `src/docline/process/correction.py`, `tests/process/test_correction_loop.py`
* Tests/verification: retry-bound tests and non-semantic-edit invariants
* Execution posture: test-first

### Unit 28: Implement quarantine artifact writing

* Changes needed: route failed documents to quarantine with escaped, non-secret failure detail records
* Affected files: `src/docline/process/quarantine.py`, `tests/process/test_quarantine.py`
* Tests/verification: quarantine routing tests and artifact-safety checks
* Execution posture: test-first

### Unit 29: Generate validated output workspace and manifest SSOT

* Changes needed: write validated Markdown outputs under a contained root and atomically update `manifest.json` without relationship data
* Affected files: `src/docline/process/output.py`, `src/docline/process/manifest.py`, `tests/process/test_manifest_output.py`
* Tests/verification: manifest content tests proving ingestion-index behavior, no relationship leakage, and contained output writes
* Execution posture: test-first

### Unit 30: Define MCP transport scope and authenticated-exposure policy

* Changes needed: lock the current scope to stdio-only MCP, reject non-local exposure modes by default, and defer any remote/authenticated transport design to a future separately approved plan
* Affected files: `src/docline/mcp/server.py`, `src/docline/config.py`, `tests/mcp/test_transport_policy.py`
* Tests/verification: tests proving stdio-default behavior and refusal of non-local transport modes
* Execution posture: test-first

### Unit 31: Implement CLI fetch/process adapters over the shared service layer

* Changes needed: map shared fetch/process/manifest operations onto CLI commands without introducing CLI-only logic
* Affected files: `src/docline/cli.py`, `tests/cli/test_fetch_process_cli.py`
* Tests/verification: CLI behavior tests for fetch, process, manifest, and error envelopes
* Execution posture: test-first

### Unit 32: Implement MCP tool adapters over the shared service layer

* Changes needed: expose the same fetch/process/manifest operations through MCP tools with matching success and error contracts
* Affected files: `src/docline/mcp/server.py`, `tests/mcp/test_tools.py`
* Tests/verification: MCP behavior tests for fetch, process, manifest, and error envelopes
* Execution posture: test-first

### Unit 33: Prove manifest and envelope parity

* Changes needed: add cross-interface verification for manifest export plus success and error envelope parity
* Affected files: `tests/parity/test_cli_mcp_parity.py`, `tests/parity/test_manifest_parity.py`
* Tests/verification: parity harness covering schemas, manifests, and error shapes
* Execution posture: test-first

### Unit 34: Prove same-input CLI/MCP output equivalence

* Changes needed: verify that the same staged inputs produce equivalent fetch/process/quarantine outcomes through both interfaces
* Affected files: `tests/parity/test_e2e_equivalence.py`
* Tests/verification: same-input/same-output equivalence tests across representative source types
* Execution posture: test-first

### Unit 35: Add package metadata and executable entrypoint

* Changes needed: define installable package metadata and entrypoint behavior on top of the already-selected optional dependency contract
* Affected files: `pyproject.toml`, `src/docline/__main__.py`, `tests/cli/test_entrypoint.py`
* Tests/verification: build metadata validation and CLI entrypoint smoke tests
* Execution posture: test-first

### Unit 36: Build a local-only quarantine viewer scaffold

* Changes needed: provide a lightweight file-local or loopback-only viewer for browsing quarantine artifacts and their failure reasons with escaped rendering only, and reject remote bind/exposure modes by default
* Affected files: `src/docline/quarantine_viewer.py`, `src/docline/static/*`, `tests/quarantine/test_viewer_index.py`
* Tests/verification: viewer manifest/index tests, escaped quarantine-record rendering checks, and non-local exposure refusal checks
* Execution posture: test-first

## Shipment Plan

* Shipment 1 — Foundations and shared contracts
  * Units 1, 2, 3, 4, 5, 6, 7, 8, 9
* Shipment 2 — Fetch acquisition hardening
  * Units 10, 11, 11A, 12, 13, 14, 15, 16, 17, 18
* Shipment 3 — Process validation and quarantine
  * Units 19, 20, 21, 22, 23, 24, 25, 26, 26A, 27, 28, 29
* Shipment 4 — CLI/MCP exposure and parity
  * Units 30, 31, 32, 33, 34
* Shipment 5 — Packaging and operator tooling
  * Units 35, 36

## Dependency Graph

* Shipment 0 from the backlog-persistence plan is a hard prerequisite for all shipments below
* Unit 1 is the foundation for Units 2 to 36
* Units 3 and 4 depend on Unit 2
* Unit 5 depends on Units 2, 3, and 4
* Unit 6 depends on Unit 5
* Unit 7 depends on Unit 1 and must precede Units 15 and 16
* Unit 8 depends on Unit 5
* Unit 9 depends on Unit 8
* Unit 10 depends on Unit 5
* Unit 11 depends on Units 8 and 10
* Unit 11A depends on Unit 11
* Units 12 and 13 depend on Unit 11
* Unit 14 depends on Units 8 and 9
* Units 15, 16, and 17 depend on Units 7 and 14
* Unit 18 depends on Unit 17
* Unit 19 depends on Units 8 and 18
* Unit 20 depends on Units 3, 4, and 19
* Unit 21 depends on Units 2, 20, and 8
* Unit 22 depends on Units 18, 20, and 21
* Unit 23 depends on Unit 22
* Unit 24 depends on Units 21 and 22
* Unit 25 depends on Units 4, 21, and 24
* Unit 26 depends on Units 5 and 21
* Unit 26A depends on Unit 26
* Unit 27 depends on Units 25, 26, and 26A
* Unit 28 depends on Units 26A and 27
* Unit 29 depends on Units 9, 21, 24, 25, 27, and 28
* Unit 30 depends on Units 5 and 6
* Unit 31 depends on Units 5, 6, 8, 29, and 30
* Unit 32 depends on Units 5, 6, 8, 29, and 30
* Unit 33 depends on Units 31 and 32
* Unit 34 depends on Units 31, 32, and 29
* Unit 35 depends on Units 7, 31, and 32
* Unit 36 depends on Units 28, 29, and 35

## Harvest-ready task breakdown

The workstream units above are planning containers. Harvest should emit the atomic tasks below as the actual 2-hour execution units.

### Foundation tasks

* F1 — Establish router contracts
* F2 — Add schema core models
* F3 — Add wiki and ADR schema families
* F4 — Add transcript and web schema families
* F5 — Add shared fetch/process/manifest operation models
* F6 — Export shared manifest through CLI and MCP
* F7 — Add guarded-import and optional-dependency policy
* F8 — Add staging job records and deterministic cache paths
* F9 — Sanitize staged source metadata before persistence
* F10 — Enforce workspace path containment

### Acquisition tasks

* A1 — Add crawler URL policy and SSRF rejection
* A2 — Implement crawl executor timeout and page-cap controls
* A3 — Add robots and backoff handling
* A4 — Extract main content from HTML
* A5 — Normalize extracted heading hierarchy
* A6 — Enforce reader size, signature, and trusted-local rules
* A7 — Add PDF reader adapter
* A8 — Add DOCX reader adapter
* A9 — Add text and VTT reader adapters
* A10 — Add transcript pre-processing hooks

### Process tasks

* P1 — Generate deterministic document identity
* P2 — Resolve document type from staged content
* P3 — Assemble validated frontmatter payloads
* P4 — Normalize transcript structure
* P5 — Add transcript topic segmentation
* P6 — Assemble Markdown with validated YAML
* P7 — Implement AST lint rules
* P8 — Add correction-provider enablement and credential policy
* P9 — Add correction payload minimization and non-persistence rules
* P10 — Implement bounded correction loop
* P11 — Write quarantine artifacts safely
* P12 — Write contained Markdown outputs
* P13 — Write manifest SSOT without relationships

### Interface and packaging tasks

* I1 — Lock MCP to stdio-only local transport
* I2 — Add CLI fetch/process adapters
* I3 — Add MCP fetch/process adapters
* I4 — Prove manifest and envelope parity
* I5 — Prove same-input output equivalence
* O1 — Add package metadata and entrypoint
* O2 — Add local-only quarantine viewer

## Shipment slices

* Shipment 1 — Foundation contracts A
  * F1, F2, F3, F4, F5
* Shipment 2 — Foundation contracts B
  * F6, F7, F8, F9, F10
* Shipment 3 — Acquisition safety and crawl core
  * A1, A2, A3, A4, A5
* Shipment 4 — Reader adapters and transcript intake
  * A6, A7, A8, A9, A10
* Shipment 5 — Process identity and structure
  * P1, P2, P3, P4, P5, P6, P7
* Shipment 6 — Correction, quarantine, and outputs
  * P8, P9, P10, P11, P12, P13
* Shipment 7 — CLI/MCP exposure and parity
  * I1, I2, I3, I4, I5
* Shipment 8 — Packaging and operator tooling
  * O1, O2

## Decisions and Rationale

* Keep fetch and process isolated because the design explicitly separates I/O-bound and compute-bound execution
* Make deterministic UUID generation a first-class process concern so dedup and downstream UPSERT flows are stable
* Treat parity as shared-service design, not an afterthought, so CLI and MCP cannot drift by construction
* Place transcript specialization before AST linting so the transcript body already matches schema expectations
* Make the manifest export dual-surface from the beginning so agent-facing discovery does not become CLI-only
* Move containment, SSRF, correction-policy, and MCP transport decisions into first-class units instead of implicit hardening notes

## Risks and Caveats

* External readers and crawl tooling introduce dependency and packaging complexity
* Header normalization can corrupt structure if its root-mapping rules are underspecified
* The correction loop must preserve semantic text while changing structure only
* The repo is greenfield, so the first module boundaries may need light refinement once test harnesses exist
* Parity risks rise sharply if CLI or MCP bindings are created before the shared operation layer stabilizes

## Plan Hardening Signals

* public API, schema, or contract change: present — CLI, MCP, manifest, schema, and output contracts are core surfaces
* security, auth, permission, or compliance-sensitive behavior: present — crawler trust boundaries and external content ingestion require safety controls
* migration, backfill, destructive data/config action, or irreversible step: absent — no destructive data migration is planned
* external integration, operator checkpoint, or external dependency: present — docling, crawler libraries, transcript tooling, and LLM-assisted correction are external dependencies
* high runtime, rollout, or rollback risk: present — fetch/process concurrency, correction loops, and output-manifest correctness are high-impact runtime concerns

Requires plan hardening: yes

## Runtime Verification and Closure

* Runtime surfaces changed: CLI commands, MCP tools, crawl/fetch jobs, process pipeline, quarantine viewer
* Verification expectations:
  * fetch can stage HTML, transcript, and file inputs with bounded crawler behavior
  * process can transform staged inputs into validated Markdown or quarantine
  * manifest output remains atomic and relationship-free
  * CLI and MCP surfaces expose matching operations, manifests, and compatible success/error schemas
  * output paths remain contained under the configured workspace root
* Mandatory Ship exit gates:
  * `ruff check .`
  * `pyright src/`
  * `pytest`
  * `ruff format --check .`
* Closure artifacts:
  * parity verification summary
  * quarantine behavior summary
  * dependency/install notes for optional readers

## Constitution Check

* Principle I — Safety-first Python: preserved by keeping the design within Python package boundaries and typed schema/service contracts
* Principle II — Test-first development: every unit requires failing tests or harnesses before implementation
* Principle III/IV — Workspace containment: containment is explicit through Unit 9 and contained-output verification in Unit 29
* Principle V — Structured observability: manifest, quarantine, and parity verification are explicit outputs
* Principle VI — Single responsibility: reader, process, schema, and interface concerns remain separated
* Principle VII — Destructive command approval: no destructive step is planned; any future destructive workflow remains out of scope and approval-gated for Ship
* Principle VIII — Safety modes: investigate-first, careful, and freeze-scope are explicit in the hardening section
* Principle IX — Git-friendly persistence: manifest, quarantine, and output artifacts are explicitly structured, persisted, and reviewable
* Principle X — Context efficiency: two-stage execution and manifest SSOT avoid ambiguous downstream context
* Principle XI — Merge commit preservation: unaffected by this plan; Ship remains bound to merge-commit-only PR closure

## Plan Hardening

Hardening is required because the plan changes public contracts, introduces external integrations, and creates meaningful runtime safety obligations.

### Safety modes

* `investigate-first` for crawler policy, external readers, and correction-provider decisions
* `careful` for public contract exposure through CLI and MCP
* `freeze-scope` to `src/docline/`, `tests/`, and packaging/config files directly needed by the plan

### Protected invariants

* `manifest.json` remains an ingestion index only and never stores relationship data
* deterministic UUID generation is stable across repeated ingests of the same canonical source
* crawler execution is bounded by timeout, backoff, total-page limits, and SSRF-safe URL policy
* correction logic may alter structure but must not rewrite the core semantic payload
* CLI and MCP operations stay schema-parity aligned
* all source, staging, and output paths remain inside the configured workspace root
* external correction is opt-in and minimized before any provider call

### ProposedAction 1

* summary: Introduce external reader and crawler dependencies for fetch-stage acquisition
* targets: packaging metadata, fetch modules, runtime dependency graph
* change_kind: external integration
* rollback: disable the affected adapter behind a guarded import or remove the dependency entry
* approval_required: yes
* ActionRisk: high
* ActionResult: planned

### ProposedAction 2

* summary: Expose shared ingestion operations through both CLI and MCP contracts
* targets: CLI command surface, MCP tool surface, parity tests
* change_kind: local edit
* rollback: revert to the shared service layer revision that preserved prior interface behavior
* approval_required: yes
* ActionRisk: high
* ActionResult: planned

### ProposedAction 3

* summary: Persist validated outputs, quarantine records, and manifest updates from process-stage execution
* targets: output workspace, manifest writer, quarantine path
* change_kind: local edit
* rollback: revert output writer changes and restore prior manifest contract
* approval_required: no
* ActionRisk: moderate
* ActionResult: planned

### ProposedAction 4

* summary: Introduce correction-provider integration for structure repair
* targets: prompt construction, provider client, correction policy, redaction flow
* change_kind: external integration
* rollback: disable provider-backed correction and retain lint-plus-quarantine behavior
* approval_required: yes
* ActionRisk: high
* ActionResult: planned

### Hardened verification

* Add manifest parity tests before exposing any MCP or CLI operation publicly
* Add success and error envelope parity tests before exposing any MCP or CLI operation publicly
* Bound correction-loop retries and prove the loop emits quarantine outcomes instead of spinning
* Verify crawl limits with explicit timeout, page-cap, redirect-cap, and private-address rejection fixtures
* Verify manifest writes atomically, exclude relationship data, and keep outputs inside the configured root
* Verify external correction is default-off and redacted when enabled
* Keep shipment sequencing phase-aligned so risky external integration work follows the schema and staging foundations
