---
title: "Stage PR #195 Copilot remediation cycle 6 (Revision R8 -- multi-layer bypass + git same-sink coverage)"
date: 2026-09-12
agent: stage
shipment: 063-S
feature: 072-F
pr: 195
head: 199e7a49693cd5eaf3e0269d3db37dc0933361e7
revision: R8
status: complete
---

# Stage cycle 6 -- PR #195 double-encoding bypass + git same-sink coverage (R7 -> R8)

Note: operator remediation cycle 6 == memory cycle6 == plan section 'Cycle 5' == revision R8
(plan-section numbering lags the memory/operator cycle number by one, as in prior cycles).

## Threads (live GraphQL, HEAD 199e7a4, copilot-pull-request-reviewer)
- Fully paginated: 22 reviews, 18 review threads, hasNextPage=false on both.
- Exactly TWO unresolved threads (no additions since Ship's snapshot):
  - PRRT_kwDOSsAX4c6h1D4t -- comment 3998169888 -- plan line 235 (ManifestGitSource pass-through)
  - PRRT_kwDOSsAX4c6h1D4y -- comment 3998169896 -- plan line 260 (R7 case (h) double-encoding bypass)
- The third cycle-5 thread PRRT_kwDOSsAX4c6h1D41 (cycle5 memory) is RESOLVED.

## Findings
1. ManifestGitSource (manifest_git:{id}:{url}@{branch}) is URL-bearing and reaches the same
   _execute_single_source metadata.source + ERROR-log sinks, but R7 left it byte-identical pass-through.
2. R7 case (h) returned double-encoded srcA?%2574oken=IDSECRET VERBATIM. parse_qsl/single-unquote
   decodes only ONE layer (%2574oken -> %74oken, not token), so the literal IDSECRET leaked. Verified
   empirically: parse_qsl('%2574oken=IDSECRET') keeps value IDSECRET and re-encodes the key unchanged,
   so the URL path (_sanitize_url) shared the same double-encoding leak, not just the id path.

## Source-fact audit (read-only)
_execute_single_source (execute.py:222-256) routes ALL config types through build_source_key ->
metadata.source + ERROR log. Same-sink URL-bearing set = {web_crawl, manifest_url, github_repo,
manifest_git}; github_repo & manifest_git fetch via _fetch_github (execute.py:246). local_file /
manifest_local are filesystem-only (path-secret = deferred 06A59B1D). R7 covered only web_crawl +
manifest_url; the audit shows github_repo (deferred 79BF0AEC) and manifest_git reach identical sinks.

## Classification (P-021 C1)
BOTH IN SCOPE -- same-contract-surface defects on Stage-owned planning/backlog artifacts for 072-F /
063-S. Fixed in-cycle under the operator no-residual-risk authorization; NEITHER deferred; no P-021 C2
capture. A known reachable credential leak is not accepted merely because a different variant is involved.

## Fix (Revision R8)
- Bounded multi-layer decode: layer_{i+1}=unquote(layer_i, utf-8, errors=replace); stop at fixed point
  or _MAX_CREDENTIAL_DECODE_LAYERS=5. Marker matched at ANY layer -> redact value over RAW bytes
  (encoded key preserved). FAIL CLOSED (redact) when a name is still decoding at the cap. Termination
  guaranteed (each pass removes >=1 decodable escape); total via errors=replace.
- Multi-layer URL guard in source_keys.py scans URL query names with the same primitive; a marker
  beyond layer 1 or cap-ambiguity -> yield <source-url-redacted> for the URL segment. _sanitize_url in
  staging.py is NOT modified (059-S blast radius held).
- Same-sink coverage extended: sanitize_source_key now sanitizes github_repo (repo_url+branch+path_glob)
  and manifest_git (id+url+branch); manifest_local id marker-gated. local_file + manifest_local path
  stay byte-identical.
- Invariants: make_job_id hashes raw build_source_key(config) (determinism); _CREDENTIAL_PARAM_PREFIXES
  NOT expanded (06A59B1D deferred).

## Task restructure (2-hour rule)
- 072.001-T (Size S, Complexity high): core helper + R8 primitive + fail-closed url wrapper + URL guard
  + crawl coverage.
- 072.004-T (NEW; Size S, Complexity medium): github_repo + manifest_git + manifest_local id coverage;
  depends on 072.001-T.
- 072.002-T: +double-encoded & git-variant regressions; now depends on 072.001-T AND 072.004-T.
- 072.003-T: wiring unchanged; R8 label.

## Stash reconciliation
79BF0AEC (github_repo deferral) demonstrably SUBSUMED by the R8 same-sink contract -> archived via
`backlogit stash archive 79BF0AEC` (tombstone in .backlogit/archive/stash.jsonl; active stash 28 -> 27).
Verified vs HEAD: only 79BF0AEC removed; 0F1A653C & 06A59B1D changed ONLY in created_at (the preserved
unrelated timestamp-normalization working-copy hunks) -- preserved byte-for-byte and EXCLUDED from the
fix commit (staged blob = HEAD minus 79BF0AEC line via git plumbing). 0F1A653C (string-arg default-fetch
sink) and 06A59B1D (vocabulary expansion) remain active deferrals -- genuinely distinct, not subsumed.

## Artifacts changed
plan (frontmatter R8, Requirements Trace, Unit 1 detection + pass-through, Unit 2 c5, Decisions, Risks,
caveat, new Cycle-5/R8 section incl. source-fact audit table), decision (Option B R8 refinement, Chosen
Direction, Done Looks Like, P-021 Deferral Watch github_repo reconciled), 072-F, 072.001-T, 072.002-T,
072.003-T, NEW 072.004-T, .backlogit/archive/stash.jsonl (79BF0AEC tombstone), this memory.

## Validation
backlogit sync OK; doctor reviewed; markdown/frontmatter integrity (balanced fences, valid YAML,
consistent tables); empirical decode-semantics check (parse_qsl/unquote layering); independent
correctness+security review verdict recorded in the plan Cycle-5/R8 section.

## Boundaries held
No product source changed (read-only source audit only). 063-S remains queued/unclaimed. No push, no PR
reply, no thread resolve, no shipment claim/status change. Commit on chore/stage-194-copilot-remediation.

## Ready replies (post after human pushes the new SHA; Stage does NOT reply/resolve)
- PRRT_kwDOSsAX4c6h1D4t (ManifestGitSource): Fixed in R8. Source-fact audit confirmed manifest_git and
  github_repo reach the same _execute_single_source sinks via _fetch_github, so both are now sanitized
  by the typed-config helper (new task 072.004-T); the former 79BF0AEC github_repo deferral is
  reconciled/archived as subsumed. See plan Cycle-5/R8 section + decision R8 refinement.
- PRRT_kwDOSsAX4c6h1D4y (double-encoding): Fixed in R8. Detection now uses a bounded multi-layer unquote
  decode (fixed point or _MAX_CREDENTIAL_DECODE_LAYERS=5) matching a marker at ANY layer and failing
  closed at the cap, so srcA?%2574oken=IDSECRET is surgically redacted (srcA?%2574oken=<redacted>),
  IDSECRET absent from metadata.source and the ERROR log on both id and url paths; tasks/decision/
  integration regressions updated (072.001-T/072.004-T/072.002-T).
