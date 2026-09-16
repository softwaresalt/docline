---
title: "Stage 064-S / 073-F final correction — P0 green-gate merge"
date: "2026-09-15"
agent: "stage"
shipment: "064-S"
feature: "073-F"
branch: "chore/stage-064-s"
status: "current-authoritative"
commit_ownership: "stage"
supersedes:
  - "docs/memory/2026-09-15/stage-064-s-operator-scope-correction.md"
  - "docs/memory/2026-09-15/stage-064-s-operator-contract-final.md"
  - "docs/memory/2026-09-15/stage-064-s-remediation-cycle1.md"
  - "docs/memory/2026-09-15/stage-064-s-remediation-cycle2.md"
  - "docs/memory/2026-09-15/stage-064-s-remediation-cycle3.md"
  - "docs/memory/2026-09-15/064-s-dark-factory-review-cap-halt.md"
authorization: "DARK_MODE_ACTIVE scope=064-S; merge-preauthorization=false; admin-fallback=false"
role_boundary: "Stage (planning/decomposition) — no production/test code, no build, no PR, no push, no shipment claim, no Ship invocation"
manifest_items: 7
retired_ids:
  - "073.004-T (merged into 073.002-T; status=blocked; edges removed; out of manifest; retained non-destructively)"
  - "073.005-T (stream C REJECTED; status=blocked; out of manifest; retained non-destructively)"
  - "073.006-T (stream C REJECTED; status=blocked; out of manifest; retained non-destructively)"
---

# Stage 064-S / 073-F final correction — P0 green-gate merge

**Agent:** Stage (planning/decomposition; role boundary preserved — no code/test written,
no build, no PR, no push, no shipment claim, no Ship invocation).
**Branch:** `chore/stage-064-s` (single worktree). Work based on committed HEAD `3317de3`.
**Handoff (authoritative — Finding 8):** Stage OWNS and COMMITS its own planning/backlog/
memory artifacts on `chore/stage-064-s`. The Orchestrator does NOT commit Stage artifacts;
it only coordinates review, the remote staging gate, and the Ship handoff. It does not
claim the shipment.

## Trigger

Final adversarial review found a P0 green-gate flaw: two separate production code tasks
(073.002-T stream-A sink wiring, 073.004-T stream-B vocabulary/decode) each fed the shared
final composition test 073.009-T, which could only go GREEN after BOTH landed. Under the
repository's test-first / per-task-green rules (P-002/P-004) every task must reach an atomic
verifiable green state on its own, so no single code task could satisfy the composition gate
— a hard invariant violation.

## P0 fix — single atomic production task

- **Merged** former code tasks 073.002-T (A2 typed sink wiring) and 073.004-T (B2 exact-match
  vocabulary + bounded query-NAME decode) into ONE atomic production task, **073.002-T**
  (survivor). It implements BOTH concerns across `staging.py`, `orchestrate.py`, and
  `src/docline/elt/source_keys.py`, plus typed-sanitizer preservation of non-credential
  provenance (branch / path_glob / manifest ID / local path / include) while sanitizing URL
  fields and typed secret fields only.
- **Retired 073.004-T non-destructively**: status=blocked, all dependency edges removed,
  removed from shipment 064-S manifest, RETIRED banner + `superseded`/`merged` labels. NOT
  deleted.
- The 2-hour / width granularity rule YIELDS to the stronger per-task-green invariant here;
  the merged task remains a single cohesive credential-redaction domain. Documented as a
  justified, operator-mandated deviation. Size: M | Complexity: medium.

## Final executable DAG (test-first only; acyclic; parent-first shipment)

```text
073.001-T ──blocks──> 073.002-T   (concern A helper test → merged code)
073.003-T ──blocks──> 073.002-T   (concern B helper test → merged code)
073.007-T ──blocks──> 073.002-T   (concern A live-stdout userinfo subset → merged code)
073.008-T ──blocks──> 073.002-T   (concern B live-WARNING new-name subset → merged code)
073.009-T ──blocks──> 073.002-T   (final A2+B2 live composition gate → merged code)
```

- Leaves (red on HEAD, no upstream deps): 073.001-T, 073.003-T, 073.007-T, 073.008-T, 073.009-T.
- 073.002-T is the SINGLE MERGED production task; all five test tasks go GREEN together in one
  atomic verifiable step when it completes. Acyclic; every edge a genuine test-first prerequisite.

## Final shipment manifest (064-S) — 7 items, parent-first, queued, unclaimed

1. 073-F (covering feature)
2. 073.001-T (concern A helper test — includes LocalFileSource / ManifestLocalSource preservation fixtures)
3. 073.003-T (concern B helper test — exact-match vocabulary + bounded query-name decode + benign prefix fixtures)
4. 073.007-T (concern A live-stdout userinfo subset)
5. 073.008-T (concern B live-WARNING new-name subset)
6. 073.009-T (final A2+B2 live default-stdout composition gate)
7. 073.002-T (SINGLE MERGED production task — depends on all five test tasks)

## Credential query-param NAME vocabulary (Finding 7 — honest, not universally complete)

- Legacy/cloud names preserved by INDIVIDUAL enumeration (no `startswith` heuristic):
  `token`, `access_token`, `api_key`, `key`, `secret`, `auth`, `sig`, `signature`,
  `authorization`, `auth_token`, and the cloud presign names
  `x-amz-credential`, `x-amz-signature`, `x-amz-security-token`, `x-goog-signature`.
- Net-new recognized names added: `refresh_token`, `apikey`, `client_secret`,
  `x-goog-credential`, `awsaccesskeyid`, plus the FINAL-contract additions
  `password`, `pwd`, `passwd`, `code`.
- Case-insensitive EXACT match. NOT universally complete: suffixed/variant spellings
  (e.g. `token_v2`, `access_token2`, `my_api_key`) are intentionally NOT redacted and are
  recorded as an accepted residual; benign prefix-preservation fixtures assert this boundary.
  Unknown names are intentionally not redacted absent explicit product support.

## Residual risk (retained, accepted)

- **Job-ID oracle** remains an explicit accepted residual. Release-observability is now aligned:
  a concrete post-release credential-safe **synthetic observation window** and **rollback
  trigger** are defined in the plan (no raw secrets logged; synthetic fixtures only).

## Validations

- `backlogit sync` — OK (index reindexed).
- `backlogit doctor` — 168 pre-existing issues, ZERO referencing 073/064 (no new orphans /
  dangling edges introduced by this correction).
- Manifest membership/status — 064-S queued, unclaimed, 7 items, parent-first (feature → tests → code).
- DAG — acyclic; per-task green satisfiable (whole suite greens on single merged code task).
- No active path/document-content redaction requirements remain in executable artifacts
  (all path-secret / stream-C references are REJECTED/retired/historical).
- No stale Orchestrator-commit INSTRUCTION remains active (all reversed per Finding 8 or
  enclosed in superseding banners).
- Markdown/template lint — see `backlogit docs lint` run; new/edited memory frontmatter valid.
- Stage-local review — zero unresolved P0/P1 (verdict recorded in session summary).

## Orchestrator next step

Coordinate review → remote staging gate → hand shipment 064-S to Ship. The Orchestrator does
NOT commit Stage artifacts (Stage owns/commits them) and does NOT claim the shipment. Ship
claims 064-S and executes the test-first DAG (five red test tasks first, then the single
merged production task 073.002-T greens the suite).
