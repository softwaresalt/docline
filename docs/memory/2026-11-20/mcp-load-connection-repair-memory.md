---
title: MCP load and connection repair memory
date: 2026-11-20T22:58:00Z
task: direct-operator-diagnostic
status: partially-complete
---

## Completed Work

* Repaired the workspace MCP startup paths in `.mcp.json`
* Added `tools/mcp/stdio-shim.cjs` for Copilot `server/discover` compatibility and Windows `.exe` / `.js` spawning
* Verified complete discovery, initialization, and tool-list handshakes for Backlogit, GitHub, Context7, Tavily, and KBDB
* Aligned `tools/mcp/install.ps1` with the `.bin` runtime directory
* Added a startup bridge for Backlogit's pinned `bin/backlogit.exe` daemon
* Added ignore rules for local MCP executables and JavaScript dependencies
* Added the MCP shim to `start.ps1` prerequisite validation
* Recorded the RCA in `docs/decisions/2026-11-20-mcp-load-connection-failures-spike.md`

## Verified Evidence

* Backlogit 1.12.1 returns 73 tools
* GitHub MCP Server 1.5.0 returns 44 tools
* Context7 4.4.4 returns 2 tools
* Tavily 0.2.22 returns 5 tools
* KBDB 0.3.1 returns 8 tools
* `copilot mcp list` finds all six workspace servers
* Node syntax check, both PowerShell parser checks, and MCP JSON parsing passed
* Ruff lint, Pyright, and Ruff format checks passed
* Pytest completed with 2,336 passed, 6 skipped, and 10 unrelated CI-workflow failures caused by the pre-existing dirty `.github/workflows/ci.yml`

## Decisions and Rationale

* Route local MCP servers through one generic stdio shim instead of relying on per-server support for Copilot's discovery preflight
* Use `.bin` for workspace runtimes and create only the `bin/backlogit.exe` bridge required by Backlogit's pinned-daemon resolver
* Keep Engram on degraded status rather than wait for its 4,210-file initial index to finish

## Failed or Bounded Approaches

* The prior JavaScript shim returned `EFTYPE` when asked to spawn `.js` files on Windows
* Directly launching GitHub MCP Server rejected `server/discover`
* Backlogit MCP failed until `bin/backlogit.exe` existed
* Engram's direct pre-warm reached 888 of 4,210 files after 636 seconds and was stopped at the bounded diagnostic limit

## Remaining Work

* Reload the active Copilot MCP configuration with `/mcp reload` or restart the session
* Run Engram's direct synchronization during a longer maintenance window
* After Engram finishes, probe `discover -> initialize -> tools/list`
* Track the Copilot CLI 1.0.114 Windows path-stripping defect upstream
