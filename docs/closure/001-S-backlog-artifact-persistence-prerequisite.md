---
title: "Closure - 001-S Backlog Artifact Persistence Prerequisite"
shipment: "001-S"
branch: "feat/backlog-artifact-persistence-prerequisite"
pr: "2"
merge_commit: "b7e3faa0bbe7be7ea9eb220f6d963911f41bd160"
merged_at: "2026-05-31T03:12:18Z"
status: "merged-shipped"
---

## Outcome

Shipment `001-S` is merged and shipped. PR `#2` merged to `main` at
`2026-05-31T03:12:18Z` with merge commit
`b7e3faa0bbe7be7ea9eb220f6d963911f41bd160`.

## Final shipped scope

| Change | Surface | Final state |
|---|---|---|
| Targeted backlog ignore contract | `.gitignore` | Durable backlog markdown and config remain trackable while volatile runtime artifacts stay ignored |
| Persistence contract coverage | `tests/test_backlog_persistence_contract.py` | Durable, volatile, and missing-`git` paths are covered under the final green suite |
| Minimal Python bootstrap | `pyproject.toml`, `src/docline/__init__.py`, `tests/` | Repository quality gates run cleanly in the shipped baseline |

## Final fix before merge

* Commit `66e8843679810a9d9cfff2447db036637c38f4e2`
  `fix(core): handle missing git in ignore contract` updated `_git_ignores()`
  to catch `FileNotFoundError` and raise `_GitCheckIgnoreError` with actionable
  PATH guidance
* The missing-`git` regression test was added first per TDD and ships in the
  final `pytest` total of 19 passing tests
* Commit `b8c961a62e4b75572c5bc3f4a4b2d27e27620d4f`
  `ops(docs): refresh archived feature commit trace` recorded the final archive
  trace before merge

## Review and merge disposition

* Existing Copilot review threads were resolved before merge
* Fresh Copilot review could not be requested after the final push:
  * `gh pr edit 2 --add-reviewer copilot` -> `'copilot' not found`
  * REST request for `copilot-pull-request-reviewer` -> `422 not a collaborator`
* Stale-review merge proceeded under an explicit operator-approved override for
  shipment `001-S` only

### Risky action record

* ProposedAction: merge PR `#2` without a fresh post-push Copilot review
* ActionRisk: high
* Approval path: explicit operator override after existing Copilot threads were
  resolved and fresh review request paths failed
* ActionResult: applied

## Verification

See the runtime verification report:
[`2026-05-31-001-s-backlog-artifact-persistence-runtime-verification.md`](2026-05-31-001-s-backlog-artifact-persistence-runtime-verification.md).

Final gates before merge:

* `python -m py_compile src/docline/__init__.py` -> exit `0`
* `ruff check .` -> passed
* `pyright src/` -> `0` errors
* `pytest` -> `19` passed
* `ruff format --check .` -> passed

## Archival state

* `backlogit shipment ship 001-S --sha b7e3faa...` succeeded
* Archived IDs: `001.001-T`, `001.002-T`, `001.003-T`, `001.004-T`, `001-F`,
  `001-S`
* Reconcile evidence already exists and both reports recommend `PROCEED`:
  * `.backlogit/reconcile/001-S-pre-20260530-201336.md`
  * `.backlogit/reconcile/001-S-post-20260530-201355.md`

## Follow-up

* Minimal candidate only: restore fresh Copilot review requestability for this
  repository before the next merge that depends on a new Copilot review
