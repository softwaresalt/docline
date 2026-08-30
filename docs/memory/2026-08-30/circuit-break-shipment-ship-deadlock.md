---
type: circuit-breaker
title: "Circuit breaker: backlogit shipment ship deadlock (059-S)"
timestamp: 2026-08-30T12:41:00-07:00
agent: ship
skill: operational-closure
breaker_type: universal
operation: "backlogit shipment ship 059-S --sha 58ba5c5 (post-merge shipment archival)"
attempts: 3
---

## Failure Chain

### Attempt 1

`backlogit shipment ship 059-S --sha 58ba5c5b67abf5c73457d11e5af76c60bdd483b1 --message "..."`
from the worktree. The command initialized the workspace, logged `workspace initialized`, and then
produced no further output for >3 minutes. Interrupted. Left a full set of per-artifact
`.backlogit/.*.lock` files.

### Attempt 2

Cleared the stale lock files and retried the same command. Same behavior: hung after
`workspace initialized`, no progress within the wait window. Interrupted.

### Attempt 3

Cleared locks again and retried with `--no-update-check` and `--log-level debug`, output
redirected to a file to observe progress. Debug log advanced only to
`level=INFO msg="workspace initialized"` and then stopped. No further phase output. Interrupted.

## Context

- Files/operations involved: `backlogit shipment ship` against
  `.copilot/worktrees/ship-059/.backlogit`; several long-lived `backlogit` daemon processes
  resident in the environment.
- Diagnostic captured: only the last log line (`workspace initialized`). No lock-owner, stack
  trace, or phase-level trace — so the cause is suspected, not proven.
- Resolution: Circuit breaker honored. Stopped retrying `shipment ship` after 3 attempts and routed
  the archival to the single-artifact CLI fallback (`move` + per-artifact `update --commit` +
  `archive`, then task-commit backfill, `sync`, and `doctor`), which completed the closure with the
  same archive placement and commit traceability.
- Reusable learning captured in
  `docs/compound/2026-08-30-ship-shipment-deadlocks-in-worktree.md`.
- Operator guidance: none required — a safe, equivalent fallback path existed and was used. The
  underlying `shipment ship` worktree hang is a candidate backlogit issue.
