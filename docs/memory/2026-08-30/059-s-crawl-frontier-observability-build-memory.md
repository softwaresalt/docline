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
- A.T4 -> 068.005: split `crawl.py` into `crawl_models.py` + `crawl_links.py` (+ `crawl_discovery.py` contingency). crawl.py = 397 lines.
- A.T5 -> 068.006: truncation observability signal harness.
- A.T6 -> 068.007: `CrawlOutcome` + WARNING promotion (origin-only payload; report only on real refusal).
- A.T7/A.T7b/A.T8a/A.T8b/A.T8c -> 068.008/068.019/068.009/068.010/068.011: caller migrations to `CrawlOutcome`.
- A.T9 -> 068.012: thread `frontier_truncated` into manifest + `StagingJob`; `CrawlStagedNothingError`.
- A.T10/A.T11a/A.T11b -> 068.013/068.014/068.015: CLI/MCP parity harness + `FetchResult` field.
- A.T12/A.T13 -> 068.016/068.017: TOC-first ordering harness + impl.
- A.T14 -> 068.018: docs (ARCHITECTURE.md, README.md).

## Key decisions and deviations

- **D5 contingency adapted**: the literal move of `_fetch_with_retries`/`_robots_allow`/`_discover_toc_links` to `crawl_discovery.py` would break the `docline.fetch.crawl.fetch_page` monkeypatch seam (5 test modules) and force test edits forbidden by A.T4. Instead moved eligibility helpers + `_origin_label` to `crawl_links.py` and `check_robots_allowed` + `compute_backoff_seconds` to `crawl_discovery.py`. crawl.py landed at 397 lines (< 400).
- **Ceiling logger**: `crawl_models.py` logger = `getLogger("docline.fetch.crawl")` so the WARNING stays on the crawl logger (keeps 058-S caplog tests green, matches A.T7 "no logger-name change").
- **WARNING fires only on real refusal** (refused_any), never on mere cap-fill (D3/D4). Existing-test DEBUG->WARNING update in `test_crawl_frontier_bound.py`.
- **StagingJob exact-field contract** in `test_envelope_parity.py` updated (plan's "A.T9 must re-check").

## Gate results

- ruff check . : PASS
- ruff format --check . : PASS
- pytest : 2040 passed, 6 skipped
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
