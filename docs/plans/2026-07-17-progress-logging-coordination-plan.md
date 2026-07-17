---
title: "Coordinate ProgressReporter with interleaved logging"
type: implementation-plan
date: 2026-07-17
source_stash_id: "3E91DB77"
slug: progress-logging-coordination
---

## Problem Frame

In NORMAL verbosity on a TTY, `ProgressReporter` writes an in-place
carriage-return progress line that is not newline-terminated until `finish()`.
Meanwhile `docline` emits `log.warning(...)` records to stderr during
fetch/process (plus Python's last-resort handler prints WARNING+ to stderr). A
warning emitted mid-progress appends to the active CR line and the next
carriage-return produces malformed terminal output. Non-TTY/piped output uses
newline lines and is unaffected. Follow-up from 052-S / PR #156; final polish
before the v1 release.

## Implementation Units

### Unit 1 — reporter clear + logging coordination (`src/docline/progress.py`)

- `ProgressReporter.clear()` erases the active in-place TTY line (CR + blanks +
  CR); no-op when no active line / non-TTY. `stream` property and
  `is_interactive()` accessor added.
- `_ProgressLogHandler(logging.Handler)` clears the reporter's line before
  writing each formatted record to the stream.
- `coordinate_logging(reporter, logger_name="docline")` context manager installs
  the handler on the package logger (propagation disabled to avoid duplicate
  output) for an interactive reporter only, restoring prior logging config on
  exit. No-op for `None`/SILENT/non-TTY.
- Tests: clear() erase + no-op cases; coordinate_logging clears before a record,
  restores logger state, and no-ops for non-TTY/None.

### Unit 2 — CLI wiring (`src/docline/cli.py`)

- Wrap the `fetch --execute` and `process` execution in
  `with coordinate_logging(reporter):` inside the existing `try/finally` that
  calls `reporter.finish()`.
- Tests: dispatch enters `coordinate_logging` for both commands.

### Unit 3 — docs (`README.md`)

- Note that interactive progress updates are coordinated with log output.

## Decisions

- **Handler on the `docline` package logger with `propagate=False`** — child
  loggers (`docline.app`, `docline.elt.execute`, …) propagate WARNING+ records up
  to it; disabling further propagation prevents duplicate output via root/last
  resort. State is restored on context exit.
- **TTY-only** — the corruption only occurs with in-place CR rendering; piped
  output already newline-terminates each line.

## Requires plan hardening: no

Additive, backward-compatible, no schema/security/migration surface. Runtime
surface: CLI stderr rendering (interactive only). Verified by unit tests with a
fake TTY stream and a test logger, plus CLI dispatch tests.
