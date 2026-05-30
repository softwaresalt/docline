# docline Development Guidelines

Last updated: 2026-05-30

docline is a document-to-markdown ingestion and normalization pipeline that operates as both a CLI tool and MCP server, converting heterogeneous documents (PDF, DOCX, VTT, HTML) into schema-validated Markdown for downstream RAG and graph database systems.

<!-- engram:start -->
## Engram Agent Memory — GitHub Copilot Integration

Engram is running as an MCP server at `http://127.0.0.1:7437/mcp`.

### Available Tools

Tool names may be client-prefixed or namespaced by the MCP host (for example,
`engram-set_workspace` instead of `set_workspace`). Use the workspace-binding,
memory, code-map, search, and optional task/history tools exposed by the
connected Engram server.

| Capability | Purpose |
|------------|---------|
| Workspace binding | Register this workspace at session start |
| Memory lookup | Retrieve stored context, tasks, and code knowledge |
| Task tracking | Create or update workspace task records when those tools are exposed |
| Code mapping | Index code files for semantic navigation |
| Unified search | Search across all content types |
| Change history | Query git commit history by file, symbol, or date when supported |

### Recommended Workflow

1. **Session start**: Call the workspace-binding tool exposed by Engram for the current workspace path.
2. **Before coding**: Use the memory lookup tool to load relevant context.
3. **Task tracking**: Use task create/update tools when the connected client exposes them.
4. **Code navigation**: Use code-map and unified-search tools for codebase exploration.
5. **Change history**: Use the history/query tool when supported by the connected Engram surface.
<!-- engram:end -->

## Technology Stack

| Layer           | Technology                | Notes                                 |
|-----------------|---------------------------|---------------------------------------|
| Language        | Python 3.12 | (requires Python 3.12+)          |
| Build           | pip            | `python -m build`                   |
| Test            | pytest           | `pytest`                    |
| Lint            | ruff                | `ruff check .`                    |
| Format          | ruff             | `ruff format --check .`                  |
| CI              | GitHub Actions           | GitHub Actions (not yet configured — greenfield project)                          |
| Pydantic | Schema validation and runtime typing |
| FastAPI | MCP server framework |
| docling | PDF/DOCX layout analysis |
| markdown-it-py | AST generation and linting |

## Project Structure

```text
src/docline/ — main package
tests/ — pytest test suite
docs/design-docs/ — architecture and design documents
docs/product-specs/ — product requirements
```

## Commands

| Command | Purpose |
|---|---|
| `python -m build` | Build distributable artifacts |
| `pytest` | Run the full pytest suite |
| `ruff check .` | Run lint gate |
| `ruff format --check .` | Verify formatting |
| `docline fetch` | Run the I/O-bound document fetch phase |
| `docline process` | Run the compute-bound processing phase |
| `docline --manifest` | Output the JSON Schema tool definition |

## Code Style and Conventions

### Error Handling

Raise specific Exception subclasses; never bare except

### Naming

snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants

### Documentation

Google-style docstrings on all public functions and classes

### Testing

* TDD required: write tests first, verify they fail, then implement
* Test tiers in `tests/` directory:
  * Unit: `pytest`
  * Integration: `pytest -m integration`
* Preserve dual-interface parity: add or update coverage when CLI and MCP behavior diverge

## Session Start Protocol

1. Send an intercom heartbeat / ping at session start; if it fails, declare `INTERCOM_DEGRADED`.
2. Verify engram workspace binding before discovery and use `unified_search` for pre-planning; if that fails, declare `ENGRAM_DEGRADED` and fall back to targeted `grep`, `glob`, and `view` usage.
3. Query backlogit first for queue selection and dependency-aware planning rather than inventing task order from prose.
4. Represent risky work as `ProposedAction` with `ActionRisk` and capture `ActionResult` after execution.
5. Broadcast phase transitions so operators can observe planning, implementation, review, verification, and closure.

## Search Strategy

Use available workspace search tools before falling back to file-based search
(grep, glob, view). Indexed search returns precise results with minimal token
cost. File-based tools read raw content into the context window, consuming
tokens proportional to file size.

**Search tool preference order:**

1. When the `agent-engram` capability pack is enabled and reachable: `unified_search`, `query_memory`, `map_code`, `list_symbols`, `impact_analysis`, `query_graph`
2. Otherwise use workspace-indexed tools (if available): semantic search, symbol lookup, call graphs
3. File-based fallback: grep, glob, view — only when indexed results are insufficient

## Durable Knowledge Layout

| Path | Purpose |
|---|---|
| `docs/compound/` | Reusable learnings and hard-won fixes |
| `docs/plans/` | Implementation plans |
| `docs/decisions/` | Durable decisions and investigation outputs |
| `docs/memory/` | Session memory and checkpoints |
| `docs/closure/` | Review, runtime verification, and closure artifacts |
| `docs/design-docs/` | Graduated architecture and design rationale |
| `docs/product-specs/` | Product-oriented requirements |

## Session Memory Requirements

* Working agent sessions MUST persist output to `docs/memory/` before the session ends — do NOT rely on built-in AI assistant memory features, which write to their own managed locations.
* When the context window reaches approximately 65% capacity, checkpoint current work before continuing.
* For long sessions, save memory checkpoints after completing each phase or major task group.
* Content to capture: task IDs completed, files modified, decisions and rationale, failed approaches, open questions, and next steps.
* File convention: `docs/memory/{YYYY-MM-DD}/{descriptive-slug}-memory.md`
* After writing memory, invoke the **compact-context** skill to consolidate stale checkpoints and finalize decided-plans. This is a mandatory workflow step, not advisory.
* If context has grown from loading multiple skill definitions mid-session, consider invoking **compact-context** proactively before hitting hard thresholds.

## Foundational Protocols

| Protocol | Location | When |
|---|---|---|
| **Circuit Breaker** | `.github/instructions/circuit-breaker.instructions.md` | All retry loops and failure handling |
| **Concurrency Control** | `.github/instructions/concurrency.instructions.md` | Multi-agent or human+agent concurrent edits |
| **Skill Discovery** | `scripts/search.ps1` / `scripts/search.sh` | Finding capabilities by keyword (Primitive 6) |

## Optional Capability Packs

### agent-intercom

When the workspace enabled the `agent-intercom` capability pack:

* verify the intercom server / tool surface is reachable before depending on remote approval or operator steering
* call heartbeat / ping at session start and keep it alive during long-running work
* broadcast major workflow transitions so the operator can observe planning, build, review, verification, and closure progress
* route destructive terminal commands and destructive file operations through the intercom approval workflow
* use transmit / standby flows when blocked on operator clarification or when intentionally pausing for instructions
* if the intercom service is unreachable, declare `INTERCOM_DEGRADED`, warn that remote visibility is reduced, and continue only with safe non-destructive work

### agent-engram

When the workspace enabled the `agent-engram` capability pack:

* verify the engram daemon / MCP surface is reachable before depending on indexed lookup
* verify workspace binding at session start and use `unified_search` during pre-planning before broad file scans
* prefer engram tools for conceptual search, symbol discovery, call-graph lookup, impact analysis, and workspace-memory retrieval
* use `sync_workspace` or the equivalent freshness operation when code changed outside the expected indexing flow
* if semantic search is unavailable or degraded, declare `ENGRAM_DEGRADED` and fall back to targeted `grep`, `glob`, and `view` usage
* treat `.engram/` generated artifacts as tool-managed state rather than files to hand-edit casually

### backlogit

When the workspace enabled the `backlogit` capability pack:

* verify the backlogit MCP / CLI surface is reachable before depending on queue, dependency, memory, or traceability operations
* select work from backlogit queue operations first and honor dependency edges rather than inferring order from prose alone
* write concise memory summaries and checkpoints through backlogit operations at task and session boundaries when supported
* append significant task comments and associate commits with task IDs for execution traceability when those operations are available
* if backlog content was edited outside the normal mutation flow, refresh the backlogit index before relying on query results

### strict-safety

When the workspace enabled the `strict-safety` capability pack:

* follow `.github/instructions/strict-safety.instructions.md`
* express risky work as `ProposedAction` entries with `ActionRisk` and `ActionResult`
* require explicit approval before destructive actions and prefer approval for high-blast-radius actions
* keep risky action records visible in plan hardening, review, runtime verification, and operational closure

## Remote Operator Integration

### agent-intercom

When `agent-intercom` is available:

* Call `ping` at the start of any multi-step session to confirm liveness.
* Broadcast progress at meaningful phase transitions — do not broadcast every trivial step.
* Route approval for destructive actions through the intercom approval workflow before executing.
* If intercom becomes unreachable mid-task, warn that operator visibility is degraded and continue only with safe, non-destructive work.

The `ping-loop.prompt.md` prompt is available in `.github/prompts/` for sustained heartbeat sessions when the pack is installed.

### agent-engram

When `agent-engram` is available:

* Verify workspace binding before relying on indexed results.
* If the workspace is not bound or indexed, run `sync_workspace` or the workspace's equivalent freshness operation before searching.
* Fall back to grep, glob, or direct file reads only when indexed results are unavailable or insufficient.

## Backlog Workflow Expectations

When a backlog tool is active in the workspace:

* prefer queue-aware and dependency-aware operations over prose-only sequencing when the tool surface supports them
* use comments, checkpoints, and commit-tracking operations when they add traceability
* refresh the backlog index or query cache after out-of-band edits before trusting query results
* avoid inventing parallel markdown trackers outside the configured backlog tool surface

Generated by autoharness | Template: copilot-instructions.md.tmpl
