---
title: "Stage session -- PR #195 Copilot remediation Cycle 2 (063-S staging, R5)"
date: 2026-09-12
agent: stage
session_id: stage-195-copilot-cycle2-2026-09-12
phase: complete
mode: report-to-Orchestrator (Stage boundary; shipment 063-S NOT claimed/started/status-changed)
---

# Stage session memory -- PR #195 Copilot remediation Cycle 2 (R5)

## Scope
Stage-owned cycle-2 remediation of PR #195 (continuing cycle 1 / commit 45a1a00). Strictly
PR #195 staging/backlog/plan/decision/memory artifacts for feature 072-F / shipment 063-S. No
product source. Shipment 063-S untouched (queued, unclaimed, no harness_status; NOT
claimed/started/status-changed/implemented). Single branch `chore/stage-194-copilot-remediation`,
single worktree.

## Tool gate (P-012)
- backlogit CLI 1.10.1 present; registry `.autoharness/backlog-registry.yaml` present
  (features.sizing/shipments/checkpoints = true). shipment get / list read-only probes OK.
- ALL_TOOLS_OK. INDEX_SYNC_OK (509 artifacts, parse_failures=0).

## Live GitHub inventory (fully paginated, authoritative)
- PR #195 OPEN, head 45a1a00df519720954a27a047f28cb46fecd9f14. reviewThreads=6 (hasNextPage
  false). Copilot GraphQL login: `copilot-pull-request-reviewer`.
- Unresolved Copilot threads = EXACTLY 4 (matched Ship handoff; no new threads found):
  1. PRRT_kwDOSsAX4c6h0OMq / PRRC_kwDOSsAX4c7uSjF7 (db 3997839739) --
     docs/decisions/...-sanitization.md:93 -- R4 overstates closure; sanitize_source(id) no-ops on
     non-URL id.
  2. PRRT_kwDOSsAX4c6h0OM1 / PRRC_kwDOSsAX4c7uSjGM (db 3997839756) --
     docs/plans/...-plan.md:123 -- non-URL credential-bearing id still leaks; require
     validation/rejection or ID-specific redaction + regression case.
  3. PRRT_kwDOSsAX4c6h0OM9 / PRRC_kwDOSsAX4c7uSjGW (db 3997839766) --
     .backlogit/queue/072-F.md:21 -- feature card stale (R3, config.url-only).
  4. PRRT_kwDOSsAX4c6h0ONH / PRRC_kwDOSsAX4c7uSjGi (db 3997839778) --
     .backlogit/queue/072.001-T.md:18 -- task "keep" _CRAWL_OPTION_KEYS but constant does not
     exist; plan says add/refactor -> contract drift.
- 2 already-resolved Copilot threads (memory line 15; plan line 112) untouched.

## P-021 C1 classification + disposition
- ALL FOUR IN SCOPE -- same-contract-surface findings on Stage-owned planning artifacts (source-key
  credential sanitization contract for 072-F / 063-S). Fixed in-cycle; NONE deferred; NO P-021 C2
  capture required. Authoritative classification (not assumed from handoff).
- Source-fact verified: staging.py sanitize_source() returns non-URL/non-path strings verbatim
  (no-op) -> findings 1/2 correct. source_keys.py has _build_crawl_source_key/_crawl_option_parts
  and NO _CRAWL_OPTION_KEYS (`__all__ = ["build_source_key"]`) -> finding 4 correct.

## R5 contract (resolves the R4 contradiction; NO product implementation)
- Credential closure: safe representation applies ID-specific credential redaction INDEPENDENT of
  URL detection to config.id via a new `sanitize_source_id()` helper (strip user:pass@ userinfo +
  redact credential-named key=value fragments using the EXISTING _CREDENTIAL_PARAM_PREFIXES
  vocabulary, NOT expanded), so `srcA?token=SECRET` -> `srcA?token=<redacted>`. R4 "known residual"
  (non-URL-form id no-op) is CLOSED, not documented as an accepted exception -- honoring the
  invariant that no credential material reaches persisted metadata or ERROR logs.
- _CRAWL_OPTION_KEYS drift: removed the R2 shared-constant add/refactor from plan Unit 1, plan
  rationale, and task 072.001-T. The typed-config recompose reuses the existing builder directly, so
  the separate parse path the constant guarded no longer exists. No forward instruction references
  the nonexistent constant.
- Determinism preserved: make_job_id keeps hashing the RAW build_source_key(config) across plan,
  decision, and all three tasks.
- Regression: non-URL-form credential-id case added to Unit 1 (unit, test_source_keys.py) and
  Unit 2 (integration, test_elt_real_execution.py).

## Artifacts changed (Stage-owned)
- docs/plans/2026-09-12-source-key-credential-sanitization-plan.md: revision R4->R5; R5 revision
  note; Requirements Trace row; Unit 1 (heading, step reorder, id-redaction sub-bullet, builder
  bullet, tests scenario 2 parametrized); Unit 2 (c2 non-URL id case); rationale bullet; Risks bullet
  (residual CLOSED); R4-record Known-residual bullet marked SUPERSEDED; new "Cycle 2 (Revision R5)"
  section.
- docs/decisions/2026-09-12-source-key-credential-sanitization.md: Option B heading R3->R3/R4/R5;
  R5 refinement paragraph; Chosen Direction relabeled R5 + sanitize_source_id behavior; Done Looks
  Like updated; "added to Unit 1 (unit) and Unit 2 (integration)".
- .backlogit/queue/072-F.md: body -> R5 contract (id + url; ID-specific redaction independent of URL
  detection); updated_at bumped.
- .backlogit/queue/072.001-T.md: CONTRACT R4->R5; builder-keep line (no _CRAWL_OPTION_KEYS); id
  sanitize_source_id sentence; __all__; AC(2) adds non-URL-form id case; updated_at bumped.
- .backlogit/queue/072.002-T.md: contract label -> R5; non-URL id assertion + AC(2); updated_at.
- .backlogit/queue/072.003-T.md: contract label -> R5; updated_at.

## Validation / review
- backlogit sync: Indexed 509, parse_failures=0. INDEX_SYNC_OK. stash.jsonl SHA256 unchanged by
  sync (no further normalization caused).
- backlogit doctor: only pre-existing `archived_from_self_ref` archive-hygiene issues on old
  archived items (001-00x...); ZERO involve 072/063 or any touched file. Out of scope.
- Markdown: plan + decision each exactly one H1, H1 is first body line (MD001/MD025/MD041 pass).
  No CRLF/BOM introduced; LF preserved.
- Independent review: Correctness Reviewer (targeted, this diff) -> PASS (ADVISORY). Confirmed leak
  closure, determinism preserved across all 5 artifacts, cross-artifact consistency, no forward
  _CRAWL_OPTION_KEYS reference, source-fact accuracy. Two P3 advisories (decision Chosen Direction
  R3-stale label; 072.002-T/plan Unit 2 integration-test drift) BOTH fixed this cycle.

## Excluded from commit
- .backlogit/stash.jsonl: pre-existing (not this session) fractional-seconds timestamp normalization
  on deferred entries 0F1A653C / 79BF0AEC / 06A59B1D (`.0000000Z` -> `Z`), a backlogit-sync side
  effect present before cycle 1 of this session; NOT part of commit 45a1a00. Left unstaged and
  preserved exactly; NO P-021 C2 capture required this cycle, so the file is not modified/staged.

## Lifecycle handoff (Stage does NOT reply/resolve here)
Ship (owner) order per thread: push fix commit first, THEN post reply, THEN resolve. Ready replies
cite the cycle-2 commit SHA. 063-S remains queued/unclaimed for Ship.

## Next steps
- Ship: push commit to origin/chore/stage-194-copilot-remediation; post replies; resolve the 4
  threads; re-request Copilot review if desired.