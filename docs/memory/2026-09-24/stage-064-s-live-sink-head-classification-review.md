---
type: stage-session-memory
date: 2026-09-24
agent: stage
shipment: 064-S
feature: 073-F
branch: chore/stage-064-s
status: bounded-correction-reviewed
---

# 064-S — live default-path test-first classification correction

Starting committed HEAD: `e6522ff35eff3ee7fef9482147659a81ae385217`.
Operator authorized a mechanical correction of the already committed 073.009-T
and its authoritative plan, without changing implementation or test files.
The prior PASS plan gate remains historical; this is a **report-only, scoped
Stage review**, not a new full independent plan-review gate or a runtime test.

## Read-only path evidence and classification

* On HEAD, `src/docline/elt/orchestrate.py:47` calls
  `create_staging_job(build_source_key(config), staging_dir)`.
  `src/docline/fetch/staging.py:160-162` sets `metadata.source` by calling
  `sanitize_source(source)` on that **compound** key. It does not pass
  `sanitize_source_key(config)`; `_sanitize_url_field` and
  `_strip_reversed_query_credentials` do not run on this live default path.
* For WebCrawlSource and ManifestUrlSource, the compound key embeds the URL.
  Credential-free `?a=1;b=2` and `?a=1&&b=2` are therefore **GREEN on HEAD**
  at the actual default-path `metadata.source` stdout sink, and their
  assertions MUST NOT REGRESS after typed sanitizer wiring. They are not
  red-on-HEAD proof of the typed pre-pass.
* Direct typed helper/pre-pass tests in 073.003-T **ARE RED on HEAD** on
  those variants. The complete 073.009-T integration test is still RED on
  HEAD because URL userinfo and recognized new credential names leak at
  the real sink; 073.002-T must make it fully green in one merged code step.
  A mixed-credential fixture is a post-073.002-T leak-free requirement, not
  an assertion that the current live path exercises the typed pre-pass.

The correction edits only 073.009-T's body/acceptance criterion and the
corresponding Unit CI, sink matrix and verification criterion in
`docs/plans/2026-09-14-elt-staging-credential-redaction-plan.md`. The
seven-member queued 064-S manifest (`073-F` + five test tasks + `073.002-T`)
and five test-task `blocks` edges into the single production task were read
back unchanged. No stash entries were consumed and no new backlog hierarchy
or shipment was assembled.

## Stage-local report-only review

Scope: inspect the corrected diff against the read-only default-path wiring
and the existing 073.003-T direct-helper contract. Result: **no P0/P1 in
this correction**. The same two no-credential fixtures now have
GREEN-on-HEAD / MUST-NOT-REGRESS classification in task AC, Unit CI, and
the WebCrawlSource/ManifestUrlSource matrix cells; the plan's verification
criterion distinguishes this from RED-on-HEAD typed helper tests. Existing
userinfo/new-name full-test RED-on-HEAD claims are unchanged. No live typed
pre-pass claim remains for HEAD. This is not a claim that tests ran or that
the entire implementation plan received a fresh independent review.

P2 residual (not changed): adjacent recognized credential tokens with one
shared separator in 073.003-T's one-adjacent-delimiter rule need an explicit
deterministic delimiter-ownership example before implementation. Specifying
that example would adjudicate output beyond this mechanical live-sink
classification, so leave it for separately authorized scope; both
credential tokens still must be removed and benign bytes protected.

## Step continuity for this targeted already-harvested correction

* [x] 0.0: backlogit MCP not exposed; registered CLI fallback
  `backlogit --version` succeeded (`TOOL_DEGRADED`).
* [x] 0.1: `backlogit sync` succeeded before scoped semantic backlog reads
  (`INDEX_SYNC_OK`).
* [x] 0–2: prior 064-S memory restored; no intercom installed; exact-path
  direct-read exemption used for source/plan/task; existing deliberation
  unchanged; no fresh stash triage, grouping or learnings needed for this
  targeted repair.
* [x] 3–4: existing hardened plan and historical PASS checked; bounded
  report-only correction review above, no new full review dispatch.
* [x] 5–5.5: prior hierarchy and queued shipment `064-S` verified, no new
  harvest/assembly; five test-to-code edges unchanged.
* [x] 5.6: no stash entries consumed; archive not applicable.
* [ ] 6: check diff/commit scope and final index sync; hand off accurate
  resulting commit SHA. No source/test/config edits, build/test/lint, claim,
  push, PR or merge. Preserve unrelated untracked memory.
