---
title: "Session memory: 058-S crawl frontier bound"
date: 2026-08-29
agent: ship
shipment: 058-S
branch: feat/067-crawl-frontier-bound
pr: 175
merge_commit: b1f4549e308b25a02dbd3f30eb6d87bf8a126331
status: shipped
---

## Scope

Shipment 058-S — bound crawl frontier growth independently of `max_pages`/`max_depth`.
Manifest: `067-F`, `067.001-T` (red harness), `067.002-T` (green implementation).

## Environment

- Isolated worktree at `.copilot/session-state/4c9a04f5-.../wt-058s`, branch
  `feat/067-crawl-frontier-bound` from `origin/main@5b84a49`.
- Primary worktree operator-owned modifications (`.autoharness/config.yaml`,
  `.github/agents/_orchestrator.agent.md`, `.github/agents/_ship.agent.md`, `.gitignore`)
  were left untouched.
- Tests require the repo venv: `C:\Source\GitHub\docline\.venv\Scripts\python.exe` with
  `PYTHONPATH=src`. Pyright needs `--pythonpath` pointed at the same interpreter, otherwise
  it reports 28 spurious unresolved-import errors.

## Work completed

| Item | Commit | Outcome |
|---|---|---|
| 067.001-T | `799d48b` | Red harness: `tests/fetch/test_crawl_frontier_bound.py`, 12 tests. Observed red: 5 behavioural failures, 7 structural passes. |
| 067.002-T | `bfa1bf4` | Green: `_admit()` admission gate enforced at both discovery append sites in `crawl()`. |
| Persona review fixes | `afd76e6` | Print-page coverage, negative-cap validation, budget-threading double, drop-log assertions. |
| Copilot cycle 1 | `4d9b422` | Discovery short-circuits once admissions are exhausted; zero cap issues no TOC-asset requests. |
| Copilot cycle 2 | `922ad78` | Ceiling record redacts the start URL; print-page branch reports drops consistently. |

Merged as `b1f4549` (true merge commit, two parents) via PR #175.

## Decisions and rationale

- **Minimal compile scaffold in the red commit.** `MAX_FRONTIER` and
  `CrawlConfig.max_frontier` were added in the harness commit with no enforcement so the
  harness compiles (harness-architect pattern: structural stubs pass, behavioural tests
  fail). Enforcement landed only in the green commit.
- **Dropped links are not added to `visited`.** Adding refused links to `visited` would
  reintroduce the unbounded growth the cap exists to prevent.
- **`break` instead of `continue` on refusal.** Once the ceiling is reached no later link in
  the same page can be admitted, so iterating the remaining fan-out is pure waste.
- **Single debug log per crawl at first drop.** The plan asks for a debug log at drop time;
  logging every dropped link would emit unbounded log volume under exactly the adversarial
  condition the cap defends against, so the ceiling-reached event is reported once.
- **Dedicated test module** rather than appending to `test_crawl_limits.py`, matching the
  repo convention of focused per-concern test files while following that file's harness
  pattern.

## Verification

Gates run in order, all green: `ruff check .`, `pyright src/` (0 errors),
`pytest` (2008 passed, 6 skipped), `ruff format --check .` (278 files). CI green on the merged
HEAD across all eight checks. Runtime spot-check: a 5,000-link fan-out with `max_pages=1_000_000`
and `max_depth=10` bounded to exactly `1 + max_frontier` requests.

## Next steps

Closure recorded in `docs/closure/2026-08-29-058-s-crawl-frontier-bound-closure.md`. Shipment
`058-S` is shipped and all four artifacts are archived with the merge SHA. Follow-ups stashed as
`8A99D90C`, `7F34A0D5`, and `ABBE9BCC`. Compound learnings captured for the admission-cap pattern
and the worktree gate invocation. `compact-context` ran with `target: all`: the 058-S plan was
consolidated into `docs/plans/2026-08-29-crawl-frontier-bound-decided-plan.md` with the verbose
original archived to `docs/archive/plans/`; memory (25 files, 174 KB) and the same-day closure
record were below their thresholds and preserved.

## Out of scope

Stash item `F0F13C0B` (low priority) is deliberately not staged; Orchestrator routes it later.
