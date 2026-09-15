---
title: "ELT staging credential redaction: default-fetch sink + coverage expansion"
description: "Implementation plan for 0F1A653C (default-path credential sink) and 06A59B1D (redaction coverage expansion)"
source: "docs/decisions/2026-09-14-elt-staging-credential-redaction-deliberation.md"
tags:
  - "security"
  - "credential-redaction"
  - "elt-staging"
---

## Problem Frame

Two distinct credential-exposure gaps remain on the ELT staging surface after
063-S/072-F (which fixed only `_execute_single_source`):

* **0F1A653C (high):** the DEFAULT `docline fetch` path
  (`cli.py:369` → `orchestrate_fetch` (orchestrate.py:47) →
  `create_staging_job(build_source_key(config), staging_dir)`) sets
  `metadata.source = sanitize_source(source)`, and `sanitize_source` is a **no-op**
  on the compound `web_crawl:` / `manifest_url:` prefixes (falls through to the
  return-as-is branch, staging.py:89). The credentialed source key survives into
  `metadata.source` and is emitted to **stdout** at `cli.py:381`
  (`json.dumps([job.model_dump(...) ...])`). `create_staging_job` has exactly one
  caller.
* **06A59B1D (medium):** `_CREDENTIAL_PARAM_PREFIXES` (staging.py:12) omits
  `password`/`pwd`/`passwd`/`client_secret`/`refresh_token`/`code`, and
  `_sanitize_url` (staging.py:92) preserves `parsed.path`, so path-embedded secrets
  are not redacted. `_is_credential_param` is shared with
  `source_keys.py:_remove_credential_query_params` (the typed/059-S WARNING path),
  so expanding the list is a shared-surface change.

## Requirements Trace

| Requirement (from decision contract) | Implementation action | Unit |
|---|---|---|
| Default-path `metadata.source`/stdout must not carry credentials | Thread `sanitize_source_key(config)` into `create_staging_job` via optional `sanitized_source` | A2 |
| `job_id` stays raw-`build_source_key`-derived | Keep `make_job_id(source)` on the raw arg | A2 |
| Backward-compatible for string-only callers | `sanitized_source: str \| None = None`, fall back to `sanitize_source(source)` | A2 |
| Prove the leak before fixing | Characterization test on orchestrate default path (web_crawl + manifest_url) | A1 |
| Additive coverage: more credential param names | Add password/pwd/passwd/client_secret/refresh_token; anchored match for `code` | B2 |
| Redact path-embedded secrets | Marker-gated path redaction in `_sanitize_url` | B2 |
| Prove expanded coverage + no false positives | Parametrized tests incl. benign `code`/path cases | B1 |

## Implementation Units

### Unit A1 — Characterization test: default-fetch credential sink (test domain)

* **Change:** Add a failing regression test asserting that `orchestrate_fetch` /
  `create_staging_job` produce a `metadata.source` (and the `cli fetch` stdout JSON)
  free of userinfo and `?token=…` for `WebCrawlSource` and `ManifestUrlSource`
  configs with credentialed URLs.
* **Files:** one test file under `tests/` (e.g. `tests/elt/test_orchestrate_redaction.py`).
* **Scenarios:** (1) web_crawl credentialed URL, (2) manifest_url credentialed URL.
* **Posture:** characterization-first (must fail on current HEAD).
* **Exit state:** test exists and fails on HEAD demonstrating the leak.

### Unit A2 — Thread typed sanitized key into `create_staging_job` (code domain)

* **Change:** Add optional `sanitized_source: str | None = None` to
  `create_staging_job`; when set, `metadata.source = sanitized_source` else the
  existing `sanitize_source(source)`. `job_id = make_job_id(source)` unchanged.
  Update `orchestrate_fetch` to import `sanitize_source_key` and call
  `create_staging_job(build_source_key(config), staging_dir, sanitized_source=sanitize_source_key(config))`.
* **Files:** `src/docline/fetch/staging.py`, `src/docline/elt/orchestrate.py` (2 files).
* **Functions:** `create_staging_job`, `orchestrate_fetch` (2).
* **Posture:** test-first (A1 must pass after this change).
* **Exit state:** A1 passes; existing staging/execute tests still green.

### Unit B1 — Tests: expanded credential coverage + path-embedded secrets (test domain)

* **Change:** Add parametrized tests for `_is_credential_param`/`sanitize_source`
  covering the new param names (`password`, `pwd`, `passwd`, `client_secret`,
  `refresh_token`, `code`), a false-positive guard case (e.g. `codec`/`code_version`
  NOT redacted), and a path-embedded-secret redaction case plus a credential-free
  path left intact.
* **Files:** one test file under `tests/` (e.g. extend `tests/fetch/test_staging_sanitize.py`).
* **Scenarios:** parametrized cases (grouped: new-param redaction, code false-positive,
  path-embedded redaction, benign-path passthrough).
* **Posture:** test-first (must fail on HEAD for the new coverage).
* **Exit state:** tests exist and fail on HEAD for the new coverage.

### Unit B2 — Expand `_CREDENTIAL_PARAM_PREFIXES` + path redaction with guards (code domain)

* **Change:** Add `password`, `pwd`, `passwd`, `client_secret`, `refresh_token` to
  `_CREDENTIAL_PARAM_PREFIXES`; add anchored/exact matching for `code` (avoid
  `codec`-style false positives) in `_is_credential_param`. Add marker-gated
  path-embedded secret redaction in `_sanitize_url` (redact only path segments
  containing a credential marker; leave benign paths intact).
* **Files:** `src/docline/fetch/staging.py` (1 file).
* **Functions:** `_CREDENTIAL_PARAM_PREFIXES`, `_is_credential_param`, `_sanitize_url` (≤3).
* **Posture:** test-first (B1 must pass after this change).
* **Exit state:** B1 passes; existing sanitizer and 059-S/063-S tests still green.

## Dependency Graph (no cycles)

```
A1 ──blocks──> A2 ──blocks──> B2
B1 ──blocks──> B2
```

* `A2 depends_on A1` (test-first within stream A)
* `B2 depends_on B1` (test-first within stream B)
* `B2 depends_on A2` (real: same-file `staging.py` contention + risk-ordering; the
  acute P0 sink lands and verifies first, and A2 reroutes the default path through
  the shared `_is_credential_param` that B2 then widens)

## Decisions and Rationale

* Reuse the 063-S typed sanitizer (`sanitize_source_key`) rather than re-parse
  compound prefixes in the string sanitizer — proven contract, preserves job_id
  determinism, minimal blast radius (1 caller).
* Keep the two streams width-isolated: A never touches the prefix list; B never
  touches `orchestrate_fetch`/`create_staging_job`.
* Anchored match for `code` and marker-gated path redaction to keep the expansion
  strictly additive without false-positive corruption.

## Risks and Caveats

* Signature change to a shared helper — mitigated by single verified caller and an
  optional/defaulted parameter.
* Shared `_is_credential_param` expansion affects the 059-S WARNING path and the
  063-S execute path — intended and additive; regression-tested.
* `code` prefix false positives — mitigated by anchored matching + explicit test.

## Runtime Verification and Closure

* **Changed runtime surface:** `docline fetch` CLI (default path) stdout and the
  in-memory `SourceMetadata.source`; the shared sanitizer used by execute-path
  `metadata.json` and WARNING-path logs.
* **Runtime verification (must prove before absorbed):**
  1. `docline fetch` (default, non `--execute`) over a config with a credentialed
     `web_crawl`/`manifest_url` URL emits stdout JSON whose `metadata.source`
     contains no userinfo, no credential query params, and no path-embedded secret.
  2. `job_id`/`cache_path` for a given config are byte-identical before and after A2
     (determinism preserved).
  3. Existing execute-path (`--execute`) and 059-S WARNING-path behavior unchanged
     except for the additive redaction from B2.
* **Operational closure:** regression tests A1/B1 become the standing guards;
  no data migration, no rollback coupling (pure code + tests, no persisted-state
  format change). Owner: ELT staging maintainer. Validation window: one green CI run
  on the shipment PR.

## Plan Hardening Signals (REQUIRED)

* public API / schema / contract change — **absent** (internal helper signature only;
  optional/defaulted param; no persisted-format or public API change).
* security / auth / permission / compliance-sensitive behavior — **PRESENT**
  (credential redaction correctness on live fetch paths; the whole point of the work).
* migration / backfill / destructive / irreversible step — **absent** (no data or
  config migration; no destructive action).
* external integration / operator checkpoint / external dependency — **absent**.
* high runtime / rollout / rollback risk — **absent** (pure code + tests; trivially
  revertible by reverting the two commits).

Conclude: **Requires plan hardening: yes** (security/compliance-sensitive signal present).

## Plan Hardening

**Hardening required?** Yes — the "security/compliance-sensitive behavior" signal is
present (credential-redaction correctness on live fetch paths). Hardening focuses on
threat modeling, trust boundaries, and verification depth; there are no destructive or
migration actions to harden.

### Learnings / instructions consulted

* `docs/memory/2026-09-13-sanitize-source-key-elt-error-paths-closure.md` (063-S
  closure; established the typed-sanitizer contract and recorded both deferrals).
* `docs/memory/stage-195-cycle6/7-*` (path-secret = 06A59B1D; web_crawl/manifest_url
  URL fields already covered on the typed path; both deferrals genuinely distinct).
* `.github/instructions/strict-safety.instructions.md` (risky-action classification).
* In-repo pattern: `execute.py:_execute_single_source` (the proven raw-job_id +
  sanitized-metadata split to mirror).

### Threat model & trust boundaries

* **Asset:** source credentials embedded in ELT source configs — URL userinfo
  (`user:pass@`), credential query params (`?token=`, `?password=`, …), and
  path-embedded secrets.
* **Trust boundary crossed:** in-process typed `SourceConfig` (trusted, may contain
  secrets) → serialized `SourceMetadata.source` that crosses to **stdout/console**
  (cli.py:381), **logs**, and (execute path) **on-disk `metadata.json`**. Everything
  past that boundary is untrusted-observer territory (terminal capture, CI logs,
  shipped artifacts).
* **Attack/leak vectors addressed:**
  1. Default-path stdout leak via unsanitized `metadata.source` (0F1A653C) — closed by A2.
  2. Credential query params outside the current prefix set
     (`password`/`pwd`/`passwd`/`client_secret`/`refresh_token`) surviving redaction
     (06A59B1D) — closed by B2 (both string + typed paths, shared `_is_credential_param`).
  3. Path-embedded secrets surviving `_sanitize_url` (06A59B1D) — closed by B2
     marker-gated path redaction.
* **Non-goals / explicitly out of scope (P-021, left stashed):** underscore-scheme
  regex gap (E89DC095), Unicode-Cf whitespace guard (9D44B6F3), query-function
  redundancy (E7878B1B), compound-prefix scheme matching in the string sanitizer.

### Risky-action classification (strict-safety)

* **ProposedAction:** modify credential-redaction control code on live fetch paths.
  **ActionRisk:** moderate (security-correctness; no destructive/runtime/PR mutation
  in this Stage plan). **Approval:** not required for planning; implementation is
  ordinary code work gated by tests + review. **ActionResult (expected):** all four
  minimal-safe-contract invariants hold, proven by A1/B1 + the runtime checks above.
* No destructive, migration, or irreversible actions exist in this plan.

### Verification criteria proving credentials cannot reach any sink

The following MUST all hold (they are the acceptance backbone of A1/B1 and the
runtime checks):

1. **Metadata:** for every source kind, `StagingJob.metadata.source` contains no
   userinfo, no credential query-param values (incl. the newly covered names), and
   no path-embedded secret — on BOTH default and execute paths.
2. **stdout:** the `docline fetch` (default) JSON printed at cli.py:381 contains no
   credential substrings for a credentialed config.
3. **Logs / error text:** the shared `_is_credential_param` expansion propagates to
   the typed WARNING/error-scrub path (`_remove_credential_query_params`), so
   error/log text also drops the newly covered params (regression-asserted).
4. **Path-derived output:** `_sanitize_url` output for a path-embedded-secret URL
   redacts the secret segment; a credential-free path is returned unchanged.
5. **Determinism preserved:** `job_id`/`cache_path` unchanged by A2 for a fixed config.
6. **No false positives:** benign params/paths (`codec`, `code_version`, secret-free
   paths) are NOT redacted.

### Review-gate capability note

Plan review below ran in single-agent declared-degradation mode (no reviewer-subagent
dispatch surface in this Stage session); every selected persona rubric was applied
inline. Markers emitted for harvest fail-closed parsing.

## Plan Review

dispatch_mode: single-agent-declared-degradation
decision: PASS

**Gate rationale:** No P0/P1 findings. Plan hardening was required (security signal)
and is present with a threat model, trust-boundary analysis, strict-safety
risky-action classification, and explicit credential-cannot-reach verification
criteria — satisfying the hardening-required gate. Two P2 items recorded as backlog
awareness (not blocking). Reviewer-subagent dispatch was unavailable; declared
degradation recorded and every selected persona rubric applied inline, so coverage is
complete.

**Persona coverage (inline, single-agent declared degradation):**

| Persona | Mode | Result |
|---|---|---|
| Constitution Reviewer | inline | PASS — P-001/P-016/P-021 respected; two width-isolated code tasks + two test tasks; no scope bleed. |
| Python Reviewer | inline | PASS — optional/defaulted param is backward compatible; single caller verified; type signature `str \| None` sound. |
| Scope Boundary Auditor | inline | PASS — no absorption of related entries; anchored `code` match avoids over-reach; strictly additive. |
| Learnings Researcher | inline | PASS — reuses 063-S typed contract; no contradiction with prior closure. |
| Architecture Strategist | inline (anchor route unavailable → same-model) | PASS — `create_staging_job` seam is the right integration point; no cyclic deps. |
| Security Lens Reviewer | inline (triggered: credential/secrets handling) | PASS — trust boundaries and all four sink classes (metadata/stdout/logs/path) covered by verification criteria. |

**Findings:**

* **P2 — B1 scenario count:** the coverage test groups several cases; keep them
  parametrized so the single test task stays within the 4-scenario granularity
  intent (grouped param cases count as one logical scenario surface). Recorded for
  the implementer, non-blocking.
* **P2 — path-redaction marker set:** the exact credential-marker set for path
  segments should mirror the typed path's `_contains_credential_marker`; a mismatch
  would be a minor coverage gap, not a correctness failure. Recorded as awareness.
* **P3 — advisory:** consider a follow-up (separate P-021 entry) to unify the string
  and typed sanitizers long-term; explicitly NOT in this batch.

<!-- plan-review-attempt: 1 -->
