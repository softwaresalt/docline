---
title: "Stage session -- PR #195 Copilot remediation cycle 3 (063-S staging, R6)"
date: 2026-09-12
agent: stage
session_id: stage-195-copilot-cycle3-2026-09-12
phase: complete
mode: report-to-Orchestrator (Stage boundary; shipment 063-S NOT claimed/started/status-changed)
---

# Stage session memory -- PR #195 Copilot remediation cycle 3 (R6)

## Scope
Stage-owned cycle-3 remediation of PR #195, feature 072-F / shipment 063-S staging artifacts only.
Continues cycles 1-2 (R4/R5). Strictly staging/backlog/plan/decision/memory artifacts + the
same-contract-surface plan/decision/task text needed by the live findings. No product source. No
push/merge/reply/resolve. Shipment 063-S untouched (queued, not claimed/started/status-changed).
Single branch `chore/stage-194-copilot-remediation`, single worktree. Dirty `.backlogit/stash.jsonl`
(3-line timestamp-normalization diff) preserved byte-for-byte and excluded from the commit.

## Live GitHub inventory (fully paginated, authoritative)
- PR #195 OPEN, base main, head `chore/stage-194-copilot-remediation`, HEAD
  472a45f13b3f9ffc78b262c308c3c8776c134869, mergeStateStatus BLOCKED, mergeable MERGEABLE,
  reviewDecision empty. reviewThreads: 9 nodes, hasNextPage false.
- Copilot GraphQL login: `copilot-pull-request-reviewer`.
- Exactly TWO unresolved Copilot-authored threads (both on the R5 helper contract):
  1. thread PRRT_kwDOSsAX4c6h0dUG (isResolved false), comment db 3997932059,
     docs/plans/...-plan.md line 129,
     url https://github.com/softwaresalt/docline/pull/195#discussion_r3997932059 --
     `sanitize_source()` not total: `_sanitize_url()` reads `parsed.port`, raises ValueError on
     malformed URL (`https://host:notaport`); helper called before fetch try + in exception logger
     would crash `_execute_single_source` or mask the fetch failure. Require fail-closed, no-raise +
     regression.
  2. thread PRRT_kwDOSsAX4c6h0dUO (isResolved false), comment db 3997932072,
     docs/plans/...-plan.md line 142,
     url https://github.com/softwaresalt/docline/pull/195#discussion_r3997932072 --
     byte-preservation guarantee conflicts with routing id through `sanitize_source()` (rewrites
     absolute-path/`file://` to `<local-path-redacted>`, drops fragments); define
     `sanitize_source_id()` to return credential-free id verbatim or narrow the guarantee.
- No new unresolved Copilot threads beyond Ship's snapshot; the 7 other threads are resolved.

## P-021 C1 classification + disposition
- BOTH IN SCOPE (same-contract-surface findings on Stage-owned planning artifacts;
  `sanitize_source_id` / `sanitize_source_key` contract for 072-F/063-S). Fixed in-cycle; NEITHER
  deferred; no P-021 C2 capture required. No `DEFERRED SCOPE EXPANSION` markers involved; no
  late-identifier reconciliation triggered.
- Premises verified against source (staging.py): `_sanitize_url` reads `parsed.port` (can raise
  ValueError); `sanitize_source` rewrites absolute-path/`file://` -> `<local-path-redacted>` and
  drops fragments. Both reviewer findings are correct.

## R6 contract (the fix, design only -- no code written)
- `sanitize_source_key(config)` is TOTAL / fail-closed: the `config.url` sanitize is wrapped so a
  ValueError from `_sanitize_url`'s `parsed.port` yields `<source-url-redacted>` instead of
  propagating. Safe to call at pre-`try` metadata build and inside the exception logger.
- `sanitize_source_id(raw_id: str) -> str` is TOTAL, non-throwing, MARKER-GATED; no longer delegates
  to `sanitize_source()`. Non-throwing marker scan (userinfo + `_CREDENTIAL_PARAM_PREFIXES` key=value
  fragments, vocabulary NOT expanded); no marker -> verbatim byte-for-byte (any shape: absolute path,
  `file://`, fragment-bearing URL); marker present -> surgical regex redaction; marker present but
  unredactable -> FAIL CLOSED to `<source-id-redacted>`.
- Invariant preserved: `make_job_id` still hashes the RAW `build_source_key(config)`.
- Regression scenarios added (Unit 1 unit + Unit 2 integration): malformed url no-raise + redacted;
  malformed credential id fail-closed; credential-free `/source-a` and `https://host/x#frag`
  verbatim; integration malformed-credential config does not crash / mask, credential absent from
  `caplog.text` + `metadata.json`.

## Artifacts changed this cycle (Stage-owned only)
- docs/plans/2026-09-12-source-key-credential-sanitization-plan.md (frontmatter R5->R6; R6 revision
  note; Requirements Trace +2 rows / refined id row; Unit 1 changes + tests; Unit 2 (c3); Risks;
  Decisions rationale; new Cycle 3 (R6) section).
- docs/decisions/2026-09-12-source-key-credential-sanitization.md (Option B heading R6; R6 refinement
  paragraph; Chosen Direction R6; Done Looks Like R6 bullet).
- .backlogit/queue/072-F.md, 072.001-T.md, 072.002-T.md, 072.003-T.md (R6 contract + ACs; updated_at).
- docs/memory/2026-09-12/stage-195-cycle3-copilot-remediation-memory.md (this file).

## Validation
- backlogit sync: markdown->DB, written=0 (no markdown clobbered), Indexed 509. DB updated_at
  reflects card edits.
- backlogit doctor: 168 issues, ALL `archived_from_self_ref` on 001-xxx archive records --
  pre-existing, unrelated to 072/063; none introduced.
- markdownlint: queue cards clean; plan+decision only pre-existing MD025 (front-matter title + H1),
  identical at HEAD, not introduced by this diff, not touched by any hunk.
- Independent review (code-review agent): CLEAN -- premises source-verified, cross-artifact
  consistency confirmed, no stale R4/R5-as-current, raw-key invariant + no-list-expansion intact.
- 063-S: status queued, unchanged (not claimed/started).
- `.backlogit/stash.jsonl`: SHA256 unchanged; excluded from commit.

## Ship handoff
- Do NOT reply/resolve performed by Stage. Ship (or operator) to post substantive replies citing the
  new commit SHA on both threads, then resolve. Both unresolved threads are addressed by R6 in the
  Stage-owned artifacts; no code change is authorized for Stage.
