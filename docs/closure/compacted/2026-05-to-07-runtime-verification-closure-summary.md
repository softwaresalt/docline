---
type: compacted-summary
scope: closure
period: 2026-05..2026-07
compacted_at: 2026-08-29
source_count: 9
---

## Overview

This compacted closure summary consolidates old runtime-verification and closure records for completed, merged shipments `001-S` through `007-S`, plus the 2026-07-06 stash follow-ups and release setup record. The source records covered backlog artifact persistence, ingestion foundations, document acquisition and reader adapters, processing validation and output generation, CLI/MCP parity, packaging and quarantine tooling, the follow-up pyright regression fix, final crawl and HTML fidelity stash items, and release automation.

## Verification Outcomes

* `001-S` backlog artifact persistence: PASS. Verified repository ignore behavior for durable and volatile backlogit artifacts, the missing-`git` regression path in `_git_ignores()`, and shipment archival. Healthy signals included successful compile, lint, typecheck, test, and format gates, plus successful archive of `001-F`, `001-S`, and child tasks. Follow-up was limited to restoring fresh Copilot review requestability.
* `002-S` document ingestion foundations: PASS. Verified shared router, schema, manifest, staging, workspace containment, and CLI/MCP manifest parity support. Healthy signals included successful compile, lint, typecheck, test, and format gates, plus successful shipment archival. No shipment-local runtime follow-up was identified.
* `003-S` document acquisition and reader adapters: PASS. Verified fetch URL policy, redirect validation, crawl controls, HTML extraction, reader limits, document adapters, and transcript preprocessing. Healthy signals included successful compile, lint, typecheck, test, and format gates, with unsafe crawl and redirect targets remaining policy-rejected. No shipment-local runtime follow-up was identified.
* `004-S` document ingestion processing validation and outputs: WARN, not a final verification PASS. Runtime-oriented tests passed and shipment archival completed, but `pyright src/` reported six errors in `src/docline/process/ast_lint.py` and `src/docline/process/metadata.py`. The follow-up was captured as stash item `F6CCF29C` and later cleared by `007-S`.
* `005-S` CLI and MCP parity: PASS. Verified manifest, fetch, process, and stdio transport parity surfaces. Healthy signals included successful compile, lint, typecheck, test, and format gates, plus shipment archival of `005-F`, `005-S`, and tasks `005.001-T` through `005.005-T`. No shipment-local follow-up was identified.
* `006-S` packaging and quarantine tooling: PASS. Verified richer package metadata, `python -m docline --manifest`, and the file-local quarantine viewer. Healthy signals included passing package entrypoint tests, quarantine viewer parity/security tests, full local quality gates, workspace-contained artifact rendering, escaped HTML output, and handled CLI errors for unsafe inputs. No pre-merge follow-up was identified.
* `007-S` pyright type regressions: PASS. Verified the process-module pyright regression fixes in `src/docline/process/metadata.py` and `src/docline/process/ast_lint.py`. Healthy signals included successful compile, lint, typecheck, test, and format gates, plus successful archive of `007-F`, `007.001-T`, and `007-S`. No shipment-local runtime follow-up was identified.
* 2026-07-06 stash follow-ups and release setup: verified. Cleared stash items `5A27C137`, `B0A77532`, and `7AA9FAA0` through PRs `#151`, `#152`, and `#153`. Verification covered crawl section-scope containment, HTML extraction fidelity, and tag-driven PyPI release workflow setup.

## Monitoring / Release Notes

* Crawl scope follow-up `5A27C137` fixed `_derive_section_scope` so crawls of sub-paths remain under the full start-path directory prefix. The PostgreSQL operational workaround was no longer needed after this change.
* HTML fidelity follow-up `B0A77532` preserved definition lists, table spans, language-tagged code fences, canonical URLs for web sources, and single-shot crawl page budgets. Real PostgreSQL `sql-select.html` verification preserved six definition-list terms, 72 code fences, and canonical URL metadata.
* Release setup follow-up `7AA9FAA0` added a tag-driven `release.yml` workflow for `v*` tags, with quality gates, package build, version matching, PyPI Trusted Publishing, and GitHub Release artifact publication.
* The first intended release version was `0.1.0`, cut from `v0.1.0` after external PyPI Trusted Publisher and GitHub Environment setup.
* Release workflow actions were SHA-pinned, permissions were least-privilege, CI release triggers were deduplicated, and `docs/RELEASING.md` documented the version scheme and release procedure.

## Follow-ups

* Restore fresh Copilot review requestability for the repository, carried from `001-S`.
* `004-S` pyright regressions were identified as stash item `F6CCF29C` and resolved by `007-S`.
* Before the first PyPI release, an operator must register the PyPI Trusted Publisher for owner `softwaresalt`, repo `docline`, workflow `release.yml`, environment `pypi`, and create the matching `pypi` GitHub Environment.
* Remaining stash entries after 2026-07-06 required external resources such as Azure Foundry credentials, GPU hardware, or specific document corpora, or were speculative deferrals.

## Archived Originals

* `2026-05-31-001-s-backlog-artifact-persistence-runtime-verification.md` -> `docs/archive/closure/2026-05-31-001-s-backlog-artifact-persistence-runtime-verification.md`
* `2026-05-31-002-s-document-ingestion-foundations-runtime-verification.md` -> `docs/archive/closure/2026-05-31-002-s-document-ingestion-foundations-runtime-verification.md`
* `2026-05-31-003-s-document-ingestion-acquisition-and-reader-adapters-runtime-verification.md` -> `docs/archive/closure/2026-05-31-003-s-document-ingestion-acquisition-and-reader-adapters-runtime-verification.md`
* `2026-05-31-004-s-document-ingestion-processing-validation-and-outputs-runtime-verification.md` -> `docs/archive/closure/2026-05-31-004-s-document-ingestion-processing-validation-and-outputs-runtime-verification.md`
* `2026-05-31-007-s-fix-pyright-type-regressions-runtime-verification.md` -> `docs/archive/closure/2026-05-31-007-s-fix-pyright-type-regressions-runtime-verification.md`
* `2026-06-01-005-s-cli-mcp-parity-runtime-verification.md` -> `docs/archive/closure/2026-06-01-005-s-cli-mcp-parity-runtime-verification.md`
* `2026-06-01-006-s-closure.md` -> `docs/archive/closure/2026-06-01-006-s-closure.md`
* `2026-06-01-006-s-runtime-verification.md` -> `docs/archive/closure/2026-06-01-006-s-runtime-verification.md`
* `2026-07-06-stash-followups-and-release.md` -> `docs/archive/closure/2026-07-06-stash-followups-and-release.md`
