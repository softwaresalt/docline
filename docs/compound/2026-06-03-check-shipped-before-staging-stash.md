---
title: "Check shipped artifacts before staging new work from stash"
date: 2026-06-03
agent: stage
context: backlogit-harvest
tags:
  - stage
  - harvest
  - stash
  - triage
  - duplicate-detection
trigger:
  - "Stash entries that appear to describe planned but undelivered work"
  - "Orchestrator-provided groupings derived from stash priority"
---

# Check shipped artifacts before staging new work from stash

## Problem

The backlogit harvest skill can create work items from a stash entry without invoking the
formal `backlogit stash harvest <id>` command. When it does, the `stash_links` table is
not populated and the stash entry remains in `active` state after the work ships. Later
triage or grouping passes that read only the active stash will surface those entries again
as if they were unfinished, leading to wasted Stage planning effort on duplicate work.

The same trap exists for any direct `backlogit_create_item` flow that records source
provenance only in `custom_fields.source_stash_ids` without archiving the stash entry.

## Detection signal during Stage triage

Before deliberating or planning **any** stash entry, run this check:

```sql
-- Look for prior artifacts that named this stash entry as a source
SELECT id, title, status, artifact_type,
       json_extract(custom_fields, '$.source_stash_ids') AS sources
FROM items
WHERE custom_fields LIKE '%<STASH_ID>%'
```

If any matching item exists with `status = 'archived'`, the stash entry is consumed —
archive it instead of replanning. If matching items exist with `status IN ('queued', 'active')`,
the work is in-flight — verify state before adding new tasks.

Also check `stash_links`:

```sql
SELECT stash_id, item_id, linked_at
FROM stash_links
WHERE stash_id = '<STASH_ID>'
```

A populated row plus an archived item = shipped. An empty row plus shipped items in
`custom_fields` lookup = the operational gap described here.

## Corrective action

When a duplicate is detected:

1. Do **not** create a new feature, plan, or shipment.
2. Archive the orphaned stash entries: `backlogit stash archive <id>`.
3. Record the discovery in session memory under `docs/memory/{date}/`.
4. Return a clear "duplicate-of-shipped-work" report to the orchestrator.

## Prevention guidance for harvest skill

The harvest skill should always either:

* Use `backlogit_harvest_stash` (auto-archives and writes `stash_links`), **or**
* When using `backlogit_create_item` directly to preserve hierarchical id control, follow
  up with an explicit `backlogit stash archive` for every consumed stash id.

Recording source provenance in `custom_fields.source_stash_ids` alone is insufficient —
the stash store must reflect consumption.

## Evidence base

* Session: `docs/memory/2026-06-03/g2-multi-source-ingestion-stage-memory.md`
* Shipped feature: `008-F` (archived), shipment `008-S` (archived), PR #16
* Stash entries left dangling: `D37D8AF7`, `5F0C557E` (archived 2026-06-03 by Stage)
* Plan artifact: `docs/plans/2026-06-01-elt-multi-source-ingestion-plan.md`
* Deliberation: `docs/decisions/2026-06-01-elt-multi-source-ingestion-deliberation.md`

## Confidence

High. The pattern is mechanical (active stash + archived item with matching
`source_stash_ids`) and the corrective action is reversible (archived stash entries can be
restored from `.backlogit/archive/stash.jsonl` if needed).
