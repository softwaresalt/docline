---
type: session-memory
date: 2026-08-30
agent: ship
shipment: 059-S
feature: 068-F
branch: ship/059-s
worktree: C:\Source\GitHub\docline\.copilot\worktrees\ship-059
---

# Ship session — 059-S crawl frontier truncation observability

## Outcome

All 19 tasks (068.001-T … 068.019-T) implemented on branch `ship/059-s`
(worktree from `origin/main` @ 6878ef1). Full quality gates green.

## Tasks completed (A.T# -> backlog id)

- A.T1/A.T2 -> 068.001/068.002: `_Frontier` admission + truncated-predicate unit harness.
- A.T2b -> 068.003: non-counting control-flow characterization harness.
- A.T3 -> 068.004: extract `_Frontier`, retire admission closures.
- A.T4 -> 068.005: split `crawl.py` into `crawl_models.py` + `crawl_links.py` (+ `crawl_discovery.py` contingency). crawl.py = 399 lines.
- A.T5 -> 068.006: truncation observability signal harness.
- A.T6 -> 068.007: `CrawlOutcome` + WARNING promotion (origin-only payload; report only on real refusal).
- A.T7/A.T7b/A.T8a/A.T8b/A.T8c -> 068.008/068.019/068.009/068.010/068.011: caller migrations to `CrawlOutcome`.
- A.T9 -> 068.012: thread `frontier_truncated` into manifest + `StagingJob`; `CrawlStagedNothingError`.
- A.T10/A.T11a/A.T11b -> 068.013/068.014/068.015: CLI/MCP parity harness + `FetchResult` field.
- A.T12/A.T13 -> 068.016/068.017: TOC-first ordering harness + impl.
- A.T14 -> 068.018: docs (ARCHITECTURE.md, README.md).

## Key decisions and deviations

- **D5 contingency adapted**: the literal move of `_fetch_with_retries`/`_robots_allow`/`_discover_toc_links` to `crawl_discovery.py` would break the `docline.fetch.crawl.fetch_page` monkeypatch seam (5 test modules) and force test edits forbidden by A.T4. Instead moved the pure eligibility helpers to `crawl_links.py`, `_origin_label` to `crawl_models.py` (its observability owner), and `check_robots_allowed` + `compute_backoff_seconds` to `crawl_discovery.py`. crawl.py landed at 399 lines (< 400). Note: the `_origin_label`/`_link_in_scope` placement reflects the post-review architecture remediation.
- **Ceiling logger**: `crawl_models.py` logger = `getLogger("docline.fetch.crawl")` so the WARNING stays on the crawl logger (keeps 058-S caplog tests green, matches A.T7 "no logger-name change").
- **WARNING fires only on real refusal** (refused_any), never on mere cap-fill (D3/D4). Existing-test DEBUG->WARNING update in `test_crawl_frontier_bound.py`.
- **StagingJob exact-field contract** in `test_envelope_parity.py` updated (plan's "A.T9 must re-check").

## Gate results

- ruff check . : PASS
- ruff format --check . : PASS
- pytest : 2049 passed, 6 skipped (final, after review-regression tests)
- pyright src/ : 0 errors when run with the `.venv` interpreter (CI resolves deps via `uv sync`). Default local pyright reports pre-existing environmental `reportMissingImports` (pydantic/httpx/etc.) unrelated to this change.

## Untouched (parity confirmed)

- `src/docline/cli.py` and `src/docline/mcp/server.py` are NOT modified (A.T11a/A.T11b): the field propagates via `StagingJob.model_dump` and `execute_fetch` respectively.

## Operator-owned files (primary worktree, untouched)

`.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`,
`.github/agents/_ship.agent.md`, `.gitignore` — never staged/committed from this
isolated worktree.

## Next steps

Multi-persona adversarial review -> remediate -> PR -> Copilot review cycles -> CI ->
merge commit -> runtime verification -> shipment archival -> operational closure ->
compound refresh -> compact-context.

## Closure (2026-08-30, session complete)

- Merged as PR #179, merge commit `58ba5c5b67abf5c73457d11e5af76c60bdd483b1` (merge commit; P-009 verified).
- Eight Copilot review cycles ended "Approval recommended" with zero unresolved threads; five-persona adversarial review had no P0/P1.
- Runtime verification: 18/18 checks passed across truncation, conservative TOC, payload redaction, manifest/StagingJob/FetchResult parity, malformed-port rejection, and uncapped no-op.
- Shipment 059-S, feature 068-F, and all 19 tasks archived with merge SHA `58ba5c5`. The `shipment ship` CLI deadlocked in the worktree; completed via `move` + per-artifact `update --commit` + `archive` + task-commit backfill (see compound learning `2026-08-30-ship-shipment-deadlocks-in-worktree.md`).
- Closure record: `docs/closure/2026-08-30-059-s-crawl-frontier-observability-closure.md`.
- Compaction: plan finalized to `docs/plans/2026-08-29-crawl-frontier-observability-decided-plan.md`; verbose original archived to `docs/archive/plans/`. `docs/memory/` remains well below the 40-file/500 KB thresholds — preserved (no memory files archived).
- Follow-up `D6E758F5` (high) preserved in stash; 060-S untouched.

