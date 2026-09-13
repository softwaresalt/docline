---
title: "Stage PR #195 Copilot remediation cycle 7 (unconditional Git traceback scrub + branch/path_glob AC + dependency-graph/order sync)"
date: 2026-09-12
agent: stage
shipment: 063-S
feature: 072-F
pr: 195
head: c92aeb763ffc299ed49295935254d67a0c5b32e8
revision: R8 (post-R8 consistency + traceback hardening)
status: complete
---

# Stage cycle 7 -- PR #195 four unresolved Copilot findings (all in-scope, fixed not deferred)

## Threads (live GraphQL, HEAD c92aeb7, copilot-pull-request-reviewer)
- Single page (reviewThreads first:100, hasNextPage=false). 24 threads total; exactly FOUR unresolved,
  all authored by exact login `copilot-pull-request-reviewer`. No additions beyond Ship's snapshot.
  1. PRRT_kwDOSsAX4c6h1V40 -- comment 3998281789 -- .backlogit/queue/072.003-T.md:20 -- Git traceback scrub conditional/crawl-only.
  2. PRRT_kwDOSsAX4c6h1V49 -- comment 3998281805 -- .backlogit/queue/063-S.md:10 -- shipment item order violates dependency ordering.
  3. PRRT_kwDOSsAX4c6h1V5K -- comment 3998281821 -- .backlogit/queue/072.004-T.md:20 -- AC lacks credential-bearing branch/path_glob + ManifestGit branch.
  4. PRRT_kwDOSsAX4c6h1V5c -- comment 3998281846 -- docs/plans/...plan.md:875 -- main Dependency Graph + decision "three tasks" stale vs Unit 1b/072.004-T.

## Classification (P-021 C1)
All FOUR IN SCOPE -- same-contract-surface defects on Stage-owned planning/backlog artifacts for
072-F / 063-S under the operator no-residual-risk authorization. Same-sink credential leakage
(finding 1) and staging contract consistency (2/3/4) are in scope; NONE deferred; no P-021 C2 capture.
Read-only source confirmation: readers/github.py raises GitHubFetchError embedding raw repo_url
(github.py:47-48,52) and branch-derived request URLs (github.py:75,77); execute.py _log.exception
renders these via exc_info even after the structured source_key arg is sanitized.

## Fixes (contract-only; no product source touched)
1. 072.003-T: reworded the conditional crawl-only scrub clause to UNCONDITIONAL scrubbing of the
   exception MESSAGE + exc_info traceback for ALL fetch-failure paths (crawl config.url AND Git
   repo_url/branch-derived URLs), keeping exc_info present but credential-free and safe diagnostics
   (error class/status/reason/credential-free host-path). New AC(5) proves credential absence from
   full caplog.text (message+traceback) AND metadata.json for github_repo AND manifest_git failures.
2. 063-S: reordered custom_fields.items to dependency order 072-F, 072.001-T, 072.004-T, 072.002-T,
   072.003-T (072.004-T now precedes dependents 072.002-T/072.003-T). Verified vs authoritative edges.
3. 072.004-T: added AC(6) github_repo credential-bearing BRANCH and PATH_GLOB cases (single- and
   double-encoded) and AC(7) manifest_git credential-bearing BRANCH case, each with an
   "impl that sanitizes only repo_url MUST FAIL" oracle -- closes the unrestricted-component gap.
4. plan main ## Dependency Graph rewritten: Unit 1b (072.004-T) depends on Unit 1; Unit 2 depends on
   BOTH Unit 1 and Unit 1b; order 1 -> 1b -> 2 -> 3; shipment 063-S order mirrored. plan Unit 3 scrub
   made unconditional + Git paths; plan Unit 2 gains (c6) git-variant GitHubFetchError traceback RED;
   plan Risk line broadened to Git paths. decision doc "three tasks" -> "four atomic tasks" with the
   072.001-T -> 072.004-T -> 072.002-T -> 072.003-T order; decision Done-Looks-Like gains an
   unconditional exception-message/traceback scrub bullet.

## Preserved invariants
Raw build_source_key job-id determinism, R8 bounded multi-layer decode semantics, distinct
0F1A653C (string-arg default-fetch sink) and 06A59B1D (vocabulary/path-embedded) deferrals -- all
untouched. The unrelated preserved timestamp-normalization working-copy diff on
.backlogit/stash.jsonl (created_at only for 0F1A653C/06A59B1D) is preserved byte-for-byte and
EXCLUDED from the fix commit.

## Validation
Live GraphQL pagination (hasNextPage=false); backlogit sync OK (indexed 482, parse_failures=0);
doctor reviewed (168 pre-existing archived_from_self_ref issues, NONE on 063/072 surfaces);
shipment get 063-S confirms new item order + status still queued; dep list confirms
072.004-T->072.001-T, 072.002-T->{072.001-T,072.004-T}, 072.003-T->072.002-T (topologically valid);
independent correctness review CLEAN; independent security-lens review CLEAN (no contract gaps).

## Boundaries held
No product source changed (read-only source audit only). 063-S remains queued/unclaimed. No push,
no PR reply, no thread resolve, no shipment claim/status change, no admin/force/history rewrite.
Commit on existing branch chore/stage-194-copilot-remediation.

## Ready replies (post after human pushes the new SHA; Stage does NOT reply/resolve)
- PRRT_kwDOSsAX4c6h1V40: Fixed. 072.003-T now mandates UNCONDITIONAL scrubbing of the exception
  message + exc_info traceback for ALL fetch-failure paths -- including the Git paths where
  readers/github.py GitHubFetchError embeds raw repo_url (github.py:47-48,52) and branch-derived
  request URLs (github.py:75,77) -- not merely the sanitized source_key arg; exc_info retained,
  credential-free, safe diagnostics kept. New AC(5) asserts credential absence from full caplog.text
  and metadata.json for github_repo AND manifest_git failures. Plan Unit 3/Unit 2(c6)/Risk and the
  decision Done-Looks-Like are synchronized. (new SHA below)
- PRRT_kwDOSsAX4c6h1V49: Fixed. Shipment 063-S items reordered to dependency order
  072-F, 072.001-T, 072.004-T, 072.002-T, 072.003-T so 072.004-T precedes its dependents; status
  unchanged (queued/unclaimed). (new SHA below)
- PRRT_kwDOSsAX4c6h1V5K: Fixed. 072.004-T AC(6) adds credential-bearing github_repo BRANCH and
  PATH_GLOB cases and AC(7) a manifest_git credential-bearing BRANCH case, each asserting the secret
  is absent, so an impl leaving branch/path_glob raw fails. (new SHA below)
- PRRT_kwDOSsAX4c6h1V5c: Fixed. plan main ## Dependency Graph now includes Unit 1b/072.004-T
  (order 1 -> 1b -> 2 -> 3, Unit 2 depends on both Unit 1 and Unit 1b) and the decision doc now
  states four tasks with the 072.001-T -> 072.004-T -> 072.002-T -> 072.003-T order; shipment order
  mirrors it. The lone remaining 1->2->3 string is the historical Plan Review Remediation note,
  intentionally left as a point-in-time record. (new SHA below)