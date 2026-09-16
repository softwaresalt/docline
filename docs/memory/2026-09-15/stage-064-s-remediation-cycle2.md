# Stage remediation memory — 064-S / 073-F review-fix cycle 2 (FINAL)

**Date:** 2026-09-15
**Agent:** Stage (planning/decomposition; role boundary preserved — no code/test written, no build, no PR, no shipment claim, no Ship invocation)
**Branch:** chore/stage-064-s (single worktree; HEAD cdcf718 NOT amended; edits left uncommitted for Orchestrator review)
**Authorization:** DARK_MODE_ACTIVE scope = 064-S; merge-preauthorization = false; admin-fallback = false
**Trigger:** post-remediation adversarial re-review cycle 1 returned BLOCKED with 4 unique P1 + 5 P2/P3 findings. This is the FINAL allowed remediation cycle (plan-review-attempt 3; remediation-cycle 2).

## Outcome

All 4 P1 and all 5 P2/P3 findings resolved as same-contract-surface planning
completions under P-021 C1 (no scope expansion; no deferral of listed findings).
No genuinely different-contract issue surfaced; nothing new deferred. No in-scope
P1 remains open. Recommendation: **READY**.

## Findings dispositions (summary; full table in plan `## Remediation & Re-Review — cycle 2 (FINAL)`)

| # | Sev | Disposition |
|---|-----|-------------|
| 1 decode-before-segmentation path-secret grammar | P1 | PLANNING_CONTRACT_FIXED — authoritative H2-C2 grammar: malformed-escape pre-scan → fail-closed `<path-redacted>`; bounded decode cap (5 layers) → fail-closed on over-cap; segmentation on fully-decoded path with byte-span map; per-segment marker grammar preserving original encoded bytes; unmappable → fail-closed. Pinned outputs (`/token%2FSECRET`→`/token%2F<redacted>`, `%3D`, `%252F` double-encode, malformed `%2/`/`%ZZ`→`<path-redacted>`). `/token/` empty-adjacent → KEEP unchanged; `/token//SECRET`→`/token//<redacted>`. Reconciled across deliberation H2-C2 + plan Unit C1/C2 + 073.005-T/073.006-T ACs to one fail-closed output. |
| 2 source-kind × sink matrix overclaim | P1 | PLANNING_CONTRACT_FIXED — live SO (cli.py stdout) re-attributed to new integration task 073.007-T; live WE (WARNING/error on `_remove_credential_query_params`) re-attributed to new integration task 073.008-T. Helper/unit A1/B1 narrowed to helper level. EX (exception) left honestly n/a (063-S residuals 95BD0DC7/709BDB53 not claimed). Every stated invariant now backed by an executable test task; test-first deps preserved. |
| 3 benign case-varied near-match fixtures | P1 | PLANNING_CONTRACT_FIXED — added benign case-varied unchanged-output rows for `passwd` (`passwd_file`, case-varied) and `refresh_token` (`refresh_token_ttl`, case-varied) alongside existing names; deliberation H1 table + 073.003-T body. |
| 4 unqualified `FIXED` in planning-only records | P1 | PLANNING_CONTRACT_FIXED — requalified to `PLANNING_CONTRACT_FIXED` (contract/grammar completions) / `RESOLVED_IN_STAGING_ARTIFACTS` (provenance/record edits) across plan cycle-1 table + cycle-1 memory. Stage writes no code, so unqualified FIXED misleads. |
| 5 job-ID oracle accepted-risk record | P2 | DECIDED — H4-C2 expanded: preimage-resistance alone insufficient for low-entropy `password`/`code` (offline dictionary confirmation feasible). Added exposure assumptions (local-only digest leak), why compatibility still wins (determinism/cache-migration/collision), and explicit rollback/revisit trigger (remote emission / high-value low-entropy class / threat-model reclassification). Decision unchanged (accepted residual); justification corrected. |
| 6 Constitution Check | P2 | PLANNING_CONTRACT_FIXED — added `## Constitution Check` to plan mapping principles I–XI: applicable, non-applicable (XI Merge History Preservation n/a to Stage — Ship owns merge/P-009), and sole justified residual (H4 job_id oracle). |
| 7 stale provenance | P3 | RESOLVED_IN_STAGING_ARTIFACTS — stage-073 session memory corrected to PR #199 implementation / PR #200 closure. |
| 8 stream-B task titles overscoped | P2 | PLANNING_CONTRACT_FIXED — 073.003-T → "Add tests for expanded credential query-param name matching"; 073.004-T → "Expand credential query-param name vocabulary and matching". Path-secret scope belongs only to stream C. Feature/shipment/plan references reconciled. |
| 9 exact `/token/` behavior | P3 | PLANNING_CONTRACT_FIXED — defined in H2-C2 + Unit C1/C2 + 073.005-T/073.006-T: redaction requires a NON-EMPTY adjacent value; `/token/` (empty adjacent) → fail-closed KEEP unchanged. |

## Backlog changes

* Created (untracked): 073.007-T (stream A live-stdout integration test; S/low; high priority; no deps),
  073.008-T (stream B live-WARNING new-names integration test; S/low; medium priority; no deps).
  Both characterization-first, under 073-F, 2-hour/width-isolation compliant, ≥1 AC each.
* Updated: 073.001-T–073.006-T, 073-F (feature description: query-name-only stream B, integration tasks, cycle-2 note), 064-S (manifest).
* Renamed (finding #8): 073.003-T, 073.004-T titles → query-param-name-only scope.
* Dependency edges (acyclic, test-first) — 6 total, verified via `dep list`:
  * 073.002-T → {073.001-T, 073.007-T}
  * 073.004-T → {073.003-T, 073.008-T}
  * 073.006-T → {073.004-T, 073.005-T}
  * 073.001-T, 073.003-T, 073.005-T, 073.007-T, 073.008-T: no deps
* Shipment 064-S: 9-item parent-first dependency-ordered manifest
  (073-F, 073.001-T, 073.007-T, 073.002-T, 073.003-T, 073.008-T, 073.004-T, 073.005-T, 073.006-T); status queued.

## Preserved prior remediations (verified intact)

Strict-safety (ActionRisk high / dark-factory approval / merge+admin false / rollback),
keyword-only fail-closed sanitized_source API (H3), template body, exact-name matching (H1 startswith→exact),
link fixes, archived-stash lineage (0F1A653C/06A59B1D), reviewer-degradation markers, branch/worktree topology,
and genuine-dependency remediation (artificial 073.004-T→073.002-T stays removed; genuine 073.006-T→073.004-T kept).

## Validation

* `backlogit sync` OK (534 artifacts indexed; +2 new tasks vs. cycle 1's 532).
* Dependency graph ACYCLIC (DFS three-color) — 6 edges; manifest parent-first/dep-order VALID (topological check).
* Shipment 064-S: 9-item parent-first manifest verified via `shipment get`.
* `backlogit doctor` (--check-orphans --check-duplicates): 168 findings, ALL pre-existing unrelated
  `archived_from_self_ref` on 001–010 archives; ZERO for 064-S/073-F/073.00x-T; no orphans/duplicates in scope.
* markdownlint-cli2 (.markdownlint.json: MD001/MD025/MD041): 0 issues across changed docs + all 10 changed/new queue files.
* P-003 chain: all 8 tasks have parent=073-F, ≥1 acceptance criterion, plan reference, and Size|Complexity.

## Preserved (untouched)

* Untracked 063-S memory: docs/memory/2026-09-13/, docs/memory/2026-09-14/063-s-bounded-extension-round8-9-checkpoint.md.
* No source/test/config code modified. Commit cdcf718 not amended; nothing committed; remediation left uncommitted.

## Next action for Orchestrator

Review the uncommitted cycle-2 staging edits and commit on chore/stage-064-s (Stage did not commit).
Shipment 064-S remains queued with a complete 9-item parent-first manifest and is ready to hand to Ship
after commit. No in-scope P1 remains deferred. Readiness: **READY**.
