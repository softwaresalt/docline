---
date: 2026-06-19
shipment: 035-S
category: engram-cli-grounding
keywords: [engram, cli, mcp, grounding, daemon, workspace, session-start, database-locked, indexed-search]
confidence: high
evidence: 2026-06-14 030-F session where engram was bypassed for an entire shipment cycle; would have caught the _read_pdf_docling_pages return-shape surprise during T1+T2 design
---

# Engram is reachable via its CLI even when MCP engram tools are absent — probe it at session start

## Problem

Some sessions expose no `engram-*` MCP tools, so agents fall straight to
file-based search (`Get-ChildItem`, `Select-String`, `view`) and lose indexed
grounding. In the 2026-06-14 030-F session this bypass let a return-shape
surprise (`_read_pdf_docling_pages` returns `[]` or `[markdown]`, **not** a
per-page list) slip into the T1/T2 design.

## The CLI is always available

Engram is invocable via `D:\Tools\engram.exe` regardless of the MCP tool
surface. CLI subcommands map 1:1 to MCP tools:

| CLI subcommand | MCP tool |
|---|---|
| `engram search` | `unified_search` |
| `engram map-code` | `map_code` |
| `engram impact` | `impact_analysis` |
| `engram query-graph` | `query_graph` |
| `engram symbols` | `list_symbols` |
| `engram query-memory` | `query_memory` |
| `engram daemon-status` | `get_daemon_status` |
| `engram workspace-status` | `get_workspace_status` |
| `engram sync` | `sync_workspace` |
| `engram index` | `index_workspace` |
| `engram bind` | `set_workspace` |

## Session-start protocol

1. Probe `engram daemon-status` + `engram workspace-status`.
2. If the daemon is reachable and the workspace is indexed, use the CLI for
   grounding **before** file-based tools.
3. Only fall back to `Get-ChildItem` / `Select-String` / `view` when engram is
   unreachable or the answer is literal-text/regex oriented.

## Diagnostics & gotchas

- **Stale-process triage:** `Get-CimInstance Win32_Process -Filter
  "Name='engram.exe'"`, then inspect `ParentProcessId` + `CommandLine` to
  distinguish shims (parent = `copilot.exe`, command line ends in `shim`) from
  daemons (command line contains `daemon --workspace <PATH>`).
- **No cross-workspace contention:** each workspace has its own cozo DB;
  daemons for different workspaces never contend. Zombie shims from prior
  sessions are harmless.
- **DB-lock envelope:** a transient `database is locked` error on the first
  call after a daemon spawn is normal. Retry once after ~5 seconds before
  declaring `ENGRAM_DEGRADED`.

## Rule

Treat the engram CLI as the grounding path of record when MCP engram tools are
not exposed. Probe at session start; prefer indexed lookup over raw file scans
for any structural or conceptual question.
