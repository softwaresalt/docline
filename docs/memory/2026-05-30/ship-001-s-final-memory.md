---
title: "Ship memory - 001-S final"
shipment: "001-S"
branch: "post-merge/001-backlog-artifact-persistence-prerequisite"
status: "complete"
---

## Final outcome

* PR `#2` merged to `main` at `2026-05-31T03:12:18Z`
* Merge commit: `b7e3faa0bbe7be7ea9eb220f6d963911f41bd160`
* Shipment `001-S` is shipped and archived

## Branch and PR state

* Source branch: `feat/backlog-artifact-persistence-prerequisite`
* Post-merge docs branch: `post-merge/001-backlog-artifact-persistence-prerequisite`
* PR state: `#2` merged into `main`

## Archival state

* `backlogit shipment ship 001-S --sha b7e3faa...` succeeded
* Archived IDs: `001.001-T`, `001.002-T`, `001.003-T`, `001.004-T`, `001-F`,
  `001-S`
* Pre/post reconcile reports already exist in `.backlogit/reconcile/`

## Decisions

* Final fix: `_git_ignores()` catches `FileNotFoundError` and raises
  `_GitCheckIgnoreError` with actionable PATH guidance
* Fresh Copilot review could not be requested after the final push, so merge
  proceeded only under the explicit shipment-`001-S` operator override after
  existing Copilot threads were resolved

## Next routing

* No shipment-local backlog item was opened from this evidence
* Orchestrator should decide the next routing
