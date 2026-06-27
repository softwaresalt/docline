---
date: 2026-06-27
category: backlog-ship-cascade-archives-parent-feature
keywords: [backlogit, shipment, ship, archive, feature, parent, cascade, orphan, partial-feature, cli, status-transition, parent_id, frontmatter]
confidence: high
evidence: "2026-06-27 session: `backlogit shipment ship 039-S` (shipment contained only child task 036.001-T) archived the PARENT feature 036-F, even though sibling task 036.002-T was still queued. The archived feature had a still-open operator-run child, leaving the feature wrongly closed. A second symptom surfaced in PR #107 Copilot review: the same cascade re-wrote the sibling task `036.002-T.md` and stripped its `parent_id: 036-F` frontmatter, orphaning the task even after the feature was restored."
---

# `backlogit shipment ship` archives the parent feature of shipped tasks — guard partial-feature shipments

## Problem

When a feature is delivered across **multiple shipments** (because only some of
its child tasks are completable now — e.g., agent-shippable vs. operator-run),
shipping a child task via `backlogit shipment ship <S>` **also archives the
parent feature**, even if that feature still has open child tasks not in the
shipment.

Concretely: feature `036-F` had two tasks — `036.001-T` (agent-built harness)
and `036.002-T` (operator-run experiment, depends on the harness). The shipment
`039-S` deliberately contained **only** `036.001-T`. Shipping it archived
`036.001-T` (correct) **and** `036-F` (wrong) while `036.002-T` remained
`queued` — orphaning the still-pending task under an archived feature.

### Second symptom: sibling `parent_id` stripped

The same cascade also **re-wrote the sibling task's markdown and dropped its
`parent_id`**. During the `ship` operation the parent feature `036-F` was
momentarily archived, so when `036.002-T.md` was re-serialized its
`parent_id: 036-F` frontmatter line was removed (the parent reference resolved
to nothing). This left `036.002-T` orphaned *at the file level* even after the
feature itself was restored to `active`. It was caught by Copilot review on
PR #107 (the diff showed the `parent_id: 036-F` line deleted), not by
`doctor` at the moment it ran. Restoring the feature's status is therefore
**not sufficient** — the sibling task's `parent_id` must be checked and
restored independently.

## Root Cause

`shipment ship` treats the shipped scope as "feature released" and cascades
archival to the ancestor feature, without checking whether the feature has
child tasks outside the shipment that are still open.

## Resolution

`archived` is a **terminal status** — `backlogit move 036-F --status active`
fails with `status "archived" has no allowed transitions`. So restoring a
wrongly-archived feature requires an **out-of-band markdown edit**:

1. Edit `.backlogit/archive/<feature>.md` frontmatter: set `status: active`,
   and remove the `archived_from:` and shipped `commit:` lines that `ship`
   added.
2. Move the file from `.backlogit/archive/` back to `.backlogit/queue/`
   (regular file move — the freshly-archived file is untracked, so `git mv`
   fails; use `Move-Item`).
3. `backlogit sync` to re-index, then `backlogit doctor` to confirm no orphans.

In the 2026-06-27 session this restored `036-F` to `active` in `queue/`, with
`036.002-T` intact and `doctor` clean.

## Prevention

* **Don't ship a feature's child task through `shipment ship` while sibling
  tasks remain open**, unless you intend to close the feature. For a feature
  delivered in stages, either:
  * keep the feature out of any shipment until **all** its tasks are done, and
    ship the tasks individually only when the feature is truly complete; or
  * accept the cascade and immediately restore the feature (steps above) when
    partial delivery is intentional.
* After any `shipment ship`, **verify the parent feature's status** if the
  feature has tasks outside the shipment: `backlogit get <feature>` should not
  read `archived` while open children remain.
* **Also verify each surviving sibling task's `parent_id`** after a partial-
  feature ship. The cascade can strip `parent_id` from sibling task markdown
  during re-serialization (separate from the feature-archival symptom). Re-add
  the dropped `parent_id: <feature>` line to `.backlogit/queue/<task>.md`,
  then `backlogit sync` and `backlogit doctor` to confirm the hierarchy is
  intact. Do not rely on a single `doctor` run — inspect the actual frontmatter.
* Treat `archived` as terminal in planning — recovering from it is a manual
  file edit, not a status transition.
