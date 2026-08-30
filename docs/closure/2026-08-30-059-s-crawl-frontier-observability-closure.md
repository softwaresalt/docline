---
title: "Operational closure: 059-S crawl frontier truncation observability"
date: 2026-08-30
shipment: 059-S
feature: 068-F
pr: 179
merge_commit: 58ba5c5b67abf5c73457d11e5af76c60bdd483b1
status: closed
---

## Released scope

| Item | Type | Commit |
|---|---|---|
| `068-F` | feature | `58ba5c5` (merge) |
| `068.001-T` | task — A.T1 `_Frontier` admission harness (red) | `0eedd8f` |
| `068.002-T` | task — A.T2 truncated-predicate harness (red) | `0eedd8f` |
| `068.003-T` | task — A.T2b control-flow characterization | `5f5cdec` |
| `068.004-T` | task — A.T3 extract `_Frontier` | `f25dfab` |
| `068.005-T` | task — A.T4 split `crawl.py` | `d037221` |
| `068.006-T` | task — A.T5 truncation-signal harness | `74d0047` |
| `068.007-T` | task — A.T6 `CrawlOutcome` + WARNING | `9dc41bd` |
| `068.008-T` | task — A.T7 crawl-core caller migration | `9eed2de` |
| `068.009-T` | task — A.T8a ELT caller migration | `4ca726c` |
| `068.010-T` | task — A.T8b budget/backoff migration | `72f2808` |
| `068.011-T` | task — A.T8c progress/amplification migration | `0060a1a` |
| `068.012-T` | task — A.T9 manifest + `StagingJob` threading | `46508a5` |
| `068.013-T` | task — A.T10 CLI/MCP parity harness | `7b8b5c0` |
| `068.014-T` | task — A.T11a CLI-no-change verification | `8ccda1d` |
| `068.015-T` | task — A.T11b `FetchResult` field | `2e99f77` |
| `068.016-T` | task — A.T12 TOC-first ordering harness | `b68525c` |
| `068.017-T` | task — A.T13 TOC-first ordering impl | `2becd68` |
| `068.018-T` | task — A.T14 docs | `7f18659` |
| `068.019-T` | task — A.T7b control-flow migration | `2cb8d07` |

Review remediation landed across `c0f6b2f`, `c142d1d`, `df5f5b1`, `91aa1f0`, `13a2f8e`, `0516847`,
`42bdcf0`, and `31f4954`. All 21 artifacts (shipment, feature, 19 tasks) are archived under
`.backlogit/archive/` with the merge SHA `58ba5c5` recorded. The `backlogit shipment ship` CLI
deadlocked from the worktree, so archival used the single-artifact fallback (`move` +
`update --commit` + `archive` + task-commit backfill); the shipment was therefore archived directly
from `active` and its frontmatter retains `archived_status: active` rather than a shipped lifecycle
state — a cosmetic difference from the normal ship path, with archive placement and merge
traceability fully intact (see `docs/compound/2026-08-30-ship-shipment-deadlocks-in-worktree.md`).

## What shipped

`crawl()` returns a `CrawlOutcome(results, frontier_truncated)` instead of a bare
`list[CrawlResult]`. The admission rule is now a testable `_Frontier` dataclass, and `crawl.py`
(660 lines) is split into three acyclic leaf modules — `crawl_models.py` (config, result, outcome,
`_Frontier`), `crawl_links.py` (pure URL/HTML + eligibility helpers), and `crawl_discovery.py`
(robots + backoff) — with the loop module at 399 lines. The fetch-calling helpers stayed in
`crawl.py` to preserve the `docline.fetch.crawl.fetch_page` monkeypatch seam.

`frontier_truncated` reports whether the ceiling **cost the crawl an eligible link**. It is set on a
direct admission refusal and, at a depth-zero exhausted short-circuit, from an eligible `toc-*.js`
reference that cannot be examined without a network fetch. The signal is deliberately conservative:
it may over-report but never under-reports. A single default-visible WARNING fires once per crawl
with an origin-only payload (scheme + host + admission count), never the path, query, fragment, or
userinfo.

The flag threads through `crawl-manifest.json` (written even when zero pages stage),
`StagingJob.frontier_truncated`, and `FetchResult.frontier_truncated`, so the CLI and MCP surfaces
report the same value for an equivalent request. `CrawlStagedNothingError(OSError, DoclineError)`
carries the flag across the zero-staged boundary. At depth zero, TOC-derived links are ordered ahead
of in-page anchors so a truncated mdBook crawl sheds anchors and keeps the authoritative TOC set.
`cli.py` and `mcp/server.py` were not modified.

## Risky action record

| Field | Value |
|---|---|
| ProposedAction | Change `crawl()`'s return type and split the live crawl module while adding a default-visible truncation WARNING |
| Targets | `crawl.py`, `crawl_models.py`, `crawl_links.py`, `crawl_discovery.py`, `elt/execute.py`, `fetch/models.py`, `app.py`, `app_models.py`, and 14 test modules |
| Change kind | Breaking internal API change + module split on the live fetch path; no config, data, or schema migration |
| ActionRisk | moderate — core crawl loop and a breaking return-type change, fully caller-updated in-shipment |
| Rollback | Revert merge commit `58ba5c5`; changes confined to `fetch/crawl*.py`, `fetch/models.py`, `elt/execute.py`, `app_models.py`, `app.py`. Persisted `crawl-manifest.json`/`metadata.json` gain a defaulted key tolerated on revert |
| Approval | Standing operator approval for shipment 059-S and PR #179 merge |
| ActionResult | applied |

## Verification

### Quality gates

| Gate | Result |
|---|---|
| `ruff check .` | pass |
| `pyright src/` | 0 errors, 0 warnings |
| `pytest` | 2049 passed, 6 skipped |
| `ruff format --check .` | pass (286 files already formatted, no changes) |

CI on PR #179's final head `31f4954` was green across all seven checks: ci gate, pyright, ruff lint,
ruff format check, pytest (ubuntu-latest), sdist + wheel, and detect code changes. The merge commit
`58ba5c5` was produced from that verified head.

### Test-first evidence

Every source task was gated behind a red harness via an explicit dependency edge. The `_Frontier`
admission harness (068.001/068.002) and the truncation-signal harness (068.006) landed red before
their implementations; the caller migrations turned the atomic unit green. The suite grew by the
new admission, truncation-signal, control-flow, TOC-priority, and CLI/MCP parity modules, plus
review-driven regression tests for IPv6 origin labels, malformed-port rejection, the exhausted
depth-zero TOC branch, the print-page branch, and the zero-staged `_fetch_url` D8 contract.

### Runtime verification

Synthetic in-memory spot-check across every affected surface, executed post-merge against the
merged tree. All 18 checks passed:

| Surface | Observation | Result |
|---|---|---|
| Direct-refusal truncation | `max_frontier=2` fan-out crawl | `frontier_truncated=True`, one WARNING |
| WARNING payload | sanitized origin only | contains `https://verify.example.com`, no path/query/`toc-1.js` |
| TOC-first ordering | mdBook root, ceiling below N+M | TOC pages admitted, anchors dropped |
| Manifest persistence | staged web job | `crawl-manifest.json` carries `frontier_truncated: true` |
| CLI parity | `StagingJob.model_dump` | flag `True`, agrees with manifest |
| MCP parity | `execute_fetch` → `FetchResult` | flag `True`, equals CLI value |
| Conservative TOC-only | `max_frontier=0`, anchor-free root, eligible `toc-*.js` | `frontier_truncated=True`, TOC asset **not** fetched (pure parse), one WARNING |
| Malformed port | `https://host:not-a-port` | typed `CrawlUrlRejectedError`, no `ValueError` leak |
| Uncapped no-op | default ceiling, two anchors | not truncated, both admitted, zero WARNING |

## Review record

Five-persona adversarial review (correctness, security, Python safety, scope boundary,
architecture) ran before submission. No P0/P1. Findings remediated in-shipment: the Python
exception-reconstruction default on `CrawlStagedNothingError`, the ELT handler consolidation, the
`_link_in_scope` deduplication of the triplicated scope filter, the `_origin_label` relocation to
its observability owner, and the `CRAWL_LOGGER_NAME` single-source constant.

Copilot review then ran eight cycles against successive HEADs, ending with an "Approval recommended"
review on the final head `31f4954` with zero unresolved threads and zero suppressed findings.
Findings remediated:

- IPv6 origin-label bracket-stripping raised `ValueError` before fetch — brackets now preserved.
- A malformed URL port leaked an untyped `ValueError` — `validate_crawl_url` now rejects it typed.
- Mutation-survivable coverage gaps — added the exhausted depth-zero TOC branch test, the print-page
  branch `CrawlOutcome` assertion, and a direct `_fetch_url` zero-staged A.T9 contract regression.
- Documentation/contract drift — the strict "only when refused" wording was reconciled everywhere
  (code docstrings, PR description, `ARCHITECTURE.md`, `README.md`) with the conservative TOC signal.
- Stale durable-memory facts (line count, module placement, pytest count) corrected.

## Accepted risk carried forward

The conservative depth-zero TOC signal can over-report truncation when a `toc-*.js` reference yields
no admissible links. This is intentional per plan decision D3 — a false "may be incomplete" prompts
a re-run, whereas a false "complete" would hide data loss — and is documented on every surface.

## Source artifact cleanup

| Artifact | Action |
|---|---|
| Deliberation record | `docs/decisions/2026-08-29-crawl-frontier-observability-deliberation.md` (status `accepted`) remains the durable decision artifact referenced by the plan. No backlog deliberation artifact to archive |
| Stash `8A99D90C`, `7F34A0D5`, `ABBE9BCC` | Consumed by Stage during harvest into 068-F; no action needed |

## Follow-ups stashed

| Stash ID | Priority | Summary |
|---|---|---|
| `D6E758F5` | high | Pre-existing credential leak: `_execute_single_source` logs the raw `source_key` (`web_crawl:<url>` with query token) at ERROR; `sanitize_source` is a no-op on the `web_crawl:` prefix. Out of scope for 059-S; requires sanitizing the URL inside `source_key` without changing `job_id` determinism |

## Monitoring and rollback

The truncation signal is itself the new monitoring surface: operators observe a WARNING on the
`docline.fetch.crawl` logger at default verbosity, plus the `frontier_truncated` field on the CLI
and MCP JSON results and in `crawl-manifest.json`. The ceiling is not operator-configurable on the
fetch paths, so the documented remedy is to narrow the crawl. Rollback is a single revert of merge
commit `58ba5c5` — changes are confined to the fetch/ELT/app modules and are additive on the
persisted artifacts.

## Operational readiness

| Field | Value |
|---|---|
| Invariants | Refused links never enter `visited` (058-S memory bound holds); the ceiling value and semantics are unchanged; `crawl()` still yields `list[CrawlResult]`-shaped iteration via `outcome.results`; CLI and MCP report the same `frontier_truncated` for an equivalent request; `max_frontier=0` issues no TOC network I/O |
| Pre-deploy audit | `ruff check`, `pyright src/`, `pytest` (2049 passed), `ruff format --check` all green on `31f4954`; CI green on the same head; five-persona + eight Copilot review cycles clean |
| Rollout path | Merged to `main` via merge commit `58ba5c5`. No staged rollout, feature flag, or migration — the change is a library-level behavior addition on the fetch path; effective immediately for all `docline fetch` / MCP `fetch` callers |
| Post-deploy checks | Runtime verification (18/18) executed against the merged tree; no separate production environment to smoke-test (CLI/MCP library) |
| Healthy signal | Crawls under the ceiling emit no WARNING and report `frontier_truncated=false`; normal uncapped crawls admit all eligible links |
| Failure signal | A `ValueError` or other untyped exception escaping `crawl()` on a valid URL; a `frontier_truncated` value diverging between the manifest, CLI, and MCP for the same request; a WARNING payload containing a URL path/query/userinfo |
| Rollback trigger | Any failure signal above that is traced to this change, or a regression in crawl completeness on the fetch path |
| Rollback command | `git revert -m 1 58ba5c5b67abf5c73457d11e5af76c60bdd483b1` — single-commit, additive on persisted artifacts |
| Validation window | Covered by the post-merge runtime verification and CI; no extended soak required for a deterministic library change |
| Readiness verdict | Ready — merged, verified, and closed |
| Owner | Ship agent (session 059-S); follow-up `D6E758F5` owned by the next Stage/Ship cycle |

