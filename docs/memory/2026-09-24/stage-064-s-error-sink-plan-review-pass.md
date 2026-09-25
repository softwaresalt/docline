---
type: stage-session-memory
date: 2026-09-24
agent: stage
shipment: 064-S
feature: 073-F
branch: chore/stage-064-s
status: plan-review-pass
---

# 064-S — narrow execute.py error-output sink correction

Starting HEAD: `fd99e2b92f9f745624ff18206a3508eefe00c3e8`.
Operator authorized one distinct planning correction after the earlier
typed-query-prepass review FAIL (historical record:
`stage-064-s-typed-query-prepass-review-halt.md`). Preserved the
uncommitted drafts of 073.002-T, 073.003-T, 073.009-T and the plan;
updated only existing 073.008-T RED criteria, 073.002-T production
criteria and the plan's current error-output/matrix/hardening/verification
sections. The old typed-prepass correction was not repeated.

## Investigation and decision

* `src/docline/elt/execute.py:254–301`: controlled
  `sanitize_source_key(config)` is logged as `source_key=%s` and saved
  in `SourceMetadata.source` / `metadata.json`, independently of
  `error=%s` and formatted traceback. `source_keys.py:83–125` builds
  typed branch/path_glob/manifest ID into that controlled key.
* `execute.py:314–354`: `_scrub_exception_message` currently applies
  `_redact_query_param_fragments` to UNTRUSTED exception prose; removing
  that pass would leak standalone `?token=SECRET` even with a clean
  configured URL. `_clone_scrubbed_exception` also copies notes verbatim
  or returns an original with unsanitized notes on the clean-message
  fast path. Formatted traceback includes cause/context/notes and may
  include `ExceptionGroup` children.
* Decision: byte-preserve known benign typed provenance ONLY in
  controlled source_key/metadata; retain the URL/config and standalone
  recognized query-fragment scrub on ALL untrusted error/traceback
  strings. No raw reinsertion into exception prose based on typed-field
  equality. Scrub notes and group members or use a detached non-leaking
  generic typed exception when reconstruction/`__str__` fails. Keep an
  incomplete-job outcome, typed exception info and safe context where
  feasible. Do not inspect document bodies, URL paths or local paths.
* RED test task 073.008-T now distinguishes trusted benign typed IDs
  from distinct synthetic URL/error credentials; captures live
  `caplog.text`, `record.getMessage()` and formatted traceback, including
  standalone fragments with no configured credentialed URL, cause,
  context, notes-only, ExceptionGroup child and raising-renderer fallback.
  Existing `test_elt_real_execution.py` global absence assertions for
  manifest ID `srcA?token=IDSECRET` must be reconciled, not blindly
  retained or dropped.

## Review and continuity

Plan review at the end of
`docs/plans/2026-09-14-elt-staging-credential-redaction-plan.md`:
`decision: PASS`, `dispatch_mode: same-model-declared-degradation`.
Constitution, Python, Scope Boundary, Architecture, Security Lens and
Learnings personas covered. Initial Python P1 (ExceptionGroup child
rendering) and P2 (throwing `__str__`) were corrected inside this same
error-sink cycle and narrowly rechecked with no remaining finding.
Constitution P2 corrected the inaccurate "additive-only" risk claim.
No remaining P0/P1 in the bounded plan review. Learnings retrieval:
confidence low; no relevant compound precedent.

Existing queued shipment `064-S` read back through `backlogit shipment
get`: seven items, parent `073-F`, five tests (073.001-T, 073.003-T,
073.007-T, 073.008-T, 073.009-T) before single production
073.002-T. No items added, harvested, archived, claimed or shipped.
No source/test/config edits, no build/test/lint, no push/PR/merge.
Unrelated untracked 2026-09-13 / 063-S memory untouched.
No structured checkpoint recovery candidate (`backlogit checkpoint
list` returned four summaries, no active Stage checkpoint or anomaly).

## Stage checklist for this targeted resume

* [x] Step 0.0: backlogit MCP unavailable in exposed tool set; registered
  CLI fallback probed (`backlogit --version`); manual ad hoc backlog
  scans not used.
* [x] Step 0.1: `backlogit sync` succeeded before scoped semantic reads.
* [x] Step 0: no agent-intercom pack; known-file direct-read exemptions
  for engram/graphtor-docs; existing Stage memory restored.
* [x] Step 1 / 1.5: operator supplied existing 064-S plan-review FAIL;
  no stash intake or task-shaped grouping needed.
* [x] Step 1.8: Learnings Researcher checked compound library (low).
* [x] Step 2: already-decided `docs/decisions/2026-09-14-elt-staging-
  credential-redaction-deliberation.md`; this pass did not alter
  deliberation or select a new scope.
* [x] Step 3: corrected same hardened implementation plan in place;
  original typed-prepass drafts retained, security hardening explicit.
* [x] Step 4: bounded multi-persona plan review PASS after same-cycle
  P1 correction; model-specific anchor unavailable/degradation declared.
* [x] Step 5: existing seven-item hierarchy inspected, not harvested
  anew; no new backlog items or dependencies.
* [x] Step 5.5: queued shipment 064-S already assembled; verified seven
  items and covering feature before child items; no duplicate created.
* [x] Step 5.6: no stash entries consumed by this targeted plan
  correction, so no archival operation.
* [ ] Step 6: after explicit-path Stage-artifact commit and final
  backlog index sync, present commit SHA and bounded handoff.

No context-overflow trigger: this session has two relevant memory files
under 500 KB. No compaction needed. No new routine observation/learning
is claimed for continuous-learning.
