---
title: "Runtime verification - 007-S fix pyright type regressions"
shipment: "007-S"
surface: "process/type-checking"
mode: "manual"
status: "pass"
verified_at: "2026-05-31"
merge_commit: "5c93476b49ffb68e8339feff062f0831293e430c"
---

## Scope

* `src/docline/process/metadata.py` and `src/docline/process/ast_lint.py`
* Shipment archival path for `007-S`

## Environment prechecks

* PR `#10` merged to `main` at `2026-06-01T00:35:39Z`
* Merge commit `5c93476b49ffb68e8339feff062f0831293e430c` is in `origin/main`
* `backlogit shipment ship 007-S` completed and `backlogit sync` refreshed the index

## Evidence

* `python -m py_compile src/docline/__init__.py` -> exit `0`
* `ruff check .` -> passed
* `pyright src/` -> `0` errors
* `pytest` -> exit `0` after collecting `367` tests in `7.34s`
* `ruff format --check .` -> passed
* `backlogit shipment ship 007-S --sha 5c93476...` archived `007-F`, `007.001-T`, and `007-S`

## Risky action record

* ProposedAction: merge PR `#10` with `--merge --admin` after GitHub's human-approval rule remained the only blocker
* ActionRisk: high
* Approval path: explicit operator approval for PR `#10`
* ActionResult: applied

## Invariants preserved

* The process-module pyright regression is cleared on the merged `main` state
* Existing lint, test, and format gates remain green after the merge
* Shipment archival landed with matching queue-to-archive state in backlogit

## Verdict

PASS

## Follow-up

* No shipment-local runtime follow-up was identified during closure
