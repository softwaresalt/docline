---
title: "backlogit shipment ship deadlocks in a worktree; fall back to update+archive per artifact"
date: 2026-08-30
agent: ship
shipment: 059-S
context: ship-shipment-lifecycle
confidence: high
evidence: "059-S post-merge closure — `backlogit shipment ship 059-S --sha ...` hung after `workspace initialized` and never progressed; repeated across three attempts with and without --no-update-check"
tags:
  - backlogit
  - ship_shipment
  - worktree
  - deadlock
  - commit-traceability
  - lock-files
trigger:
  - "Closing a shipment from an isolated git worktree while a backlogit MCP daemon runs against the primary workspace"
  - "`backlogit shipment ship` produces no output after the workspace-initialized log line"
  - "Many stale `.backlogit/.*.lock` files appear after an interrupted ship"
---

## Problem

Post-merge closure for 059-S ran from an isolated worktree
(`.copilot/worktrees/ship-059`). `backlogit shipment ship 059-S --sha <merge>` initialized the
workspace, logged `workspace initialized`, then hung indefinitely with no further output — through
three attempts, including with `--no-update-check` and `--log-level debug`. Each interrupted run
left a full set of per-artifact `.backlogit/.*.lock` files (one per manifest item plus the shipment
and its `.jsonl` logs). Lighter CLI mutations against the same worktree DB — `update`, `archive`,
`move`, `sync`, `query` — all completed in well under a second.

## Root cause

Several long-lived `backlogit` daemon processes were resident (the MCP server instances bound to
the **primary** workspace, running for days). `shipment ship` is the heaviest lifecycle operation:
it acquires a lock on **every** manifest artifact at once to archive the released scope as a single
transaction. That broad multi-lock acquisition is where it wedges in this environment, whereas the
single-artifact mutations never contend. The stale lock files are a *symptom* of the interrupted
broad acquisition, not the cause — clearing them and retrying reproduces the same hang.

## Resolution

Complete the shipment lifecycle with the single-artifact CLIs that do not deadlock, preserving the
same end state (`ship_shipment`'s outputs are: all manifest items archived + merge SHA recorded):

1. `backlogit move <feature> --status done` — clear the feature's non-terminal state.
2. `backlogit update <id> --commit <merge_sha>` for the **shipment and the feature** — record merge
   traceability before archiving.
3. `backlogit archive <shipment>` then `backlogit archive <feature>`.
4. **Backfill the tasks.** Tasks moved to archive earlier via `move --status done` never received
   the merge SHA (the known `ship_shipment`-skips-already-archived gap). Insert
   `commit: <merge_sha>` into each archived task's frontmatter, alphabetically after
   `artifact_type`. See the sibling learning on that traceability gap.
5. `backlogit sync` and run `backlogit doctor` — confirm zero orphans/duplicates for the shipment's
   items (ignore the pre-existing workspace-wide `archived_from_self_ref` advisory).

Run each of these as a **backgrounded process with file-redirected stdout/stderr** (not a piped
foreground command) so you can watch the debug log advance and detect a hang immediately instead of
blocking a piped `Select-Object` that only flushes on exit.

## Caveat

Archiving a shipment directly with `archive` records `archived_status: active` rather than a
`shipped` state, because `ship` is the only path that first transitions the shipment through
`shipped`. The material outcomes — archived scope + merge SHA on every artifact — are satisfied;
note the cosmetic `archived_status` in the closure record.

## Reusable rule

When `backlogit shipment ship` hangs from a worktree, do not keep retrying it (it will re-wedge and
re-litter lock files). Fall back to `move` + per-artifact `update --commit` + `archive`, backfill
the task commit fields, then `sync` + `doctor`. Prefer backgrounded, file-redirected invocations of
backlogit mutations in worktrees so a deadlock is observable rather than silent.

## Related

- `docs/compound/2026-06-04-ship-shipment-commit-traceability-gap.md` — the archived-before-ship
  items miss the `commit:` field; the same backfill applies here for all 19 tasks.
- `docs/compound/2026-07-03-backlogit-mcp-down-fall-back-to-cli.md` — the general MCP→CLI fallback
  posture.
