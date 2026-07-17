---
title: "Console verbosity + progress reporting for docline fetch/process"
type: implementation-plan
date: 2026-07-16
source: docs/decisions/2026-07-16-console-verbosity-progress-deliberation.md
slug: console-verbosity-progress
source_stash_id: "079BBFE3"
---

## Problem Frame

`docline fetch` and `docline process` emit only a single terminal JSON line at
the end of a run, so a long crawl (~30–40 min for the ~1148-page PostgreSQL
`/docs/current` ingest) gives the operator zero visibility. We add a verbosity
control and live progress reporting to both commands **without** changing the
library functions' print-free contract or the terminal JSON on stdout.

Grounded code seams (2026-07-16):

- fetch CLI: `cli.py` `fetch` dispatch → `execute_elt_fetch` (`elt/execute.py:99`)
  → `_execute_single_source` (`:167`) → `_fetch_url` (`:479`) →
  `asyncio.run(crawl(...))` (`fetch/crawl.py:100`, BFS loop `:142`).
- fetch MCP: `execute_fetch` (`app.py:554`) → `execute_source_configs`
  (`elt/execute.py:140`) → same `_execute_single_source` seam.
- process: `execute_process` (`app.py:716`), per-file loop
  `for file_path in _ordered_staged_files(...)` (`:782`); per-job total is
  `len(_ordered_staged_files(...))`.

## Requirements Trace

| Requirement (stash 079BBFE3) | Implementation |
|---|---|
| Verbosity flag on both commands (default normal) | Unit 4 — `-q/--quiet` + `-v/--verbose` on fetch + process subparsers → `Verbosity` enum |
| Live progress during long runs | Units 1–4 — reporter + library callbacks + CLI wiring |
| Progress percentage (process = done/total; fetch = fetched/max_pages) | Unit 1 (math) + Units 2b/3 (counts) |
| Dual-interface parity — no printing from library | Units 2a/2b/3 — optional `progress` callback, default `None` |
| TTY awareness (CR in-place vs newline lines) | Unit 1 — reporter stream-`isatty()` branch |
| Throttle updates (~1s / every N) | Unit 1 — reporter cadence gate |
| Terminal JSON contract unchanged; progress off stdout | Unit 4 — progress → stderr, JSON → stdout unchanged |
| Unit tests: reporter math/throttle/TTY + CLI flag parsing | Units 1 & 4 test scenarios |

## Implementation Units

### Unit 1 — ProgressReporter core (test-first)

- **Change**: New module `src/docline/observability/progress.py` (create
  `observability/` package if absent) defining: `Verbosity` enum
  (`SILENT`/`NORMAL`/`VERBOSE`); a small `ProgressEvent` (phase label, done,
  total-or-None, optional detail string); and `ProgressReporter` that renders an
  event to a stream (default `sys.stderr`). Rendering is verbosity-aware:
  **NORMAL** emits throttled concise updates (a single percentage/count line,
  in-place via carriage-return on a TTY, at most every ~1.0s or every N items);
  **VERBOSE** emits one line per item with its detail (URL/path) + running
  percentage (not throttled); **SILENT** emits nothing. When the stream is not a
  TTY, all output is newline-terminated with no control characters. A
  `finish(detail=None)` method emits the final line **unconditionally**
  (bypassing the throttle): 100% when the total is known, or the final count when
  the total is unknown or the run ended before reaching it (e.g. crawl frontier
  exhausted before `max_pages`). Percentage helper clamps `done/total` to
  `[0,100]` and treats `total is None`/`0` as count-only ("no ETA") output.
- **Files**: `src/docline/observability/progress.py`, `tests/observability/test_progress.py`.
- **Tests**: (1) percentage math incl. clamp + `total=None` count-only;
  (2) throttling — rapid NORMAL calls coalesce, final call always emits;
  (3) TTY vs non-TTY formatting (CR vs `\n`, no control chars when not a TTY);
  (4) SILENT emits nothing; (5) NORMAL renders a single throttled concise line
  while VERBOSE renders one detailed line per item (per-item lines not dropped);
  (6) `finish()` emits the final line even when the last update had `done < total`
  (early completion) — 100% when total known, else the final count.
- **Posture**: test-first.

### Unit 2a — `crawl()` progress callback (test-first)

- **Change**: Add optional keyword `progress: Callable[[int, int, str], None] | None = None`
  to `crawl()` (`fetch/crawl.py:100`). Invoke it once per processed page inside
  the BFS loop with `(page_count, crawl_config.max_pages, current_url)`. The
  per-page callback is a **progress** signal only — when the frontier exhausts
  before `max_pages` its last event has `done < total`; final completion is
  emitted separately by the CLI via `ProgressReporter.finish()` after `crawl()`
  returns (see Units 1 and 4), preserving the actual fetched count. Default
  `None` = exact current behavior.
- **Files**: `src/docline/fetch/crawl.py`, `tests/fetch/test_crawl_progress.py`.
- **Tests**: callback invoked once per page with monotonic non-decreasing counts
  ≤ max_pages; **early frontier exhaustion** (frontier empties before `max_pages`)
  ends with a last event where `done < total` and `crawl` forges no synthetic
  100%; `None` default leaves results unchanged (characterization).
- **Posture**: test-first.

### Unit 2b — Thread fetch callback through the library seam

- **Change**: Add optional `progress` param (default `None`) to `_fetch_url`,
  `_execute_single_source`, `execute_source_configs`, `execute_elt_fetch`
  (`elt/execute.py`) and `execute_fetch` (`app.py`), forwarding into
  `crawl(..., progress=progress)`. No function prints.
- **Files**: `src/docline/elt/execute.py`, `src/docline/app.py`.
- **Tests**: `tests/elt/test_execute_fetch_progress.py` — a stub `crawl` (or a
  fake source) confirms the callback reaches `crawl`; `None` default unchanged.
- **Posture**: test-first. **Depends on Unit 2a.**

### Unit 3 — `execute_process` per-file progress callback (test-first)

- **Change**: Add optional `progress: Callable[[int, int, str], None] | None = None`
  to `execute_process` (`app.py:716`). For each completed job, compute
  `total = len(ordered_files)` and invoke `progress(files_done, total, rel_path)`
  after each file. No printing.
- **Files**: `src/docline/app.py`, `tests/test_execute_process_progress.py`.
- **Tests**: callback invoked once per staged file with correct running
  `files_done`/`total`; `None` default preserves current behavior.
- **Posture**: test-first.

### Unit 4 — CLI flags + reporter wiring

- **Change**: Add a mutually-exclusive `-q/--quiet` + `-v/--verbose` group to the
  `fetch` and `process` subparsers (`cli.py`); resolve to a `Verbosity` enum
  (`-q`→SILENT, default→NORMAL, `-v`→VERBOSE). In `main()` dispatch, build a
  `ProgressReporter(verbosity, stream=sys.stderr)`, pass its `__call__` as the
  `progress` callback to `execute_elt_fetch` (fetch `--execute`) and
  `execute_process`, and call `reporter.finish()` after the call returns so the
  final 100%/final-count line is always emitted (even if the last per-item event
  had `done < total`). Keep the terminal `print(json...)` on stdout unchanged in
  all modes.
- **Files**: `src/docline/cli.py`, `tests/test_cli_verbosity.py`.
- **Tests**: (1) flag parsing — quiet/verbose/default resolve to the right enum;
  (2) `-q -v` raises argparse error (exit 2); (3) dispatch passes a reporter and
  the stdout JSON line is still emitted unchanged (capsys: JSON on stdout, no
  JSON on stderr); (4) `reporter.finish()` is invoked after the run so a final
  line is emitted on stderr in NORMAL/VERBOSE (and nothing in SILENT).
- **Posture**: test-first. **Depends on Units 1, 2b, 3.**

### Unit 5 — Docs (help text + README/ARCHITECTURE)

- **Change**: Document the new flags, the stderr-progress vs stdout-JSON
  contract, and the fetch/process percentage semantics in README and (if a CLI
  surface table exists) `docs/ARCHITECTURE.md`. Argparse `help=` strings are set
  in Unit 4; this unit is prose only.
- **Files**: `README.md` (+ `docs/ARCHITECTURE.md` if it lists CLI flags).
- **Tests**: none (docs). Width-isolated from code.
- **Posture**: docs.

## Dependency Graph

```text
Unit 1 (reporter core) ─────────────┐
Unit 2a (crawl callback) → Unit 2b ─┤
Unit 3 (process callback) ──────────┼→ Unit 4 (CLI wiring) → Unit 5 (docs)
                                     │
```

- Unit 1, Unit 2a, Unit 3 are independent and may proceed in parallel.
- Unit 2b depends on 2a. Unit 4 depends on 1 + 2b + 3. Unit 5 depends on 4.
- No cycles.

## Decisions and Rationale

- **`-q/-v` pair → internal `Verbosity` enum** (not a bare `--verbosity` enum):
  idiomatic Unix ergonomics with argparse mutual-exclusion, while the enum keeps
  a single clean value flowing through the code. (Deliberation O1.)
- **fetch % = `pages_fetched/max_pages`, clamp to 100% on completion** (not the
  moving-frontier estimate): stable, monotonic, no regressing bar. (O2.)
- **Optional `progress` callback, default `None`** (not stdlib logging): keeps
  the library print-free and the MCP surface identical; deterministic to test. (O3.)
- **Progress → stderr, result JSON → stdout (unchanged)**: separates human vs
  machine output; scripts and pipes are unaffected in every verbosity mode; no
  `--json` flag needed. (O4.)
- **process reports per-job progress** (not a pre-scan global total): avoids a
  second directory walk; counts stay accurate, only the denominator scope is
  per-job.

## Risks and Caveats

| Risk | Mitigation |
|---|---|
| Callback threading changes library signatures | All new params are optional keyword, default `None` → backward-compatible; characterization tests assert unchanged behavior when omitted |
| Progress control chars leak into captured/piped output | Progress is stderr-only and CR is used **only** when `stream.isatty()`; non-TTY → plain newline lines; stdout JSON never carries progress |
| Crawl is fully async and returns results at the end | Callback fires **inside** the BFS loop (per page), so progress tracks the slow network phase, not the fast post-crawl staging write |
| Console spam on large corpora | Reporter throttles to ~1s / every N items; verbose per-item lines are opt-in |
| MCP surface accidentally changed | `progress` is a Python-level param excluded from the MCP/JSON manifest; add a test asserting the manifest/JSON result is unchanged |

## Plan Hardening Signals (REQUIRED)

- **public API, schema, or contract change**: PARTIAL/absent-risk — library
  functions gain optional keyword `progress` params (additive, backward-
  compatible); the MCP JSON manifest and the terminal JSON result contract are
  **unchanged**. No breaking change.
- **security, auth, permission, compliance**: absent — no auth/permission surface
  touched; progress strings are URLs/paths already handled by the crawler's
  existing SSRF/URL-policy guards.
- **migration, backfill, destructive/irreversible step**: absent — no data,
  schema, or config migration; purely additive UX.
- **external integration, operator checkpoint, external dependency**: absent — no
  new dependency (stdlib only); no external service.
- **high runtime, rollout, or rollback risk**: absent — default verbosity is
  NORMAL with throttled stderr output; rollback is removing flags/params, no
  state to unwind.

**Requires plan hardening: no**

## Runtime Verification and Closure

Changed runtime surface: **CLI** (`docline fetch`, `docline process`). No API,
browser, or background-job surface changes; MCP tool schema unchanged.

Runtime verification before absorption:

- `docline process -v` on a small staged corpus → per-file lines on **stderr**
  with running percentage; final result **JSON on stdout** unchanged.
- `docline process -q` → **no** stderr progress; JSON still on stdout.
- `docline process 1>out.json 2>err.log` (piped) → `out.json` is pure JSON with
  **no** carriage-return/control chars; `err.log` holds newline progress lines.
- `docline fetch --execute -v` against a small bounded crawl → periodic
  `pages_fetched/max_pages` percentage on stderr; JSON result unchanged.
- `docline process -q -v` → argparse error, exit code 2.

Operational closure artifact: lightweight (CLI UX feature, no monitoring/rollback
infra). Closure = README + `--help` updated, all four quality gates green
(`ruff check`, `pyright src/`, `pytest`, `ruff format --check`), and the manual
three-mode runtime check above recorded in the shipment's closure note. Ownership:
CLI surface owner. Validation window: n/a (no rollout gating).

## Plan Review

**Gate: ADVISORY** — proceed to harvest. No P0/P1 findings. Two P2 refinements
are folded into task acceptance criteria (recorded as follow-ups per the P2
gate action), three P3 advisories noted.

Plan hardening: the plan declares `Requires plan hardening: no` and all five
hardening signals are absent or additive-only (optional keyword params defaulting
to `None`; MCP schema + terminal JSON unchanged). No `## Plan Hardening` section
is required because no signals are present — the hardening-missing FAIL condition
does not apply.

Personas run inline (no subagent-spawn surface in this session): Constitution
Reviewer, Python Reviewer, Scope Boundary Auditor, Learnings Researcher,
Architecture Strategist (always-on), Agent-Native Parity Reviewer (triggered —
`execute_fetch` / `execute_process` are MCP-exposed). Security Lens: marginal
trigger (external URLs); no finding — progress strings are public doc URLs/paths
on stderr only, existing SSRF/URL-policy guards unchanged.

### P2 — moderate (folded into task acceptance criteria)

1. **Callback signature coherence (Python Reviewer).** Unit 1 defines a
   `ProgressEvent` dataclass, but Units 2a/2b/3 pass `(done, total, detail)`
   positionally. Reconcile: the **library seam emits positional primitives**
   `(done: int, total: int, detail: str)` (keeps the library decoupled from the
   reporter's type), and `ProgressReporter.__call__(done, total, detail)`
   constructs the `ProgressEvent` internally. Acceptance criterion added to Units
   1, 2a, 3, 4.
2. **MCP request-model isolation (Agent-Native Parity Reviewer).** `progress`
   MUST be a standalone function parameter on `execute_fetch` / `execute_process`
   and MUST NOT be added to the `FetchRequest` / `ProcessRequest` Pydantic models,
   or it would leak into the MCP/JSON schema. Add an explicit test asserting the
   `--manifest` output and the terminal JSON result are byte-for-byte unchanged.
   Acceptance criterion added to Units 2b, 3, 4.

### P3 — advisory

- **Module placement (Scope Boundary Auditor).** Consider `src/docline/progress.py`
  (flat) or reuse an existing package instead of a new `observability/` package for
  a single module; avoids a one-file package. Non-blocking — implementer's call.
- **Signature churn (Architecture Strategist).** Threading `progress` through five
  fetch functions is unavoidable given the print-free constraint; acceptable, but
  keep the param name and default (`progress=None`) identical across the chain.
- **Non-crawl sources (Architecture Strategist).** `_execute_single_source` also
  handles local/github/manifest-local sources that bypass `_fetch_url`; those
  won't emit crawl progress. Expected (they're fast/bounded) — document that
  fetch progress covers web-crawl sources only.

### Scope / constitution / learnings

- **Scope Boundary**: units respect the 2-hour rule (≤2 files each, isolated
  domains); no scope creep. Unit 5 is docs-only, width-isolated.
- **Constitution**: II (test-first) satisfied per-unit; I (typed public
  interfaces) satisfied; X (dual-interface / context efficiency) preserved.
- **Learnings Researcher**: `docs/compound/` scan — no prior learning on CLI
  progress/verbosity; no contradiction. Closest prior art is the crawl
  architecture from `docs/decisions/2026-07-06-postgresql-online-docs-fetch-capability.md`
  (already grounded in the plan). Confidence: low; no finding.

<!-- plan-review-attempt: 1 -->

