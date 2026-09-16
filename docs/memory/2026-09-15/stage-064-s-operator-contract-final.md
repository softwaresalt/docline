# Stage session memory — 064-S/073-F FINAL operator contract rewrite

**Date:** 2026-09-15
**Agent:** Stage (route: claude-opus-4.8 / anthropic / high)
**Branch:** chore/stage-064-s
**Operator directive:** "Make it so" — execute the FINAL Stage-owned planning/backlog
rewrite for shipment 064-S / feature 073-F under an authoritative product contract
that supersedes all earlier remediation language.
**ActionRisk:** high (operator-approved requirements-correction + planning work).
Merge/admin preauthorization remain false. No destructive deletion.

## Authoritative product contract (supersedes all prior remediation language)

Docline redacts ONLY structured source-access credentials from Docline-generated
metadata/stdout/log/warning/error output:
1. URL user-info;
2. query parameter NAMES in an explicit, case-insensitive recognized credential
   vocabulary;
3. typed configuration fields explicitly designated secret.

Docline MUST NOT inspect/classify/redact/rewrite source-document body content, MUST
NOT redact/decode ordinary URL paths, and MUST NOT interpret provenance identifiers
(branches, path globs, manifest IDs, local paths, include patterns) as credential
structures — they are preserved byte-for-byte even if they contain text like
`?token=`. Benign query parameters and provenance are preserved.

## Findings resolved (1–10)

1. Replaced all legacy query-name `startswith` heuristics with an explicit
   case-insensitive EXACT-match credential-name vocabulary; enumerated legacy/cloud
   variants; added benign-preservation coverage for tokenizer, keynote, secretary,
   authorship, signal, password_policy, pwd_length, client_secretary, codec,
   code_version, passwd_file, refresh_token_ttl, and case variants
   (073.003-T / 073.004-T).
2. Bounded decode of QUERY-PARAMETER NAMES ONLY on BOTH string and typed sanitizer
   paths: re-check vocabulary after each layer, max 5 layers, fail closed past the cap;
   coverage for `%70assword`, `%2570assword`, deeper valid layers, over-cap; NO path or
   value decode (073.003-T / 073.004-T).
3. Typed sanitization redesign: URL fields + explicitly-secret typed fields sanitized;
   branch/path_glob/manifest ID/local path/include byte-preserved
   (073.001-T characterization / 073.002-T code).
4. Replaced `sanitized_source=None` whole-key sentinel: compound-key omission RAISES a
   typed, non-leaking exception (str() must not echo the raw key); parameter made
   keyword-only; bare-URL compatibility retained only where it preserves paths and
   sanitizes structured userinfo/query credentials (073.002-T).
5. Final live default-stdout composition gate proving A2+B2 for userinfo and ALL
   recognized new names across applicable URL-bearing source kinds. Added new test task
   073.009-T (test-first) that BLOCKS both code tasks (073.002-T, 073.004-T) so the DAG
   stays satisfiable; 073.007-T/073.008-T honestly describe their subset scope.
6. LocalFileSource/ManifestLocalSource matrix corrected: local paths/includes preserved;
   manifest IDs preserved under this contract.
7. Stale active-looking path/C1/C2/H2/three-stream/obsolete rollback/verification
   instructions removed or marked HISTORICAL/REJECTED; the current executable plan has
   exactly two streams and no path/document-content behavior.
8. Handoff corrected: Stage owns and COMMITS its own planning/backlog artifacts;
   Orchestrator only coordinates review/remote staging gate/Ship. Removed every
   Orchestrator-commits-Stage-artifacts instruction.
9. Minor audit inconsistencies corrected (three retired stream-C edges, manifest
   description, current rollback boundaries, current verification backbone).
10. Rejected 073.005-T/073.006-T retained non-destructively as status=blocked, outside
    064-S; no ambiguous executable wording in active sections.

## IDs changed

- **Created:** 073.009-T (final A2+B2 live default-stdout composition gate; Size: S |
  Complexity: low; leaf test task).
- **Edges added:** 073.002-T depends-on 073.009-T; 073.004-T depends-on 073.009-T
  (type=blocks).
- **Edited task bodies:** 073.001-T, 073.002-T, 073.003-T, 073.004-T, 073.007-T,
  073.008-T (note), 073.009-T.
- **Feature:** 073-F description + Operator-Decision Revision FINAL note.
- **Shipment:** 064-S manifest 7 → 8 items; description/Items/handoff prose.
- **Plan / deliberation:** FINAL Operator Contract top blocks + surgical active-section
  reconciliation.
- **Retired (unchanged, non-destructive):** 073.005-T, 073.006-T (status=blocked, no
  edges, out of shipment).

## Final DAG (acyclic, test-first)

- Leaves: 073.001-T, 073.003-T, 073.007-T, 073.008-T, 073.009-T
- 073.002-T ← {073.001-T, 073.007-T, 073.009-T}
- 073.004-T ← {073.003-T, 073.008-T, 073.009-T}
- Retired (out of DAG/shipment): 073.005-T, 073.006-T (blocked)

## Final manifest (064-S, 8 items, parent-first / dependency-ordered)

073-F, 073.001-T, 073.007-T, 073.009-T, 073.002-T, 073.003-T, 073.008-T, 073.004-T

## Handoff (Finding 8)

Stage committed its own final planning/backlog artifacts on chore/stage-064-s (no push).
Orchestrator next action: coordinate review → remote staging gate → hand shipment 064-S
to Ship. Orchestrator does NOT commit Stage artifacts, does not claim the shipment.

## Commit scope

Included: 064-S.md, 073-F.md, 073.001-T…073.009-T.md, plan, deliberation, scoped memory
(2026-09-14/stage-073 session + 2026-09-15/ 064-S records). Excluded (unrelated 063-S):
docs/memory/2026-09-13/, docs/memory/2026-09-14/063-s-bounded-extension-round8-9-checkpoint.md,
docs/memory/2026-09-14/063-s-pr200-copilot-review-rounds-complete.md.
