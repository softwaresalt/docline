---
type: compacted-summary
scope: memory
period: 2026-07
compacted_at: 2026-08-29
source_count: 10
---

## Overview

July 2026 memory captured a rapid sequence of Stage/Ship work focused on graphtor integration and Microsoft Learn ingestion: pre-Mistral hardening, page boundary markers, canonical URL derivation v1 and v2, CI cost controls, docling accelerator override, OpenAPI/Swagger design and implementation, Swagger-to-OpenAPI conversion, BOM handling, and external split-file `$ref` resolution for fabric REST specs. Most work ran with backlogit MCP degraded and CI paused, so local `uv run` gates, Copilot review handling, and operator-approved merge commits were the release controls.

## Key Decisions

* `045-S` pre-Mistral hardening
  * Grouped two low-priority follow-ups into one shipment at operator request while keeping them width-isolated across two commits
  * Made `load_weights` and `load_pre_triage_weights` containment opt-in via `workspace_root=None` to avoid breaking trusted absolute-path callers
  * Kept Foundry/Mistral items blocked until credentials are available
* `046-S` page boundary markers
  * Added opt-in `page_markers` to the PDF batch stitcher with default off so existing stitched output remains byte-identical
  * Skipped overlap-duplicated boundary pages using source-relative numbering and guarded tiny chunks with `len(pages) > page_overlap`
  * Reused marker stitching for the early heuristic path by populating `ChunkResult.chunk_pages` from `read_pdf_pages`
* `047-S` canonical URL v1
  * Emitted per-document `docline:canonical_url` via the existing `docline_namespace` merge, avoiding a frontmatter schema change
  * Staged publish config JSON so `_load_publish_config` can read it while `_SUPPORTED_EXTENSIONS` excludes it from processing
  * Fixed longest-match ordering before prefix checks; a wrong cross-source prefix is worse than omitting `canonical_url`
* `048-S` canonical URL v2
  * Real MS Learn repos derive URL prefixes from docfx `breadcrumb_path`, not `url_path_prefix`; v1 was effectively 0% on real repos
  * Added optional `prefixes` to preserve v1 callers while enabling breadcrumb-derived prefixes
  * Treated config `build_source_folder` as untrusted and contained it with `safe_workspace_path`
  * Modeled an unsupported `spike` type as a feature labeled `spike` because backlogit CLI did not register a spike artifact type
* `049-S` CI cost reduction
  * Added `paths-ignore` and PR-title guards, but routed branch protection to an always-running `ci-gate` aggregate job because required skipped jobs would block docs/chore PRs
  * Verified ops/config changes through YAML validity and workflow convention checks rather than red-green TDD
* `050-S` accelerator env override
  * Implemented only the verifiable slice of GPU work: `DOCLINE_ACCELERATOR` override; docling already auto-detects devices
  * Kept default `auto` behavior unchanged; `cpu`, `cuda`, `mps`, and `xpu` are explicit escape hatches
  * Resolved accelerator before conversion `try` so `PdfConfigError` is not masked as `PdfReadError`
  * Left `num_threads` at docling default to avoid thread-behavior regression
* `051-S` OpenAPI/Swagger design spike
  * Chose structured rendering rather than layout extraction for OpenAPI specs
  * Scoped v1 to per-operation rendering, local `$ref` only, and no new dependency because PyYAML was present
  * Flagged external `$ref` as an SSRF/traversal boundary for a deferred task
  * Shipped only completable and verifiable work; Foundry, GPU, scanned-corpus, release, and YAGNI envelope items remained deferred
* `050-F` OpenAPI/Swagger ingestion
  * Routed OpenAPI through an isolated `execute_process` branch rather than `_build_markdown_with_frontmatter` to avoid re-deriving or clobbering assembled doc type/source fields
  * Required OpenAPI 3.x for process ingestion; Swagger 2.0 was detected but not ingested until the converter follow-up
  * Fixed YAML integer-status-code handling and Copilot findings for README usage, Swagger 2.0 scope gate, and DRY
* `051-F` / `052-F` Swagger conversion and BOM fix
  * Stripped leading U+FEFF in Markdown frontmatter parsing and read `.md/.txt` with `utf-8-sig`
  * Added Swagger 2.0 to OpenAPI 3.x pre-conversion, reopening `_is_openapi_staged` for 2.0 after conversion existed
  * Batched related closures into one PR to reduce Copilot cycles
  * Learned converter/render helpers must be total because unexpected exceptions inside the OpenAPI branch abort the entire job
* `053-F` external split-file `$ref` resolution
  * Wrote dedicated containment that permits legitimate in-root `..` refs while rejecting URL and path escapes, because `safe_workspace_path` rejects any `..` token
  * Passed corpus-relative document paths into cross-doc link resolution so relative hrefs produce correct graph edge targets
  * Limited ref linking to one hop, verified target existence, and avoided dangling/cyclic cross-file links

## Files & Areas Modified

* OCR and scoring hardening: `scripts/study/ocr_memory_calibration.py`, `src/docline/process/fidelity_scorer.py`, associated tests
* PDF batch output: `src/docline/process/pdf_batch.py`, `tests/process/test_pdf_batch.py`
* Canonical URLs: `src/docline/process/canonical_url.py`, `src/docline/app.py`, `src/docline/cli.py`, canonical URL tests, docfx spike/plan/compound docs
* CI workflow: `.github/workflows/ci.yml`
* PDF accelerator configuration: `src/docline/readers/pdf.py`, `tests/readers/test_pdf_accelerator_env.py`, README
* OpenAPI reader stack: `src/docline/readers/openapi/detect.py`, `errors.py`, `loader.py`, `render.py`, `reader.py`, `convert.py`, `resolve.py`; `src/docline/router.py`; `src/docline/app.py`; `SourceKind.OPENAPI`; tests under OpenAPI and process suites
* Frontmatter and text parsing: `_parse_md_frontmatter`, UTF-8 BOM handling for `.md` and `.txt`
* Backlog, closure, and documentation artifacts for shipments `045-S` through `053-F`

## Key Learnings

* backlogit MCP transport can drop for an entire session; the CLI at `C:\Tools\backlogit.exe` is a viable fallback for claim, move, get, stage, ship, sync, and archive operations
* `uv run` is the reliable local runner; system `python` may lack project dependencies and bare `pyright src/` can report false import-resolution errors unless the venv is active
* Copilot bot review requests work through REST `pulls/{n}/requested_reviewers` with `reviewers[]=copilot-pull-request-reviewer[bot]`; `gh pr edit --add-reviewer` and GraphQL request paths failed
* Required branch-protection checks should target an aggregate job that always reports, not conditionally skipped jobs
* Real corpus evidence should trump assumptions: MS Learn canonical URLs come from docfx breadcrumbs, Fabric REST needed Swagger conversion, and external refs require cross-file containment rather than same-file-only logic
* `docline.paths.safe_workspace_path` is intentionally strict; cross-file spec refs need a dedicated resolver that allows in-root parent traversal while denying escapes
* Keep existing uncommitted operator changes out of shipment commits, especially `.gitignore`, `uv.lock`, workflow tune-ups, and MCP config changes
* Editable reinstall (`pip install -e . --no-deps`) matters after building a wheel so tests and CLI use current `src` changes
* When inserting tests, preserve adjacent `def` lines; Copilot caught a botched multi-test edit where a test definition was accidentally dropped
* PowerShell commit messages require care with `$` and `%` characters to avoid accidental expansion or formatting mangling

## Failed Approaches / Halts

* Mistral OCR and hybrid routing work remained blocked on Azure Foundry credentials
* GPU throughput benchmarking remained blocked on GPU hardware even though `DOCLINE_ACCELERATOR` override was verifiable
* Release workflow remained gated on a 1.0 readiness decision
* Scanned-corpus OCR calibration and generalization studies remained deferred for appropriate corpora and operator supervision
* `050-S` backlogit friction: creating a task directly with `--status done` auto-archived it without merge SHA, and done-to-active transition was blocked; the stray task had to be deleted and recreated as active
* `053-F` branch discipline slipped when implementation was committed locally on `main`; recovered non-destructively by creating the feature branch at the commit and resetting local `main` pointer to `origin/main` without disturbing working tree changes
* Some PR merges used admin bypass because CI was intentionally paused and branch protection required approvals the author could not self-provide

## Outcomes

* `045-S` merged through PR #118 with merge SHA `31c8c5e`; closure PR followed
* `046-S` merged through PR #122 with merge SHA `6f1a559`
* `047-S` merged through PR #125 with merge SHA `7a3009c`
* `048-S` canonical URL v2 merged through PR #127 with merge SHA `e0e1df5`
* `049-S` CI cost reduction merged through PR #130 with merge SHA `cd56682`
* `050-S` accelerator override merged through PR #132 with merge SHA `dc427aa`; OpenAPI design spike `051-S` merged through PR #134 with merge SHA `8059eba`
* `050-F` OpenAPI ingestion merged through PR #136 with merge SHA `27df3c3` and archived
* `052-F` BOM fix merged through PR #138 with merge SHA `6889c4e`; `051-F` Swagger conversion merged through PR #139 with merge SHA `c6dd151`
* `053-F` external `$ref` resolution merged through PR #142 with merge SHA `e6ee9cb`, raising Fabric operation cross-linking from 0% to 78% with no dangling links

## Archived Originals

| Original | Archive path |
|---|---|
| `docs/memory/2026-07-03/045-S-ship-session-memory.md` | `docs/archive/memory/2026-07-03/045-S-ship-session-memory.md` |
| `docs/memory/2026-07-03/046-S-ship-session-memory.md` | `docs/archive/memory/2026-07-03/046-S-ship-session-memory.md` |
| `docs/memory/2026-07-04/047-S-ship-session-memory.md` | `docs/archive/memory/2026-07-04/047-S-ship-session-memory.md` |
| `docs/memory/2026-07-04/048-S-ship-session-memory.md` | `docs/archive/memory/2026-07-04/048-S-ship-session-memory.md` |
| `docs/memory/2026-07-04/049-S-ship-session-memory.md` | `docs/archive/memory/2026-07-04/049-S-ship-session-memory.md` |
| `docs/memory/2026-07-04/050-S-ship-session-memory.md` | `docs/archive/memory/2026-07-04/050-S-ship-session-memory.md` |
| `docs/memory/2026-07-04/051-S-ship-session-memory.md` | `docs/archive/memory/2026-07-04/051-S-ship-session-memory.md` |
| `docs/memory/2026-07-05/050-F-openapi-ingestion-memory.md` | `docs/archive/memory/2026-07-05/050-F-openapi-ingestion-memory.md` |
| `docs/memory/2026-07-05/051-052-openapi-swagger-bom-memory.md` | `docs/archive/memory/2026-07-05/051-052-openapi-swagger-bom-memory.md` |
| `docs/memory/2026-07-05/053-F-external-ref-resolution-memory.md` | `docs/archive/memory/2026-07-05/053-F-external-ref-resolution-memory.md` |
