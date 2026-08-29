---
shipment_id: 009-S
feature_id: 009-F
task_id: 009.001-T
title: "Restore Copilot review requestability"
closure_type: verify-and-archive
code_changes: false
closed_at: 2026-06-02
closed_by: ship
references:
  - docs/plans/2026-06-01-restore-copilot-review-requestability-plan.md
  - docs/decisions/2026-06-01-restore-copilot-review-requestability-deliberation.md
---

## Outcome

Shipment **009-S** closed via verify-and-archive. No code surface was modified.
The Copilot code review bot has been restored as a requestable reviewer on
`softwaresalt/docline`; operator enabled the setting in GitHub repository
configuration, and live PR activity confirms the bot is functioning.

## Acceptance Evidence

The three acceptance criteria for task **009.001-T** are all satisfied:

| Criterion | Status | Evidence |
|---|---|---|
| `gh pr edit <N> --add-reviewer copilot` exits 0 | met | Copilot has been successfully added to PR #16 and PR #17; review submissions prove the request succeeded. |
| Copilot review with `state != PENDING` present | met | 5 Copilot reviews observed, all `state: COMMENTED`. None PENDING. |
| No `422 not a collaborator` error | met | Reviews were successfully posted by the bot; no collaborator error encountered. |

### PR #16 (008-S feature merge)

`copilot-pull-request-reviewer` submitted **4 reviews**:

| State | Submitted |
|---|---|
| COMMENTED | 2026-06-01T21:57:46Z |
| COMMENTED | 2026-06-02T00:22:27Z |
| COMMENTED | 2026-06-02T19:57:42Z |
| COMMENTED | 2026-06-02T20:47:21Z |

### PR #17 (008-S post-merge closure)

`copilot-pull-request-reviewer` submitted **1 review**:

| State | Submitted |
|---|---|
| COMMENTED | 2026-06-02T22:11:18Z |

## Skipped Phases

This shipment had no code surface. The following Ship phases are intentionally
skipped and documented here in lieu of executing them:

* **Harness generation (P-002 / P-004)** — N/A: no code, `harness_status: not-applicable`.
* **Build / test loop** — N/A: nothing to build.
* **Quality gates** (`ruff check`, `pyright`, `pytest`, `ruff format`) — N/A: no source delta.
* **Review skill** — N/A: no diff to review.
* **CI / fix-ci** — N/A: no PR triggering CI for the feature scope.
* **Feature PR lifecycle (Step 5)** — N/A: shipment manifest explicitly states
  "Ship closes the task and shipment without a code PR."

## Runtime Verification

Runtime verification is covered by the pre-collected acceptance evidence above.
The Copilot review pipeline is the runtime surface, and it has been observed
operating across two live PRs (`#16` and `#17`) since enablement.

## Monitoring & Rollback

| Item | Detail |
|---|---|
| Signal | Future PRs continue to receive Copilot reviews with `state != PENDING` |
| Rollback trigger | `422 not a collaborator` or `'copilot' not found` recurs on `gh pr edit --add-reviewer copilot` |
| Rollback procedure | Re-enable Copilot code review in GitHub Settings → Code security and analysis → Copilot |
| Owner | Repository admin |

## Follow-ups

None. The original deliberation and plan considered documenting the
configuration prerequisite; the closure artifact and the plan/deliberation
references on the feature artifact already satisfy that need.

## Closure Trail

* Shipment manifest: `.backlogit/queue/009-S.md` → archived
* Feature: `.backlogit/queue/009-F.md` → archived
* Task: `.backlogit/queue/009.001-T.md` → archived
* Default-branch HEAD at closure: `73e06eb`
