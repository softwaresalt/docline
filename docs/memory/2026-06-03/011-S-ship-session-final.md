---
type: ship-session-final
date: 2026-06-03
agent: ship
shipment: 011-S
merged_pr: 21
merge_sha: e07ffe6
post_merge_pr: TBD
---

# Ship session-final — 011-S docline CI workflow

## Shipment lifecycle summary

| Phase | Date | Output |
|---|---|---|
| Stage (deliberation, plan, plan-review, harvest) | 2026-06-03 (earlier) | Adopted Option C (Linux-only CI); plan APPROVED 0 P0/P1; harvested `9C40BF99` + `CE758832`; created 011-F + 3 tasks |
| Ship build (single session) | 2026-06-03 | All 3 tasks completed, harness green, real CI probe caught 2 dependency issues |
| Copilot review + fixes | 2026-06-03 | 2 review comments addressed (action SHA pin docs, control audit phrasing); 2 threads resolved |
| Operator-approved merge | 2026-06-03 | PR #21 merged with merge commit at `e07ffe6` |
| Post-merge closure (this PR) | 2026-06-03 | 011-S archived, closure doc finalized, this memory written |

## Stage outputs consumed

* Deliberation: `docs/decisions/2026-06-03-docline-ci-workflow-deliberation.md`
* Plan: `docs/plans/2026-06-03-docline-ci-workflow-plan.md`
* Plan review: `docs/decisions/2026-06-03-docline-ci-workflow-plan-review.md`

## Ship execution highlights

* Branch `feat/docline-ci-workflow` cut from main at session start.
* Three tasks completed in order: 011.001-T (workflow scaffold), 011.002-T (uv + gate jobs), 011.003-T (probe + verification).
* **CI probe value-add caught two real issues on day 1** that no manual local gate had surfaced:
  1. `defusedxml` was used at runtime but missing from `uv.lock` — globally-installed package shadowed the omission locally.
  2. `[dependency-groups.dev]` was never declared, so `uv sync --group dev` resolved nothing — `pyright`/`ruff`/`pytest` worked locally only because they were installed globally.
* Fixes pushed iteratively across 4 CI runs:
  - `26910902443` failure
  - `26911040660` failure
  - `26911313237` failure
  - `26911471341` ✅ all 5 gates green (lint 13s, format 12s, typecheck 17s, test 17s, build 19s)
* Copilot review on PR #21: 2 comments addressed, replies posted, threads resolved per §1.6 GraphQL flow.
* §1.9 readiness gate PASSED before requesting operator merge approval.
* Operator approved; merge commit `e07ffe6` (no squash, no rebase — P-009 compliant).

## Stash items consumed

| Stash ID | Priority | Disposition |
|---|---|---|
| `9C40BF99` | high | Harvested into 011-F during Stage; archived |
| `CE758832` | low | Bundled into 011-S scope during Stage; archived |

## New stash items created during 011-S

These were carved out as out-of-scope follow-ups during plan-harden and remain
in stash for the next pipeline cycle:

| Stash ID | Priority | Subject |
|---|---|---|
| `7AA9FAA0` | low | Release workflow (PyPI + GitHub Releases) once 1.0 ready |
| `ED74577A` | medium | Cross-OS CI matrix once Windows root cause is known |
| `0AA8B223` | low | Windows `tmp_path` `PermissionError` root cause investigation |

## Compound learnings worth capturing

1. **CI probe surfaces dependency-state drift that no local manual gate catches.**
   Globally-installed Python tooling silently masks `uv.lock` omissions and
   missing dev dependency groups. The first PR opened against a fresh CI
   workflow will almost always discover these — budget for 2–4 fix iterations
   on the initial probe, not zero.

2. **Linux-only CI bypasses the Windows `tmp_path` `PermissionError` noise per design.**
   The deliberation explicitly chose Option C to avoid blocking on a Windows-
   specific pytest cleanup issue. Validated: zero false failures from that
   surface across the probe runs.

3. **Ship's recovery pattern from 010-S was NOT needed this shipment.**
   In 010-S, Ship had to `git checkout HEAD --` un-staged artifact drift and
   re-run the backlogit lifecycle in proper order. This shipment maintained
   tighter discipline: backlogit operations only via MCP tools, immediate
   commit-per-mutation, no in-flight drift. Pattern: keep the working tree
   surface small per commit and let backlogit own the `.backlogit/` writes.

## Closure artifacts

* Closure doc (updated this PR): `docs/closure/011-S-docline-ci-workflow.md`
* This memory: `docs/memory/2026-06-03/011-S-ship-session-final.md`
* Archived shipment: `.backlogit/archive/011-S.md`
* Archived feature + tasks (during merge PR): `011-F`, `011.001-T`, `011.002-T`, `011.003-T`

## Next pipeline cycle

Three stash follow-ups are queued for next Stage invocation. None blocks
current main; all are quality-of-life extensions of the CI surface.
