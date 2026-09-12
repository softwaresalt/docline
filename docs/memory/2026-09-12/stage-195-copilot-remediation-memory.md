---
title: "Stage session -- PR #195 Copilot remediation (063-S staging, R4)"
date: 2026-09-12
agent: stage
session_id: stage-195-copilot-2026-09-12
phase: complete
mode: report-to-Orchestrator (Stage boundary; shipment 063-S NOT claimed/started/status-changed)
---

# Stage session memory -- PR #195 Copilot remediation

## Scope
Stage-owned portion of PR #195 remediation, continuing the PR #194 staging-artifact remediation
(prior commit 1e42fc4). Strictly PR #195 staging/backlog/plan/decision/memory artifacts + the
same-contract-surface plan/decision needed by the live finding. No product source. Shipment 063-S
untouched (not claimed/started/status-changed/implemented). Single branch, single worktree.

## Live GitHub inventory (fully paginated, authoritative)
- PR #195 OPEN, base main, head `chore/stage-194-copilot-remediation`, HEAD pre-commit
  1e42fc473fd59708a7dad5ff5a5e5b0e8ed57d58, mergeStateStatus BLOCKED.
- reviewThreads totalCount = 1 (hasNextPage false). Reviews: 1 (COMMENTED, copilot). Review
  comments: 1.
- Copilot GraphQL login: `copilot-pull-request-reviewer`.
- Exactly ONE unresolved Copilot-authored thread:
  - thread node id: PRRT_kwDOSsAX4c6hz0Jq (isResolved false, isOutdated false)
  - comment node id: PRRC_kwDOSsAX4c7uR7ht ; databaseId: 3997677677
  - path: docs/plans/2026-09-12-source-key-credential-sanitization-plan.md, line 99
  - url: https://github.com/softwaresalt/docline/pull/195#discussion_r3997677677
  - summary: R3 contract leaves ManifestUrlSource.id verbatim in the sanitized key; a
    credential-bearing id still leaks to metadata.source + ERROR log even when config.url is
    sanitized. Asked to define how the safe representation sanitizes/validates id and add the
    credential-bearing-id case to Unit 1.

## P-021 C1 classification + disposition
- IN SCOPE (same-contract-surface finding on a Stage-owned plan artifact; source-key credential
  sanitization). Fixed in-cycle; NOT deferred. No P-021 C2 capture required.
- Finding verified against source: manifest_models.py:65 ManifestUrlSource.id: str (unrestricted);
  source_keys.py build_source_key/_build_crawl_source_key compose `manifest_url:<id>:<url>:<opts>`
  with config.id verbatim -> reviewer correct.

## Corrections (R4 contract: id + url sanitized)
- docs/plans/...-plan.md: R4 revision note; Requirements Trace row (id segment); Unit 1
  id-sanitization sub-bullet + scenario 2 strengthened to credential-bearing id; Risks bullet
  (closed by R4) + distinct non-URL-form-id no-op residual; new "PR #195 Copilot Remediation (R4)"
  record section.
- docs/decisions/...-sanitization.md: Option B R4 refinement paragraph; Chosen Direction +
  Done Looks Like updated to cover id sanitization.
- .backlogit/queue/072.001-T.md: CONTRACT R4 (id + url sanitized) + id-sanitization sentence +
  AC(2) rewritten to credential-bearing-id; updated_at bumped.
- .backlogit/queue/072.002-T.md, 072.003-T.md: contract label R3 -> R4 (id + url sanitized);
  updated_at bumped.
- Contract remedy: safe representation routes config.id through sanitize_source() before recompose
  (`manifest_url:{sanitize_source(config.id)}`); make_job_id still hashes raw build_source_key(config)
  so job_id determinism unchanged.

## Known residual (documented, not deferred as stash)
sanitize_source() no-ops on a non-URL-form id embedding a raw credential (no scheme). Distinct from
the _sanitize_url credential-param/path-secret residual (string never enters _sanitize_url). Narrow
vector (manifest ids are short opaque identifiers). Recorded in plan Risks/Caveats + Unit 1.

## Validation
- backlogit sync: Indexed 509 artifacts, parse_failures=0 (markdown edits valid).
- backlogit doctor: 168 issues, ALL `archived_from_self_ref` on archived items -- pre-existing,
  zero involve 072/063 or the touched files; out of scope (archive hygiene).
- markdownlint enforced rules MD001/MD025/MD041: plan + decision each have exactly one H1;
  headings increment; first line H1. Pass. (No markdownlint binary installed locally.)
- Independent review: Correctness Reviewer (targeted, this diff) -> leak closure, determinism,
  cross-artifact consistency, source-fact accuracy confirmed; one P3 (residual mischaracterization)
  raised and remediated same cycle. Verdict PASS.

## Excluded from commit
- .backlogit/stash.jsonl carried a pre-existing (not this session) fractional-seconds timestamp
  normalization on deferred entries 0F1A653C/79BF0AEC/06A59B1D. Left unstaged; not authored here.

## Lifecycle handoff (owner-ready; Stage does NOT own reply/resolve here)
Order per thread: push fix commit first, THEN post reply, THEN resolve.
- Thread PRRT_kwDOSsAX4c6hz0Jq -> resolve after reply citing the fix commit SHA.

## Next steps
- Push commit to origin/chore/stage-194-copilot-remediation (owner-authorized push).
- Post the ready reply body; resolve the thread; re-request Copilot review if desired.
- 063-S remains queued and unclaimed for Ship.
