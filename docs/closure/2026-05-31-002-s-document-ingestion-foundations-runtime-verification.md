---
title: "Runtime verification - 002-S document ingestion foundations"
shipment: "002-S"
surface: "cli/mcp/schema/fetch"
mode: "manual"
status: "pass"
verified_at: "2026-05-31"
merge_commit: "cf7e8d5236409f882a5f759ad141424baeef017b"
---

## Scope

* Shared router, schema, manifest, staging, and workspace-containment surfaces
* CLI and MCP manifest parity support
* Shipment archival path for `002-S`

## Environment prechecks

* PR `#4` merged to `main` at `2026-05-31T09:54:14Z`
* Merge commit `cf7e8d5236409f882a5f759ad141424baeef017b` is in `origin/main`
* Reconcile reports were recorded under `.backlogit/reconcile/`

## Evidence

* `python -m py_compile src/docline/__init__.py` -> exit `0`
* `ruff check .` -> passed
* `pyright src/` -> `0` errors
* `pytest` -> `193` passed
* `ruff format --check .` -> passed
* `backlogit shipment ship 002-S --sha cf7e8d...` succeeded and archived
  `002-F`, `002-S`, and `002.001-T` through `002.010-T`

## Risky action record

* ProposedAction: merge PR `#4` without a fresh Copilot review on current HEAD
* ActionRisk: high
* Approval path: explicit operator override after zero unresolved Copilot
  threads and failed fresh-review request paths
* ActionResult: applied

## Invariants preserved

* Boundary models remain schema-valid and parity-tested across CLI and MCP
* Staging metadata sanitization strips credentials and unsafe local-path forms
* Workspace containment rejects absolute, rooted, UNC, and traversal inputs
* Shipment archival landed with matching queue-to-archive evidence

## Verdict

PASS

## Follow-up

* No shipment-local runtime follow-up was identified during closure
