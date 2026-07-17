---
shipment: 052-S
title: "Closure record — console verbosity + live progress for docline fetch/process (056-F)"
status: verified
merge_sha: 2ccd638
merged_pr: 156
---

## Scope delivered

Feature `056-F` (shipment `052-S`, from stash `079BBFE3`) adds a `-q/--quiet` +
`-v/--verbose` verbosity control and live progress reporting to `docline fetch`
and `docline process`. Progress is written to **stderr** (TTY-aware, throttled);
the terminal JSON result on **stdout** is unchanged in every mode, and the
`progress` callback is kept off the `FetchRequest`/`ProcessRequest` Pydantic
models so the MCP tool schema is unchanged.

| Task | Delivered |
|---|---|
| `056.010-T` | `src/docline/progress.py` — `Verbosity` enum, `ProgressEvent`, and a pure TTY-aware `ProgressReporter` (NORMAL throttled concise line / VERBOSE per-item line / SILENT no-op). `finish()` emits a final line and never fabricates 100% (`total is None` is the only count-only case; incomplete known totals keep their true ratio, capped at 99). `detail` is sanitized against control-character/terminal injection. |
| `056.008-T` | `crawl()` gains an optional `progress` callback that fires once per `page_count` increment (budget-consuming branches only — robots-denied, fetch failure, domain-rejected redirect, emitted page). |
| `056.011-T` | The fetch seam (`_fetch_url`, `_execute_single_source`, `execute_source_configs`, `execute_elt_fetch`, `execute_fetch`) forwards `progress` into `crawl`; `_fetch_url` emits a final count-only `(staged_count, None)` completion event via `except/else` that preserves the original error and never masks it. |
| `056.012-T` | `execute_process` reports a global cumulative `files_done/total` across all completed jobs (monotonic, job identity in the detail), firing after each file's processing across every exit path; the progress pre-scan's ordered file lists are cached to avoid a second corpus traversal. |
| `056.007-T` | `cli.py` adds a mutually-exclusive `-q/-v` group to both subparsers, resolves to `Verbosity`, builds a stderr `ProgressReporter` (or `None` for quiet, skipping the pre-scan), and finalizes it in `try/finally`. |
| `056.009-T` | `README.md` — flags, the stderr-progress / stdout-JSON contract, metric semantics, and the verbose final completion line. |

## Verification

All quality gates green on the merge: `ruff check`, `ruff format --check`,
`pyright src/` (0 errors), and `pytest` (1626 passed, 6 skipped). New coverage:
`tests/test_progress.py`, `tests/fetch/test_crawl_progress.py`,
`tests/elt/test_execute_fetch_progress.py`,
`tests/test_execute_process_progress.py`, `tests/test_cli_verbosity.py`.

Runtime behavior verified via the CLI dispatch tests: `-q` silences stderr and
still prints the JSON result on stdout; `-v` emits per-item lines plus a final
completion line on stderr while stdout carries only the JSON; `-q -v` is rejected
by argparse (exit 2).

The PR passed a thorough Copilot review (10 rounds) covering a terminal-injection
fix, a double-traversal performance fix, the fetch budget-vs-staged-count model,
and error-path exception preservation.

## Follow-ups

* Stash `3E91DB77` (low): coordinate the reporter's in-place TTY line with
  interleaved `log.warning` output (NORMAL/interactive-TTY only; piped output is
  unaffected). Deferred as a distinct enhancement beyond the shipped units.
