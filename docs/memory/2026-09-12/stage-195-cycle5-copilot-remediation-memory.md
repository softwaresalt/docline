---
title: "Stage PR #195 Copilot remediation cycle 5 (Revision R7 -- encoded-marker bypass)"
date: 2026-09-12
agent: stage
shipment: 063-S
feature: 072-F
pr: 195
head: 11b7d39a75e6c180ac10cca0d612146b4866502f
revision: R7
status: complete
---

# Stage cycle 5 -- PR #195 encoded credential-marker bypass (R6 -> R7)

## Threads (live GraphQL, HEAD 11b7d39, copilot-pull-request-reviewer)
- Full paginated fetch: 18 reviews, 15 review threads, ALL Copilot-authored.
- Exactly TWO unresolved threads (no additions since Ship's snapshot):
  - `PRRT_kwDOSsAX4c6h05Dd` -- comment 3998103338 -- `.backlogit/queue/072.001-T.md:18`
  - `PRRT_kwDOSsAX4c6h05Ds` -- comment 3998103357 -- plan lines 174/178
- Both point at the SAME contract surface: `sanitize_source_id()` marker detection.

## Finding
The R6 marker-gated `sanitize_source_id()` scanned RAW id bytes for credential
parameter names. The real URL sanitizer (`_sanitize_url` in
`src/docline/fetch/staging.py`) classifies query names AFTER `parse_qsl`
percent-decoding, so `%74oken=IDSECRET` (decodes to `token`) bypassed the raw scan and
the no-marker branch returned the id verbatim, leaking `IDSECRET` into `metadata.source`
and the ERROR log (URL-shaped AND opaque non-URL ids).

## Classification (P-021 C1)
BOTH IN SCOPE -- same-contract-surface defects on Stage-owned planning/backlog artifacts
for 072-F / 063-S. Fixed in-cycle under operator continue-autonomously authorization;
neither deferred; no P-021 C2 capture. Ship's erroneous deferral stash entry `C53CF18E`
(which proposed deferring exactly this fix) reconciled as superseded/fixed-in-scope and
archived via `backlogit stash archive` (tombstone in `.backlogit/archive/stash.jsonl`).

## Fix (Revision R7)
`sanitize_source_id()` marker detection now classifies parameter names on a DECODED VIEW
mirroring parse_qsl: exactly ONE `urllib.parse.unquote` pass, `encoding="utf-8"`,
`errors="replace"`, never `.port`. Detection-only (returned id built from raw bytes:
credential-free verbatim; marker-bearing fragment surgically redacted in place with the
raw/encoded key preserved and only the value replaced; `<source-id-redacted>` only when
surgical redaction cannot complete). Bounded single pass => a double-encoded `%2574oken`
(decodes once to literal `%74oken`) stays verbatim, identical to the URL sanitizer =>
id/URL consistency, no over-redaction, guaranteed termination. `errors="replace"` keeps
malformed/non-UTF8 percent sequences total and non-throwing. `make_job_id` still hashes
raw `build_source_key(config)` (determinism). `_CREDENTIAL_PARAM_PREFIXES` NOT expanded
(06A59B1D deferred). Crawl `config.url` path unchanged (already decode-aware).

## Regressions specified
Unit 1: (g) encoded-key id `srcA?%74oken=IDSECRET` + URL-shaped variant surgically
redacted; (h) double-encoded `srcA?%2574oken=IDSECRET` verbatim; (i) malformed/non-UTF8
percent credential-free id verbatim without raising; (j) percent-encoded userinfo
stripped. Unit 2: encoded-key manifest id => IDSECRET absent from caplog.text +
metadata.json.

## Artifacts changed
plan (frontmatter R7, Revision R7 note, Requirements Trace row, Unit 1, Unit 2,
Decisions, Risks, new Cycle-4/R7 section), decision (Option B R7 refinement + Chosen
Direction + Done Looks Like), feature card 072-F, tasks 072.001-T/072.002-T/072.003-T,
and `.backlogit/archive/stash.jsonl` (C53CF18E tombstone).

## Stash reconciliation
`C53CF18E` archived (active stash 29 -> 28 lines; removed byte-exactly). The pre-existing
unrelated 3-line timestamp-normalization working-copy diff on `0F1A653C` / `79BF0AEC` /
`06A59B1D` PRESERVED byte-for-byte (verified SequenceEqual) and EXCLUDED from the fix
commit (left unstaged). Archive tombstone (+1 line only, no reformat) committed.

## Validation
backlogit sync OK (509 artifacts); doctor: only pre-existing archived_from_self_ref
warnings (none touch 072/063/C53CF18E); markdown/frontmatter integrity OK (balanced
fences, consistent tables, valid YAML); independent code-review verdict PASS (empirically
verified parse_qsl decode semantics).

## Boundaries held
No product source changed. 063-S remains queued/unclaimed. No push, no PR reply, no
thread resolve, no shipment claim/status change. Commit on
`chore/stage-194-copilot-remediation` only.
