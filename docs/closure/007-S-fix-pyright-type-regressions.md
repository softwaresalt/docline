---
title: "Closure - 007-S Fix Pyright Type Regressions"
shipment: "007-S"
branch: "feat/fix-pyright-type-regressions"
pr: "10"
merge_commit: "5c93476b49ffb68e8339feff062f0831293e430c"
merged_at: "2026-06-01T00:35:39Z"
status: "merged-shipped"
---

## Outcome

Shipment `007-S` is merged and shipped. PR `#10` merged to `main` at
`2026-06-01T00:35:39Z` with merge commit
`5c93476b49ffb68e8339feff062f0831293e430c`.

## Final shipped scope

| Change | Surface | Final state |
|---|---|---|
| Pyright type-annotation repair | `src/docline/process/metadata.py`, `src/docline/process/ast_lint.py` | `Mapping[str, Any]` and concrete `Token` typing restore the `pyright` gate without changing runtime behavior |
| Release verification | `src/`, `tests/` | Compile, lint, typecheck, tests, and format gates all pass on merged `main` |

## Review and merge disposition

* Fresh Copilot review covered current HEAD `ffba84e56adedc5d6d08419f558b4fed1f15a778` with zero unresolved Copilot threads
* GitHub still required one human approving review before a standard merge could proceed
* Merge proceeded under the explicit operator-approved administrator-merge override for shipment `007-S`

### Risky action record

* ProposedAction: merge PR `#10` with `--merge --admin`
* ActionRisk: high
* Approval path: explicit operator approval
* ActionResult: applied

## Verification

See the runtime verification report:
[`2026-05-31-007-s-fix-pyright-type-regressions-runtime-verification.md`](2026-05-31-007-s-fix-pyright-type-regressions-runtime-verification.md).

Final gates before closure:

* `python -m py_compile src/docline/__init__.py` -> exit `0`
* `ruff check .` -> passed
* `pyright src/` -> `0` errors
* `pytest` -> `367` collected, exit `0`
* `ruff format --check .` -> passed

## Archival state

* `backlogit shipment ship 007-S --sha 5c93476...` succeeded
* Archived IDs: `007-F`, `007.001-T`, `007-S`
* `backlogit sync` succeeded after archival

## Operational closure

* Readiness: READY
* Deployment path: merge-only release via `main`
* Validation window: next normal development cycle on `main`
* Owner: operator / repository maintainer
* Monitoring and rollback: rely on the documented quality gates and revert merge commit `5c93476b49ffb68e8339feff062f0831293e430c` if the process-module type-fix regresses
* A dedicated closure PR is required from `post-merge/007-fix-pyright-type-regressions` and remains subject to separate approval

## Knowledge graduation

* The shipped change is narrowly corrective and does not require new architecture or design-document updates
* No additional source-artifact cleanup was required for `007-F`
* No shipment-local follow-up backlog items were identified during closure
