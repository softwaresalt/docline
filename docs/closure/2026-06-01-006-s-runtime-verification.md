---
title: "Shipment 006-S runtime verification"
shipment_id: "006-S"
feature_id: "006-F"
surface: "cli"
mode: "manual"
verdict: "PASS"
date: "2026-06-01"
---

# Runtime verification

## Scope

* Packaging metadata and `python -m docline` entrypoint
* File-local quarantine viewer CLI path

## Environment prechecks

* Branch: `feat/shipment-5-packaging-and-quarantine-tooling`
* Workspace compile check passed via `python -m py_compile src/docline/__init__.py`
* Full quality gates passed locally: `ruff check .`, `ruff format --check .`, `pytest`

## Scenarios

### Package entrypoint

* Command: `python -m docline --manifest`
* Expected: shared manifest JSON emitted with success exit code
* Observed: matched expected behavior through `tests/build/test_packaging_entrypoint.py`

### Quarantine viewer

* Command set: `pytest tests/parity/test_quarantine_viewer_cli.py tests/security/test_quarantine_viewer.py`
* Expected:
  * render escaped local HTML from a workspace-contained quarantine artifact
  * reject artifact and output paths that escape the workspace
  * return handled CLI errors instead of tracebacks
* Observed: all targeted verification scenarios passed

## Evidence

* `tests/build/test_packaging_entrypoint.py` passed
* `tests/parity/test_quarantine_viewer_cli.py` passed
* `tests/security/test_quarantine_viewer.py` passed
* Full suite passed locally after integration

## Verdict

PASS

## Follow-up recommendations

* None from pre-merge verification
