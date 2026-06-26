---
date: 2026-06-25
category: workflow-single-open-pr
keywords: [git, github, pull-request, pr, merge-conflict, workflow, ship, single-pr, sequential, branch]
confidence: high
evidence: "2026-06-25 session opened PR #100 (default-flip, touches src/process) and PR #101 (routing investigation, docs) concurrently; operator directive: never allow multiple open PRs simultaneously because concurrent PRs accrue merge conflicts and complicate review/merge ordering."
---

# Keep at most one open PR at a time — open the next only after the current merges

## Problem

During a multi-step session the agent opened a second pull request (#101,
docs-only) while the first (#100, source change) was still open and under
review. Even when the two PRs touch non-overlapping files, multiple
simultaneously-open PRs are a workflow hazard:

* The later PR is branched from a `main` that does **not** yet contain the
  earlier PR's commits, so after the first merges the second goes stale and
  must be fast-forwarded / rebased before it is mergeable.
* Any overlap (or a shared file touched later) produces merge conflicts that
  must be resolved across branches.
* Review and merge ordering becomes ambiguous for the operator, who has to
  track which PR depends on which.

## Root Cause

Treating each deliverable (a fix, a doc, an investigation) as an independent
shippable unit and opening a PR for each as soon as it is ready — instead of
serializing them through a single-PR pipeline gated on merge.

## Resolution

Enforce a **single-open-PR discipline**:

1. Before creating a new PR, check `gh pr list --state open`. If a PR is
   already open, do **not** create another.
2. Finish the current PR's lifecycle first (review → fixes → operator-approved
   merge), then create the next PR from the freshly-updated `main`.
3. If a second deliverable is already on a branch and a PR was opened
   prematurely, **close** the extra PR (`gh pr close <n>`) with a note —
   keeping its branch — and re-open it after the current PR merges. Closing a
   PR preserves the branch and commits; it is non-destructive.
4. Queue subsequent work as branches (or backlog items) rather than open PRs.

In the 2026-06-25 session this was applied by closing PR #101 (branch
`docs/cosmos-routing-investigation` preserved) so PR #100 was the only open PR,
to be reopened after #100 merged.

## Prevention

* Add a pre-PR-create guard: `gh pr list --state open --json number --jq 'length'`
  must return `0` before `gh pr create`.
* When a session produces multiple deliverables, ship them **sequentially**:
  one PR open, merged, then the next branched from the new `main`.
* Stack dependent work as local branches and only promote the next to a PR once
  its predecessor lands.
