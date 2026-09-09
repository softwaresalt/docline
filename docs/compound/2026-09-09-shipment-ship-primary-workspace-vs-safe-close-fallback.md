---
title: "shipment ship succeeds from the primary workspace; prefer cascade close to avoid a new archived_status:active predecessor block"
date: 2026-09-09
agent: ship
shipment: 060-S
context: ship-shipment-lifecycle
confidence: medium
evidence: "060-S post-merge closure — backlogit shipment ship 060-S --sha f278cff... completed successfully from the PRIMARY workspace (not an isolated worktree) in ~90s, with 3 resident backlogit daemon processes present. archived_ids covered all 9 manifest artifacts, returned_ids: [] (no unintended requeue/detach), and the shipment record carries genuine archived_status: shipped. Contrast: 059-S's post-merge closure (docs/compound/2026-08-30-ship-shipment-deadlocks-in-worktree.md) hung 3x from an ISOLATED worktree and was closed via the single-artifact safe-close fallback, leaving archived_status: active."
tags:
  - backlogit
  - ship_shipment
  - worktree
  - pipeline-topology
  - archived_status
  - commit-traceability
related:
  - docs/compound/2026-08-30-ship-shipment-deadlocks-in-worktree.md
  - docs/compound/2026-05-07-backlogit-shipment-status-constraints.md
trigger:
  - "About to close a shipment whose manifest verifiably qualifies for the P-015 fully-covered-root cascade exception"
  - "Deciding between the cascade `backlogit shipment ship` and the single-artifact safe-close fallback"
  - "A downstream shipment is blocked by `pipeline-topology`'s PREDECESSOR_NOT_SHIPPED check on a predecessor with `archived_status: active`"
---

## Problem

059-S's closure hit a `backlogit shipment ship` hang from an isolated worktree and fell back to
the documented single-artifact safe-close sequence (`move` + per-artifact `update --commit` +
`archive`). That fallback's own documented caveat is that it leaves `archived_status: active`
rather than `shipped`, because only the `ship` cascade path first transitions a shipment through
`shipped` before archiving.

This session (060-S) needed to unblock on that exact gap: `pipeline-topology`'s
`PREDECESSOR_NOT_SHIPPED` check has **zero tolerance** for the `archived_status: active`
provenance shape, even when the predecessor is independently verified materially complete (merge
ancestry, full archival, commit backfill). The only way through was an operator-authorized,
audited `--force` override of the topology gate — a real operational cost, repeated at every
phase the gate recurs (`pre_claim`, `post_claim`, `lifecycle`), because 059-S's provenance can
never be honestly corrected after the fact (directly editing `archived_status` was correctly
rejected in a prior session as provenance fabrication).

## Root cause

Two independent, previously-unconnected facts combine into an avoidable recurring cost:

1. The single-artifact safe-close fallback is **cosmetically degraded**: it archives correctly
   (placement + commit traceability) but never reaches `shipped` provenance, and there is no
   supported way to correct that after the fact without fabricating history.
2. `pipeline-topology`'s predecessor-readiness check treats `archived_status: active` as an
   unconditional block, with no allowance for "verified materially complete but closed via the
   documented fallback." So a fallback-closed shipment becomes a **permanent** predecessor block
   for every future dependent, not a one-time cost.

The prior compound note (`2026-08-30-ship-shipment-deadlocks-in-worktree.md`) correctly diagnosed
the deadlock symptom but its scope was narrower than the prose suggested: the reproduced hangs
were all from an **isolated worktree** (`.copilot/worktrees/ship-059`) with several long-lived
resident daemons from the **primary** workspace. This session's closure ran `shipment ship` from
the **primary** workspace itself — with 3 resident `backlogit` processes present, the same
daemon-contention risk factor the prior note flagged as a suspected cause — and it completed
successfully in ~90 seconds (slow relative to single-artifact ops, but not hung). This suggests the
contention, if real, is specific to cross-worktree lock/DB-handle sharing, not to resident daemons
existing at all.

## Resolution

For 060-S, before defaulting to the safe-close fallback: verify whether the shipment's manifest
qualifies for the P-015 fully-covered-root exception (root feature, fully covered by the manifest,
no manifest member beyond the feature and its descendants). It did (069-F: root, 7 children, all
manifest members, no member's own subtasks). Given that qualification, and given this session runs
from the **primary** worktree (confirmed via `git worktree list --porcelain` — no isolated worktree
in play), attempted `backlogit shipment ship` directly, backgrounded with file-redirected
stdout/stderr per the prior note's own reusable rule, so a genuine hang would be observable within
seconds rather than blocking indefinitely. It succeeded: `archived_ids` covered all 9 artifacts,
`returned_ids: []`, and the shipment now carries genuine `archived_status: shipped`.

## Prevention

* **Always classify the close path first** (P-015's `classify_shipment_close_path`-shaped check),
  regardless of which path you expect to use. A manifest that qualifies for the cascade close
  should default to attempting it — not to the safe-close fallback — specifically because the
  fallback's `archived_status: active` result is a **permanent**, not transient, cost: it blocks
  every future `pipeline-topology`-gated dependent until an operator authorizes a force override.
  The safe-close fallback remains correct and necessary when the manifest does **not** qualify
  (partial-feature shipments, manifests with out-of-scope siblings) — it is not being deprecated,
  only de-prioritized as the *default* choice when cascade qualifies.
* **When attempting the cascade from a worktree** (not the primary workspace), the deadlock risk
  documented in the prior note is real and reproduced 3x — do not retry past the circuit-breaker
  threshold; fall back promptly per that note's resolution.
* **When attempting the cascade from the primary workspace**, this session's evidence suggests it
  is likely to succeed even with resident daemons present, but budget for it being noticeably
  slower (tens of seconds, not sub-second) than single-artifact mutations — run it backgrounded
  with file-redirected output so slowness is observable and distinguishable from a true hang
  (no new log line for an extended period with the process still alive, vs. the process actually
  exiting).
* **Do not attempt to retroactively correct a prior fallback-closed shipment's `archived_status`**
  by direct edit — that is provenance fabrication (already correctly rejected once for 059-S). The
  only supported remediation for a *historical* fallback-closed predecessor is either operator
  authorization to force the downstream gate (as this session did for 059-S → 060-S), or a future
  gate revision that recognizes the documented fallback shape as an alternate valid provenance —
  neither of which is retroactive surgery on the closed record itself.
