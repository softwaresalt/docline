---
type: decided-plan
source_plan: 2026-07-16-console-verbosity-progress-plan.md
consolidated_at: 2026-08-29
status: shipped
---

## Decision Summary

The shipped console verbosity work added live progress reporting for long `docline fetch` and `docline process` runs without changing the library print-free contract, MCP schemas, or terminal JSON on stdout. Human progress goes to stderr, while stdout remains machine-readable result JSON.

The chosen model uses `-q/--quiet` and `-v/--verbose` mapped to a `Verbosity` enum, optional progress callbacks through library seams, TTY-aware rendering, and throttled normal-mode updates. Fetch reports budget-consumed crawl progress and a final staged-count event; process reports monotonic global file progress across jobs.

## Implementation Units

* Unit 1: `ProgressReporter`, `ProgressEvent`, and `Verbosity` with math, throttle, TTY, non-TTY, silent, normal, verbose, and `finish()` behavior
* Unit 2a: optional `crawl()` progress callback fired only when `page_count` is consumed
* Unit 2b: thread progress through fetch execution seams and emit final staged-count event
* Unit 3: add per-file progress callback to `execute_process` with global totals across jobs
* Unit 4: add CLI quiet/verbose flags and wire reporter to fetch/process dispatch
* Unit 5: document flags and stdout/stderr semantics

## Key Constraints

* No library function prints; progress is callback-driven and defaults to `None`
* Progress never leaks into stdout JSON
* Fetch completion never fabricates 100%; known totals render actual `done/total`, unknown totals render count-only
* Non-TTY output uses newline lines and no carriage-return control characters
* `progress` must not enter Pydantic request models or MCP/JSON manifest schemas
* New parameters are optional keywords and backward-compatible

## Rejected Alternatives

* Use a single `--verbosity` enum flag — rejected in favor of idiomatic Unix `-q` and `-v`
* Use stdlib logging for progress — rejected because callbacks are deterministic and keep libraries print-free
* Force fetch progress to 100% at completion — rejected because `max_pages` is a budget, not an expected total
* Reset process progress per job — rejected because cumulative global progress avoids regressions at job boundaries
* Add a `--json` mode to protect stdout — rejected as unnecessary because stdout JSON remains unchanged in all modes

## Review Outcome

Plan review was advisory. Two P2 refinements were folded into acceptance criteria: keep callback seams primitive while `ProgressReporter` constructs events internally, and explicitly test that MCP request models and manifest output remain unchanged.

## Traceability

Full deliberation history archived at docs/archive/plans/2026-07-16-console-verbosity-progress-plan.md

