---
title: "Console verbosity + progress reporting for docline fetch/process"
type: deliberation
date: 2026-07-16
conclusion: "proceed"
confidence: "high"
source_stash_id: "079BBFE3"
linked_parent_work_item: "079BBFE3"
tags:
  - "cli"
  - "fetch"
  - "process"
  - "observability"
  - "progress"
---

## Problem frame

`docline fetch` and `docline process` print only a single terminal JSON line at
the very end of a run. During a long web crawl (e.g. the ~1148-page PostgreSQL
`/docs/current` ingest, ~30–40 min) the operator sees **no progress** and must
monitor process memory or output-file counts externally to know the run is
alive and advancing. This entry decides the shape of a verbosity + live-progress
capability for both commands.

Grounded in code (2026-07-16):

- **fetch (CLI)**: `cli.py` `fetch` dispatch → `execute_elt_fetch` (`elt/execute.py:99`)
  → `_execute_single_source` → `_fetch_url` (`elt/execute.py:479`) →
  `asyncio.run(crawl(url, cfg))` (`fetch/crawl.py:100`). The crawl is a bounded
  BFS: `while frontier and page_count < max_pages` — the slow, network-bound
  phase. `crawl()` accumulates all `CrawlResult`s in memory and returns at the
  end; `_fetch_url` writes staged files only **after** crawl returns.
- **fetch (MCP)**: `execute_fetch` (`app.py:554`) → `execute_source_configs`
  (`elt/execute.py:140`) → same `_execute_single_source` → `_fetch_url` → `crawl`.
- **process**: `execute_process` (`app.py:716`) iterates
  `for file_path in _ordered_staged_files(files_dir, crawl_entries)` (`app.py:782`),
  nested inside an outer loop over each completed staging job's `metadata.json`.
  The per-job file total is known up front (`len(_ordered_staged_files(...))`).

## Options considered

### O1 — Flag convention

- **O1a `-q/--quiet` + `-v/--verbose` pair** (mutually exclusive), resolved to an
  internal `Verbosity` enum (SILENT / NORMAL / VERBOSE), default NORMAL.
- **O1b `--verbosity {silent,normal,verbose}` enum flag.**

**Chosen: O1a.** The `-q`/`-v` pair is the conventional Unix idiom, ergonomic for
interactive use, and argparse's mutually-exclusive group cleanly rejects
`-q -v`. Internally both still resolve to a single `Verbosity` enum, so the enum
value (not the raw flags) flows through the code — this keeps O1b's clarity
without its verbosity at the call site.

### O2 — fetch progress percentage estimator

- **O2a `pages_fetched / max_pages`** — simple, bounded, monotonic.
- **O2b `pages_fetched / (visited + remaining_frontier)`** — moving estimate that
  tracks the growing BFS frontier.

**Chosen: O2a.** The frontier estimate (O2b) oscillates as discovery expands and
can regress, which reads as a broken progress bar. `max_pages` is a hard budget
already enforced by the crawl loop, so `pages_fetched / max_pages` is a stable
lower-bound percentage. When the frontier exhausts before the budget (crawl ends
early), the reporter **clamps to 100% on completion**. Percent is advisory; the
absolute `pages_fetched` count is always shown alongside.

### O3 — Progress transport (dual-interface parity)

- **O3a Optional `progress` callback/observer** threaded through the library
  functions (`crawl`, `_fetch_url`, `execute_elt_fetch`, `execute_source_configs`,
  `execute_fetch`, `execute_process`), default `None`. The CLI constructs a
  reporter and passes it; the library never prints.
- **O3b stdlib `logging` at a level mapped from verbosity.**

**Chosen: O3a.** A default-`None` keyword callback keeps every library function
pure and print-free, preserving the MCP surface exactly (the callback is a
Python-level param, not part of the MCP/JSON schema). Logging (O3b) couples
progress to global logger configuration and risks leaking handlers into the MCP
process; a passed-in observer is easier to unit-test deterministically.

### O4 — Output routing vs the terminal JSON contract

- **O4a Progress → `stderr`; result JSON → `stdout` (unchanged in all modes).**
- **O4b Progress + JSON both on stdout; suppress/gate JSON in silent via `--json`.**

**Chosen: O4a.** Routing progress to **stderr** and keeping the final result JSON
on **stdout** cleanly separates human-facing progress from machine-parseable
output. Scripts that parse stdout are unaffected regardless of verbosity, and
piping stdout is automatically progress-free (no control chars in captured
output). `quiet` therefore only silences stderr progress; the terminal JSON
result contract is **never** changed. This sidesteps O4b's "should silent
suppress JSON" question entirely and needs no separate `--json` flag.

## Chosen direction (summary)

1. Add a `-q/--quiet` + `-v/--verbose` mutually-exclusive pair to the `fetch` and
   `process` subparsers, resolving to a `Verbosity` enum (default NORMAL).
2. Add a pure, TTY-aware `ProgressReporter` (new module) that formats and
   throttles progress and writes to a stream (default `stderr`): carriage-return
   in-place updates when the stream is a TTY, newline-terminated lines otherwise;
   throttle to ~1s / every N items; SILENT emits nothing.
3. Thread an optional `progress` callback (default `None`) through the fetch
   library seam (`crawl` → `_fetch_url` → `execute_elt_fetch` /
   `execute_source_configs` / `execute_fetch`) and the process seam
   (`execute_process` per-file loop). Libraries stay print-free.
4. Wire the reporter only at the CLI layer; keep the terminal JSON on stdout
   unchanged in every mode.

- **fetch %**: `pages_fetched / max_pages`, clamped to 100% at completion.
- **process %**: `files_done / total_files` (per-job total from
  `len(_ordered_staged_files(...))`).

## Open questions / risks

- **process multi-job total**: `execute_process` loops over multiple completed
  staging jobs; a true global percentage needs a pre-scan sum of per-job file
  counts. Deferred decision surfaced to the plan: report **per-job** progress
  (files_done/total within each job, with a job index prefix) rather than
  pre-scanning, to avoid a second directory walk. Low risk — counts are still
  accurate, only the denominator scope differs.
- **Backward compatibility**: all library signature changes are additive optional
  keyword params defaulting to `None`; MCP schema and terminal JSON are unchanged.
- **No security/migration/destructive surface** — purely additive CLI UX.

## Traceability

Promotes stash `079BBFE3` (kind: feature, medium). This deliberation is the
source document for the implementation plan
(`docs/plans/2026-07-16-console-verbosity-progress-plan.md`).
