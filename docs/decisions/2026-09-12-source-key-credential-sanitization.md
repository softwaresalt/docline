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

### Option B — New source-config-aware sanitizer `sanitize_source_key()` (CHOSEN; contract amended R3)
Add a dedicated helper (co-located with `build_source_key` in `source_keys.py`) that consumes the
**typed `SourceConfig`** (not the composed key string): for the two leak-scoped crawl configs
(`WebCrawlSource` / `ManifestUrlSource`) it sanitizes the typed `config.url` via the existing
`sanitize_source()` URL logic and recomposes the key through the same builder grammar
(`_build_crawl_source_key`) used by `build_source_key`, so the sanitized representation is
grammar-identical to the raw key except for the URL segment. All other config types return
`build_source_key(config)` byte-identical (`local_file:`, `github_repo:`, `manifest_local:`,
`manifest_git:` — github_repo token handling DEFERRED). `job_id` still hashes the raw
`build_source_key(config)`. Chosen: smallest blast radius, reuses the vetted URL sanitizer, keeps
`sanitize_source` semantics intact, single clear seam.

**R3 amendment (Copilot review, PR #194 thread PRRT_kwDOSsAX4c6hzYmm):** the earlier R2 contract
isolated the URL by scheme anchor over the composed key string. That grammar could not reliably
resolve the manifest_url case: `ManifestUrlSource.id` is an unrestricted `str`
(`src/docline/elt/manifest_models.py:65`) and the composed key is
`manifest_url:<id>:<url>:<options>` (`src/docline/elt/source_keys.py:32-40`), so an `id` containing
`http://`/`https://` makes the FIRST-scheme-after-prefix anchor select the wrong segment. Consuming
the typed config removes all string-parse ambiguity (there is no composed string to disambiguate)
and is preferred over the alternative unambiguous-encoded-delimiter remedy because it requires no
change to the `build_source_key` wire format or the `make_job_id` input.

**R4 refinement (Copilot review, PR #195 thread PRRT_kwDOSsAX4c6hz0Jq):** the R3 typed-config
recompose removed the URL mis-isolation ambiguity but still placed `ManifestUrlSource.id` (an
unrestricted `str`) VERBATIM into the recomposed `manifest_url:<id>:<url>:<options>` key, so a
credential-bearing `id` (a scheme-bearing string carrying userinfo or `?token=...`) still reached
`metadata.source` and the ERROR log even when `config.url` was sanitized. The contract is refined so
the safe representation ALSO routes `config.id` through `sanitize_source()` before recompose
(`manifest_url:<sanitized_id>:<sanitized_url>:...`); `job_id` still hashes the raw
`build_source_key(config)`. A credential-bearing-id case is added to Unit 1 of the plan.

### Option C — Redact by not logging / not persisting the key at all
Drop `source_key` from the log and store only `job_id` in metadata. Rejected: loses
operator-facing diagnostic value (sanitized host/path is useful) and changes the metadata
contract more than necessary; the existing test depends on a source field being present.

## Chosen Direction

**Option B (typed-config contract, R3).** Introduce
`sanitize_source_key(config: SourceConfig) -> str` that sanitizes the typed `config.url` and
recomposes via `_build_crawl_source_key`; route `metadata.source` and the ERROR log through
`sanitize_source_key(config)`; keep `make_job_id(build_source_key(config))` on the raw key
unchanged. Update the affected test to assert the sanitized representation appears and that a
credential token does NOT appear (including for a manifest_url config whose `id` is itself a
credential-bearing scheme-bearing string, with `config.id` sanitized via `sanitize_source()` before recompose (R4)), while `job_id` continues to be asserted against the raw-key recomputation.

## Done Looks Like

- No raw URL credential (userinfo or credential query param) reaches `metadata.json` or the
  ERROR log written by `_execute_single_source` (incl. the `exc_info` traceback) for
  `web_crawl:` / `manifest_url:` keys -- including a credential embedded in the manifest_url `id` segment, which the safe representation routes through `sanitize_source()` (R4). NOTE: the separate `orchestrate_fetch` /
  `create_staging_job` default-fetch sink is a distinct, out-of-scope leak captured as a P-021
  deferral (see below) — NOT closed by this shipment.
- `job_id` for identical inputs is byte-identical before and after the fix (determinism proof).
- Non-URL source keys are unchanged by the sanitizer.
- `test_url_fetch_failure_logs_source_key_and_job_id` updated and green; a credential-bearing
  case proves redaction.

## Covering Feature Synthesis

Single task-shaped bug -> solo group -> synthesize one covering top-level **chore** release unit
(security remediation / internal hardening, not a net-new user capability). Decomposes directly
into three atomic single-domain tasks (backlogit WIT defines no sub-epic type; tasks attach
directly to the covering feature 072-F).

## Open Questions

None blocking. Security-sensitive + persistence path => plan hardening required (P-006).

## P-021 Deferral Watch

Adjacent, out-of-scope leak sinks identified during scoped analysis and the Stage adversarial
multi-model review (2026-09-12). Each is captured as a separate stash entry for future triage and
MUST NOT expand shipment 063-S:

- **`orchestrate_fetch` / `create_staging_job` default-fetch sink** (`src/docline/fetch/staging.py:161`):
  the non-`--execute` `docline fetch` path also routes a prefixed crawl `source_key` through the
  no-op `sanitize_source()`, leaking the raw credentialed key to `metadata.json` and stdout
  (`cli.py:381`). Same leak class as D6E758F5 but a distinct function/path (this shipment fixes only
  `_execute_single_source`). Captured as stash **0F1A653C** (high).
- **`github_repo:` token leak**: `github_repo:{repo_url}` may embed tokens; `sanitize_source_key()`
  is pass-through for this prefix in 063-S. Captured as stash **79BF0AEC** (medium).
- **`_CREDENTIAL_PARAM_PREFIXES` expansion + path-embedded secrets**: the shared param list omits
  `password`/`pwd`/`passwd`/`client_secret`/`refresh_token`/`code` and `_sanitize_url` does not
  redact path-embedded secrets; expanding it would alter the 059-S WARNING path, widening blast
  radius beyond D6E758F5. Captured as stash **06A59B1D** (medium).
