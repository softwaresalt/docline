# Stage remediation memory — 064-S / 073-F review-fix cycle 3 (OPERATOR-AUTHORIZED EXCEPTIONAL)

> **SUPERSEDED (2026-09-15 operator scope correction).** This cycle-3 memory records
> the state BEFORE the operator's authoritative scope correction. Its "Readiness:
> READY" recommendation and its 9-item / 7-edge topology (with stream C intact) are
> NO LONGER CURRENT: stream C (path-embedded secret redaction, 073.005-T/073.006-T) is
> now REJECTED and retired, the manifest is 7 items, and the DAG is two test-first
> streams. See `064-s-dark-factory-review-cap-halt.md` → "Operator-Decision Resolution"
> and `stage-064-s-operator-scope-correction.md` for the current state.

**Date:** 2026-09-15
**Agent:** Stage (planning/decomposition; role boundary preserved — no code/test written, no build, no PR, no shipment claim, no Ship invocation)
**Branch:** chore/stage-064-s (single worktree; HEAD cdcf718 NOT amended; edits left uncommitted for Orchestrator review)
**Authorization:** DARK_MODE_ACTIVE scope = 064-S; merge-preauthorization = false; admin-fallback = false. **Operator explicitly authorized ONE additional bounded Stage correction/re-review cycle** beyond the normal 2-cycle budget (cycle 2 was the recorded FINAL cycle; the dark-factory run halted at the review cap per `064-s-dark-factory-review-cap-halt.md`).
**Trigger:** final-cycle adversarial review left four unresolved P1 planning defects (blocking findings 1–4) + one non-blocking residual. Operator chose the "one bounded correction pass" disposition.

## Outcome

All five final-cycle residuals resolved as same-contract-surface planning completions
under P-021 C1 (no scope expansion; no deferral). Scope held exactly to 064-S / 073-F.
No genuinely different-contract issue surfaced; nothing new deferred. No in-scope P1
remains open. Recommendation: **READY** (pending fresh current-HEAD review + commit by
Orchestrator; Stage did not commit).

## Findings dispositions (full tables in plan `## Remediation & Re-Review — cycle 3` and deliberation `## Remediation cycle 3`)

| # | Sev | Disposition |
|---|-----|-------------|
| F-01 A1/073.001-T live-stdout + source-kind overclaim | P1 | PLANNING_CONTRACT_FIXED — A1/073.001-T restricted to HELPER-level in-memory `metadata.source` + reconstructed `model_dump` JSON; live-stdout wording removed; live stdout kept SOLELY in 073.007-T; source kinds aligned exactly to the four AI/matrix use (web_crawl, manifest_url, github_repo, manifest_git); plan matrix SO column cites only AI/073.007-T (A1 reconstructed-JSON moved to the M column). |
| F-02 percent escapes validated only pre-first-decode | P1 | PLANNING_CONTRACT_FIXED — ITERATIVE malformed-escape validation before AND after every decode layer; pinned nested-malformed fail-closed rows `/token/%252`→`<path-redacted>` (`%252`→`%2`) and `/token/%25ZZ`→`<path-redacted>` (`%25ZZ`→`%ZZ`); bounded multilayer + over-cap consistent across deliberation H2-C2 (steps 1–2 + table), plan Unit C1/C2 + criterion 4, and 073.005-T/073.006-T ACs. |
| F-03 073.008-T does not exercise all four URL source kinds | P1 | PLANNING_CONTRACT_FIXED — 073.008-T + plan Unit BI exercise the live WARNING/error path for all four URL-bearing source kinds × six new names (4×6 parametrization; within 2-hour test-domain boundary). Matrix WE rows and the task now agree. |
| F-04 live-stdout path-secret cell only compositional | P1 | PLANNING_CONTRACT_FIXED — 073.007-T + plan Unit AI add a DIRECT path-embedded-secret fixture with exact secret-absence + `/token/<redacted>` assertions on the real `cli.py:381` stdout; matrix SO path-secret cell cites AI/073.007-T direct. Genuine test-first edge `073.006-T depends_on 073.007-T` added (data flow: `sanitize_source_key`→`_sanitize_url_field`→`sanitize_source`→`_sanitize_url`). Stream A code (073.002-T) stays DECOUPLED from stream C. |
| F-05 job-ID revisit uses HMAC over sanitized key | P3 | RESOLVED_IN_STAGING_ARTIFACTS — H4-C2 rollback/revisit trigger corrected to a keyed construction (HMAC) over the RAW canonical source key (`build_source_key(config)`) with explicit key-management + cache-migration requirements; HMAC-over-sanitized explicitly REJECTED because same-structure sources collide under the sanitized key. Decision (accept residual) unchanged; only the revisit trigger corrected. |

## Backlog changes (cycle 3)

* Updated (no items added/removed): 073.001-T (F-01), 073.005-T (F-02), 073.006-T (F-02 + F-04 dep + AC), 073.007-T (F-04 + F-01 split), 073.008-T (F-03), 073-F (description), 064-S (manifest note; membership unchanged, 9 items).
* Dependency edges (acyclic, test-first) — now 7 total:
  * 073.002-T → {073.001-T, 073.007-T}
  * 073.004-T → {073.003-T, 073.008-T}
  * 073.006-T → {073.004-T, 073.005-T, 073.007-T}  ← NEW edge 073.006-T→073.007-T (F-04, test-first for the direct path-secret fixture)
  * 073.001-T, 073.003-T, 073.005-T, 073.007-T, 073.008-T: no upstream deps
* Shipment 064-S: 9-item parent-first dependency-ordered manifest unchanged
  (073-F, 073.001-T, 073.007-T, 073.002-T, 073.003-T, 073.008-T, 073.004-T, 073.005-T, 073.006-T); status queued, unclaimed.

## Acyclicity proof for the new edge (F-04)

073.007-T has NO upstream deps (leaf test). Adding `073.006-T → 073.007-T` cannot form
a cycle: 073.007-T is only ever a target of dependency edges, never a source. The path
`073.002-T → 073.007-T` (userinfo/query milestone) and `073.006-T → 073.007-T`
(path-secret milestone) share the same leaf test but 073.002-T does NOT depend on
073.006-T or any stream-C/stream-B node, so stream A stays width-isolated.

## Preserved prior remediations (verified intact)

Strict-safety (ActionRisk high / dark-factory approval / merge+admin false / rollback),
keyword-only fail-closed sanitized_source API (H3), decode-before-segmentation grammar
(H2-C2), exact-name query matching (H1 exact-equality), Constitution Check, provenance
(PR #199 impl / #200 closure), archived-stash lineage (0F1A653C/06A59B1D), reviewer-degradation
markers, branch/worktree topology, genuine-dependency remediation (artificial
073.004-T→073.002-T stays removed; genuine 073.006-T→073.004-T kept). Cycle-1 and cycle-2
disposition tables retained verbatim as historical records.

## Preserved (untouched)

* Unrelated 063-S memory: docs/memory/2026-09-13/, docs/memory/2026-09-14/063-s-bounded-extension-round8-9-checkpoint.md, docs/memory/2026-09-14/063-s-pr200-copilot-review-rounds-complete.md.
* No source/test/config code modified. Commit cdcf718 not amended; nothing committed; remediation left uncommitted.

## Next action for Orchestrator

Review the uncommitted cycle-3 staging edits and commit on chore/stage-064-s (Stage did
not commit). Then run a fresh current-HEAD review. Shipment 064-S remains queued with a
complete 9-item parent-first manifest and is ready to hand to Ship after commit + merge +
remote-manifest gate. No in-scope P1 remains deferred. Readiness: **READY**.
