---
title: "MCP load and connection failure root cause"
source: "docs/decisions/2026-11-20-mcp-load-connection-failures-spike.md"
doc_type: decision
description: "Root-cause analysis and local repairs for workspace MCP startup and handshake failures."
docline:
  type: spike
  date: 2026-11-20
  time_box: "2h"
  conclusion: proceed
  confidence: medium
  linked_parent_work_item: null
  promoted_to: ["none"]
  tags:
    - mcp
    - windows
---

## Goal

Determine why the workspace MCP servers fail to load or connect, repair workspace-local causes, and identify failures that require an upstream fix.

## Success Criteria

* Every configured server is mapped to an existing executable and entrypoint
* Each locally repairable server completes `server/discover`, `initialize`, and `tools/list`
* Remaining failures have reproducible evidence and a bounded root cause
* The repair survives startup through `start.ps1`

## Scope Constraints

* The investigation is limited to the workspace MCP runtime, local launch configuration, and Copilot CLI startup evidence
* Secrets are not copied into tracked configuration or diagnostic artifacts
* Upstream binary replacement and version-control cleanup are out of scope

## Investigation Approach

1. Compare `.mcp.json` entrypoints with files present in the workspace
2. Reproduce each server's MCP lifecycle over stdio
3. Test daemon health and direct binary startup independently
4. Repair local path, process-launch, and discovery issues
5. Re-run lifecycle probes and record unresolved client defects

## Findings

### What Was Discovered

The active workspace configuration referenced entrypoints that did not exist:

* Context7 and Tavily pointed at `.copilot/servers/node_modules`, but their installed packages are under `tools/mcp/node_modules`
* KBDB pointed at `.copilot/kbdb-mcp-shim.cjs`, which does not exist
* The existing `.copilot/graphtor-mcp-shim.cjs` cannot launch JavaScript files on Windows because `child_process.spawn` receives a `.js` file as an executable and returns `EFTYPE`

The servers also do not uniformly implement the Copilot client preflight. GitHub MCP Server rejected `server/discover` as an invalid method during initialization. This repository's MCP deliberation already records `server/discover` as the modern compatibility probe, so local server configuration must bridge legacy servers rather than modify the Copilot client.

Backlogit started its outer executable but required a pinned daemon at `bin/backlogit.exe`; the workspace runtime was installed only at `.bin/backlogit.exe`. Creating the missing pinned bridge allowed the daemon to start.

Engram did not crash during startup. Its shim spawned a daemon, but the daemon could not reach Ready within the configured 30-second wait because it was pre-warming a graph from 4,210 workspace files. Direct synchronization remained CPU-active at hundreds of seconds and is a first-index cost rather than an immediate transport failure.

The workspace had no ignore rules for `.bin/` or `node_modules/`. This exposed local runtime artifacts to Git and made workspace indexing broader than intended. Copilot CLI 1.0.114 also logged Windows paths with backslashes removed for its own Git and plugin operations, for example changing the workspace path into a form that cannot be passed to `git -C`. That behavior is in the host CLI, not the workspace MCP servers.

### Repairs Applied

* Added `tools/mcp/stdio-shim.cjs` to answer `server/discover`, preserve initialization ordering, and launch either native executables or JavaScript entrypoints on Windows
* Routed all six local MCP servers through the generic shim
* Corrected Context7 and Tavily paths to `tools/mcp/node_modules`
* Corrected KBDB to use the existing `.bin/kbdb.exe`
* Added the `bin/backlogit.exe` pinned-daemon bridge to `start.ps1`
* Aligned `tools/mcp/install.ps1` with the `.bin` runtime used by `start.ps1`
* Added `.bin/`, `bin/`, and `node_modules/` ignore rules
* Added the shim to the startup prerequisite check

### Verification

Full `discover -> initialize -> tools/list` probes succeeded:

| Server | Version | Tools |
|---|---|---:|
| Backlogit | 1.12.1 | 73 |
| GitHub MCP Server | 1.5.0 | 44 |
| Context7 | 4.4.4 | 2 |
| Tavily | 0.2.22 | 5 |
| KBDB | 0.3.1 | 8 |

`copilot mcp list` reports all six workspace server definitions. Engram could not complete its first direct synchronization within the investigation budget: it reached 888 of 4,210 files after 636 seconds and remained CPU-active. The transport probe therefore remains degraded.

### What Was Tried and Failed

* Running the existing shim directly against JavaScript entrypoints failed with `uv_spawn` / `EFTYPE`
* Pointing Copilot directly at GitHub MCP Server failed at the discovery request
* Starting Backlogit MCP before the pinned binary bridge failed with `mcp daemon binary missing`
* Starting an Engram daemon without a completed graph returned a readiness timeout after 30 seconds

### Remaining Unknowns

* Whether the Engram initial sync completes within a practical startup budget on this workspace
* Whether a future Copilot CLI release fixes the Windows path-stripping behavior
* Whether Tavily's keyless fallback mode is acceptable when Copilot is launched outside `start.ps1`; the server connects, but authenticated calls still depend on the environment loaded by that script

## Recommendation

**Conclusion**: proceed
**Confidence**: medium

Use the generic stdio shim for local MCP servers and keep the workspace-local binary layout aligned around `.bin`. After the current CLI session reloads its MCP configuration, the five verified servers are ready to use.

Keep Engram initialization as degraded. Its daemon performs a full 4,210-file pre-warm before becoming Ready, and the 30-second shim budget is too short by orders of magnitude at the observed rate. This needs an Engram readiness or indexing optimization rather than another workspace path adjustment. The Copilot Git path-stripping defect likewise requires an upstream client fix; no repository-local MCP change can repair a path already stripped inside the host CLI.

## Next Steps

1. Run `/mcp reload` in the active Copilot session or restart it
2. Run an Engram direct synchronization separately when a longer maintenance window is available, then run its `discover -> initialize -> tools/list` probe
3. Track Engram daemon readiness separately from MCP transport configuration
4. Track the Copilot CLI Windows path issue upstream

## References

* `.mcp.json`
* `start.ps1`
* `tools/mcp/install.ps1`
* `tools/mcp/stdio-shim.cjs`
* `.copilot/logs/process-1795213098757-29496.log`
* `.engram/diagnostics/shim-startup-failures.jsonl`
* `docs/decisions/2026-08-27-mcp-stdio-server-deliberation.md`
