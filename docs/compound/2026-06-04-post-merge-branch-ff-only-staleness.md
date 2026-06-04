---
date: 2026-06-04
shipment: 014-S
category: post-merge-branch-staleness
keywords: [git, post-merge, branch, ff-only, fetch, closure, ship, github, update-branch]
confidence: high
evidence: PR #29 closure branch flagged out-of-date on GitHub after creation; operator manually clicked "Update branch" producing benign merge commit b6817f8
---

# Post-merge closure branch must explicitly fast-forward to the new origin/main HEAD

## Problem

After Ship admin-merges a feature PR (e.g., `gh pr merge --merge --admin`),
the local `main` branch is typically still pointing at the pre-merge HEAD.
The subsequent post-merge closure branch (per Ship Step 6.0) must be
created from the new `origin/main` HEAD (which includes the merge commit
that just landed), NOT from local stale `main`.

If the closure branch is created from a stale local `main`, the closure
PR will be flagged "out of date" by GitHub even though all the file
content is correct. The operator (or branch-protection auto-update) then
has to click "Update branch" in the GitHub UI, which produces a benign
"Merge branch 'main' into post-merge/..." commit that:

- Adds no file changes
- Re-triggers CI from scratch
- Resets the Copilot review baseline (Copilot may not re-review the
  merge-only commit, producing an "encountered an error" review state)
- Adds another round-trip before the closure PR can merge

## Symptom

During Ship Step 6.0:

1. `gh pr merge 28 --merge --admin` succeeds
2. `git fetch origin main` runs silently
3. `git checkout main` may report "Aborting" if untracked files conflict,
   then succeed
4. `git pull --ff-only` reports "Already up to date" (because local main
   *seems* synced)
5. `git checkout -b post-merge/...` creates the branch
6. Push closure branch and create PR
7. GitHub UI flags branch as out-of-date
8. Operator manually clicks "Update branch" → produces benign merge commit
   (e.g., `Merge branch 'main' into post-merge/...`)

The benign merge commit has zero file diff vs the prior closure commit,
so it's harmless functionally — but it adds a round-trip and confuses
the Copilot review baseline.

## Root cause

`git pull --ff-only` on local `main` only reports "Already up to date"
when local and remote agree at the SHA level. The deeper issue is that
either:

- The local `main` was not actually behind (the operator may have already
  pulled it in another session), but the branch protection check on GitHub
  uses different timing semantics that flag the branch.
- Some interleaving with another local edit or terminal session caused
  the local `main` to lag the actual remote HEAD.

The fix is defensive: always explicitly fetch and reset the branching
base to the exact remote SHA that includes the just-merged PR, then
verify before branching.

## Fix

Replace the brittle `git checkout main && git pull --ff-only` pattern
with an explicit reset-to-remote sequence after every admin merge:

```powershell
# After 'gh pr merge --admin' confirms MERGED at $mergeSha
git fetch origin main
git checkout main
git reset --hard origin/main   # NOT just --ff-only; force-align local to remote
git log -1 origin/main --oneline  # verify the merge SHA is current HEAD
# Now branch
git checkout -b post-merge/{feature_slug}
```

The `git reset --hard origin/main` step is critical when local `main`
might have drifted (uncommitted changes auto-discarded, stale local
commits realigned). For Ship's post-merge workflow this is safe because
we just merged remotely and local `main` should always be a strict
ancestor of `origin/main`.

Then verify before the post-merge branch is pushed:

```powershell
git log -1 origin/main --format="%H"  # capture remote HEAD
git log -1 HEAD~1 --format="%H"        # parent of the new post-merge branch
# These two should match — the closure branch should be one commit beyond
# the remote main HEAD.
```

## Reusable rule

**After any admin merge, always `git reset --hard origin/main` (after
fetch) before creating the post-merge closure branch.** Trust the remote
HEAD; do not assume local main is in sync.

## Detection in code review / Ship workflow

Watch for the pattern `git checkout main && git pull --ff-only` in
Ship's Step 6.0 post-merge branch creation. Replace with:

```powershell
git fetch origin main
git checkout main
git reset --hard origin/main
git checkout -b post-merge/{slug}
```

The post-merge branch should be exactly one commit beyond `origin/main`
at push time; if it's two or more commits ahead, something has gone
wrong in the branching base.

## Related

- 014-S closure PR #29 — the operator manually updated the branch via
  GitHub UI, producing benign merge commit `b6817f8`
- Ship Step 6.0 (`.github/agents/ship.agent.md`) — current text says
  "checkout main && pull && checkout -b" which is the brittle pattern
- Compare to feature branch creation in Step 0.5.3a — similar fetch +
  pull pattern but operates on a "create from fresh main" assumption
  that holds because the feature PR has not yet been merged
