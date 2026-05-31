---
title: "Backlog persistence prerequisite deliberation"
description: "Deliberation outcome for the operational prerequisite caused by .backlogit being ignored in Git."
topic: "Backlog artifact persistence prerequisite"
depth: "standard"
decision_status: "decided"
promoted_to: "plan"
linked_artifacts:
  - ".gitignore"
  - ".backlogit/"
  - "docs/plans/2026-05-30-backlog-persistence-prerequisite-plan.md"
tags:
  - "backlogit"
  - "operations"
  - "shipment"
  - "stage"
stash_ids:
  - "EA04770A"
---

# Backlog persistence prerequisite deliberation

## Problem Frame

Stage and Ship rely on `.backlogit/` as the structured source of truth for backlog items, checkpoints, and shipments. The current repository ignores `.backlogit/`, so locally created work artifacts do not naturally survive Git-based handoff. That creates a planning and execution integrity gap even if the local backlog workspace behaves correctly.

## Research Findings

The repository has an active local backlogit workspace and the CLI is healthy. The backlog registry is tracked in `.autoharness/`, but the actual queue and shipment artifacts live under `.backlogit/`. Without a persistence fix or alternative export contract, a later Ship session on another clone or branch may not see the staged backlog state that this session creates.

## Options Evaluated

### Option A: Accept local-only backlog state

Proceed without a prerequisite and rely on local continuity only. This is fastest now but makes remote orchestration and traceability fragile.

### Option B: Manually restate backlog state outside backlogit

Keep `.backlogit/` ignored and mirror the plan in prose elsewhere. This creates duplicate state and violates the backlog-first operating model.

### Option C: Create a small operational prerequisite release unit

Ship a narrowly scoped persistence fix so backlog artifacts that Stage creates can survive normal handoff and review workflows.

## Decision

Choose Option C.

The repository should execute a small prerequisite shipment before implementation of the design feature begins. This keeps the design backlog authoritative instead of duplicating it into ad hoc markdown trackers.

## Rejected Alternatives

Option A was rejected because it weakens remote handoff. Option B was rejected because it introduces parallel task tracking outside the configured backlog workspace.

## Unresolved Questions

* Whether the chosen persistence fix is selective tracking of backlog artifacts, an export mirror, or another minimal contract-preserving approach
* Whether runtime cache files remain ignored while queue and shipment Markdown are tracked

## Risks and Mitigations

* Risk: broad `.gitignore` changes accidentally capture volatile backlog database files
  * Mitigation: scope the prerequisite to durable artifact files only and keep ephemeral DB files ignored
* Risk: Stage work becomes blocked if the persistence contract is deferred
  * Mitigation: make this the next shipment before design implementation begins
