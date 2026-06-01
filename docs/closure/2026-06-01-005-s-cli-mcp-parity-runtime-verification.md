---
title: "Runtime verification - 005-S CLI and MCP parity"
shipment: "005-S"
surface: "cli/mcp/parity"
mode: "manual"
status: "pass"
verified_at: "2026-06-01"
merge_commit: "160153ac56851b69dd97c2a07cf1129543ddbdea"
---

## Scope

* CLI and MCP parity surfaces for manifest, fetch, process, and stdio transport enforcement
* Shipment archival path for `005-S`

## Environment prechecks

* PR `#12` merged to `main` at `2026-06-01T17:44:35Z`
* Merge commit `160153ac56851b69dd97c2a07cf1129543ddbdea` is in `origin/main`
* `backlogit shipment ship 005-S` completed and `backlogit sync` refreshed the index

## Evidence

* `python -m py_compile src/docline/__init__.py` -> exit `0`
* `ruff check .` -> passed
* `pyright src/` -> `0` errors
* `pytest` -> exit `0` after collecting `424` tests
* `ruff format --check .` -> passed
* `backlogit shipment ship 005-S --sha 160153ac...` archived `005-F`, `005-S`, and `005.001-T` through `005.005-T`

## Risky action record

* ProposedAction: merge PR `#12` with `--merge --admin` after GitHub remained blocked on stale review state
* ActionRisk: high
* Approval path: explicit operator approval for PR `#12`
* ActionResult: applied

## Invariants preserved

* CLI and MCP adapter surfaces compile and pass lint, typecheck, test, and format gates on merged `main`
* Shipment archival landed with matching queue-to-archive state in backlogit
* No `008-S` intake or stash work was folded into shipment `005-S`

## Verdict

PASS

## Follow-up

* No shipment-local follow-up backlog items were identified during runtime verification
