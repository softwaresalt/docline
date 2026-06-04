---
date: 2026-06-04
shipment: 015-S
category: ship-shipment-commit-traceability
keywords: [backlogit, ship_shipment, commit, archive, traceability, move_item, frontmatter]
confidence: high
evidence: PR #31 Copilot review on .backlogit/archive/016-F.md, 016.001-T.md, 016.002-T.md
---

# backlogit_ship_shipment skips items already in archive — manually backfill commit field

## Problem

`backlogit_ship_shipment(sha=<merge_sha>)` adds the merge SHA to the
`commit:` frontmatter field of every artifact it *actively moves* from
queue to archive — but if items have already been moved to archive
earlier in the workflow (via `move_item(status="done")` during Ship's
per-task closure step), those archive files keep their pre-merge state
and never receive the merge SHA.

Result: archived items split into two camps after a shipment closes:

- Tasks and features still in queue at `ship_shipment` time → archived
  with `commit: <merge_sha>` field ✓
- Tasks and features moved to archive before `ship_shipment` ran →
  archived without the `commit` field ✗

This breaks the established traceability convention from earlier
shipment closures (e.g. 014-S where every archived item carries
`commit:`), and downstream tooling that grep-walks for `commit:`
entries gets inconsistent results within a single shipment.

## Symptom

Copilot review (or any audit that checks for consistency) flags some
but not all archived items in a shipment as missing the `commit:`
field. The split typically falls on:

- "Tasks 1 and 2" (or generally early tasks) missing
- "Tasks 3 and 4" (later tasks) have it
- Feature artifact missing
- Shipment manifest itself has it (since it's the last item ship_shipment moves)

## Detection

After `ship_shipment` returns, grep the archive directory for the
shipment's items:

```powershell
@('NNN-F','NNN.001-T','NNN.002-T','NNN.003-T','NNN.004-T') | ForEach-Object {
    $hasCommit = (Select-String -Path ".backlogit/archive/$_.md" -Pattern "^commit:" -Quiet)
    "$_ : commit=$hasCommit"
}
```

Any `commit=False` entries need manual backfill.

## Fix

Manually add the `commit: <merge_sha>` line to the frontmatter of each
archived item missing it. Place it alphabetically between
`artifact_type` and `created_at` (matches the field order in the items
that ship_shipment touched).

```yaml
---
archived_from: .backlogit/archive/{id}.md
artifact_type: {feature|task}
commit: <merge_sha>          # ADD THIS LINE
created_at: ...
...
```

Commit the backfill on the post-merge closure branch so the closure
PR carries the corrected state.

## Reusable rule

**After `backlogit_ship_shipment`, audit every archived item in the
manifest for the `commit:` field and backfill any that are missing.**
The check should be part of Ship's Step 6 post-merge closure cycle
before the closure PR is created.

## Detection in code review

Watch for archive frontmatter inconsistencies across items in a single
shipment. Copilot tends to catch this pattern by comparing siblings.

## Workaround until backlogit is fixed

The proper fix is in backlogit itself: `ship_shipment` should add the
merge SHA to every manifest item regardless of whether the item was
in queue or already archived. Until that lands, the audit-and-backfill
workflow above is the manual workaround.

A backlogit issue could be filed describing the desired behavior:
"ship_shipment should propagate merge SHA to all manifest items
regardless of their current archive/queue state."

## Related

- 015-S closure PR #31 — three findings: `016-F`, `016.001-T`, `016.002-T` missing commit field
- Earlier shipment closures (012-S, 013-S, 014-S) — pattern was masked because most archived items were still in queue at ship_shipment time
- 014-S closure record for reference convention: `docs/closure/014-S-docling-sidecars.md`
