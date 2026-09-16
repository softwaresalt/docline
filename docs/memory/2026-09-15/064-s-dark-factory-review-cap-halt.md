---
title: "064-S dark factory review-cap halt"
date: "2026-09-15"
shipment: "064-S"
feature: "073-F"
status: "resolved-operator-scope-correction"
branch: "chore/stage-064-s"
head: "cdcf718180e6c481aa9f8d0cc438df7e70b0b376"
---

## Outcome

Dark factory execution halted before the staging PR, shipment claim, source
implementation, or merge. The final allowed adversarial re-review cycle found
four unresolved P1 planning defects. The P-021 same-contract guard and the
review-cycle cap prohibit silently deferring or applying another autonomous
fix cycle.

## Completed work

* Activated dark mode with scope limited to shipment `064-S`
* Confirmed DAG readiness, predecessor closure, P-020 compaction, and
  single-worktree topology
* Committed the initial Stage artifacts as `cdcf718`
* Completed two Stage remediation cycles
* Added tasks `073.005-T` through `073.008-T` and updated the shipment manifest
* Ran two post-remediation adversarial review cycles

## Current branch state

* Branch: `chore/stage-064-s`
* Committed base: `cdcf718`
* Cycle-1 and cycle-2 remediation changes remain uncommitted
* Unrelated 063-S memory files remain untracked and untouched
* Shipment `064-S` remains `queued` and unclaimed
* The shipment manifest is not present on `origin/main`

## Blocking findings

1. A1 still claims live CLI stdout coverage that belongs to integration task
   `073.007-T`, and its source-kind scope conflicts with the matrix.
2. Iterative percent decoding can expose a malformed inner escape without
   revalidation after each layer.
3. The WARNING/error matrix claims all four URL-bearing source kinds, but
   `073.008-T` does not require all four.
4. The live stdout path-secret invariant lacks a direct path-secret integration
   fixture in `073.007-T`.

## Non-blocking residual

The job-ID revisit proposal should use a keyed construction over the raw
canonical source key rather than the sanitized key if its risk trigger fires.

## Decisions

* `ActionRisk`: high
* `ActionResult`: blocked
* Merge pre-authorization: false
* Admin fallback pre-authorization: false
* No P1 finding was converted into deferred scope
* No staging PR was created because local readiness is `BLOCKED`

## Resume condition

Resume only after the operator explicitly chooses one of these dispositions:

* extend the review-fix cycle limit for one bounded Stage correction pass, or
* explicitly accept and document the residual P1 risk

The recommended disposition is one bounded correction pass followed by a fresh
current-HEAD review. Do not invoke Ship until the staging artifacts are
committed, merged to `main`, and the remote manifest gate passes.

## Authorized exceptional cycle outcome

The operator authorized one additional bounded Stage correction and re-review
cycle. Stage applied the correction without touching production or test code.
The exceptional adversarial re-review remained `BLOCKED`, so the authorization
is exhausted and the dark run is halted again.

Remaining P1 findings:

1. `073.002-T` requires all of `073.007-T` to pass, but that integration test
   intentionally contains a path-secret assertion that cannot pass until
   `073.006-T`; the milestone contract is unsatisfiable without redesign.
2. Reusing query-prefix matching for path segments can redact benign paths such
   as `/authentication/overview`, `/keys/rotation`, and
   `/tokenizer/config`.
3. Per-layer percent validation can reject valid terminal literal-percent data
   such as `/docs/100%25-off`.

The final review also recorded three non-blocking P2 follow-ups: update the
human-readable Stream C prerequisite list, name the decoder entry point for the
`%70assword` fixture, and include processed-document `source`/`source_url`
consumers in the exposure analysis.

No staging PR was created or pushed. Shipment `064-S` remains queued and
unclaimed. The branch remains at committed HEAD `cdcf718` with all remediation
cycles preserved as uncommitted changes.

## Operator-Decision Resolution — 2026-09-15 (scope correction; blockers cleared)

The operator issued an authoritative scope correction that RESOLVES all three of
the exceptional-cycle P1 blockers above by REMOVING the unjustified path-redaction
requirement — NOT by inventing more path parsing. Docline's responsibility is
narrowed to structured access credentials (URL user-info + recognized credential
query params + typed secret config fields); it does not scan/rewrite source-document
content and leaves ordinary URL paths byte-for-byte unchanged (path-secret detection
is an upstream DLP concern).

Resolution of the three P1 blockers:

1. **Unsatisfiable `073.002-T` ↔ `073.007-T` path milestone** — RESOLVED. The
   direct path-secret fixture and the `073.006-T` coupling were removed from
   `073.007-T`; it is now fully satisfied by `073.002-T` alone. No stream-C task is
   required.
2. **Query-prefix matching over-redacting benign paths** (`/authentication/overview`,
   `/keys/rotation`, `/tokenizer/config`) — RESOLVED. Path redaction is removed
   entirely; ordinary paths are preserved byte-for-byte and are now positively
   asserted in `073.001-T`/`073.007-T`.
3. **Per-layer percent validation rejecting valid literal-percent data**
   (`/docs/100%25-off`) — RESOLVED. All path percent-decoding/validation is removed;
   the literal `%25` is preserved unchanged.

Actions taken (Stage, planning/backlog only; no code/test written; nothing committed):
stream C tasks `073.005-T`/`073.006-T` set to `blocked` via `shipment return-blocked`
and removed from the `064-S` manifest; their dependency edges removed; `073.007-T`
narrowed to structured-access-credential coverage + benign-path preservation; plan,
deliberation, feature, shipment, and memory updated with the operator decision and
REJECTED-alternatives record; DAG rebuilt to two test-first streams
(`073.001-T`/`073.007-T`→`073.002-T`, `073.003-T`/`073.008-T`→`073.004-T`).

Updated status: the review-cap BLOCK is CLEARED by operator decision. Shipment
`064-S` is a 7-item, parent-first, queued, unclaimed manifest. Changes remain
UNCOMMITTED for Orchestrator review; Ship is not invoked. Readiness after
Orchestrator commit + fresh review: **READY** (no in-scope path work remains).
