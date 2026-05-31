---
title: "Runtime verification - 001-S backlog artifact persistence prerequisite"
shipment: "001-S"
surface: "cli/repository"
mode: "manual"
status: "pass"
verified_at: "2026-05-31"
merge_commit: "b7e3faa0bbe7be7ea9eb220f6d963911f41bd160"
---

## Scope

* Repository ignore contract for durable and volatile backlogit artifacts
* Missing-`git` regression path in `_git_ignores()`
* Shipment archival path for `001-S`

## Environment prechecks

* PR `#2` is merged to `main` at `2026-05-31T03:12:18Z`
* Merge commit `b7e3faa0bbe7be7ea9eb220f6d963911f41bd160` is the shipped head
* Reconcile reports already exist under `.backlogit/reconcile/`

## Evidence

* `python -m py_compile src/docline/__init__.py` -> exit `0`
* `ruff check .` -> passed
* `pyright src/` -> `0` errors
* `pytest` -> `19` passed
* `ruff format --check .` -> passed
* `_git_ignores()` now catches `FileNotFoundError` and raises
  `_GitCheckIgnoreError` with actionable PATH guidance
* `backlogit shipment ship 001-S --sha b7e3faa...` succeeded and archived
  `001.001-T`, `001.002-T`, `001.003-T`, `001.004-T`, `001-F`, and `001-S`

## Risky action record

* ProposedAction: merge PR `#2` without a fresh post-push Copilot review
* ActionRisk: high
* Approval path: explicit operator override for shipment `001-S` after all
  existing Copilot threads were resolved and fresh review requests failed
* ActionResult: applied

## Invariants preserved

* Durable backlog markdown and config remain Git-trackable
* Volatile backlog runtime artifacts remain ignored
* Missing `git` produces an actionable failure instead of an opaque traceback
* Shipment archival landed with matching pre/post reconcile evidence

## Verdict

PASS

## Follow-up

* Minimal candidate only: restore fresh Copilot review requestability for this
  repository
