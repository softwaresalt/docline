# backlogit ship gate needs a genuine active→done transition

**Date:** 2026-07-17
**Context:** Shipping shipment `053-S` (feature `057-F`) — `backlogit_ship_shipment`
repeatedly refused with `member <task> missing passing gate evidence: gate
blocked: <task> remains active`.

## Symptom

`backlogit_ship_shipment` refuses a shipment whose member tasks show
`status: done` in both the markdown frontmatter and the SQL index, with:

```
shipment refused: member 057.001-T missing passing gate evidence:
gate blocked: 057.001-T remains active
```

Editing the shipment manifest markdown (`custom_fields.items`) + `sync_index`
does **not** change the refusal — the ship reads the shipment's **internal**
membership + gate ledger, not the markdown item list.

## Root cause

The member tasks were created directly with `status: done` (a compressed inline
Stage→Ship flow that skipped `queued → active → done`). backlogit opens a
per-item **ship gate** that only closes when the item passes through a genuine
`active → done` transition. A task born as `done` has an open gate that never
closed. `done → done` moves (even with a `commit_sha`) do **not** close it, and
`done → active` is a rejected transition (`invalid status transition`), so the
item is stuck.

## Resolution

Force a real forward transition to generate passing gate evidence:

1. `backlogit_return_blocked(shipment_id, item_id, reason)` — moves the stuck
   member to `blocked` (still a member; ship now refuses "member is blocked").
2. `backlogit_move_item(item_id, status="active")` — `blocked → active` is
   allowed.
3. `backlogit_move_item(item_id, status="done", commit_sha=<merge_sha>)` —
   `active → done` returns a `gate` object with `"outcome":"passed"` and
   `"state_changed":true`. **This is the passing gate evidence.**
4. `backlogit_ship_shipment(...)` now succeeds and archives the members.

The covering feature `057-F` shipped fine on the first try because it had a
natural `active → done` transition (harvested features start non-done).

## Prevention

* Do not create tasks/subtasks directly with `status: done`. Create them
  `queued` (or let harvest do it), then `move_item` to `active`, then `done`
  with the `commit_sha`. This records gate evidence the ship step requires.
* Related: `backlogit_update_item` with a `description`-only payload silently
  drops body `sections` — always pass `sections` alongside `description`.
* Related: `backlogit_create_item` / `move_item` to `status: done` auto-archives
  (moves `queue → archive`).
