---
date: 2026-07-03
category: backlogit-mcp-down-fall-back-to-cli
keywords: [backlogit, mcp, transport-closed, cli, fallback, move, update, sync, shipment, degraded]
confidence: high
evidence: 044-S Ship session 2026-07-02 — backlogit MCP returned "Transport closed" mid-build; the backlogit CLI (C:\Tools\backlogit.exe v1.3.0) completed every operation
---

# When the backlogit MCP surface is down, fall back to the backlogit CLI — do not defer

## Problem

During the 044-S build the backlogit MCP tools began returning
`MCP request failed: Transport closed` and never recovered within the session.
Task status transitions (move to done, archive shipment) could not be applied
through MCP, and the work was left unrecorded until an operator intervened.

## Root Cause

Treating the MCP surface as the only path to backlogit. The MCP server and the
CLI are two front-ends over the same `.backlogit/` workspace (the Markdown files
are the source of truth; the SQLite index is a disposable cache). An MCP
transport failure does not disable the CLI.

## Fix

Fall back to the `backlogit` CLI immediately when MCP is unavailable. It is
installed on PATH (`C:\Tools\backlogit.exe`, v1.3.0) and exposes the same
operations:

```powershell
backlogit move 041.004-T --status done
backlogit update 041.004-T --commit 9b9a549
backlogit move 041-F --status done
backlogit shipment ship 044-S --sha <merge_sha> --message "..." --author "..."
backlogit sync            # rehydrate the SQLite index after mutations
backlogit query "SELECT id, status FROM items WHERE status='active'"
```

Gotchas learned:

* `backlogit query` takes the SQL as a **positional** argument, not `--sql`.
* The CLI logs INFO lines to stderr (e.g. `index may be stale after mutation`);
  run `backlogit sync` afterward to refresh the cache before querying.

## Rule

* MCP `Transport closed` (or any MCP unavailability) is a `*_DEGRADED` condition,
  not a stop condition — switch to the CLI and keep going.
* Never leave backlog state unrecorded because one front-end is down.
* After a batch of CLI mutations, run `backlogit sync` so `query`/`list` reflect
  the Markdown source of truth.
