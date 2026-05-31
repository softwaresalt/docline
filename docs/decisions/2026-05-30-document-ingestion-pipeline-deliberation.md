---
title: "Document ingestion pipeline staging deliberation"
description: "Deliberation outcome for staging the full document ingestion and schema validation pipeline design into phased backlog execution."
topic: "Document Ingestion and Schema Validation Pipeline"
depth: "standard"
decision_status: "decided"
promoted_to: "plan"
linked_artifacts:
  - "docs/design-docs/DocumentIngestion&ValidationPipelineDesign.md"
  - "docs/plans/2026-05-30-document-ingestion-pipeline-plan.md"
tags:
  - "ingestion"
  - "schema"
  - "cli"
  - "mcp"
  - "stage"
stash_ids:
  - "C5B2DACB"
---

# Document ingestion pipeline staging deliberation

## Problem Frame

We need to convert the design in `docs/design-docs/DocumentIngestion&ValidationPipelineDesign.md` into execution-ready backlog work without losing scope. The design is a full program of work, not a single MVP slice. Stage must therefore represent the whole body of work, preserve the design doc's phase order, and still decompose work into 2-hour implementation units that Ship can execute safely.

The solution must preserve dual CLI and MCP parity, the two-stage fetch/process architecture, schema-enforced Markdown output, deterministic document identity, crawler safety controls, transcript handling, and manifest generation rules. Because `.backlogit/` is ignored in Git, we must also decide whether a prerequisite operational shipment is needed before relying on backlog artifacts for remote handoff.

## Research Findings

The design doc already provides the authoritative requirements, phase ordering, and architectural constraints. The local backlog workspace supports features, tasks, subtasks, dependencies, stash, deliberation artifacts, and shipments. The compound learnings library is empty, so no prior reusable solution constrains this plan.

The backlog workspace has one operational caveat: `.gitignore` ignores `.backlogit/`, which means the Stage-generated backlog and shipment artifacts are locally valid but may not persist through normal Git-based handoff unless the repository's artifact persistence contract is corrected.

## Options Evaluated

### Option A: Stage only the first implementation phase

Represent Phase 1 only and defer later phases until implementation begins. This keeps the first shipment tight, but it violates the operator request to represent the whole design up front and hides downstream dependencies.

### Option B: Stage the entire design as one undifferentiated feature

Create one feature with a large flat task list and one shipment. This preserves scope but creates execution ambiguity, makes review weaker, and does not respect the design doc's phase boundaries.

### Option C: Stage the full design as phased backlog with ordered shipments

Represent the complete design as one covering feature, decompose the work into atomic tasks, attach explicit dependencies, and create multiple queued shipments that follow the design doc's phases. Handle the `.backlogit/` persistence risk as a separate prerequisite release unit.

## Trade-off Comparison

| Criterion | Option A | Option B | Option C |
|---|---|---|---|
| Full scope representation | Poor | Good | Best |
| Phase clarity | Good | Poor | Best |
| Shipment handoff quality | Poor | Poor | Best |
| Compliance with operator request | Poor | Partial | Best |
| Risk isolation | Medium | Poor | Best |

## Decision

Choose Option C.

We will stage the full design as a single covering feature with phase-ordered atomic tasks and explicit dependencies, then assemble queued shipments that follow the design doc's implementation phases. We will also create a separate tightly scoped operational prerequisite release unit to address backlog artifact persistence, because the ignored `.backlogit/` directory materially weakens Stage-to-Ship handoff durability.

## Rejected Alternatives

We rejected staging only the first phase because it leaves the rest of the design implicit and contradicts the operator's request. We rejected a single undifferentiated shipment because it obscures dependencies, exceeds reliable execution scope, and weakens review and planning quality.

## Unresolved Questions

* The repository is still greenfield, so exact module names under `src/docline/` remain implementation-time choices
* The precise shipment size cut between Phase 1 foundations and later Phase 1 ingestion adapters may shift once Ship creates the first failing harnesses

## Risks and Mitigations

* Risk: CLI and MCP parity drifts during implementation
  * Mitigation: make parity a first-class implementation unit with dedicated verification
* Risk: crawler and extraction work creates broad runtime blast radius
  * Mitigation: keep fetch work behind explicit timeout, page-limit, and staging-cache tasks
* Risk: the full program is under-represented if only immediate work is harvested
  * Mitigation: queue later shipments now and wire explicit task dependencies
* Risk: backlog artifacts remain local-only because `.backlogit/` is ignored
  * Mitigation: create and prioritize an operational prerequisite shipment
