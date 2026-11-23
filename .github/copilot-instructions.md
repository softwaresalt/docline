# docline Development Guidelines

Last updated: 2026-11-18

docline is a docline workspace.

## Technology Stack

| Layer           | Technology                | Notes                                 |
|-----------------|---------------------------|---------------------------------------|
| Language        | Python 3.12 | (3.12)          |
| Build           | uv / build            | `uv run python -m build`                   |
| Test            | pytest           | `uv run pytest`                    |
| Lint            | ruff                | `uv run ruff check .`                    |
| Format          | ruff             | `uv run ruff format --check .`                  |
| CI              | GitHub Actions           | Uses GitHub Actions for CI validation.                          |


## Project Structure

```text
src/docline/ — main package
tests/ — pytest test suite
docs/design-docs/ — architecture and design documents
docs/product-specs/ — product requirements
```

## Commands

```bash
uv run python -m build              # Build
uv run pytest               # Run all tests
uv run ruff check .               # Lint
uv run ruff format --check .             # Format check
uv run pyright src/                   # Type check
docline fetch                  # Run the I/O-bound document fetch phase
docline process                # Run the compute-bound processing phase
docline --manifest             # Output the JSON Schema tool definition
```

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
Primary test command: uv run pytest

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
* Memory date folders (`docs/memory/{YYYY-MM-DD}/`) use the UTC date, and all recorded dates and times are UTC (`Z`); see `.github/instructions/output-timestamps.instructions.md`.
* After writing memory, invoke the **compact-context** skill to consolidate stale checkpoints and finalize decided-plans. This is a mandatory workflow step, not advisory.
* If context has grown from loading multiple skill definitions mid-session, consider invoking **compact-context** proactively before hitting hard thresholds.

## Foundational Protocols

| Protocol | Location | When |
|---|---|---|
| **Circuit Breaker** | `.github/instructions/circuit-breaker.instructions.md` | All retry loops and failure handling |
| **Concurrency Control** | `.github/instructions/concurrency.instructions.md` | Multi-agent or human+agent concurrent edits |
| **Skill Discovery** | `scripts/search.ps1` / `scripts/search.sh` | Finding capabilities by keyword (Primitive 6) |

## Optional Capability Packs

### agent-engram

When the workspace enabled the `agent-engram` capability pack:

* verify the engram daemon / MCP surface is reachable before depending on indexed lookup
* prefer engram tools for conceptual search, symbol discovery, call-graph lookup, impact analysis, and workspace-memory retrieval
* verify the workspace binding state before relying on results; if the daemon auto-binds the workspace, prefer status checks over repeated rebinding
* use `sync_workspace` or the equivalent freshness operation when code changed outside the expected indexing flow
* if semantic search is unavailable or degraded, fall back to `list_symbols` + `map_code` + `impact_analysis` before resorting to broad file scans
* treat `.engram/` generated artifacts as tool-managed state rather than files to hand-edit casually

### backlogit

When the workspace enabled the `backlogit` capability pack:

* follow `.github/instructions/backlogit.instructions.md`
* verify the backlogit MCP / CLI surface is reachable before depending on queue, dependency, memory, or traceability operations
* prefer backlogit query operations for targeted state lookup instead of reading many backlog markdown files into context
* use backlogit queue and dependency operations when available rather than inferring execution order from prose alone
* write concise memory summaries and checkpoints through backlogit operations at task and session boundaries when supported
* append significant task comments and associate commits with task IDs for execution traceability when those operations are available
* if backlog content was edited outside the normal mutation flow, refresh the backlogit index before relying on query results

### kbdb

When the workspace enabled the `kbdb` capability pack:

* follow `.github/instructions/kbdb.instructions.md`
* verify the kbdb server / MCP surface is reachable and sources are indexed before depending on indexed documentation retrieval
* prefer `search_local_docs`, `search_semantic`, and `research_topic` for conceptual, API-oriented, or documentation questions before broad web search or raw file scans
* use `traverse_doc_links` to follow related documentation and `list_sources` to confirm indexed coverage
* if the server is unavailable or sources are not indexed, fall back to grep, glob, or direct file reading and note reduced confidence
* treat `.kbdb/` generated artifacts as tool-managed state rather than files to hand-edit casually

## Core Workflow Protocols

These protocols are part of the core harness and are always active; they are not capability packs. Each applies when its surface condition is met.

### browser-verification

When verifying browser-visible UI flows (core protocol):

* verify the target server or preview environment is reachable before launching browser work
* choose headed vs headless mode intentionally and record the reason
* derive browser routes from changed pages, components, or affected user journeys
* treat OAuth, email, SMS, payments, CAPTCHAs, or other external flows as explicit human checkpoints
* carry browser findings into runtime verification and operational closure rather than leaving them as informal notes

### continuous-learning

When recurring practice is observed across sessions (core protocol):

* follow `.github/instructions/continuous-learning.instructions.md`
* store observation state under `.gsd/continuous-learning/`
* keep hook capture optional and environment-specific; manual capture is still valid
* use `observe` to capture recurring workflow signals, `learn` to infer instincts, and `evolve` to promote mature patterns into `learned-*` artifacts
* do not harden a rule into a learned instruction or skill until it has enough corroborating observations to justify the promotion
* treat learned artifacts as explicit repository knowledge rather than invisible prompt-only behavior

### strict-safety

For elevated-risk or destructive work (core protocol):

* follow `.github/instructions/strict-safety.instructions.md`
* express risky work as `ProposedAction` entries with `ActionRisk` and `ActionResult`
* require explicit approval before destructive actions and prefer approval for high-blast-radius actions
* keep risky action records visible in plan hardening, review, runtime verification, and operational closure

### release-observability

For runtime-affecting or deployment-sensitive release units (core protocol):

* follow `.github/instructions/release-observability.instructions.md`
* produce monitoring plans with SLIs, dashboards, baselines, and alert thresholds before merge
* complete pre-deploy audit checklists for runtime, migration, or rollout-risk changes
* define explicit post-deploy observation windows with owner and duration
* declare rollback triggers with named metrics and thresholds
* carry all release-observability artifacts into operational closure

### adversarial-review

When a review surfaces 3+ P0/P1 findings or touches security-sensitive work (core protocol):

* follow `.github/instructions/adversarial-review.instructions.md`
* escalate from standard review when 3+ P0/P1 findings appear or the work is security-sensitive
* dispatch parallel reviewer instances across different model tiers for cross-model diversity
* assemble consensus-weighted findings (HIGH / MEDIUM / LOW confidence)
* treat HIGH-confidence P0/P1 findings as gate-blocking
* feed remediation queue entries into backlog

## Remote Operator Integration

<!-- pack-scope:agent-engram:begin -->
### agent-engram

When `agent-engram` is available:

* Verify workspace binding before relying on indexed results.
* If the workspace is not bound or indexed, run `sync_workspace` or the workspace's equivalent freshness operation before searching.
* Fall back to grep, glob, or direct file reads only when indexed results are unavailable or insufficient.
<!-- pack-scope:agent-engram:end -->

## Backlog Workflow Expectations

When a backlog tool is active in the workspace:

* prefer queue-aware and dependency-aware operations over prose-only sequencing when the tool surface supports them
* use comments, checkpoints, and commit-tracking operations when they add traceability
* refresh the backlog index or query cache after out-of-band edits before trusting query results
* avoid inventing parallel markdown trackers outside the configured backlog tool surface

## Workspace-Local `.gsd/` Runtime

Target workspaces provision the `gsd` executable (`.gsd/gsd` or `.gsd/gsd.exe`), pre-built versioned release archives (`.gsd/gsd-assets-v<version>.zip` and `.gsd/gsd-assets.zip`), and `.gsd/runtime-manifest.json` inside `<workspace>/.gsd/` (ignored by Git via `# gsd-runtime-ignore`) so all CLI and install/tune operations stay inside the workspace sandbox without unpacking `templates/` or `schemas/` into the repository.

Generated by gsd | Template: copilot-instructions.md.tmpl
