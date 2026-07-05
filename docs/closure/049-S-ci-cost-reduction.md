---
shipment: 049-S
title: "Closure record — CI cost reduction: paths-ignore + PR-title guards (047-F)"
status: verified
merge_sha: cd56682
merged_pr: 130
---

## Scope delivered

Feature `047-F` reduces GitHub Actions consumption once CI is re-enabled, by
guarding the heavy jobs against non-code changes.

| Task | Delivered |
|---|---|
| `047.001-T` | `.github/workflows/ci.yml` — `paths-ignore` (`​.backlogit/**`, `docs/**`, `**/*.md`, `README.md`) inlined into the restore-ready trigger template; PR-title `if:` guards on `test` (matrix) + `build` skipping `chore:`/`docs:` PRs (inert on non-PR events); an always-reporting `ci-gate` aggregate job so skipped jobs never block those PRs under branch protection; PENDING item 3 resolved. |

## Verification

- YAML validates; `test`/`build` carry the guard; `ci-gate` (`if: always()`,
  needs all five jobs) reports a single status; triggers unchanged
  (`workflow_dispatch`/`release`/`push tags`) — CI stays paused.
- Ops/config change — no test coupling to `ci.yml`; verified by validity +
  workflow conventions rather than TDD.
- Copilot review: 1 thread — required-check-skip-blocks-merge gotcha — resolved
  by the `ci-gate` job + a "require ci-gate" header note (`aeb731b`).

## Operator note for re-enabling CI

The two guards are independent and restore-ready. When restoring the
`pull_request` / `push: branches` triggers: (1) the `paths-ignore` is already in
the commented template; (2) require the **`ci-gate`** job in branch protection —
not `test`/`build` directly — so `chore:`/`docs:` PRs with intentionally-skipped
jobs remain mergeable.
