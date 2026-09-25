---
type: stage-session-memory
date: 2026-09-24
agent: stage
shipment: 064-S
feature: 073-F
branch: chore/stage-064-s
status: blocked-plan-review
---

# 064-S — typed URL pre-pass correction, plan-review FAIL

Starting HEAD: `fd99e2b92f9f745624ff18206a3508eefe00c3e8`.
Only one worktree; unrelated untracked 2026-09-13 / 063-S memory untouched.
No source/test/config edits or execution, shipment claim, push, PR or commit.

## Bounded authorized correction

Read-only root cause: `source_keys._sanitize_url_field` runs
`_strip_reversed_query_credentials` before `staging.sanitize_source`.
The pre-pass selects tokens `[::2]` from a separator-preserving split,
drops empty tokens and rejoins with `&`. With NO credential,
`?a=1;b=2` becomes `?a=1&b=2` and `?a=1&&b=2` becomes
`?a=1&b=2`; fixing staging's parse_qsl/urlencode alone cannot repair
this typed input. `_remove_credential_query_params` also drops fragments,
and staging reconstructs authority from `hostname`/`port`, so the corrected
requirements pin benign fragment and `HOST:080` byte identity too.

Updated task contracts: 073.003-T adds direct typed-pre-pass and completed
typed sanitizer failing fixtures, separate no-credential identity versus
mixed credential removal, query/fragment malformed `?` guard and
raw-authority/first-token edge cases; 073.009-T adds live `metadata.source`
assertions only where stdout prints the typed URL; 073.002-T requires
raw-span filtering across source_keys and staging, not staging alone.
The plan's authoritative contract, units, matrix and verification criterion
were aligned, including the formerly incomplete four-file Unit A2/B2
summary (`execute.py`). The 064-S seven-item manifest and five-test-to-one-code
DAG have not changed.

## Gate

Stage-local plan review: `decision: FAIL`, `dispatch_mode: multi-agent`,
recorded in the plan (attempt 6). Two independent reviewers found a
separate unclosed P1 in the pre-existing execute.py error-sink plan:
removing global `_redact_query_param_fragments` to protect known typed
provenance can expose standalone `?token=SECRET` in untrusted exception
text. This bounded authorization covers the typed pre-pass P1 only, so
do not silently extend the cycle to 073.008-T/execute.py; operator must
decide whether to authorize a distinct test-first same-sink correction
before a new review. A P2 notes/traceback issue is recorded in the review
for separate scope adjudication, not counted as closed here.

No SHA to hand off: changes remain uncommitted because the plan gate
failed. No new backlog items or shipment were created. If explicitly
reauthorized, first inspect the plan FAIL and update the warning-sink
contract/test; re-run plan review, then (only if PASS) commit Stage artifacts
with Copilot trailer. Do not claim or ship 064-S from this checkpoint.
