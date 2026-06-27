---
title: Closure — 038-S Range-level docling attribution
date: 2026-06-26
shipment: 038-S
feature: 035-F
status: verified
merged_pr: 103
merge_sha: b7c021a
branch: feat/038-S-docling-attribution
---

## Readiness status

**READY** — merged to `main` (PR #103, merge commit `b7c021a`, a true two-parent
merge commit per P-009). Closes feature **035-F**.

## What shipped

Task **035.001-T** — add a `docling_attribution` section to the pa3 runtime
verification summary so the per-page docling metric is not misread.

The 2026-06-25 cosmos routing investigation found `engine_distribution`
overstates docling coverage: 96.9% of "docling" pages are empty
`docling-collapsed` placeholders (86 ranges → 86 concatenated blobs). The new
section reports the honest range-level picture:

```json
"docling_attribution": {
  "ranges": 86,
  "content_pages": 86,
  "collapsed_placeholder_pages": 2713,
  "total_docling_chars": 3438001
}
```

`scripts/pa3_triage_cosmos.py` gains a `_docling_attribution()` helper wired
into the summary. `engine_distribution` is unchanged (backward-compat). Single
domain: the pa3 reporting script — no `src/` change.

## Verification

- Red→green TDD: the new test reproduces the collapsed-attribution shape and
  asserts the fields reconcile (`content + collapsed == total docling pages`,
  `ranges == len(flagged_ranges)`).
- `pytest tests/test_pa3_script_flags.py` — 8 passed.
- `ruff check` / `ruff format --check` — clean.
- `pyright scripts/pa3_triage_cosmos.py` — no errors.
- Adversarial review (Copilot review unavailable for this workspace): no findings.

## Process note

Built entirely via the **backlogit CLI** (MCP server unavailable this session):
stash harvest → add task → shipment create/claim → move → `update --commit` →
shipment ship. Single-open-PR discipline maintained throughout.

## Follow-ups

- `2BB5B1C3` (medium spike) — merge_gap tuning experiment, now able to measure
  docling routing accurately thanks to this metric fix. Needs operator-run
  cosmos inference.
- `D771B78E` (deferred) — per-page fidelity restoration would retire the
  `docling-collapsed` attribution entirely (2.22× overhead per the 032.001-T
  probe).
