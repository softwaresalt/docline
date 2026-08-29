---
title: "Runtime verification - 004-S document ingestion processing validation and outputs"
shipment: "004-S"
surface: "process/validation/output"
mode: "manual"
status: "warn"
verified_at: "2026-05-31"
merge_commit: "b9d138904f7a9ff2f222cdd0a5103b07152de3cc"
---

## Scope

* Processing-stage identity, metadata, transcript normalization, Markdown assembly, AST lint, correction scaffolding, quarantine, output, and manifest surfaces
* Shipment archival path for `004-S`

## Environment prechecks

* PR `#8` merged to `main` at `2026-05-31T22:53:00Z`
* Merge commit `b9d138904f7a9ff2f222cdd0a5103b07152de3cc` is in `origin/main`
* `backlogit shipment ship 004-S` completed and `backlogit sync` refreshed the index

## Evidence

* `python -m py_compile src/docline/__init__.py` -> exit `0`
* `ruff check .` -> passed
* `pyright src/` -> failed with `6` errors in `src/docline/process/ast_lint.py` and `src/docline/process/metadata.py`
* `pytest` -> exit `0` after collecting `367` tests
* `ruff format --check .` -> passed
* `backlogit shipment ship 004-S --sha b9d1389...` archived `004-F`, `004-S`, and `004.001-T` through `004.013-T`

## Risky action record

* ProposedAction: merge PR `#8` with `--merge --admin` after the normal merge path was blocked by base-branch policy
* ActionRisk: high
* Approval path: explicit operator approval for PR `#8`
* ActionResult: applied

## Invariants preserved

* Processing-stage modules from shipment `004-S` compile and pass the existing runtime-oriented tests
* Shipment archival landed with matching queue-to-archive state in backlogit
* No unresolved Copilot review threads remained on PR `#8` at merge time

## Verdict

WARN

## Follow-up

* Stashed follow-up `F6CCF29C`: fix the post-merge `pyright` regressions in `src/docline/process/metadata.py` and `src/docline/process/ast_lint.py`

