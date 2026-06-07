---
shipment: 010-S
session: 5 (continuation of session-4 Phase 4)
phase: stale-copilot-review-halt
branch: feat/docline-graphtor-alignment
head: b90b56b
base: a62cd24 (origin/main)
pr: 19
status: HALTED — §1.9 Check 2 FAIL, awaiting operator decision (P-014 NON-NEGOTIABLE)
---

## Session-5 mission

Drive §1.9 readiness gate to full PASS for PR #19 by securing a fresh Copilot review at HEAD `b90b56b`,
then halt for operator merge approval.

## Outcome — HALT at §1.9.4 stale-review route

§1.9 readiness gate result:

| Check | Result | Detail |
|---|---|---|
| 1. No pending Copilot review | ✅ PASS | `reviewRequests.nodes` empty |
| 2. Latest Copilot review covers current HEAD | ❌ FAIL | Latest review covers `e8407cd`; HEAD is `b90b56b` (stale) |
| 3. Zero unresolved Copilot threads | ✅ PASS | 0 unresolved threads (all resolved in session-4) |

## What was attempted

1. **REST POST** `repos/softwaresalt/docline/pulls/19/requested_reviewers` with `{"reviewers":["Copilot"]}` — returned `HTTP/2.0 201 Created` with full PR JSON body.
2. **REST DELETE** then re-POST cycle — same 201 success response but no effect.
3. **GraphQL `requestReviews` mutation** with bot node ID `BOT_kgDOCnlnWA` — rejected with `NOT_FOUND: Could not resolve to User node`. The `requestReviews` mutation does not accept bot IDs.
4. **Timeline event verification** via `repos/.../issues/19/events` — only the original `review_requested` event from 17:53:13Z (previous session) is recorded. None of the new POST requests created new timeline entries.
5. **Polling cadence**: total wait time ~20 minutes (initial 2-min poll, 30s recheck, 1-min recheck, 5-min long poll). No fresh Copilot review materialized.

## Diagnosis

The REST `POST /requested_reviewers` endpoint accepts the request (HTTP 201) but silently
deduplicates Copilot bot re-requests after the bot has already submitted a review on the PR.
There is no programmatic mechanism available to the agent harness from the gh CLI / REST API
that reliably forces Copilot to re-review after new commits land. The standard
`mcp_github_request_copilot_review` MCP tool referenced in
`.github/instructions/github-pr-automation.instructions.md` is not exposed in this workspace.

## Branch / working-tree state

* HEAD: `b90b56b` (`test(process): refresh chunk anchor docstring and drop obsolete type-ignores`)
* `HEAD == origin/feat/docline-graphtor-alignment` (pushed, no local commits ahead of remote)
* Working tree clean except 4 ignored scratch files (`docs/scratch/00{9,10}-S-*.md`)
* Last 3 commits resolved Copilot review feedback for review at `e8407cd`
* Review-fix cycles used this PR: **1 of 3** (per §1.8 cap)

## Operator decision points (presented at halt)

The operator must choose one of:

1. **Manually trigger Copilot re-review via GitHub PR web UI** — open https://github.com/softwaresalt/docline/pull/19, request Copilot re-review from the UI sidebar. Then re-run the §1.9 gate from the Ship agent.
2. **Wait longer for Copilot to pick up** — Copilot bot occasionally re-reviews after long delays. Recheck PR state in 30-60 min.
3. **Accept the stale review and merge** — invoke the §1.9.4 warning route. The previous review at `e8407cd` covers the substantive code; the only commit since (`b90b56b`) is a docstring + type-ignore cleanup with no logic changes. Operator may judge this acceptable.
4. **Hold the merge** — defer until further investigation.

## Constraints to honor on resume

* P-014 NON-NEGOTIABLE: operator approval required before any merge.
* P-009: merge commit only (`gh pr merge 19 --merge --delete-branch`).
* §1.8 cycle cap: 1 of 3 used. 2 cycles remain if new fixes needed.
* Conventional commits with valid scopes (`core`, `cli`, `mcp`, `fetch`, `process`, `schema`, `docs`).
* Push after each commit.
* Backlogit CLI from docline cwd only.
* Role boundary unchanged (Ship execution only).

## Files unchanged in this session

No source, schema, doc, or backlog mutations occurred in session-5. The only side effect is
this memory checkpoint plus accumulated PR-side review-request API calls (which had no effect).
