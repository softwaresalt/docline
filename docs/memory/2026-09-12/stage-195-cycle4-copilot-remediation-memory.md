---
title: "Stage session -- PR #195 Copilot remediation cycle 4 (063-S staging, R6 malformed-id contract)"
date: 2026-09-12
agent: stage
session_id: stage-195-copilot-cycle4-2026-09-12
phase: complete
mode: report-to-Orchestrator (Stage boundary; shipment 063-S NOT claimed/started/status-changed)
---

# Stage session memory -- PR #195 Copilot remediation cycle 4 (R6 malformed-id contract)

## Scope
Stage-owned cycle-4 remediation of PR #195, feature 072-F / shipment 063-S staging artifacts only,
under explicit operator authorization extending the prior review-fix cycle limit. Strictly
staging/backlog/plan/decision/memory artifacts. No product source (`src/`). No push/merge/reply/
resolve. Shipment 063-S untouched (queued, not claimed/started/status-changed). Single branch
`chore/stage-194-copilot-remediation`, single worktree. Dirty `.backlogit/stash.jsonl` (3-line
timestamp-normalization diff) preserved byte-for-byte (SHA256
3920DCA85D587C0EA35D04E9B04F5B101D30636E4783A735BC9F60E388B4EA22) and excluded from the commit.

## Live GitHub inventory (fully paginated, authoritative)
- PR #195 OPEN, base main, head branch `chore/stage-194-copilot-remediation`, HEAD
  31547a493f7585b453ce25627b0b09bf6644bb67, mergeStateStatus BLOCKED, mergeable MERGEABLE.
- Copilot GraphQL login: `copilot-pull-request-reviewer`.
- reviewThreads: 13 nodes, hasNextPage false. Exactly THREE unresolved Copilot-authored threads;
  no new threads beyond the Orchestrator snapshot. All three are C1 same-contract-surface (operator
  authorized as must-fix, not deferrable); no genuinely new out-of-scope thread, so no P-021 C2
  capture required this cycle.
  1. PRRT_kwDOSsAX4c6h0rxB, comment db 3998020691, `.backlogit/queue/072.001-T.md:18`,
     https://github.com/softwaresalt/docline/pull/195#discussion_r3998020691
  2. PRRT_kwDOSsAX4c6h0rxI, comment db 3998020702,
     `docs/decisions/2026-09-12-source-key-credential-sanitization.md`,
     https://github.com/softwaresalt/docline/pull/195#discussion_r3998020702
  3. PRRT_kwDOSsAX4c6h0rxY, comment db 3998020722,
     `docs/plans/2026-09-12-source-key-credential-sanitization-plan.md`,
     https://github.com/softwaresalt/docline/pull/195#discussion_r3998020722

## Root cause (single contract inconsistency across 3 artifacts)
The R6 refinement conflated TWO distinct sanitizer paths:
- URL path (`config.url` via `sanitize_source()`/`_sanitize_url()`): DOES parse `parsed.port`, raises
  ValueError on a malformed URL, so it is wrapped fail-closed to `<source-url-redacted>`. CORRECT.
- ID path (`sanitize_source_id()`): MARKER-GATED, pure regex, does NOT parse ports.
The stale acceptance criteria / test sentinel wrongly claimed a malformed URL-shaped credential-
bearing id (`https://<userinfo>@host:notaport?token=IDSECRET`) FAILS CLOSED to `<source-id-redacted>`
"via port parsing". Under the marker-gated contract the token fragment is surgically redactable and
the malformed port is irrelevant (never parsed), so the correct result is SURGICAL redaction, not
the sentinel.

## Resolution (coherent R6 contract, now uniform across all surfaces)
- credential-free id of ANY shape (incl. malformed URL-shaped `https://host:notaport`) -> VERBATIM
  byte-for-byte.
- marker-bearing id -> SURGICALLY redacted: `https://<userinfo>@host:notaport?token=IDSECRET` ->
  `https://host:notaport?token=<redacted>` (userinfo stripped, token redacted, malformed `:notaport`
  preserved, no port parse, no ValueError).
- `<source-id-redacted>` reserved ONLY for a marker-bearing id whose surgical redaction cannot
  complete -- never for a credential-free or merely-malformed id.
- url path unchanged: malformed `config.url` -> `<source-url-redacted>` (wrapped fail-closed).
- `make_job_id` still hashes RAW `build_source_key(config)` (determinism invariant preserved).
- vocabulary-expansion deferral 06A59B1D untouched.

## Edits applied (8 sub-edits across 3 Stage-owned artifacts; prose only, no frontmatter/IDs/refs)
- `.backlogit/queue/072.001-T.md`: criterion (2)(c) malformed-id -> surgical result; added (f)
  credential-free malformed URL-shaped `https://host:notaport` verbatim case; descriptor -> "MALFORMED
  URL-shaped".
- `docs/decisions/...-sanitization.md`: Chosen Direction R6 paragraph + Done-Looks-Like bullet
  narrowed to distinguish url-path vs id-path fail-closed and reserve the id sentinel for the genuine
  trigger.
- `docs/plans/...-plan.md`: Unit 1 test scenario (c) -> surgical + (f) verbatim case; design/rationale
  bullet narrowed; R6 cycle-3 "Regression scenarios added" line corrected from "fails closed to the
  sentinel" to surgical redaction.

## Audit of other R6 surfaces (operator-requested)
- Feature `072-F`: CLEAN -- ties sentinel to "marker-bearing input it cannot surgically redact";
  "a malformed credentialed id never leaks or raises" is correct.
- Task `072.002-T`: CLEAN -- its malformed case is the URL path (no sanitizer ValueError escaping).
- Task `072.003-T`: CLEAN -- only wires sinks, no malformed-id expectation.
- Correct/genuine-trigger `<source-id-redacted>` mentions retained at decision:121, plan:78/186/304/588.
- Prior-cycle memory (cycle3) left as historical record (not rewritten).

## Validations
- markdownlint (config MD001/MD025/MD041): the 3 edited files show 2 MD025 errors on decision:17 /
  plan:12 (frontmatter-title vs H1 interaction). CONFIRMED PRE-EXISTING on HEAD (same 2 errors on
  unmodified `git show HEAD:` versions); on untouched heading lines; OUT OF SCOPE for R6 -- not fixed.
- `backlogit sync`: OK, 509 artifacts indexed, 0 parse failures.
- `backlogit doctor`: 168 pre-existing backlog-wide hygiene issues (archive/orphan), ZERO in the 072-*
  scope -- no integrity regression from these prose edits.
- Independent Correctness Reviewer (targeted, this diff): CLEAN, zero high-confidence findings; all 5
  consistency checks + sibling-file scan pass.
- Dirty `.backlogit/stash.jsonl` hash unchanged post-edit; excluded from commit.

## Handoff to Ship (Stage did NOT reply/resolve)
Ready substantive replies for all three live unresolved threads are in the session report. Ship owns
posting replies, resolving threads, and any push. Commit created on `chore/stage-194-copilot-
remediation`; not pushed. Shipment 063-S remains queued/unclaimed.
