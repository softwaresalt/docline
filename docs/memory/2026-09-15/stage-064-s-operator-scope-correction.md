---
title: "064-S / 073-F operator scope correction — path redaction rejected"
date: "2026-09-15"
agent: "stage"
shipment: "064-S"
feature: "073-F"
branch: "chore/stage-064-s"
status: "superseded"
superseded_by: "docs/memory/2026-09-15/stage-064-s-final-correction-merge.md"
superseded_reason: "P0 green-gate fix: the two code tasks 073.002-T+073.004-T were merged into one atomic production task 073.002-T; manifest is now 7 items; Stage owns and commits its own artifacts (no Orchestrator commit)."
commit_ownership: "stage"
---

> **SUPERSEDED (2026-09-15 final correction).** Two facts recorded below are now stale
> and are corrected by `docs/memory/2026-09-15/stage-064-s-final-correction-merge.md`:
> (1) the manifest/DAG below shows TWO code tasks (073.002-T + 073.004-T) — they are now
> MERGED into the SINGLE production task 073.002-T (073.004-T retired/merged, out of
> manifest, edges removed), so the manifest is 7 items and 073.002-T depends on all five
> test tasks; (2) any "pending Orchestrator commit" / "Orchestrator to commit" language
> is REVERSED — Stage OWNS and COMMITS its own planning/backlog/memory artifacts on
> `chore/stage-064-s`; the Orchestrator only coordinates review, the remote staging gate,
> and the Ship handoff. The scope-correction decision itself (path redaction REJECTED)
> remains authoritative.

# Stage session — 064-S / 073-F operator-directed scope correction

**Role boundary preserved:** planning/backlog/artifact edits only. No production or
test code written, no build/test run, no shipment claimed, no PR created, no Ship
invocation. Stage COMMITS its own planning/backlog/memory artifacts on
`chore/stage-064-s` (does not push, does not claim the shipment).

## Authoritative operator decision

Docline's credential-redaction responsibility is narrowed to **structured access
credentials** supplied to connect to a source: URL user-info, explicitly recognized
credential query parameters, and typed config fields designated secret. These MUST NOT
appear in Docline-generated metadata, stdout/logs, warnings, or errors. Docline MUST
NOT scan/interpret/rewrite source-document content for secrets, and ordinary URL paths
(source identifiers/content locations) MUST remain byte-for-byte unchanged. Path-secret
detection/redaction is REJECTED as an upstream DLP concern. Benign URL/query/path/
provenance data is preserved. This supersedes the path-redaction requirements added
during review remediation cycles 1–3.

## REJECTED alternatives (recorded)

1. Arbitrary path-embedded secret redaction in `_sanitize_url` (former stream C /
   Units C1-C2 / H2 / H2-C2 decode-before-segmentation grammar; tasks
   073.005-T/073.006-T) — REJECTED (upstream DLP scope; over-redacts benign paths;
   rejects literal `%25`; created an unsatisfiable milestone). Retired
   non-destructively.
2. Source-document body/content scanning for secrets — REJECTED (upstream DLP).

## Changed / retired IDs

| ID | Change |
|---|---|
| 073.005-T | RETIRED — status=blocked (shipment return-blocked); removed from 064-S; labels +rejected/+superseded; REJECTED banner prepended |
| 073.006-T | RETIRED — status=blocked; removed from 064-S; 3 dependency edges removed; labels +rejected/+superseded; REJECTED banner prepended |
| 073.007-T | NARROWED — path-secret fixture + 073.006-T coupling removed; asserts structured-credential absence + benign-path byte-for-byte preservation; fully satisfied by 073.002-T |
| 073.002-T | AC6 clarified: fully satisfies 073.007-T; benign paths preserved; no stream-C task needed |
| 073.001-T | AC added: ordinary paths unchanged in in-memory metadata.source |
| 073.008-T | AC added: scope = structured access credentials only (no path assertion) |
| 073-F | description: two executable streams; stream C rejected/retired; Operator-Decision Revision section |
| 064-S | description + items: 7-item manifest; stream C rejected; operator-decision note |
| plan | top Operator-Decision Revision + REJECTED alternatives; rebuilt DAG; Units C1/C2 retired, AI narrowed; criteria/matrix/trace reconciled |
| deliberation | top Operator-Decision Revision; invariant 1 reframed; work-stream C rejected; H2/H2-C2/H5 marked historical |
| halt memory | Operator-Decision Resolution section; three P1 blockers cleared; status updated |

## Final shipment 064-S manifest (queued, unclaimed, parent-first, 7 items)

```
073-F (covering feature)
├─ 073.001-T (A helper test)
├─ 073.007-T (A live-stdout integration test)   ── blocks ─▶ 073.002-T (A code)
├─ 073.003-T (B helper test)
├─ 073.008-T (B live-WARNING integration test)  ── blocks ─▶ 073.004-T (B code)
```

## Dependency edges (test-first only; acyclic)

* 073.002-T → 073.001-T (blocks)
* 073.002-T → 073.007-T (blocks)
* 073.004-T → 073.003-T (blocks)
* 073.004-T → 073.008-T (blocks)
* (removed) 073.006-T → 073.005-T / 073.004-T / 073.007-T

## Three cycle-3 P1 blockers — resolved by REMOVING path work

1. Unsatisfiable 073.002-T↔073.007-T path milestone → removed path-secret fixture + coupling.
2. Benign-path over-redaction → path redaction removed; benign paths asserted preserved.
3. Literal-percent (`%25`) rejection → path percent-decoding removed.

## Retained residual risk

H4/H4-C2 job-ID confirmation-oracle STILL APPLIES (raw `build_source_key` digest of
structured access credentials, incl. low-entropy query `code`/`password`). Decision
(accept) unchanged; keyed-construction-over-RAW-key revisit trigger stays coherent.

## Validation evidence

* backlogit sync OK; scoped doctor shows no NEW 073/064 issues (pre-existing
  archived_from_self_ref noise unchanged).
* Shipment 064-S: queued, unclaimed, 7-item parent-first manifest.
* DAG acyclic and test-first (4 edges).
* Literal search: no executable 064-S artifact (7 manifest items) requires
  path-secret/document-content redaction.
* Benign paths (`/authentication/overview`, `/tokenizer/config`, `/keys/rotation`,
  `/docs/100%25-off`) explicitly asserted preserved in 073.001-T/073.007-T.

## Final validation run (2026-09-15, end of session)

* `backlogit sync`: 534 artifacts, parse_failures=0.
* Scoped `backlogit doctor`: 168-issue pre-existing baseline unchanged; ZERO
  lines referencing 073/064 (no new orphans or dangling edges from this work).
* Literal token scan over the 7 executable manifest files + 064-S.md
  (`<path-redacted>`, `decode-before`, `percent-decod`, `PATHSECRET`,
  `path-embedded secret redaction`, `stream C`, `073.005/006`): every remaining
  hit is REJECTED/retired/exclusion context only — no ACTIVE requirement.
  Tightened residual stale phrasing in 073-F (cycle-3 F-02/F-04 marked
  SUPERSEDED/RETIRED), 073.003-T and 073.004-T (stream-C exclusions marked
  "REJECTED/retired") so no executable artifact reads as active path work.
* Markdown/frontmatter: `backlogit docs lint` = 488-violation repo-wide
  PRE-EXISTING baseline (closure/compound/all planning docs). New session-memory
  file lints CLEAN (0 violations); all 4 edited memory files = 0 violations.
  Plan (1) + deliberation (2) `required`-rule violations are pre-existing —
  git diff confirms edits are body-only (plan frontmatter closes at line 9;
  earliest change at line 11), YAML frontmatter untouched.
* Retired 073.005-T/073.006-T: status=blocked with descriptive blocked_reason;
  NOT deleted; NOT in shipment manifest; dependency edges removed.

## Next action for Orchestrator

Coordinate review of the Stage-committed edits on `chore/stage-064-s`, run the remote
staging gate, then hand shipment 064-S to Ship. Stage has COMMITTED its own
planning/backlog/memory artifacts (no push); the Orchestrator does NOT commit Stage
artifacts, does not claim the shipment, and does not build or invoke Ship.

## Readiness: READY (Stage-committed; superseded by the 2026-09-15 final-correction merge — see banner)
