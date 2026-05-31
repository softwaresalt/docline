---
title: "Backlog persistence prerequisite plan"
description: "Implementation plan for making Stage and Ship backlog artifacts survive normal repository handoff."
source_documents:
  - "docs/decisions/2026-05-30-backlog-persistence-prerequisite-deliberation.md"
  - ".gitignore"
tags:
  - "operations"
  - "backlogit"
  - "persistence"
---

# Backlog persistence prerequisite plan

## Problem Frame

The repository uses backlogit as the operational source of truth, but `.gitignore` currently ignores `.backlogit/`. That makes queued work, shipments, and related agent handoff artifacts local-only. Before Ship starts executing the design backlog, we need a minimal persistence contract that preserves durable backlog artifacts without accidentally tracking runtime cache files.

## Requirements Trace

* Preserve backlogit as the authoritative work tracker
  * Define a tracked durable-artifact subset or equivalent persistence mechanism
* Avoid tracking volatile local state
  * Keep database, WAL, editor, and lock artifacts ignored
* Preserve Stage-to-Ship handoff integrity
  * Ensure queued work and shipments survive clone, branch, and PR workflows
* Preserve content hygiene for newly tracked artifacts
  * Keep secrets, machine-local paths, and volatile telemetry out of the tracked subset

## Implementation Units

### Unit 1: Define the durable backlog artifact contract

* Changes needed: choose the minimal set of `.backlogit/` artifacts that must persist for work tracking and shipment handoff, and define an allowlist for durable files versus ignored runtime state
* Affected files: `.gitignore`, `.backlogit/registry.yaml`, repository backlog conventions docs as needed
* Tests/verification: failing harness proving the chosen contract includes queue/shipment artifacts and excludes DB/cache files
* Execution posture: test-first

### Unit 2: Apply the repository tracking rule and artifact layout updates

* Changes needed: update ignore rules and any supporting backlogit layout/config so durable artifacts are trackable and unsafe artifact classes remain ignored
* Affected files: `.gitignore`, `.backlogit/` durable artifact layout files
* Tests/verification: verify newly created queue and shipment artifacts appear in Git status while runtime DB files remain ignored
* Execution posture: test-first

### Unit 3: Add artifact-hygiene and sync verification

* Changes needed: define screening rules for newly tracked backlog artifacts and require a `backlogit sync` verification after direct layout changes
* Affected files: repository backlog conventions docs, workflow docs, optional backlogit config
* Tests/verification: prove that tracked artifacts avoid secrets/machine-local metadata and that index refresh reflects the new durable layout
* Execution posture: test-first

### Unit 4: Prove Stage-to-Ship handoff durability

* Changes needed: document and verify the minimal operator flow that creates a backlog item, creates a shipment, and confirms the resulting artifacts survive standard Git-based handoff
* Affected files: docs or closure artifact paths plus backlog-generated artifacts
* Tests/verification: demonstrate a sample artifact chain remains visible after sync/branch operations and passes a stop/go review checkpoint
* Execution posture: test-first

## Dependency Graph

* Unit 2 depends on Unit 1
* Unit 3 depends on Unit 2
* Unit 4 depends on Unit 2 and Unit 3

## Decisions and Rationale

* Treat the problem as an operational prerequisite rather than embedding it inside the design feature, because it blocks reliable use of the staged backlog itself
* Prefer the smallest persistence contract that keeps queue and shipment artifacts durable while leaving ephemeral runtime data ignored
* Treat this plan as Shipment 0 for the design program; no ingestion shipment should begin until this prerequisite passes review

## Risks and Caveats

* Over-broad Git tracking can create noisy diffs or leak local state
* Under-broad tracking leaves Stage/Ship handoff incomplete
* Newly tracked queue artifacts may still expose sensitive notes or local paths if hygiene rules are not explicit

## Plan Hardening Signals

* public API, schema, or contract change: present — repository workflow contract changes for backlog persistence
* security, auth, permission, or compliance-sensitive behavior: absent — no auth surface expected
* migration, backfill, destructive data/config action, or irreversible step: absent — config change only, reversible in Git
* external integration, operator checkpoint, or external dependency: present — the workflow must remain compatible with backlogit and Git handoff expectations
* high runtime, rollout, or rollback risk: absent — low runtime risk, straightforward rollback through Git

Requires plan hardening: yes

## Runtime Verification and Closure

* Runtime surface changed: repository/operator workflow for backlog persistence
* Verification:
  * confirm durable backlog files are trackable
  * confirm ephemeral DB/cache files remain ignored
  * run `backlogit sync` after direct layout edits and verify the index rehydrates cleanly
  * stop at a formal review checkpoint before declaring the persistence contract ready for Ship
* Closure artifact: short operational note proving the supported handoff path and any remaining limitations

## Constitution Check

* Principle II — Test-first development: preserved by requiring verification before adoption
* Principle I — Safety-first Python: the prerequisite only changes repository workflow/config and does not add non-Python production surfaces
* Principle III/IV — Workspace containment: preserved; changes stay inside repo
* Principle V — Structured observability: preserved via backlog and closure artifacts
* Principle VI — Single responsibility: the prerequisite is isolated to backlog persistence and does not absorb unrelated product work
* Principle VII — Destructive command approval: no destructive command is required; any rollback is Git-reversible
* Principle VIII — Safety modes: investigate-first, careful, and freeze-scope are explicit in the hardening section
* Principle IX — Git-friendly persistence: this plan exists to restore Git-mergeable durability for backlog artifacts
* Principle X — Context efficiency: preserved by keeping backlogit authoritative instead of duplicating state
* Principle XI — Merge commit preservation: unaffected; Ship remains bound to merge-commit-only closure

## Plan Hardening

Hardening required because this work changes the repository's operational contract for backlog durability.

### Safety modes

* `investigate-first` while deciding the durable artifact allowlist
* `careful` while changing `.gitignore` and tracked backlog layout
* `freeze-scope` to `.gitignore`, `.backlogit/`, and directly related workflow docs

### ProposedAction 1

* summary: Narrow the ignore contract so durable backlog artifacts can be tracked
* targets: `.gitignore`, durable `.backlogit/` artifact paths
* change_kind: config change
* rollback: restore the prior ignore pattern in Git
* approval_required: no
* ActionRisk: moderate
* ActionResult: planned

### Hardened verification

* Explicitly verify that queue and shipment artifacts become trackable
* Explicitly verify that `.backlogit/backlogit.db`, WAL, and other runtime files remain ignored
* Explicitly verify that tracked backlog artifacts exclude secrets, machine-local paths, and volatile telemetry
* Run `backlogit sync` after direct layout edits and confirm the rehydrated index matches the durable artifact set
* Require a final stop/go review checkpoint before Shipment 0 is marked ready
* Stop if the chosen contract requires tracking volatile runtime state
