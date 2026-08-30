---
title: "Operational closure: 058-S bound crawl frontier growth"
date: 2026-08-29
shipment: 058-S
feature: 067-F
pr: 175
merge_commit: b1f4549e308b25a02dbd3f30eb6d87bf8a126331
status: closed
---

## Released scope

| Item | Type | Commit |
|---|---|---|
| `067-F` | feature | `b1f4549` (merge) |
| `067.001-T` | task — red harness | `799d48b` |
| `067.002-T` | task — green implementation | `bfa1bf4` |

Review remediation landed in `afd76e6`, `4d9b422`, and `922ad78`. All four artifacts are archived
under `.backlogit/archive/` with the merge SHA recorded.

## What shipped

`crawl()` now enforces a whole-crawl discovered-link admission ceiling, `CrawlConfig.max_frontier`,
defaulting to the module constant `MAX_FRONTIER = 10_000`. The ceiling is absolute and independent
of `max_pages` and `max_depth`. It is applied at both discovery append sites through a single
`_admit()` gate, and discovery short-circuits entirely once admissions are exhausted so no
mdBook `toc-*.js` asset requests are issued for links that would all be refused.

Refused links are not added to `visited`, which is what makes the bound hold: total resident
identity keys are bounded by `MAX_FETCH_ATTEMPTS + max_frontier`. Breadth-first order is preserved
for admitted links, the start URL is never subject to the ceiling, and the crawl always runs to
completion with the admitted set.

## Risky action record

| Field | Value |
|---|---|
| ProposedAction | Add an admission ceiling to the live crawl loop in `src/docline/fetch/crawl.py` |
| Targets | `crawl()`, `CrawlConfig`, `tests/fetch/test_crawl_frontier_bound.py` |
| Change kind | Local edit to a core runtime path; no config, data, or schema migration |
| ActionRisk | moderate — core crawl loop on the live fetch path |
| Rollback | Revert merge commit `b1f4549`; single-module change, inert below the ceiling |
| Approval | Standing operator approval for shipment 058-S |
| ActionResult | applied |

## Verification

### Quality gates

| Gate | Result |
|---|---|
| `ruff check .` | pass |
| `pyright src/` | 0 errors, 0 warnings |
| `pytest` | 2008 passed, 6 skipped |
| `ruff format --check .` | 278 files formatted |

CI on PR #175's final head `922ad78` was green across all eight checks: ci gate, pyright, ruff lint,
ruff format check, pytest (ubuntu-latest), sdist + wheel, detect code changes, and the Copilot
reviewer check. The merge commit `b1f4549` itself was produced from that verified head.

### Test-first evidence

The red harness landed first with a minimal compile scaffold and no enforcement. Observed red:
5 behavioural failures against 7 structural passes. The green commit turned it fully green. The
suite grew to 19 tests covering the plan's four scenario groups plus the review-driven additions.

### Runtime verification

Synthetic high-fan-out spot-check: a root page advertising 5,000 discovered links crawled with
`max_pages=1_000_000`, `max_depth=10`, and `max_frontier=250`.

| Observation | Result |
|---|---|
| Pages requested | 251 — exactly `1 + max_frontier` |
| `CrawlResult` values emitted | 251 |
| Start URL crawled first | yes |
| Loop terminated | yes |
| Ceiling records emitted | 1, at DEBUG, start URL sanitised |

The bound held with `max_pages` and `max_depth` effectively unbounded, confirming independence.

## Review record

Three independent persona reviews ran before submission — correctness, Python safety, and scope
boundary. No P0 or P1 findings. Copilot review then ran three cycles against successive HEADs,
ending with a fresh review on PR #175's final head `922ad78` and zero unresolved threads.

Findings remediated in this shipment:

- Print-page admission site had no test coverage (P2 verification gap).
- `max_frontier` had no boundary validation, unlike the sibling `max_pages` knob; negative values
  now raise `CrawlLimitExceededError` and `0` explicitly means discovery disabled.
- The scenario-4 envelope assertion was tautological; the fetch double now threads and debits the
  request-scoped `RemainingByteBudget`, so the `MAX_FETCH_ATTEMPTS` envelope is load-bearing.
- A zero ceiling still issued mdBook TOC-asset network requests.
- The ceiling record leaked the raw start URL; it is now passed through `sanitize_source()`.
- The print-page branch skipped silently when the ceiling was already exhausted; it now reports
  consistently with the main discovery branch.
- Removed a vacuous default-inequality test that did not demonstrate independence.

Verified by inspection rather than automated assertion: nothing. The drop-log acceptance criterion,
originally flagged as untested by the scope auditor, is now covered by four log assertions
(single-record cardinality, no record under the cap, credential redaction, print-page reporting).

## Accepted risk carried forward

A ceiling hit is signalled only at DEBUG and produces no downstream truncation marker, so a
truncated crawl is indistinguishable from a complete one in `crawl-manifest.json`. The reviewed
plan explicitly deferred any counter field or `CrawlResult` marker, so this is accepted risk, not a
defect. It is stashed as follow-up `7F34A0D5`.

## Source artifact cleanup

| Artifact | Action |
|---|---|
| Stash `173238FD` | Already consumed by Stage during harvest; no action needed |
| Deliberation record | `docs/decisions/2026-08-29-crawl-frontier-bound-deliberation.md` (status `accepted`) is the durable decision artifact, referenced by the plan. No backlog `source_deliberation_id` was recorded on `067-F`, so there is no backlog deliberation artifact to archive |
| Stash `F0F13C0B` | Left active by design — out of scope for 058-S, routed separately |

## Follow-ups stashed

| Stash ID | Priority | Summary |
|---|---|---|
| `8A99D90C` | medium | Split `crawl.py` and extract frontier bookkeeping into a module-level dataclass |
| `7F34A0D5` | medium | Surface frontier truncation downstream and raise the drop-record log level |
| `ABBE9BCC` | low | Prioritise TOC-derived links over in-page anchors when the ceiling truncates |

## Context compaction

`compact-context` ran with `target: all` as the mandatory post-merge step.

| Target | Assessment | Action |
|---|---|---|
| `docs/plans/` | 058-S plan complete and carrying plan-review and plan-hardening content | Consolidated into `docs/plans/2026-08-29-crawl-frontier-bound-decided-plan.md`; verbose original archived to `docs/archive/plans/` |
| `docs/memory/` | 25 files, 174 KB — below the 40-file and 500 KB thresholds; the 058-S entry is the most recent checkpoint for the completed release unit | Preserved |
| `docs/closure/` | This record is same-day, below the 14-day threshold | Preserved |

No files were deleted. The decided-plan records `source_plan` so the path back to the archived
original stays traceable.

## Monitoring and rollback

No new monitoring surface is required. A ceiling hit is observable through the DEBUG record on the
`docline.fetch.crawl` logger; follow-up `7F34A0D5` raises that visibility. Rollback is a revert of
merge commit `b1f4549` — the change is single-module, additive, and inert below the ceiling.
