---
title: "Ship memory — 001-S resume"
shipment: "001-S"
branch: "feat/backlog-artifact-persistence-prerequisite"
status: "pr-ready"
---

## Completed

* Replaced the blanket `.backlogit/` ignore with targeted volatile-runtime rules
* Added a minimal greenfield Python bootstrap: `pyproject.toml`, `src/docline/__init__.py`, `tests/`
* Added contract tests that prove durable backlog artifacts stay trackable and volatile backlogit runtime files stay ignored
* Added a closure note for shipment 001-S
* Extended the contract to cover checkpoint durability and telemetry exclusion
* Re-validated with `python -m py_compile`, `pytest`, `ruff check .`, and `ruff format --check .`

## Decisions

* The missing `src/docline/__init__.py` was a greenfield bootstrap gap, not product work
* Archive artifacts under `.backlogit/archive/` are durable and must remain trackable
* Runtime artifacts under `.backlogit/logs/`, `hooks_queue.jsonl`, and SQLite sidecar files remain ignored

## Pending

* Stage and commit the shipment changes
* Push branch and create the feature PR
* Await explicit operator merge approval before any merge
