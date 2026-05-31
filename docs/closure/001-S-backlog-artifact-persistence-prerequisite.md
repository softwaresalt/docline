---
title: "Closure — 001-S Backlog Artifact Persistence Prerequisite"
shipment: "001-S"
branch: "feat/backlog-artifact-persistence-prerequisite"
prepared_at: "2026-05-30"
status: "prepared"
---

## Shipment Summary

Shipment 001-S established the durability and hygiene contract for backlogit
artifacts in this workspace. The deliverable was a `.gitignore` configuration
and a test suite that together enforce which backlog files are Git-trackable
and which remain volatile.

## What Shipped

| Change | File | Effect |
|--------|------|--------|
| Blanket `.backlogit` ignore removed | `.gitignore` | Queue, config, stash, and archive artifacts become trackable |
| Volatile runtime rules added | `.gitignore` | Database, WAL, shm, journal, hook queue, and logs stay excluded |
| Persistence contract tests | `tests/test_backlog_persistence_contract.py` | CI gate proves ignore rules match intent |

## Durability Decisions

**Archive artifacts are durable.** `.backlogit/archive/` is explicitly
unignored. Archived items represent completed work history and must remain
accessible in version control for traceability and audit. This was confirmed
in the post-shipment review and is covered by the parametrized contract test.

**Logs remain volatile.** `.backlogit/logs/` is excluded. Session log files
are ephemeral diagnostic output and must not accumulate in the repository.

## Post-Shipment Review Findings and Resolutions

Two substantive findings from the 001-S review were addressed after shipment:

1. **Unused constants** — `_DURABLE_PATHS` and `_VOLATILE_PATHS` were defined
   but not consumed by the class-based tests. Resolved by converting both test
   classes to `@pytest.mark.parametrize` functions driven by those lists.
   Adding coverage for a new path now requires only an entry in the relevant
   list — no new test function.

2. **Archive coverage gap** — `.backlogit/archive/` was unignored but had no
   contract test. Resolved by adding two archive paths to `_DURABLE_PATHS`
   and a representative log path to `_VOLATILE_PATHS`.

## Quality Gate Results

All gates green at closure commit:

```text
python -m py_compile src/docline/__init__.py  → exit 0
pytest                                         → 13 passed
ruff check .                                   → no issues
ruff format --check .                          → no issues
```

## Handoff Notes

The persistence contract is now self-extending: reviewers and agents add
entries to `_DURABLE_PATHS` or `_VOLATILE_PATHS` in the test module to grow
coverage. No structural test changes are required for new backlogit artifact
types.
