---
title: "ELT multi-source ingestion staging deliberation"
description: "Deliberation outcome for the .elt staging area, multi-config loading, and end-to-end multi-source validation feature."
topic: "ELT Multi-Source Ingestion Pipeline"
depth: "standard"
decision_status: "decided"
promoted_to: "plan"
linked_artifacts:
  - "docs/plans/2026-06-01-elt-multi-source-ingestion-plan.md"
tags:
  - "elt"
  - "config"
  - "multi-source"
  - "ingestion"
  - "validation"
stash_ids:
  - "D37D8AF7"
  - "5F0C557E"
---

# ELT multi-source ingestion staging deliberation

## Problem Frame

The docline pipeline currently has a single-source staging model (`fetch/staging.py`) and no concept of a configuration directory that declares multiple ingestion sources. Two related stash entries describe:

1. **D37D8AF7** — Support loading multiple configuration files from directories such as `.elt/config`
2. **5F0C557E** — End-to-end validation for multi-source ingestion using the `.elt` staging area with YAML-defined website and GitHub sources, ensuring all source types normalize to schema-conformant markdown

These entries share the `.elt/` staging directory as a common workspace concept: `.elt/config/` holds YAML source definitions, and `.elt/` serves as the local extract-land-transform staging area for fetched content (PDFs, DOCX, web crawl, GitHub repos).

The covering feature must also account for the `.gitignore` entry (`.elt/` added to `.gitignore`) since the staging area contains local transient content that must not be committed.

## Research Findings

* `src/docline/config.py` — Only handles `CorrectionProviderConfig`; no multi-file config loader exists
* `src/docline/fetch/staging.py` — Has `StagingJob` and `create_staging_job` for single-source staging with deterministic IDs and sharded cache paths
* `src/docline/cli.py` — `fetch` and `process` commands are stubs returning exit code 1
* `src/docline/fetch/models.py` — `SourceMetadata` captures source, timestamp, HTTP status, content type
* Test suite has thorough unit coverage for staging, crawl, URL policy, but no multi-config or multi-source integration tests
* No `.elt/` directory concept exists in the codebase yet
* The existing `paths.py` module enforces workspace containment — the `.elt/` directory must resolve within workspace root

## Options Evaluated

### Option A: Minimal config loader only (D37D8AF7 alone)

Build a config directory scanner that discovers YAML files in `.elt/config/`, parses them into typed source descriptors, but defer end-to-end validation to a later session.

**Pro**: Smaller scope, faster delivery.
**Con**: Leaves 5F0C557E unaddressed; config loader without validation has no verifiable integration path.

### Option B: Full ELT staging feature (D37D8AF7 + 5F0C557E together)

Build the config loader AND the end-to-end validation in one feature. The config loader defines what sources exist; the validation proves the full pipeline works across PDF, DOCX, web crawl, and GitHub sources through to schema-conformant markdown output.

**Pro**: Coherent feature that delivers a testable capability; both stash entries resolved together.
**Con**: Larger scope — needs careful task decomposition to stay within 2-hour task limits.

### Option C: ELT staging feature with deferred GitHub source type

Like Option B but defer GitHub repository sources to a later feature, focusing first on local files (PDF/DOCX) and web crawl sources.

**Pro**: Reduces blast radius by removing the most complex source type.
**Con**: 5F0C557E explicitly requests GitHub sources; partial delivery contradicts operator intent.

## Trade-off Comparison

| Criterion | Option A | Option B | Option C |
|---|---|---|---|
| Stash entry resolution | Partial (1 of 2) | Complete (2 of 2) | Partial (intent gap) |
| Testable integration path | Poor | Best | Good |
| Task decomposition safety | Easy | Manageable with discipline | Easy |
| Operator alignment | Poor | Best | Moderate |

## Decision

**Option B selected.** Both stash entries form one coherent feature: "ELT multi-source ingestion with config directory support." The config loader is the enabler; the end-to-end validation is the proof. Decomposition into 2-hour tasks keeps scope safe.

## Covering Feature Scope

**Title**: ELT multi-source ingestion pipeline

**Scope**:

1. `.elt/` staging area directory convention and `.gitignore` entry
2. YAML config file discovery and parsing from `.elt/config/`
3. Typed source descriptors (local file, website crawl, GitHub repo)
4. Config-driven multi-source fetch orchestration (extending existing staging.py)
5. End-to-end validation tests proving PDF, DOCX, web crawl, and GitHub sources all normalize to schema-conformant markdown
6. CLI integration (`docline fetch` reads from `.elt/config/`)

**Out of scope**: MCP adapter changes (covered by 005-F/005-S), packaging changes (covered by 006-F/006-S), production deployment, performance optimization.

## .gitignore Decision

The `.elt/` entry in `.gitignore` is an integral part of this feature — it defines the local staging workspace that must not be committed. It should travel with this feature's shipment at Ship time as part of the first task that establishes the `.elt/` directory convention.
