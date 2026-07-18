---
shipment: 053-S
title: "Closure record — coordinate progress reporter with interleaved logging (057-F)"
status: verified
merge_sha: 173c820
merged_pr: 158
---

## Scope delivered

Feature `057-F` (shipment `053-S`, from stash `3E91DB77`) is the interactive-TTY
polish follow-up to `056-F` / PR #156. In NORMAL verbosity on a TTY, the
`ProgressReporter` writes a carriage-return progress line that is not
newline-terminated until `finish()`. A `log.warning` emitted mid-progress
previously appended to that active line and the next carriage-return produced
malformed terminal output. This feature coordinates the two so log records are
emitted cleanly and the progress line redraws afterward. Non-TTY / piped output
is unaffected (no carriage-return is used).

| Task | Delivered |
|---|---|
| `057.002-T` | `src/docline/progress.py` — `ProgressReporter.clear()` erases the active in-place TTY line (CR + blanks + CR) and re-arms the NORMAL throttle (`_emitted = False`) so the next event redraws immediately; `stream` property + `is_interactive()`; a module-level `_ProgressLogHandler` that clears the active line before emitting each record; and a `coordinate_logging()` context manager that **replaces** the target logger's handlers with the clearing handler (restoring the originals and `propagate` on exit) so pre-existing handlers cannot double-emit onto the progress line. All paths no-op for `None` / SILENT / non-TTY. |
| `057.001-T` | `src/docline/cli.py` — the `fetch --execute` and `process` executions are wrapped in `with coordinate_logging(reporter):` inside the existing `try/finally` that finalizes the reporter. |
| docs | `README.md` — note on interactive log/progress coordination. |

## Verification

All quality gates green on the merge: `ruff check`, `ruff format --check`,
`pyright src/` (0 errors), and `pytest` (1638 passed, 6 skipped). New coverage in
`tests/test_progress.py` (clear / is_interactive / coordinate_logging, including
throttle re-arm and existing-handler suppression) and `tests/test_cli_verbosity.py`
(both dispatch paths enter `coordinate_logging`).

CI was 7/7 green on the merge head. The PR passed Copilot review; round-1 comments
(throttle re-arm on `clear()`, handler replacement to suppress duplicate emission,
and a backlog-manifest reconciliation note) were fixed in `910a715`, replied to,
and resolved before merge.

## Notes

* This is the final polish item the operator wanted completed before docline's
  first release; the remaining stash entries are largely blocked on Mistral OCR
  v4 access.
* Backlog tooling note: the two child tasks were originally created directly as
  `done` in a compressed inline Stage→Ship flow, which left their ship-gate
  ledger open (no `active→done` transition). The shipment was unblocked by
  transitioning each task `blocked → active → done` with the merge SHA to record
  genuine passing gate evidence, then shipping. Captured as a compound learning
  to avoid re-deriving this next time.
