---
title: "Sanitize credential-bearing source_key on ELT error and persistence paths"
date: 2026-09-12
agent: stage
kind: deliberation
stash_id: D6E758F5
status: accepted
references:
  - src/docline/elt/execute.py
  - src/docline/elt/source_keys.py
  - src/docline/fetch/staging.py
  - tests/elt/test_elt_real_execution.py
surfaced_by: 059-S security review (P2)
scope_guard: "Single stash entry D6E758F5 only. Not bundled with 059-S/060-S. No scope expansion."
---

# Deliberation: Source-key credential sanitization (stash D6E758F5)

## Traceability

- Consumed stash ID: **D6E758F5** (kind: bug, priority: high, age 13d).
- Surfaced by the 059-S security review as a pre-existing P2 on `origin/main`; explicitly
  out of scope for 059-S and must NOT bundle with shipment 060-S.
- No `DEFERRED SCOPE EXPANSION` marker present -> normal task-shaped route (not a P-021 C2
  deferred-expansion entry). No P-021 late-identifier reconciliation obligation triggered
  (entry carries no `N/A` source-ref fields; it is a normal stash bug, not a Ship C2 capture).
- Duplicate scan (unconditional): backlogit search for `D6E758F5` returned no other stash or
  backlog entry describing this expansion. **CLEAN DUPLICATE SCAN — no duplicate found.**

## Problem Frame

`_execute_single_source` in `src/docline/elt/execute.py` derives
`source_key = build_source_key(config)`. For `WebCrawlSource` / `ManifestUrlSource` the key is
a prefixed string embedding the raw URL, e.g. `web_crawl:https://user:pass@host/path?token=SECRET`.

Two leak sinks consume this raw key:

1. **Persistence:** `metadata.source = sanitize_source(source_key)` is written to
   `metadata.json`. But `sanitize_source()` only sanitizes strings that *start with*
   `http://`/`https://`/`file://`/an absolute path. A `web_crawl:`-prefixed key matches none of
   those branches, so `sanitize_source()` is a **no-op** and the raw URL (userinfo + credential
   query params) is persisted.
2. **Logging:** `_log.exception("... source_key=%s job_id=%s", source_key, job_id)` logs the
   **raw** `source_key` at ERROR, leaking the same credentials to logs.

The adjacent 059-S WARNING payload is origin-only and clean; this is the separate ERROR /
persistence path.

## Hard Constraint (invariant to preserve)

`job_id = make_job_id(source_key)` is `sha256(source_key)[:16]`. Job-ID determinism and the
staging cache-path layout depend on hashing the **exact raw `source_key` bytes**. The fix MUST
NOT change the string fed to `make_job_id`. Only the *representation used for metadata and
logging* may be sanitized.

## Options Considered

### Option A — Extend `sanitize_source()` to recognize prefixed source keys
Make `sanitize_source()` detect `web_crawl:`/`manifest_url:<id>:` prefixes and sanitize the
embedded URL. Rejected: `sanitize_source` is a general primitive also used by
`create_staging_job` on bare sources; overloading it with source-key grammar couples two
concerns and risks regressions on the bare-URL callers.

### Option B — New source-key-aware sanitizer `sanitize_source_key()` (CHOSEN)
Add a dedicated helper (co-located with `build_source_key` in `source_keys.py`) that splits a
prefixed key, applies the existing `sanitize_source()` URL logic to the embedded URL segment,
preserves the prefix and non-URL option suffixes (`depth=`, `max_pages=`, ...), and is a
pass-through for non-URL keys (`local_file:`, `github_repo:`, `manifest_local:`,
`manifest_git:`). `job_id` still hashes the raw key. Chosen: smallest blast radius, reuses the
vetted URL sanitizer, keeps `sanitize_source` semantics intact, single clear seam.

### Option C — Redact by not logging / not persisting the key at all
Drop `source_key` from the log and store only `job_id` in metadata. Rejected: loses
operator-facing diagnostic value (sanitized host/path is useful) and changes the metadata
contract more than necessary; the existing test depends on a source field being present.

## Chosen Direction

**Option B.** Introduce `sanitize_source_key()`; route `metadata.source` and the ERROR log
through it; keep `make_job_id(source_key)` on the raw key unchanged. Update the affected test to
assert the sanitized representation appears and that a credential token does NOT appear, while
`job_id` continues to be asserted.

## Done Looks Like

- No raw URL credential (userinfo or credential query param) reaches `metadata.json` or the
  ERROR log for `web_crawl:` / `manifest_url:` keys.
- `job_id` for identical inputs is byte-identical before and after the fix (determinism proof).
- Non-URL source keys are unchanged by the sanitizer.
- `test_url_fetch_failure_logs_source_key_and_job_id` updated and green; a credential-bearing
  case proves redaction.

## Covering Feature Synthesis

Single task-shaped bug -> solo group -> synthesize one covering top-level **chore** release unit
(security remediation / internal hardening, not a net-new user capability). Decomposes into one
sub-epic and three atomic single-domain tasks.

## Open Questions

None blocking. Security-sensitive + persistence path => plan hardening required (P-006).

## P-021 Deferral Watch

None discovered during this scoped analysis. If Ship later finds adjacent leak sinks (e.g.
`github_repo:` tokens), those are separate findings and MUST NOT expand this shipment.
