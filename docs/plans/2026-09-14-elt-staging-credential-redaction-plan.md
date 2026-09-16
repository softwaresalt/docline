---
title: "ELT staging credential redaction: default-fetch sink + coverage expansion"
description: "Implementation plan for 0F1A653C (default-path credential sink) and 06A59B1D (redaction coverage expansion)"
source: "docs/decisions/2026-09-14-elt-staging-credential-redaction-deliberation.md"
tags:
  - "security"
  - "credential-redaction"
  - "elt-staging"
---

## Operator Contract — 2026-09-15 (FINAL, AUTHORITATIVE — supersedes ALL earlier sections)

> This block is the SINGLE authoritative product contract for 064-S / 073-F and
> SUPERSEDES every earlier section of this plan, INCLUDING the prior
> "Operator-Decision Revision" block below, wherever they conflict. All lower
> content is retained only as a HISTORICAL / REJECTED-alternatives record. The
> active executable plan has exactly TWO streams (A, B), no path-secret behavior,
> and no source-document-content behavior.

### Product boundary (authoritative)

* Docline MUST NOT inspect, classify, redact, or rewrite source-document BODY content.
* Docline MUST NOT redact or decode ordinary URL PATHS. Ordinary URL paths, branches,
  path globs, manifest IDs, local paths, include patterns, and other provenance
  identifiers are preserved BYTE-FOR-BYTE even if they contain text like `?token=`.
  They are NEVER interpreted as credential structures.
* Docline redacts ONLY structured source-access credentials from Docline-generated
  metadata / stdout / log / warning / error outputs: (1) URL user-info;
  (2) query-parameter NAMES in an explicit, case-insensitive recognized credential
  vocabulary; (3) typed configuration fields explicitly designated secret.
* All benign query parameters and all provenance are preserved.

### Consensus findings — resolution mapping (authoritative)

1. **Explicit exact-match vocabulary (replaces all `startswith`).** The query-name
   matcher recognizes an EXPLICIT, case-insensitive credential-name vocabulary by
   EXACT equality; the legacy `startswith`/prefix heuristic is REPLACED. The existing
   recognized names are preserved by INDIVIDUAL enumeration (token, access_token, key,
   api_key, secret, auth, sig, signature, x-amz-credential, x-amz-signature,
   x-amz-security-token, x-goog-signature); the real-credential names previously caught
   only by the `startswith("auth")` prefix are enumerated to keep prior coverage
   (auth_token, authorization); the intended additional legacy/cloud names are added
   (refresh_token, apikey, client_secret, x-goog-credential, awsaccesskeyid) plus the
   new names (password, pwd, passwd, code). This vocabulary is NOT claimed universally
   complete: unknown/vendor-specific names and suffixed/prefixed variants (e.g.
   `token_v2`) that exact-match no longer catches are INTENTIONALLY NOT redacted absent
   explicit product support (recorded as accepted residual). Benign
   preservation tests cover tokenizer, keynote, secretary, authorship, signal,
   password_policy, pwd_length, client_secretary, codec, code_version, passwd_file,
   refresh_token_ttl and case variants, plus benign prefix fixtures. See Unit B1/B2 and
   deliberation H1.
2. **Bounded decode — query NAMES only, both sanitizer paths.** Bounded
   percent-decoding is applied to query-parameter NAMES on BOTH the string and typed
   sanitizer paths: re-check the vocabulary after each layer, max 5 layers, fail
   closed if still transforming past the cap. Covers `%70assword` (1 layer),
   `%2570assword` (2 layers), a deeper valid layered case, and an over-cap case. NO
   decoding of URL paths or query-parameter VALUES. See Unit B1/B2.
3. **Typed sanitization redesign.** The typed sanitizer sanitizes URL fields and
   explicitly-secret typed fields, while BYTE-PRESERVING branch, path_glob, manifest
   ID, local path, and include fields. Characterization test 073.001-T proves this.
4. **Raise, not sentinel.** The whole-key `sanitized_source=None` sentinel fallback is
   REPLACED: for a compound source key, omission RAISES a typed, non-leaking exception
   that does NOT echo the raw key. Bare-URL compatibility remains only where it
   preserves paths and sanitizes structured userinfo/query credentials correctly. The
   parameter is keyword-only. See Unit A2 and deliberation H3.
5. **Satisfiable A2+B2 composition gate (single merged production task).** The final
   live default-stdout integration test 073.009-T proves the A2+B2 composition (userinfo
   AND all recognized new credential query-param names) across the URL-bearing source
   kinds. It is written first and is a leaf gate for the SINGLE MERGED production task
   073.002-T. Because A2 (userinfo sink) and B2 (vocabulary) are now ONE atomic
   production task, 073.009-T — and every other test task (073.001-T, 073.003-T,
   073.007-T, 073.008-T) — goes GREEN together in one verifiable step when 073.002-T
   completes. This is the 2026-09-15 P0 GREEN-GATE FIX: two separate code tasks could
   not each green the composition gate (a per-task-green / test-first violation), so the
   former stream-B code task 073.004-T is merged into 073.002-T. 073.007-T is the
   stream-A userinfo subset; 073.008-T is the stream-B WARNING subset. The 2-hour rule
   yields here to the stronger per-task-green invariant; the merged task stays a single
   cohesive credential-redaction domain (see Unit A2/B2 merge note and Justified residual
   risk).
6. **LocalFileSource / ManifestLocalSource matrix.** Local paths and include patterns
   are PRESERVED; manifest IDs are PRESERVED under this operator contract. Only
   explicitly-secret typed fields (if any) are redacted; there is no URL credential to
   redact on these kinds.
7/9/10. **Historical hygiene.** Every path / C1 / C2 / H2 / H2-C2 / three-stream /
   obsolete-rollback / obsolete-verification instruction below is HISTORICAL / REJECTED
   and non-executable. The active plan has exactly two streams. Retired tasks
   073.005-T / 073.006-T remain status=blocked, out of shipment 064-S, retained
   non-destructively. The three removed stream-C edges are
   `073.006-T→073.005-T`, `073.006-T→073.004-T`, `073.006-T→073.007-T`.

### Handoff (authoritative — Finding 8)

Stage OWNS and COMMITS its own planning/backlog artifacts on branch
`chore/stage-064-s` (this correction is committed by Stage). The Orchestrator does
NOT commit Stage artifacts; it only coordinates review, the remote staging gate, and
the handoff to Ship. Any earlier "left uncommitted for Orchestrator review" or
"Orchestrator to commit" wording is superseded.

### Rebuilt executable DAG (test-first only; acyclic; parent-first shipment)

```text
073.001-T ──blocks──> 073.002-T   (concern A: helper test → merged code)
073.003-T ──blocks──> 073.002-T   (concern B: helper test → merged code)
073.007-T ──blocks──> 073.002-T   (concern A: live-stdout userinfo subset → merged code)
073.008-T ──blocks──> 073.002-T   (concern B: live-WARNING subset → merged code)
073.009-T ──blocks──> 073.002-T   (final A2+B2 composition gate → merged code)
```

Leaves (no upstream deps): 073.001-T, 073.003-T, 073.007-T, 073.008-T, 073.009-T.
073.002-T is the SINGLE MERGED production task (A2 typed sink wiring + B2 exact-match
vocabulary/decode). All five test tasks are red on HEAD and go GREEN together when
073.002-T completes — a single atomic verifiable green state, satisfying the test-first
per-task-green invariant. Former separate stream-B code task 073.004-T is retired/merged
into 073.002-T (status=blocked, edges removed, out of shipment). The graph is acyclic and
every edge is a genuine test-first prerequisite.

## Operator-Decision Revision — 2026-09-15 (AUTHORITATIVE; supersedes cycles 1–3 path work)

> This section is authoritative and SUPERSEDES every path-redaction requirement
> introduced during prior review remediation (cycles 1–3). Where any later
> section of this plan (Units C1/C2, the H2/H2-C2 grammar, the path rows of the
> Requirements Trace, verification criterion 4, the matrix path-secret cells, or
> the cycle-1/2/3 remediation tables) conflicts with this section, THIS section
> wins. The conflicting path material is retained below only as a HISTORICAL /
> REJECTED-alternatives record, clearly marked, not as executable scope.

### Authoritative operator decision

* Docline MUST NOT scan, interpret, or rewrite source-document content for secrets.
* Ordinary URL paths are source identifiers / content locations and MUST remain
  BYTE-FOR-BYTE unchanged. Path-secret detection/redaction is REJECTED as an
  upstream DLP concern, not Docline's responsibility.
* Docline's responsibility is limited to NOT re-emitting **structured access
  credentials** supplied to connect to a source: URL user-info, explicitly
  recognized credential query parameters, and typed config fields designated
  secret. These MUST NOT appear in Docline-generated metadata, stdout/logs,
  warnings, or errors.
* Useful source provenance and benign URL / query / path data are preserved.

### REJECTED alternatives (recorded with rationale)

1. **Arbitrary path-embedded secret redaction in `_sanitize_url`** (former Units
   C1/C2, H2/H2-C2 decode-before-segmentation grammar; tasks 073.005-T/073.006-T)
   — **REJECTED.** Rationale: (a) it required Docline to decode and re-interpret
   URL path content, which the operator scopes as an upstream DLP concern; (b) a
   marker-gated path matcher over-redacts benign endpoints such as
   `/authentication/overview`, `/keys/rotation`, and `/tokenizer/config`
   (cycle-3 P1 blocker #2); (c) per-layer percent-escape validation rejects valid
   terminal literal-percent data such as `/docs/100%25-off` (cycle-3 P1 blocker
   #3); (d) the direct path-secret milestone made the `073.002-T → 073.007-T`
   contract unsatisfiable without stream C (cycle-3 P1 blocker #1). Retired
   non-destructively (status=blocked, removed from shipment 064-S).
2. **Source-document body / content scanning for secrets** — **REJECTED.** Docline
   never inspects fetched document content for secrets; that is an upstream DLP
   responsibility. No such requirement is introduced anywhere in this plan.

### Executable scope after the revision

* **Concern A (KEPT)** — default (non-`--execute`) source-key sink: thread
  `sanitize_source_key(config)` into `create_staging_job`/`orchestrate_fetch`
  (073.001-T helper test; 073.007-T live-stdout integration test,
  narrowed to structured access credentials + benign-path preservation).
* **Concern B (KEPT)** — exact-match credential QUERY-parameter name expansion
  (073.003-T helper test; 073.008-T live-WARNING integration test,
  structured access credentials only).
* **Single merged production task** — both concerns are implemented by ONE atomic
  code task 073.002-T (A2 typed sink wiring + B2 exact-match vocabulary/decode across
  staging.py, orchestrate.py, source_keys.py); the final composition gate 073.009-T
  greens when it completes. Former separate stream-B code task 073.004-T is
  retired/merged into 073.002-T (2026-09-15 P0 green-gate fix).
* **Stream C (RETIRED/REJECTED)** — 073.005-T + 073.006-T removed from shipment.
* **Job-ID residual risk (RETAINED)** — H4/H4-C2 still applies: it concerns the raw
  `build_source_key` digest of structured access credentials (incl. low-entropy
  query `code`/`password` values), so it remains in force with its keyed-raw-source
  revisit trigger.

### Three cycle-3 P1 blockers — resolved by REMOVING the path requirement

The three P1 blockers recorded in
`docs/memory/2026-09-15/064-s-dark-factory-review-cap-halt.md` are resolved here by
DELETING the unjustified path work, NOT by inventing more path parsing:
(1) the unsatisfiable `073.002-T ↔ 073.007-T` path milestone — resolved by removing
the path-secret fixture and the `073.006-T` coupling from 073.007-T; (2) benign-path
over-redaction — resolved by never redacting paths; (3) literal-percent (`%25`)
rejection — resolved by removing all path percent-decoding.

### Rebuilt executable DAG (test-first only; acyclic; parent-first shipment)

> **SUPERSEDED by the top FINAL Operator Contract DAG (2026-09-15 P0 green-gate fix).**
> The prior two-code-task graph (073.001-T/073.007-T→073.002-T and
> 073.003-T/073.008-T→073.004-T) is replaced: the two code tasks are MERGED into the
> single production task 073.002-T. The authoritative graph below matches the top
> FINAL Operator Contract.

```text
073.001-T ──blocks──> 073.002-T   (concern A: helper test → merged code, test-first)
073.003-T ──blocks──> 073.002-T   (concern B: helper test → merged code, test-first)
073.007-T ──blocks──> 073.002-T   (concern A: live-stdout integration test → merged code, test-first)
073.008-T ──blocks──> 073.002-T   (concern B: live-WARNING integration test → merged code, test-first)
073.009-T ──blocks──> 073.002-T   (final A2+B2 composition gate → merged code, test-first)
```

Leaves (no upstream deps): 073.001-T, 073.003-T, 073.007-T, 073.008-T, 073.009-T. The
single merged production task 073.002-T greens all five test tasks together in one
atomic verifiable step. Former stream-B code task 073.004-T is retired/merged into
073.002-T; all stream-C edges (`073.006-T→073.005-T`, `073.006-T→073.004-T`,
`073.006-T→073.007-T`) are removed. The graph is acyclic and every edge is a genuine
test-first prerequisite.

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
| Default-path `metadata.source`/stdout must not carry credentials | Thread `sanitize_source_key(config)` into `create_staging_job` via keyword-only `sanitized_source` (H3) | A2 |
| `job_id` stays raw-`build_source_key`-derived (determinism; oracle residual accepted, H4) | Keep `make_job_id(source)` on the raw arg | A2 |
| Fallback must fail closed on compound keys, safe for bare strings (H3) | Keyword-only param; compound-key omission RAISES a typed non-leaking exception (no sentinel, no raw-key echo); bare-string `sanitize_source` retained only where it preserves paths + sanitizes structured userinfo/query creds | A2 |
| Typed non-credential provenance fields preserved (operator contract, Finding 3) | Typed sanitizer sanitizes URL + explicitly-secret fields; byte-preserves branch/path_glob/manifest ID/local path/include | A1, A2 |
| Prove the leak + all URL-bearing source kinds before fixing | Characterization test on default path (web_crawl, manifest_url, github_repo, manifest_git) | A1 |
| Additive coverage: explicit exact-match credential-name vocabulary (H1, Finding 1) | Replace the `startswith` heuristic with an explicit exact-match vocabulary; individually enumerate legacy/cloud variants; add password/pwd/passwd/code | B2 |
| Prove expanded coverage + no benign false positives (H1) | Parametrized tests incl. benign near-matches + percent-encoded marker | B1 |
| ~~Redact path-embedded secrets, fail-closed, benign paths intact (H2)~~ | **REJECTED — 2026-09-15 operator decision; `_sanitize_url` leaves URL paths byte-for-byte unchanged** | ~~C2~~ (retired) |
| ~~Prove path grammar exact outputs + fail-closed~~ | **REJECTED — retired with stream C** | ~~C1~~ (retired) |
| Ordinary URL paths preserved byte-for-byte (operator decision) | Assert benign paths (`/authentication/overview`, `/tokenizer/config`, `/keys/rotation`, `/docs/100%25-off`) unchanged in metadata.source/stdout | A1, AI |
| Vocabulary is not universally complete (Finding 7) | Enumerate existing names + auth_token/authorization + refresh_token/apikey/client_secret/x-goog-credential/awsaccesskeyid + password/pwd/passwd/code; record unknown/variant names as intentionally-unredacted accepted residual; benign prefix fixtures | B2, B1 |

> **Unit → task mapping (2026-09-15 P0 green-gate fix):** conceptual code Units **A2**
> and **B2** are BOTH delivered by the SINGLE MERGED production task **073.002-T**
> (files `staging.py`, `orchestrate.py`, `source_keys.py`). Test Units A1→073.001-T,
> B1→073.003-T, AI→073.007-T, BI→073.008-T, CI→073.009-T. Former separate stream-B code
> task 073.004-T is retired/merged into 073.002-T.

## Implementation Units

### Unit A1 — Characterization test: default-fetch credential sink (test domain)

* **Change:** Add a failing regression test asserting that `orchestrate_fetch` /
  `create_staging_job` produce an **in-memory** `metadata.source` (and a
  **reconstructed** `model_dump` JSON — the in-process shape, NOT the live
  `cli.py:381` stdout) free of userinfo and `?token=…` for all four URL-bearing
  source kinds. This is HELPER-level coverage only; the live `cli.py:381` stdout
  sink is asserted solely by Unit AI/`073.007-T` (cycle-3 finding F-01 removes A1's
  live-stdout overclaim and aligns A1's source kinds exactly to the same four the
  task and matrix use).
* **Files:** one test file under `tests/` (e.g. `tests/elt/test_orchestrate_redaction.py`).
* **Scenarios:** (1) web_crawl, (2) manifest_url, (3) github_repo, (4) manifest_git —
  each a credentialed URL on the default path (all four URL-bearing source kinds).
* **Posture:** characterization-first (must fail on current HEAD; helper-level
  in-memory assertion, does not invoke the live CLI).
* **Exit state:** test exists and fails on HEAD demonstrating the in-memory
  `metadata.source` leak; the live stdout leak is demonstrated by AI/`073.007-T`.

### Unit A2 — Thread typed sanitized key into `create_staging_job` (code domain) — part of merged 073.002-T

> **MERGED (2026-09-15 P0 green-gate fix):** Units A2 and B2 are delivered by the
> SINGLE production task **073.002-T**. The composition gate 073.009-T only greens once
> both userinfo (A2) and vocabulary (B2) land, so a single atomic code task is required
> for per-task green. Files below combine with B2's; the typed-preservation work also
> touches `src/docline/elt/source_keys.py`, and the error-output provenance-preservation
> work touches `src/docline/elt/execute.py` (four files total).

* **Change:** Add **keyword-only** `sanitized_source: str | None = None` to
  `create_staging_job` (declared after `*`, so it can never bind positionally).
  When set, `metadata.source = sanitized_source`. When `None`, apply the
  **fail-closed fallback (H3, revised per Finding 4)**: if `source` starts with a
  known COMPOUND source-key prefix (`web_crawl:`, `manifest_url:`, `github_repo:`,
  `manifest_git:`, `manifest_local:`, `local_file:`) **RAISE a typed, non-leaking
  exception** (e.g. `CredentialRedactionError`) whose `str()` echoes neither the raw
  key nor any credential substring — the whole-key sentinel fallback is REMOVED;
  otherwise use the existing `sanitize_source(source)` for genuine bare URL/path
  strings, retained only because that branch preserves URL paths byte-for-byte while
  sanitizing structured userinfo/query credentials. `job_id =
  make_job_id(source)` unchanged (raw). Update `orchestrate_fetch` to import
  `sanitize_source_key` and call
  `create_staging_job(build_source_key(config), staging_dir, sanitized_source=sanitize_source_key(config))`.
  Additionally, in `src/docline/elt/execute.py` the exception/log composition
  (`_scrub_exception_message` / `_exception_scrub_replacements` /
  `_sanitize_exception_text` / `_redact_query_param_fragments` /
  `_strip_reversed_query_credentials`, emitted through the `_log.exception(...)`
  WARNING/error sink) currently applies `sanitize_source_id` to `config.id` (manifest
  ID) and `_sanitize_exception_text` to `config.branch` / `config.path_glob`; these are
  PROVENANCE and MUST be byte-preserved in the composed WARNING/error text (operator
  contract, Finding 3 error-output extension). Change the composition to remove ONLY
  structured URL/typed credentials (userinfo + recognized query-param NAMES on
  `config.url`/`config.repo_url` + typed secret fields) while leaving branch /
  path_glob / manifest ID / local path / include byte-for-byte — even when they contain
  credential-looking text.
* **Files:** `src/docline/fetch/staging.py`, `src/docline/elt/orchestrate.py`,
  `src/docline/elt/source_keys.py`, `src/docline/elt/execute.py` (4 files — shared with
  B2 in the merged 073.002-T; source_keys.py carries the typed-field preservation of
  Finding 3; execute.py carries the WARNING/error error-output provenance preservation).
* **Functions:** `create_staging_job`, `orchestrate_fetch`, `sanitize_source_key` /
  `_sanitize_url_field` / `_remove_credential_query_params` (typed preservation),
  `_exception_scrub_replacements` / `_scrub_exception_message` / `_sanitize_exception_text`
  (execute.py error-output provenance preservation).
* **Posture:** test-first (A1 must pass after this change).
* **Exit state:** A1 passes; existing staging/execute tests still green
  (existing bare-string positional callers unaffected — keyword-only proof).

### Unit B1 — Tests: expanded credential-name coverage + exact-match grammar (test domain)

* **Change:** Add parametrized tests for `_is_credential_param`/`sanitize_source`
  proving the H1 grammar: the new names (`password`, `pwd`, `passwd`,
  `client_secret`, `refresh_token`, `code`) are redacted by case-insensitive
  EXACT match (incl. case-varied `Passwd`/`PASSWD`/`Refresh_Token`/`REFRESH_TOKEN`
  to prove case-insensitivity for `passwd`/`refresh_token`, not just `pwd`); the
  benign near-matches `tokenizer`, `keynote`, `secretary`, `authorship`, `signal`
  (legacy-marker false positives now correctly preserved after the startswith→exact
  change), `password_policy`, `pwd_length`, `client_secretary`, `codec`,
  `code_version` are NOT redacted, and the finding-#3 additions
  `passwd_file`/`refresh_token_ttl` plus case-varied variants of every benign
  near-match (`Password_Policy`, `PWD_Length`, `Client_Secretary`, `Codec`,
  `Code_Version`, `Passwd_File`, `PASSWD_HASH`, `Refresh_Token_TTL`,
  `REFRESH_TOKEN_EXPIRY`) are NOT redacted; the enumerated legacy/cloud vocabulary
  (`auth_token`, `token`, `api_key`, …) still redacts by EXACT match (coverage parity
  for real credential names after the startswith→exact change); percent-encoded new
  markers are redacted via the bounded query-NAME decode path on BOTH the string and
  typed sanitizers — `%70assword`→`password` (1 layer),
  `%2570assword`→`%70assword`→`password` (2 layers), a deeper still-valid layered case
  within the 5-layer cap, and an over-cap case (>5 layers still transforming) that
  fails closed — with no path or query-value decoding.
* **Files:** one test file under `tests/` (e.g. extend `tests/fetch/test_staging_sanitize.py`).
* **Scenarios:** parametrized (grouped: new-name exact redaction, benign
  near-match passthrough, existing-prefix additive, percent-encoded new marker).
* **Posture:** test-first (must fail on HEAD for the new coverage).
* **Exit state:** tests exist and fail on HEAD for the new coverage.

### Unit B2 — Expand credential vocabulary + exact-match new markers (code domain) — part of merged 073.002-T

* **Change:** Add `password`, `pwd`, `passwd`, `code` (and the intended additional
  legacy/cloud names `refresh_token`, `apikey`, `client_secret`, `x-goog-credential`,
  `awsaccesskeyid`) to the credential vocabulary. In `_is_credential_param`, apply the H1
  grammar (Finding 1): REPLACE the `startswith` heuristic with an explicit,
  case-insensitive, EXACT-match vocabulary; preserve the existing recognized names by
  INDIVIDUAL enumeration (token, access_token, key, api_key, secret, auth, sig,
  signature, x-amz-credential, x-amz-signature, x-amz-security-token, x-goog-signature),
  enumerate the names previously caught only by `startswith("auth")` to keep coverage
  (auth_token, authorization), and add the new/additional names above; match every name
  by case-insensitive EXACT equality (delimiter-`_` boundary rejected — see H1 benign
  fixtures). The vocabulary is NOT universally complete — unknown/variant names are
  intentionally not redacted (Finding 7, accepted residual). Apply the bounded query-NAME
  decode (≤5 layers, fail-closed over-cap) on BOTH the string and typed sanitizer paths
  (Finding 2). No path handling and no query-value decoding in this unit.
* **Files:** `src/docline/fetch/staging.py` (shared with A2 in the merged 073.002-T;
  the shared matcher is reused by `source_keys.py`).
* **Functions:** the credential-name vocabulary constant (data), `_is_credential_param`,
  and the shared bounded-decode matcher reused by `source_keys._is_credential_name`.
* **Posture:** test-first (B1 must pass after this change).
* **Exit state:** B1 passes; existing sanitizer and 059-S/063-S tests still green.

### Unit C1 — Tests: path-embedded secret redaction grammar (test domain) — REJECTED / RETIRED

> **REJECTED by the 2026-09-15 operator decision (task 073.005-T, status=blocked,
> removed from shipment 064-S). NOT executable.** The grammar below is a historical
> record only; ordinary URL paths are preserved byte-for-byte.

### Unit C1 (historical record)

* **Change:** Add parametrized tests for the H2/H2-C2 path-secret grammar against
  `_sanitize_url`/`sanitize_source`, asserting the exact expected outputs in the
  H2 + H2-C2 tables: `/token/SECRET`→`/token/<redacted>`; `/token=SECRET`→`/token=<redacted>`;
  case-insensitive `/Token/SECRET`; percent-encoded `/%74oken/SECRET`; a new-marker
  path `/client_secret/hunter2`→`/client_secret/<redacted>` (proves shared
  vocabulary from B); interior replacement `/a/token/SECRET/b`; benign
  `/api/v1/data` and `/codec/data` unchanged; **decode-before-segmentation cases
  (H2-C2, finding #1):** encoded-slash `/token%2FSECRET`→`/token%2F<redacted>`
  (and lowercase `/token%2fSECRET`), encoded-equals `/token%3DSECRET`→`/token%3D<redacted>`,
  nested `/%74oken%2FSECRET`→`/%74oken%2F<redacted>`, multilayer
  `/token%252FSECRET`→`/token%252F<redacted>`; **fail-closed cases:** malformed
  escape `/token%2/SECRET` and `/%ZZ/SECRET`→`<path-redacted>`, **nested per-layer
  malformed escapes (finding F-02)** `/token/%252`→`<path-redacted>` (`%252`→`%2`
  truncated after one decode layer) and `/token/%25ZZ`→`<path-redacted>`
  (`%25ZZ`→`%ZZ` after one layer) — proving escapes are validated after EVERY decode
  layer, over-cap (>5 decode
  layers)→`<path-redacted>`, unparseable/malformed URL→`<path-redacted>`;
  **`/token/` trailing-empty (findings #1/#9):** `/token/`→`/token/` unchanged
  (no non-empty adjacent value), and `/token//SECRET`→`/token//<redacted>`;
  trailing `/token` (no value) unchanged.
* **Files:** one test file under `tests/`.
* **Scenarios:** parametrized (grouped: marker=value, bare-marker+value,
  case/percent-encoding, benign passthrough, fail-closed).
* **Posture:** test-first (must fail on HEAD).
* **Exit state:** tests exist and fail on HEAD for path-secret coverage.

### Unit C2 — Path-embedded secret redaction in `_sanitize_url` with guards (code domain) — REJECTED / RETIRED

> **REJECTED by the 2026-09-15 operator decision (task 073.006-T, status=blocked,
> dependency edges removed, removed from shipment 064-S). NOT executable.**
> `_sanitize_url` MUST leave URL path components unchanged. The grammar below is a
> historical record only.

### Unit C2 (historical record)

* **Change:** Implement the H2/H2-C2 grammar in `_sanitize_url` (plus a small
  path-redaction helper) using   **decode-before-segmentation** (H2-C2, finding #1; iterative-validation
  refinement, finding F-02):
  (1) ITERATIVE malformed-escape validation → fail closed to `<path-redacted>` on any
  invalid `%`-escape, validated BEFORE EACH decode layer AND re-validated on the
  freshly-decoded string before the next layer (not only a single pre-first-decode
  scan; catches nested `%252`→`%2` and `%25ZZ`→`%ZZ` at the layer they surface);
  (2) bounded iterative percent-decode (≤5 layers), each layer gated by the step-1
  re-validation → fail closed on over-cap;
  (3) segment on `/` over the FULLY-DECODED path so encoded structural delimiters
  (`%2F`→`/`, `%3D`→`=`) are treated as boundaries, retaining a byte-span map back
  to the ORIGINAL raw bytes; (4) per-segment marker detection via the SHARED
  credential-name matcher (reuses B2's expanded vocabulary + exact-match — genuine
  dependency), redact `marker=value` values and bare-marker-associated NON-EMPTY
  following segments, preserve benign segments/separators and original encoded bytes
  byte-for-byte; `/token/` (empty adjacent value) stays unchanged; (5) fail closed
  to `<path-redacted>` on unparseable/unmappable input.
* **Files:** `src/docline/fetch/staging.py` (1 file).
* **Functions:** `_sanitize_url` + one path-redaction helper (≤2).
* **Posture:** test-first (C1 must pass after this change).
* **Exit state:** C1 passes; existing sanitizer and 059-S/063-S tests still green;
  strictly additive (never redacts a benign path).

### Unit AI — Integration test: live default-path stdout sink (test domain) — NARROWED to structured access credentials

> **NARROWED by the 2026-09-15 operator decision (task 073.007-T).** The direct
> path-embedded-secret fixture (former finding F-04) and the `073.006-T` coupling
> are REMOVED. AI now asserts only that URL user-info and recognized credential
> query params are absent from live stdout for all four URL source kinds, and that
> ordinary paths (`/authentication/overview`, `/tokenizer/config`, `/keys/rotation`,
> `/docs/100%25-off`) are preserved BYTE-FOR-BYTE. AI has NO upstream dependency and
> is fully satisfied by 073.002-T. The historical description below is retained but
> its path-secret fixture is void.

### Unit AI (073.007-T: structured-credential + benign-path preservation)

* **Change:** Add an integration test that invokes the LIVE `docline fetch` default
  (non-`--execute`) CLI entrypoint (via the project CLI test runner or subprocess)
  and asserts the REAL stdout emitted at `cli.py:381` contains no URL user-info and
  no recognized credential query params for a credentialed config of each of the four
  URL-bearing source kinds, AND that ordinary URL paths (`/authentication/overview`,
  `/tokenizer/config`, `/keys/rotation`, `/docs/100%25-off`) are preserved
  BYTE-FOR-BYTE. This backs the live-stdout (SO) userinfo/query invariant with an
  executable test instead of attributing live coverage to the helper-level A1. NO
  path-embedded-secret fixture is included — path-secret redaction is REJECTED by the
  2026-09-15 operator contract; the former finding F-04 direct path-secret fixture and
  the `073.006-T` coupling are VOID.
* **Files:** one test file under `tests/` (e.g. `tests/elt/test_fetch_cli_stdout_redaction.py`).
* **Scenarios:** parametrized over the four URL source kinds (userinfo/query surface)
  plus byte-for-byte benign-path-preservation assertions.
* **Posture:** characterization-first (FAILS on HEAD demonstrating the live stdout
  userinfo/query leak).
* **Exit state:** test exists, fails on HEAD; the userinfo/query + benign-path
  assertions are fully satisfied by `073.002-T` (NO upstream stream-C dependency). The
  recognized credential-NAME coverage across the A2+B2 composition is proven separately
  by the final composition gate `073.009-T`.

### Unit CI — Final live default-stdout A2+B2 composition gate (test domain; 073.009-T)

* **Change:** Add an integration test that invokes the LIVE `docline fetch` default
  (non-`--execute`) CLI entrypoint and asserts the REAL stdout is free of BOTH URL
  user-info (A2) AND EVERY recognized NEW credential query-param NAME in the explicit
  exact-match vocabulary (B2) — the full new set `password`, `pwd`, `passwd`,
  `client_secret`, `refresh_token`, `code`, `apikey`, `x-goog-credential`,
  `awsaccesskeyid`, including at least one percent-encoded query NAME (e.g.
  `%70assword`) — across the four URL-bearing source kinds, while ordinary paths and
  benign params are preserved byte-for-byte. This is the honest composition gate: it
  proves the A2+B2 composition that no single stream-scoped test proves alone.
* **Files:** one test file under `tests/` (e.g. `tests/elt/test_fetch_cli_stdout_composition.py`).
* **Scenarios:** parametrized over the four URL source kinds × (userinfo + EVERY
  recognized new name in the final vocabulary + at least one percent-encoded name).
* **Posture:** test-first (FAILS on HEAD; because A2 and B2 are the SINGLE merged
  production task 073.002-T, the userinfo AND credential-name assertions all go green
  together when 073.002-T lands — one atomic verifiable green state).
* **Dependencies:** genuine test-first prerequisite — `073.009-T` blocks the single
  merged production task `073.002-T`.
* **Exit state:** test exists, fails on HEAD; FULL green when the merged production task
  `073.002-T` (A2+B2) lands.

### Unit BI — Integration test: live WARNING/error sink new-name coverage (test domain; finding #2)

* **Change:** Add an integration test that drives the live WARNING/error emission
  path — the `execute.py` exception/log composition (`_scrub_exception_for_logging` →
  `_scrub_exception_message` / `_exception_scrub_replacements` /
  `_sanitize_exception_text` / `_redact_query_param_fragments`, plus the shared
  `source_keys._remove_credential_query_params` typed/059-S surface), capturing the
  emitted `_log.exception(...)` text — for EACH of the four URL-bearing source kinds
  (WebCrawlSource, ManifestUrlSource, GitHubRepoSource, ManifestGitSource) and asserts
  (a) the FULL new credential vocabulary
  (`password`/`pwd`/`passwd`/`client_secret`/`refresh_token`/`code`/`apikey`/
  `x-goog-credential`/`awsaccesskeyid`) is dropped from the emitted text on each, and
  (b) the composition BYTE-PRESERVES non-credential provenance — source `branch`,
  `path_glob`, manifest `id`, local filesystem `path`, and `include` patterns — even
  when those fields contain credential-looking text, removing only structured URL
  userinfo + recognized credential query-param NAMES + typed secret fields. This backs
  the live-WARNING (WE) invariant AND the error-output provenance-preservation invariant
  with an executable test instead of attributing live coverage to the helper-level B1,
  and gives explicit all-four coverage matching the four matrix rows that attribute BI to
  each (cycle-3 finding F-03).
* **Files:** one test file under `tests/` (e.g. extend the 059-S WARNING-path test module).
* **Scenarios:** parametrized over the nine new credential names × the four
  URL-bearing source kinds, plus provenance byte-preservation assertions (one logical
  live-sink surface; within the 2-hour test-domain boundary, one test file, finding F-03).
* **Posture:** characterization-first (FAILS on HEAD for the new names and/or altered
  provenance; green after the merged 073.002-T).
* **Exit state:** test exists, fails on HEAD, passes after the merged production task `073.002-T`.

## Dependency Graph (no cycles)

> **RECONCILED to the top FINAL Operator Contract DAG (2026-09-15 P0 green-gate fix).**
> The two former code tasks 073.002-T (A2) and 073.004-T (B2) are MERGED into the single
> production task 073.002-T; 073.004-T is retired/merged (status=blocked, edges removed,
> out of shipment). Stream C (073.005-T/073.006-T) is REJECTED/retired and out of the
> graph. The authoritative executable DAG is below and matches the top FINAL Operator
> Contract section exactly.

```text
A1 ──blocks──> A2/B2 (073.002-T)   (concern A helper test → merged code, test-first)
B1 ──blocks──> A2/B2 (073.002-T)   (concern B helper test → merged code, test-first)
AI ──blocks──> A2/B2 (073.002-T)   (concern A live-stdout userinfo subset → merged code, test-first)
BI ──blocks──> A2/B2 (073.002-T)   (concern B live-WARNING subset → merged code, test-first)
CI ──blocks──> A2/B2 (073.002-T)   (final A2+B2 composition gate → merged code, test-first)
```

Backlog IDs: A1=`073.001-T`, B1=`073.003-T`, AI=`073.007-T` (concern A live-stdout
integration test), BI=`073.008-T` (concern B live-WARNING integration test),
CI=`073.009-T` (final A2+B2 composition gate), merged code = `073.002-T`. Retired/out of
graph: `073.004-T` (merged into 073.002-T), `073.005-T`/`073.006-T` (stream C rejected).

* `073.002-T depends_on 073.001-T` (test-first: in-memory sink + typed-field preservation)
* `073.002-T depends_on 073.003-T` (test-first: exact-match vocabulary + bounded decode)
* `073.002-T depends_on 073.007-T` (test-first: the live default-path stdout
  integration test — real `cli.py:381` sink — is green only after the merged code routes
  through `sanitize_source_key`)
* `073.002-T depends_on 073.008-T` (test-first: the live WARNING/error integration
  test — real `_remove_credential_query_params` sink — is green only after the merged
  code adds the new credential names)
* `073.002-T depends_on 073.009-T` (test-first: the final A2+B2 live default-stdout
  composition gate is green only after the merged code lands both userinfo and vocabulary)

All five test tasks (`073.001-T`, `073.003-T`, `073.007-T`, `073.008-T`, `073.009-T`)
have no upstream dependencies (authored first, characterization/test-first: all FAIL on
HEAD demonstrating the leak, then go GREEN together when the single merged production
task `073.002-T` lands). Every edge is a genuine test-first prerequisite; no
execution-ordering-only edge is introduced.

**Merge rationale (P0 green-gate fix):** the composition gate `073.009-T` only greens
once BOTH userinfo redaction and the expanded vocabulary land, so two separate code
tasks could not each produce a green suite (a per-task-green / test-first violation).
Merging A2+B2 into one atomic production task makes every test task green in a single
verifiable step. Width isolation yields to the stronger per-task-green invariant; the
merged task remains a single cohesive credential-redaction domain.

The graph is acyclic and every edge is test-first or a genuine behavioral
prerequisite.

## Decisions and Rationale

* Reuse the 063-S typed sanitizer (`sanitize_source_key`) rather than re-parse
  compound prefixes in the string sanitizer — proven contract, preserves job_id
  determinism, minimal blast radius (1 production caller).
* Keep the two executable streams width-isolated: A never touches the credential-name
  vocabulary; B only touches the credential-name vocabulary + matcher (query names on
  both sanitizer paths). Neither stream touches URL path handling — ordinary paths are
  preserved byte-for-byte (path redaction is REJECTED/retired, operator contract).
* Explicit exact-match credential-name vocabulary (H1, Finding 1) keeps the expansion
  strictly additive for real credential names while eliminating the legacy
  `startswith` false positives (tokenizer/keynote/secretary/authorship/signal etc.)
  without benign corruption.
* Keyword-only `sanitized_source` whose compound-key omission RAISES a typed
  non-leaking exception (H3, Finding 4) removes both the positional-binding ambiguity
  and the known unsafe no-op-on-compound-key path — without a whole-key sentinel.

## Risks and Caveats

* Signature change to a shared helper — mitigated by a single production caller,
  keyword-only placement (proven positional compatibility), and a defaulted
  parameter.
* Shared `_is_credential_param` expansion affects the 059-S WARNING path and the
  063-S execute path — intended and additive; regression-tested.
* New-name false positives — mitigated by exact-equality matching + explicit
  benign near-match tests (`password_policy`, `pwd_length`, `client_secretary`,
  `codec`, `code_version`).
* Path preservation replaces path-secret redaction — ordinary URL paths are left
  byte-for-byte unchanged (2026-09-15 operator decision; former marker-gated H2
  path redaction REJECTED and retired), verified by benign-path regression
  assertions in A1/073.001-T and AI/073.007-T.
* Deterministic raw-source `job_id` confirmation-oracle — accepted narrowly-reasoned
  residual risk (H4/H4-C2; still applies to the raw structured access credentials in
  the source key); not remediated to preserve cross-path determinism/cache
  stability.

## Runtime Verification and Closure

* **Changed runtime surface:** `docline fetch` CLI (default path) stdout and the
  in-memory `SourceMetadata.source`; the shared sanitizer used by execute-path
  `metadata.json` and WARNING-path logs.
* **Runtime verification (must prove before absorbed):**
  1. `docline fetch` (default, non-`--execute`) over a config with a credentialed
     `web_crawl`, `manifest_url`, `github_repo`, or `manifest_git` URL emits stdout
     JSON whose `metadata.source` contains no userinfo and no credential query
     params, while ordinary URL path components remain byte-for-byte unchanged
     (2026-09-15 operator decision: no path redaction).
  2. `job_id`/`cache_path` for a given config are byte-identical before and after A2
     (determinism preserved; H4 confirmation-oracle residual accepted).
  3. Existing execute-path (`--execute`) and 059-S WARNING-path behavior unchanged
     except for the additive query-name redaction from B2.
* **Operational closure:** regression tests A1/B1 plus the live integration
  tests 073.007-T (stdout userinfo subset), 073.009-T (stdout A2+B2 composition), and
  073.008-T (WARNING full vocabulary + provenance preservation) become the standing
  guards; no data migration and no persisted-state format change (pure code + tests).
  Remediation on regression is SAFE CONTAINMENT + ROLL-FORWARD (see the trigger below),
  NOT a revert to the already-shipped 063-S behavior (which still carries the known
  default-path credential leak this shipment closes). Owner: ELT staging maintainer.
  Validation window: one green CI run on the shipment PR.
* **Post-release synthetic observation window (credential-safe) — concrete window,
  owner, cadence:** Window = **7 calendar days OR the first 10 production ELT-staging
  runs after merge, whichever comes first.** Owner = **ELT staging maintainer**
  (security on-call as backup). Cadence = **one scheduled synthetic probe run per day
  AND one per production run within the window** (at minimum the daily run). Each probe
  runs a SYNTHETIC `docline fetch` (default, non-`--execute`) over a fixture config whose
  URLs carry KNOWN SYNTHETIC credentials (synthetic userinfo + every recognized
  credential query-param NAME in the final vocabulary + one percent-encoded name)
  alongside benign provenance fields (branch / path_glob / manifest ID / local path /
  include), and asserts (a) the emitted stdout / metadata / WARNING-error text contains
  NONE of the known synthetic credential tokens, and (b) the benign provenance fields are
  emitted byte-for-byte. The probe NEVER logs, echoes, or stores raw source credentials
  or raw source keys — it asserts ABSENCE of pre-known synthetic tokens and emits only a
  boolean/count result (pass = zero tokens observed), so no real or synthetic secret is
  ever written to logs.
* **Containment / roll-forward trigger (SAFE — never restores the known leak):** the
  trigger fires ONLY on the boolean probe result and the incident signal (never on or
  emitting raw secret values). If the synthetic probe observes ANY known credential token
  in stdout / metadata / WARNING-error text (probe FAILS), OR a production incident
  reports a credential in Docline-generated output, DO NOT revert to the 063-S behavior —
  reverting the merged production commit would REINTRODUCE the already-known default-path
  credential leak (0F1A653C) this shipment closes, which is itself the incident
  condition. Instead follow this SAFE CONTAINMENT + ROLL-FORWARD procedure:
  1. **Stop the affected fetch execution** — halt/disable the ELT-staging fetch path(s)
     for the affected source kind(s) so no further credential-bearing output is emitted.
  2. **Revoke / rotate the possibly-exposed credentials** — treat any credential that may
     have reached a sink as compromised and rotate it out of band (operational security
     action, not a code change).
  3. **Suppress the leaking sink immediately** — omit the affected source field from the
     Docline-generated output, OR deploy a SAFE WHOLE-FIELD REDACTION HOTFIX that replaces
     the ENTIRE offending field with a non-leaking placeholder (never a partial redaction
     that could still leak), closing the leak forward while preserving availability.
  4. **Preserve the tests** — the five test tasks (073.001-T, 073.003-T, 073.007-T,
     073.008-T, 073.009-T) and their assertions are RETAINED as standing regression
     guards and NEVER reverted; add a new failing regression reproducing the observed
     leak.
  5. **Roll forward** — fix the defect on top of the current tree (re-open 073-F or a
     follow-up shipment), make the new + existing tests green, and re-run the synthetic
     probe to confirm zero tokens before re-enabling the fetch path. NEVER restore the
     known default-path leak (063-S behavior) as a rollback destination.

  **Disposition of all five test tasks under containment/roll-forward:** all five
  (073.001-T helper sink + typed-field preservation; 073.003-T vocabulary + bounded
  decode; 073.007-T live-stdout userinfo subset; 073.008-T live-WARNING full vocabulary +
  provenance preservation; 073.009-T live-stdout A2+B2 composition) are PRESERVED as
  standing guards and roll forward with the fix — none is reverted, disabled, or removed.

## Source-Kind x Sink Test Matrix (finding P1-2)

This matrix declares exactly which (source-kind x sink) cells THIS shipment's
tasks test, distinguishing **helper/unit-level** coverage (A1, B1, C1 exercise
functions directly) from **live-sink integration** coverage (AI=073.007-T,
BI=073.008-T drive the real emission points) — no live sink is attributed to a
helper-only test (finding #2). Sinks: **M** = typed sanitization output
(`sanitize_source_key`); **PM** = execute-path persisted `metadata.json`;
**SO** = default CLI stdout (`cli.py:381`); **WE** = live WARNING/error text
(execute.py `_scrub_exception_for_logging` composition — `_scrub_exception_message` /
`_exception_scrub_replacements` / `_sanitize_exception_text` /
`_redact_query_param_fragments` — over the shared
`source_keys._remove_credential_query_params` surface); **EX** = exceptions/causes/contexts.

| Source kind | M | PM | SO (live) | WE (live) | EX |
|---|---|---|---|---|---|
| WebCrawlSource (userinfo + `?token=`) | inherited-063-S; A1 in-memory metadata.source + reconstructed `model_dump` JSON (helper) | inherited-063-S | **073.007-T** (userinfo subset) + **073.009-T** (A2+B2 composition) — live `cli.py:381` | **BI/073.008-T** (live WARNING, full new vocabulary + provenance byte-preservation, all four kinds); B1 matcher (helper unit) | n/a — no throw on this path |
| ManifestUrlSource (userinfo + `?token=`) | inherited-063-S; A1 in-memory metadata.source + reconstructed `model_dump` JSON (helper) | inherited-063-S | **073.007-T** (userinfo subset) + **073.009-T** (A2+B2 composition) — live `cli.py:381` | **BI/073.008-T** (all four kinds); B1 helper | n/a |
| GitHubRepoSource (token in `repo_url`) | inherited-063-S; A1 in-memory metadata.source + reconstructed `model_dump` JSON (helper) | inherited-063-S | **073.007-T** (userinfo subset) + **073.009-T** (A2+B2 composition) — live `cli.py:381` | **BI/073.008-T** (all four kinds); B1 helper | n/a |
| ManifestGitSource (token in `url`) | inherited-063-S; A1 in-memory metadata.source + reconstructed `model_dump` JSON (helper) | inherited-063-S | **073.007-T** (userinfo subset) + **073.009-T** (A2+B2 composition) — live `cli.py:381` | **BI/073.008-T** (all four kinds); B1 helper | n/a |
| ~~Path-embedded secret (any URL kind)~~ | — | — | **REJECTED / RETIRED (2026-09-15 operator decision)** — Docline does NOT redact URL paths; ordinary paths are preserved byte-for-byte. AI/073.007-T instead asserts benign-path preservation. Former C1/C2 path grammar retired. | — | n/a |
| LocalFileSource / ManifestLocalSource | local path / include patterns / manifest ID preserved byte-for-byte (operator contract, Finding 6); only explicitly-secret typed fields redacted (none present) | 063-S | n/a | n/a | n/a |

Notes and honest scope boundaries:

* **A1** (helper) exercises the DEFAULT path (`orchestrate_fetch`→`create_staging_job`)
  for all four URL-bearing source kinds and asserts the in-memory `metadata.source`
  (**M** as emitted on the default path) and a reconstructed `model_dump` JSON are
  credential-free after A2. Both A1 assertions are HELPER-level (**M** column); A1
  does NOT invoke the live CLI, so it is NOT credited in the **SO** column at all
  (cycle-3 finding F-01 removes A1's prior SO/reconstructed-JSON attribution and
  removes its live-stdout wording). The live **SO** sink is covered by
  **073.007-T** (the stream-A userinfo subset) and **073.009-T** (the A2+B2
  composition — userinfo + all recognized new credential query-param names), both of
  which invoke the real `docline fetch` entrypoint and assert the actual `cli.py:381`
  stdout. A1's source kinds are aligned exactly to the same four these tests and the
  matrix use. On the default path `create_staging_job` does
  NOT write `metadata.json`, so **PM** is NOT a live default-path sink — the
  persisted-metadata column is covered by 063-S on the execute path and is not
  re-tested here (not overclaimed).
* **Path-embedded-secret SO — REJECTED / RETIRED (2026-09-15 operator decision):**
  the former direct path-secret fixture in AI/073.007-T and the `073.006-T` coupling
  are REMOVED. Docline does not redact URL paths; AI/073.007-T instead asserts that
  ordinary paths (`/authentication/overview`, `/tokenizer/config`, `/keys/rotation`,
  `/docs/100%25-off`) are preserved byte-for-byte. The former C1/C2 grammar is retired.
* GitHubRepoSource/ManifestGitSource default-path emission is sanitized because A2
  routes ALL source kinds through `sanitize_source_key` (which already sanitizes
  those prefixes). This is a beneficial consequence of A2, TESTED at the live stdout
  sink by AI/073.007-T. It does NOT close the separate, still-active archived entry
  `79BF0AEC` (the STRING sanitizer's `github_repo:` pass-through when
  `sanitize_source` is called directly on a raw compound string) — that path is
  bypassed on the default path after A2 and remains out-of-scope P-021 work.
* **WE** (live WARNING/error text) is backed by **BI/073.008-T**, which drives the
  real `execute.py` exception/log composition (`_scrub_exception_for_logging` →
  `_scrub_exception_message` / `_exception_scrub_replacements` /
  `_sanitize_exception_text` / `_redact_query_param_fragments`) over the shared
  `source_keys._remove_credential_query_params` matcher, emitted through the
  `_log.exception(...)` sink, for all four URL-bearing source kinds (cycle-3 finding
  F-03: explicit all-four coverage matching the four matrix rows). It asserts BOTH that
  the FULL new vocabulary
  (`password`/`pwd`/`passwd`/`client_secret`/`refresh_token`/`code`/`apikey`/
  `x-goog-credential`/`awsaccesskeyid`) drops from that path AND that non-credential
  provenance — `branch` / `path_glob` / manifest `id` / local `path` / `include` — is
  BYTE-PRESERVED in the composed text (error-output provenance-preservation finding).
  The `execute.py` composition INDEPENDENTLY applies `sanitize_source_id` /
  `_sanitize_exception_text` to `config.branch` / `config.path_glob` / `config.id`, so
  the provenance-preservation change lands in the single merged production task
  073.002-T (execute.py is the 4th file in its scope). B1 is a helper unit test of the
  shared `_is_credential_param` matcher; it is NOT credited with the live WARNING sink
  (finding #2 — no live coverage attributed to helper-only
  tests).
* **EX** (exceptions/causes/contexts): the exception cause/context CHAIN scrubbing
  (`_clone_scrubbed_exception`, PEP-678 `__notes__`, ExceptionGroup traversal) is a
  separate, currently-unreachable 063-S residual (`95BD0DC7`, `709BDB53`) and is
  explicitly NOT tested or claimed by this shipment. EX (the exception object's
  cause/context chain) stays honestly `n/a`. NOTE: this is distinct from the WE column
  — the exception MESSAGE composition that feeds the `_log.exception(...)` WARNING/error
  TEXT (`_scrub_exception_message`) IS in scope for provenance byte-preservation and is
  tested by BI/073.008-T; the EX `n/a` refers only to the unreachable cause/context
  chain-object scrubbing, not to the reachable message-composition sink.
* **Processed-document `source` / `source_url` consumers (exposure inventory — recorded
  disposition):** beyond the ELT-staging sinks above, the PROCESS stage
  (`src/docline/app.py`) independently emits a fetched-URL–derived
  `source_url` into processed-document output metadata — `_extract_source_url(source)`
  (app.py:84), `base_data["source_url"]` for `WebFrontmatter` auto-routing
  (app.py:346–347), and `manifest_entry["source_url"] = page_metadata.get("page_url")`
  (app.py:1017–1019) — and `schema/library.py` defines a validated `source_url` field.
  These consume the fetched page/canonical URL for provenance. DISPOSITION for this
  shipment (064-S/073-F): **OUT OF SCOPE — recorded exposure, not remediated here.**
  Rationale: 064-S/073-F is bounded to the ELT-staging default-fetch sink + credential
  query-name vocabulary (structured-access-credential redaction on the staging paths).
  The processed-document `source_url` path is a DISTINCT sink surface (PROCESS stage,
  different module, different emission point) whose credential-exposure risk depends on
  whether upstream page URLs carry userinfo/credential query params; redacting it would
  be different-contract work under P-021, not a same-contract completion of this
  shipment. It is inventoried here for exposure completeness and flagged for a separate
  P-021 follow-up entry; this shipment neither claims to cover it nor silently ignores
  it. No product boundary is widened by recording it.

## Constitution Check

Mapping this plan against the workspace constitution
(`.github/instructions/constitution.instructions.md`) and the governing workflow
policies. Added in remediation cycle 2 (finding #6).

### Applicable principles (satisfied)

| Principle | How this plan complies |
|---|---|
| I. Safety-First Python | New `sanitized_source: str \| None` is type-hinted and keyword-only; no new untyped surfaces; ruff-clean expectation carried into the code ACs; fail-closed **typed exceptions** (not whole-key sentinels) on compound-key omission. |
| II. Test-First Development (NON-NEGOTIABLE) | The single merged production code task 073.002-T is gated by ALL five preceding test tasks via `blocks` edges (2026-09-15 P0 green-gate fix): 073.001-T/073.003-T/073.007-T/073.008-T/073.009-T → 073.002-T. Tests must fail on HEAD (red) before code (green), and the whole suite greens together in one atomic step when 073.002-T completes (per-task-green satisfied). Enforces P-002/P-004. (Former separate stream-B code task 073.004-T is merged into 073.002-T; the former stream-C edges are removed with the retired path work.) |
| III. Workspace Isolation & Security Boundaries | The plan's entire purpose is preventing credential leakage into stdout/logs/metadata; no secrets are placed in committed files; fixtures use synthetic credentials. |
| IV. CLI Workspace Containment (NON-NEGOTIABLE) | All Stage edits are confined to the repo working tree (`docs/`, `.backlogit/`); no writes outside cwd. |
| V. Structured Observability | Deliberation, plan, task ACs, session memory, and intercom-style broadcasts provide traceable records; TOOL_DEGRADED markers recorded for degraded review dispatch. |
| VI. Single Responsibility | No new runtime dependency (bounded query-name decode uses stdlib `urllib.parse.unquote` already in use); two width-isolated streams keep each change single-purpose. |
| VII. Destructive Command Approval (NON-NEGOTIABLE) | No destructive action exists in this plan; strict-safety classification records ActionRisk=high, not destructive. Stash duplicate-disposition (if any) uses archive, never destructive removal. |
| VIII. Explicit Safety Modes for Elevated Risk | Operator authorized this exact 064-S scope via DARK_MODE_ACTIVE; merge-preauthorization=false and admin-fallback=false remain in force; ActionResult=`approved` (not executed by Stage). |
| IX. Git-Friendly Persistence | Backlog artifacts are file-backed Markdown/JSONL reconciled via `backlogit sync`; plan/deliberation/memory are plain Markdown. |
| X. Agent Context Efficiency | Session memory checkpoints (cycle-1 + cycle-2) capture state for resumption; no context bloat introduced. |

### Governing policies (satisfied)

* **P-001 / P-010 role separation & boundary** — Stage authored only planning/backlog
  artifacts; no product/test code written, no build/PR/merge/shipment-claim/Ship
  invocation. Stage committed its own planning/backlog artifacts on `chore/stage-064-s` (Finding 8).
* **P-003 decomposition chain** — source (deliberation) → plan → feature 073-F →
  tasks with ≥1 acceptance criterion each (validated in Step 5.0 re-run).
* **P-005 gate discipline** — no gate bypass; plan-review re-entered per the cycle
  budget; no `skip_plan`/`skip_review`.
* **P-006 plan hardening** — hardening was required (security signal) and is present
  (threat model, trust boundaries, strict-safety classification, verification
  criteria, H1–H5 + cycle-2 H2-C2/H4-C2).
* **P-016 single worktree** — single branch `chore/stage-064-s`, single worktree; no
  parallel implementation worktree.
* **P-021 deferred-scope-expansion** — both source entries carried the marker; forced
  deliberate route honored; duplicate detection clean; late-identifier reconciliation
  recorded; cycle-2 findings resolved as same-contract completions, none deferred.

### Non-applicable principles

* **XI. Merge Commit History Preservation (NON-NEGOTIABLE)** — governs merge
  execution (P-009), which is **Ship's** responsibility. Stage performs no merge, so
  this principle does not bind Stage's output here; it is flagged for Ship at PR time.

### Justified residual risk / deviations

* **Raw-source `job_id` confirmation-oracle (H4/H4-C2)** — accepted narrowly-reasoned
  residual risk: deriving `job_id` from the sanitized key would break cross-path
  determinism (invariant 2), force cache migration, and risk cache-poisoning. Cycle-2
  H4-C2 records the low-entropy dictionary-confirmation limitation, exposure
  assumptions, and an explicit rollback/revisit trigger; cycle-3 (finding F-05)
  corrects that trigger to a **keyed construction over the RAW canonical source key**
  (HMAC over `build_source_key(config)`, NOT the sanitized key — which would retain
  same-structure collisions) with explicit key-management and cache-migration
  requirements. No other deviation. This is
  the sole residual; no principle is violated.
* **Four-file single production task (granularity deviation, documented)** — the merged
  production task 073.002-T spans FOUR files (`staging.py`, `orchestrate.py`,
  `source_keys.py`, `execute.py`), exceeding the nominal <3-file granularity guideline.
  This is a deliberate, operator-mandated deviation on the SAME rationale as the A2+B2
  merge: the live composition gates 073.008-T (WARNING/error, execute.py provenance) and
  073.009-T (stdout A2+B2) can only each reach an atomic verifiable green state after the
  single production task lands, so splitting the execute.py provenance-preservation change
  into a separate task would violate the stronger per-task-green (P-002/P-004) invariant.
  The change remains one cohesive credential-redaction domain (structured-credential
  removal + provenance byte-preservation across the shared sanitizer + error-output
  composition surface). Size M / Complexity medium; still bounded.

## Plan Hardening Signals (REQUIRED)

* public API / schema / contract change — **absent for public API** (internal
  helper signature only; the new `sanitized_source` is keyword-only and defaulted,
  no persisted-format or public API change), but note the internal
  `create_staging_job` signature does change (keyword-only param added, H3) — a
  shared-helper contract change gated by tests + review.
* security / auth / permission / compliance-sensitive behavior — **PRESENT**
  (credential redaction correctness on live fetch paths; the whole point of the work).
* migration / backfill / destructive / irreversible step — **absent** (no data or
  config migration; no destructive action).
* external integration / operator checkpoint / external dependency — **absent**.
* high runtime / rollout / rollback risk — **absent** (pure code + tests; no
  persisted-format/schema change). Note: remediation-on-regression is SAFE
  CONTAINMENT + ROLL-FORWARD, not a revert to the 063-S behavior (which still carries
  the known default-path leak); see `## Runtime Verification and Closure`.

Conclude: **Requires plan hardening: yes** (security/compliance-sensitive signal present).

## Plan Hardening

**Hardening required?** Yes — the "security/compliance-sensitive behavior" signal is
present (credential-redaction correctness on live fetch paths). Hardening focuses on
threat modeling, trust boundaries, and verification depth; there are no destructive or
migration actions to harden.

### Learnings / instructions consulted

* `docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-closure.md` (063-S
  closure narrative — established the typed-sanitizer contract and recorded both
  deferrals in its "Reconciled Deferred Findings" table; published with closure
  PR #200; the 063-S implementation itself merged as PR #199 at HEAD `f1f5f8f`).
* `docs/memory/2026-09-12/stage-195-cycle6-copilot-remediation-memory.md` and
  `docs/memory/2026-09-12/stage-195-cycle7-copilot-remediation-memory.md`
  (path-secret = 06A59B1D; web_crawl/manifest_url URL fields already covered on
  the typed path; both deferrals genuinely distinct).
* `.github/instructions/strict-safety.instructions.md` (risky-action classification).
* In-repo pattern: `execute.py:_execute_single_source` (the proven raw-job_id +
  sanitized-metadata split to mirror).

### Threat model & trust boundaries

* **Asset:** source credentials embedded in ELT source configs — URL userinfo
  (`user:pass@`), credential query params (`?token=`, `?password=`, …), and
  path components are NOT redacted (2026-09-15 operator decision: ordinary URL paths
  preserved byte-for-byte; path-secret detection is an upstream DLP concern).
* **Trust boundary crossed:** in-process typed `SourceConfig` (trusted, may contain
  secrets) → serialized `SourceMetadata.source` that crosses to **stdout/console**
  (cli.py:381), **logs**, and (execute path) **on-disk `metadata.json`**. Everything
  past that boundary is untrusted-observer territory (terminal capture, CI logs,
  shipped artifacts).
* **Attack/leak vectors addressed:**
  1. Default-path stdout leak via unsanitized `metadata.source` (0F1A653C) — closed by A2.
  2. Credential query params outside the current prefix set
     (`password`/`pwd`/`passwd`/`client_secret`/`refresh_token`/`code`/`apikey`/
     `x-goog-credential`/`awsaccesskeyid`) surviving
     redaction (06A59B1D) — closed by B2 (both string + typed paths, shared
     `_is_credential_param`; exact-match new markers per H1).
  3. ~~Path-embedded secrets surviving `_sanitize_url` (06A59B1D)~~ — **REJECTED /
     OUT OF SCOPE (2026-09-15 operator decision):** path-embedded secret detection is
     an upstream DLP concern; Docline leaves URL path components unchanged. Former
     stream C (C2 marker-gated path redaction) retired. Only structured access
     credentials (userinfo + recognized query params + typed secret fields) are
     redacted.
* **Non-goals / explicitly out of scope (P-021, left stashed):** underscore-scheme
  regex gap (E89DC095), Unicode-Cf whitespace guard (9D44B6F3), query-function
  redundancy (E7878B1B), compound-prefix scheme matching in the string sanitizer.

### Risky-action classification (strict-safety)

* **ProposedAction:**
  * `summary` — modify credential-redaction control code on the live default and
    shared ELT fetch paths (default-path sink threading, credential-name
    vocabulary/matcher expansion, and error-output provenance preservation on the
    execute.py WARNING/error composition). Path-embedded secret redaction is
    REJECTED/retired (2026-09-15 operator decision) and is NOT part of this action.
  * `targets` — `src/docline/fetch/staging.py`, `src/docline/elt/orchestrate.py`,
    `src/docline/elt/source_keys.py`, `src/docline/elt/execute.py` (4 files),
    and new tests under `tests/`; runtime surfaces: `docline fetch` default-path
    stdout, in-memory `SourceMetadata.source`, the shared sanitizer used by the
    execute-path `metadata.json` and the 059-S / execute.py WARNING/error text.
  * `change_kind` — local edit to security-sensitive control code (no migration,
    no destructive step, no external call).
  * `rollback` / containment — pure code + tests, no persisted-format or schema
    change. Containment on regression is SAFE ROLL-FORWARD, NOT a revert to 063-S:
    reverting the merged production commit would REINTRODUCE the known default-path
    credential leak (0F1A653C) this shipment closes, so revert-to-063-S is explicitly
    PROHIBITED as a rollback destination. On a post-merge regression follow the safe
    containment + roll-forward procedure in `## Runtime Verification and Closure` (stop
    the affected fetch, revoke/rotate possibly-exposed credentials, suppress/omit the
    sink or deploy a safe whole-field redaction hotfix, preserve the five test guards,
    then roll forward). Cache paths/`job_id` are unchanged (H4 determinism guard), so no
    cache migration is needed. Blast radius is contained to the sanitizer + error-output
    composition surface; additive-only redaction means a partial landing can only redact
    more, never less — and never re-exposes a credential.
  * `approval_required` — yes for execution (security-sensitive, ActionRisk high).
* **ActionRisk:** **high** — security/credential-redaction-correctness behavior on
  live fetch paths (per the strict-safety "high" level: security/compliance-
  sensitive). Not `destructive` (no deletes/force/irreversible steps).
* **Approval / ActionResult:** **`approved`** — the operator authorized execution
  of this exact 064-S scope by invoking **dark factory mode**
  (`DARK_MODE_ACTIVE`, scope = 064-S). This authorizes the work to proceed to
  Ship; it is NOT a merge or admin authorization: **merge preauthorization =
  false** and **admin fallback = false** remain in force. Execution itself is
  Ship's responsibility (Stage does not build, run, or merge), so from Stage's
  vantage the ActionResult is `approved` (approved, not yet executed). Valid
  strict-safety states referenced: `planned` → `approved` (here) → `applied` /
  `rolled-back` (recorded by Ship at execution/closure time).
* No destructive, migration, or irreversible actions exist in this plan.

### Verification criteria proving credentials cannot reach any sink

The following MUST all hold (they are the acceptance backbone of A1/B1 and the
runtime checks; the exact grammars and expected outputs are specified in the top
FINAL Operator Contract and the deliberation's H1):

1. **Metadata:** for every URL-bearing source kind (WebCrawlSource,
   ManifestUrlSource, GitHubRepoSource, ManifestGitSource),
   `StagingJob.metadata.source` contains no userinfo and no credential query-param
   values (incl. the newly covered names) — on the default path (this shipment)
   and, inherited from 063-S, the execute path. Ordinary URL PATH components are
   preserved byte-for-byte (2026-09-15 operator decision: no path redaction; the
   former "no path-embedded secret" clause is REJECTED).
2. **stdout (live sink):** the `docline fetch` (default) JSON printed at cli.py:381
   contains no userinfo and no credential query-param values (incl. the newly
   covered names) for a credentialed config (all four URL source kinds) — backed by
   073.007-T (userinfo subset) and the 073.009-T A2+B2 composition gate (not a
   helper-only assertion).
3. **Logs / error text (live sink):** the shared `_is_credential_param` expansion
   propagates to the typed WARNING/error-scrub path
   (`_remove_credential_query_params`) and to the `execute.py` exception/log
   composition (`_scrub_exception_message` / `_exception_scrub_replacements` /
   `_sanitize_exception_text`), so error/log text drops the FULL new vocabulary
   (`password`/`pwd`/`passwd`/`client_secret`/`refresh_token`/`code`/`apikey`/
   `x-goog-credential`/`awsaccesskeyid`) AND byte-preserves non-credential provenance
   (`branch` / `path_glob` / manifest `id` / local `path` / `include`) in the composed
   WARNING/error text — backed by the live integration test BI/073.008-T (B1 covers the
   matcher at the helper/unit level only; no live coverage is attributed to it).
4. **Path preservation (REPLACES the former H2/H2-C2 path-redaction criterion —
   REJECTED 2026-09-15):** `_sanitize_url` leaves the URL PATH component unchanged.
   Ordinary paths — `/authentication/overview`, `/tokenizer/config`,
   `/keys/rotation`, `/docs/100%25-off` (literal `%25` intact) — are emitted
   BYTE-FOR-BYTE unchanged. No path decoding, percent-decoding, path matcher,
   malformed-escape handling, or `<path-redacted>` sentinel exists in executable
   scope. Backed by benign-path assertions in A1/073.001-T and AI/073.007-T.
5. **Determinism preserved:** `job_id`/`cache_path` unchanged by A2 for a fixed
   config; the raw-source oracle is accepted residual risk (H4/H4-C2 — including the
   low-entropy dictionary-confirmation acknowledgment and explicit rollback trigger,
   whose keyed-construction revisit is over the RAW canonical source key — not the
   sanitized key, which would retain cache-poisoning collisions — with key-management
   and cache-migration requirements; finding F-05).
6. **No false positives (H1 exact-match grammar):** benign near-matches — the
   legacy-marker false positives `tokenizer`, `keynote`, `secretary`, `authorship`,
   `signal` (now preserved after startswith→exact), plus `password_policy`,
   `pwd_length`, `client_secretary`, `codec`, `code_version`, the finding-#3
   additions `passwd_file`/`refresh_token_ttl`, and case-varied variants of all of
   them, plus benign paths — are NOT redacted.
7. **Typed-field preservation + fail-closed raise (operator contract, Findings 3/4):**
   the typed sanitizer sanitizes URL fields + explicitly-secret typed fields while
   byte-preserving branch / path_glob / manifest ID / local path / include fields;
   the `execute.py` WARNING/error composition likewise byte-preserves those same
   provenance fields while removing only structured URL/typed credentials
   (error-output provenance-preservation finding, backed by BI/073.008-T);
   and `create_staging_job` RAISES a typed non-leaking exception (no whole-key
   sentinel, no raw-key echo) when a compound source key is passed without
   `sanitized_source`. Backed by A1/073.001-T (typed-field preservation),
   BI/073.008-T (error-output provenance preservation), and
   A2/073.002-T (raise-on-omission).

### Review-gate capability note

Plan review ran in single-agent declared-degradation mode (no reviewer-subagent
dispatch surface in this Stage session); every selected persona rubric was applied
inline. Markers emitted for harvest fail-closed parsing.

**Reviewer-dispatch degradation telemetry markers (finding P1-11, literal):**

```text
TOOL_DEGRADED: reviewer-subagent-dispatch — fallback: inline single-agent persona rubrics (all personas applied inline)
TOOL_DEGRADED: anchor-review-model — fallback: same-model inline Architecture Strategist rubric (anchor route openai/gpt-5.6-sol unavailable in this session)
```

Per `.github/instructions/adversarial-review.instructions.md`, the anchor route
being unavailable requires the literal `TOOL_DEGRADED: anchor-review-model` marker
with a declared fallback; it is recorded here and the anchor slot is never
silently dropped. The remaining inline persona pool still meets coverage.

**Branch / worktree topology evidence (finding P1-11):**

```text
branch: chore/stage-064-s
worktrees: single — `C:/Source/GitHub/docline  cdcf718  [chore/stage-064-s]` (no parallel/implementation worktrees; P-016 single-active preserved)
HEAD-at-staging: cdcf718 (staging artifacts commit)
remediation-cycle-1-HEAD: cdcf718 (prior cycle left edits uncommitted; the FINAL 2026-09-15 operator-contract correction is committed by Stage on chore/stage-064-s — Finding 8)
DARK_MODE_ACTIVE scope: 064-S | merge-preauthorization: false | admin-fallback: false
```

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

## Remediation & Re-Review — cycle 1 (064-S review BLOCKED → resolved)

The initial-cut Plan Review above (attempt 1) recorded PASS, but a subsequent
**standard review + 4-reviewer adversarial review returned BLOCKED** with P1
findings. Under the operator's DARK_MODE_ACTIVE 064-S scope these are
same-contract-surface completions (P-021 C1) and were fixed here, not deferred.
This section records the disposition of every finding. The initial persona table
above is retained as the attempt-1 historical record; its now-superseded phrasings
("two width-isolated code tasks", "anchored `code` match", "optional/defaulted
param … single caller") are corrected by the H1–H5 contract and the dispositions
below.

dispatch_mode: single-agent-declared-degradation (see markers above)
re-review decision: PASS (all P1 resolved; residual items are explicit accepted
risk or out-of-scope P-021)

### Finding dispositions

| # | Finding (severity) | Disposition | Where resolved |
|---|---|---|---|
| P1-1 | Path-secret grammar incomplete/untestable | PLANNING_CONTRACT_FIXED — full fail-closed grammar with exact outputs (`/token/SECRET`, `/token=SECRET`, case, percent-encoded, bounded decode, malformed, replacement boundaries, marker-associated value, benign) | Deliberation H2; plan Unit C1/C2 + verification criterion 4 |
| P1-2 | No source-kind x sink test matrix; sink overclaim risk | PLANNING_CONTRACT_FIXED — explicit matrix; PM/EX not overclaimed; 4 URL source kinds covered | Plan "Source-Kind x Sink Test Matrix" |
| P1-3 | Broad `startswith` for new names | PLANNING_CONTRACT_FIXED — exact-equality for every new name; benign near-match + malicious fixtures; enumerated legacy/cloud names kept (exact match) | Deliberation H1; plan Unit B1/B2 |
| P1-4 | Strict-safety miscalssified (moderate; no dark-factory/rollback) | PLANNING_CONTRACT_FIXED — ActionRisk=high; ActionResult=approved via dark factory mode; merge/admin=false; rollback/containment | Plan "Risky-action classification" |
| P1-5 | Unsafe `sanitized_source=None` fallback + position ambiguity | PLANNING_CONTRACT_FIXED — keyword-only param; compound-prefix fail-closed fallback; bare-string compat proven | Deliberation H3; plan Unit A2 |
| P1-6 | Deterministic raw-source job_id oracle undecided | DECIDED — accepted narrowly-reasoned residual risk; determinism/cache-stability rationale; tests/compat recorded | Deliberation H4; plan verification criterion 5 |
| P1-7 | Provenance (PR #199 vs #200) + stale closure/memory paths | RESOLVED_IN_STAGING_ARTIFACTS — #199 impl / #200 closure; `docs/closure/…` path; exact stage-195 cycle6/7 paths | Deliberation provenance + late-identifier reconciliation; plan "Learnings consulted" |
| P1-8 | Shipment description/H1 template compliance | PLANNING_CONTRACT_FIXED — 064-S required `description` section added; markdown H1 rules verified (frontmatter-title records carry no H1; compliant) | `.backlogit/queue/064-S.md` + backlog records |
| P1-9 | Archived stash lineage not reconciled | ADDRESSED — durable lineage recorded in Stage artifacts; tool limitation reported (backlogit cannot pointer archived stash → work item) | Deliberation "Archived-stash lineage reconciliation" |
| P1-10 | Width isolation / artificial dependency edge | PLANNING_CONTRACT_FIXED — 2→3 streams (B split into B query-name + C path-secret); removed artificial `073.004-T→073.002-T`; genuine `073.006-T→073.004-T` added | Deliberation H5; plan Dependency Graph |
| P1-11 | Missing reviewer-dispatch degradation marker + topology | PLANNING_CONTRACT_FIXED — literal `TOOL_DEGRADED` markers + branch/worktree topology block | Plan "Review-gate capability note" |
| P1-12 | `non---execute` wording | RESOLVED_IN_STAGING_ARTIFACTS — corrected to `non-\`--execute\`` in backlog records | 073-F, 073.001-T descriptions |

### Re-review persona confirmation (inline, cycle 1)

| Persona | Result |
|---|---|
| Constitution Reviewer | PASS — P-001/P-016/P-021 respected; 3 width-isolated streams (3 test + 3 code tasks); no scope bleed beyond 064-S; DARK_MODE scope honored. |
| Python Reviewer | PASS — keyword-only `sanitized_source` proves positional compat with existing bare-string test callers; fail-closed compound fallback sound; exact-match grammar sound. |
| Scope Boundary Auditor | PASS — no absorption of related entries (79BF0AEC/E89DC095/9D44B6F3/E7878B1B stay stashed); exact-match avoids over-reach; strictly additive; stream split satisfies 2-hour rule. |
| Learnings Researcher | PASS — reuses 063-S typed contract; provenance corrected; no contradiction with prior closure. |
| Architecture Strategist | PASS (anchor route unavailable → same-model inline) — `create_staging_job` seam correct; shared matcher single-source-of-truth justifies genuine C→B edge; acyclic. |
| Security Lens Reviewer | PASS (triggered: credential/secrets) — trust boundaries + sink matrix complete; H2 fail-closed path grammar; H1 no benign false positives; H4 oracle residual explicitly accepted. |

### Residual / out-of-scope (captured, NOT fixed here)

* H4 raw-source `job_id` confirmation-oracle — accepted residual risk, documented.
* Archived-stash→work-item tool pointer — backlogit limitation, durable prose
  traceability substituted (P1-9).
* `79BF0AEC` (string-sanitizer `github_repo:` pass-through), `E89DC095`,
  `9D44B6F3`, `E7878B1B`, `95BD0DC7`, `709BDB53` — distinct-contract P-021 entries,
  remain active/archived and out of 064-S scope. No new different-contract issue
  surfaced during this remediation.

<!-- plan-review-attempt: 2 -->
<!-- remediation-cycle: 1 -->

## Remediation & Re-Review — cycle 2 (FINAL; 064-S adversarial re-review cycle 1 BLOCKED → resolved)

Post-remediation adversarial re-review (cycle 1) returned **BLOCKED** with four
unique P1 and five P2/P3 findings. All are **same-contract-surface completions**
(P-021 C1) — none is different-contract work — and are resolved here, not deferred.
This is the FINAL allowed remediation cycle; no in-scope P1 is silently deferred.
Stage authored no product/test code. The authoritative contract lives in the
deliberation's `## Remediation cycle 2` (H2-C2 decode-before-segmentation, H4-C2
low-entropy oracle) and in this plan's updated Units, matrix, dependency graph, and
`## Constitution Check`.

dispatch_mode: single-agent-declared-degradation (markers below)
re-review decision: PASS (all four P1 + five P2/P3 resolved; residual items are
explicit accepted risk or out-of-scope P-021)

### Cycle-2 finding dispositions

| # | Finding (sev) | Disposition | Where resolved |
|---|---|---|---|
| 1 (P1) | Path-secret grammar incomplete where percent-decode introduces structural delimiters; `/token/` undefined | PLANNING_CONTRACT_FIXED — decode-before-segmentation grammar; pinned fail-closed outputs for `%2F`/`%3D`/multilayer/malformed/over-cap; exact `/token/` (non-empty-adjacent-value) rule | Deliberation H2-C2; plan Unit C1/C2 + criterion 4; 073.005-T/073.006-T ACs |
| 2 (P1) | Live WARNING/stdout coverage attributed to helper-only tests | PLANNING_CONTRACT_FIXED — added integration test tasks 073.007-T (live stdout) + 073.008-T (live WARNING new-names); A1/B1 narrowed to helper level; EX honestly n/a; test-first edges added | Plan Source-Kind×Sink matrix, Units AI/BI, Dependency Graph, criteria 2/3 |
| 3 (P1) | Missing benign case-varied near-match fixtures for `passwd`/`refresh_token` | PLANNING_CONTRACT_FIXED — H1 table + Unit B1 + 073.003-T add `passwd_file`/`refresh_token_ttl` and case-varied variants of every benign near-match | Deliberation H1 table; plan Unit B1 + criterion 6; 073.003-T ACs |
| 4 (P1) | Unqualified `FIXED` in planning-only reporting | RESOLVED_IN_STAGING_ARTIFACTS — cycle-1 tokens requalified to PLANNING_CONTRACT_FIXED / RESOLVED_IN_STAGING_ARTIFACTS across plan + memory | plan cycle-1 disposition table; cycle-1 + cycle-2 memory |
| 5 (P2) | Job-ID oracle record too narrow (preimage-only) | RESOLVED_IN_STAGING_ARTIFACTS — H4-C2 adds low-entropy dictionary-confirmation, exposure assumptions, compatibility rationale, explicit rollback/revisit trigger | Deliberation H4-C2; plan criterion 5; Constitution Check residual |
| 6 (P2) | Missing `## Constitution Check` | PLANNING_CONTRACT_FIXED — added mapping applicable/non-applicable principles + governing policies + residual risk | plan `## Constitution Check` |
| 7 (P3) | Stale provenance in stage-073 memory (PR #200 as impl) | RESOLVED_IN_STAGING_ARTIFACTS — corrected to PR #199 implementation / #200 closure | docs/memory/2026-09-14/stage-073-elt-credential-redaction-session.md |
| 8 (P2) | Stream-B task titles claim path-secret scope | PLANNING_CONTRACT_FIXED — 073.003-T/073.004-T titles narrowed to query credential-name matching; 073-F/064-S/plan reconciled | backlog records; 073-F description; plan streams |
| 9 (P3) | Exact `/token/` behavior undefined | PLANNING_CONTRACT_FIXED — non-empty-adjacent-value requirement (`/token/` KEEP); folded into H2-C2 | Deliberation H2-C2 `/token/` rule; plan Unit C1/C2 |

### Re-review persona confirmation (inline, cycle 2)

| Persona | Result |
|---|---|
| Constitution Reviewer | PASS — new `## Constitution Check` maps I–XI + P-001/003/005/006/010/016/021; XI (merge) correctly deferred to Ship; sole residual (H4) justified. |
| Python Reviewer | PASS — decode-before-segmentation is a pure-function contract over stdlib `unquote`; keyword-only param and fail-closed sentinels sound; new integration tests are test-domain only. |
| Scope Boundary Auditor | PASS — two added tasks are same-contract live-sink coverage (not new scope); no related stash entry absorbed; each new task within 2-hour/width rule. |
| Learnings Researcher | PASS — provenance corrected (PR #199 impl / #200 closure) consistently across plan + memory; no contradiction with 063-S closure. |
| Architecture Strategist | PASS (anchor route unavailable → same-model inline) — new edges are genuine test-first prerequisites; graph remains acyclic; no execution-ordering edge introduced. |
| Security Lens Reviewer | PASS (triggered: credential/secrets) — H2-C2 closes the encoded-structural-delimiter gap fail-closed; H4-C2 stops over-relying on preimage resistance and adds a rollback trigger; live sinks now test-backed. |

### Residual / out-of-scope (captured, NOT fixed here)

* H4 raw-source `job_id` confirmation-oracle — accepted residual risk with cycle-2
  low-entropy justification + explicit rollback trigger (H4-C2).
* Archived-stash→work-item tool pointer — backlogit limitation; durable prose
  traceability substituted.
* `79BF0AEC`, `E89DC095`, `9D44B6F3`, `E7878B1B`, `95BD0DC7`, `709BDB53` —
  distinct-contract P-021 entries, remain active/archived, out of 064-S scope. No new
  different-contract issue surfaced during cycle 2. **No in-scope P1 remains
  unresolved or silently deferred.**

<!-- plan-review-attempt: 3 -->
<!-- remediation-cycle: 2 -->
<!-- TOOL_DEGRADED: reviewer-subagent-dispatch -->
<!-- TOOL_DEGRADED: anchor-review-model -->

## Remediation & Re-Review — cycle 3 (OPERATOR-AUTHORIZED EXCEPTIONAL cycle; final-cycle residuals → resolved)

**Cycle-budget note (explicit).** The normal plan-review re-entry budget is 2 cycles
(cycle 1 + cycle 2, exhausted above). Cycle 2 was recorded as the "FINAL allowed"
cycle and the dark-factory run correctly HALTED at the review cap
(`docs/memory/2026-09-15/064-s-dark-factory-review-cap-halt.md`) rather than silently
deferring or auto-applying another fix pass. The **operator then explicitly authorized
ONE additional bounded Stage correction/re-review cycle** for shipment 064-S, scope
held exactly to 064-S / 073-F. This section is that operator-authorized exceptional
cycle. It does not widen scope, absorb any related P-021 entry, or write product/test
code; Stage authored only planning/backlog artifacts and left them uncommitted for
Orchestrator review. This supersedes cycle 2's "FINAL cycle" language solely by that
explicit operator authorization.

dispatch_mode: single-agent-declared-degradation (markers below)
re-review disposition: all listed final-cycle residuals resolved as same-contract-surface
completions (P-021 C1); none deferred. No new in-scope P1 remains.

### Cycle-3 finding dispositions

| # | Finding (sev) | Disposition | Where resolved |
|---|---|---|---|
| F-01 (P1) | A1/073.001-T still overclaim live CLI stdout + source-kind coverage | PLANNING_CONTRACT_FIXED — A1/073.001-T restricted to helper-level in-memory `metadata.source` + reconstructed `model_dump` JSON; live-stdout wording removed; source kinds aligned exactly to the same four AI/matrix use; live stdout kept SOLELY in 073.007-T; matrix SO column now cites only AI/073.007-T (A1 reconstructed-JSON moved to the M column) | Plan Unit A1 + Source-Kind×Sink matrix + notes; 073.001-T ACs |
| F-02 (P1) | Percent escapes validated only before first decode, not after every iterative layer | PLANNING_CONTRACT_FIXED — ITERATIVE malformed-escape validation before AND after every decode layer; pinned nested-malformed fail-closed outputs `/token/%252`→`<path-redacted>` (`%252`→`%2`) and `/token/%25ZZ`→`<path-redacted>` (`%25ZZ`→`%ZZ`); bounded multilayer decode + over-cap consistent across deliberation H2-C2, plan Unit C1/C2 + criterion 4, and 073.005-T/073.006-T | Deliberation H2-C2 steps 1–2 + pinned table; plan Unit C1/C2 + criterion 4; 073.005-T/073.006-T ACs |
| F-03 (P1) | 073.008-T does not exercise all four URL-bearing source kinds the WE matrix claims | PLANNING_CONTRACT_FIXED — 073.008-T (and plan Unit BI) exercise the live WARNING/error path for all four URL-bearing source kinds × the full new-name vocabulary (9 names; final-correction round extended this from the original six to the complete set and added execute.py error-output provenance byte-preservation) (explicit all-four coverage, within the 2-hour test-domain boundary); matrix and task now agree | Plan Unit BI + matrix WE notes; deliberation live-sink coverage; 073.008-T ACs |
| F-04 (P1) | Live-stdout path-secret matrix cell covered compositionally, not directly | PLANNING_CONTRACT_FIXED — 073.007-T (and plan Unit AI) add a DIRECT path-embedded-secret fixture with exact secret-absence + `/token/<redacted>` assertions on the real `cli.py:381` stdout; matrix SO path-secret cell now cites AI/073.007-T direct; genuine test-first edge `073.006-T depends_on 073.007-T` added (acyclic; stream A code stays decoupled from stream C) | Plan Unit AI + matrix + dependency graph; 073.006-T deps/ACs; 073.007-T ACs |
| F-05 (P3) | Job-ID revisit proposal recommends HMAC over the SANITIZED key (retains collisions) | RESOLVED_IN_STAGING_ARTIFACTS — H4-C2 rollback/revisit trigger corrected to a keyed construction (HMAC) over the RAW canonical source key with explicit key-management + cache-migration requirements; HMAC-over-sanitized explicitly rejected (reintroduces same-structure cache-poisoning collisions) | Deliberation H4-C2 trigger; plan criterion 5 + Constitution Check residual |

### Re-review persona confirmation (inline, cycle 3)

| Persona | Result |
|---|---|
| Constitution Reviewer | PASS — scope held to 064-S/073-F; operator-authorized exceptional cycle recorded; P-001/P-010 boundary intact (planning artifacts only, uncommitted); test-first edges preserved. |
| Python Reviewer | PASS — iterative per-layer `%`-escape validation is a pure-function contract over stdlib `unquote`; helper-vs-live A1/AI split is sound; new path-secret fixture is test-domain only. |
| Scope Boundary Auditor | PASS — no related stash entry absorbed; 073.007-T/073.008-T stay within 2-hour/width rule; no new scope introduced; F-04 edge is a genuine test-first prerequisite, not execution ordering. |
| Learnings Researcher | PASS — corrections consistent with 063-S typed-sanitizer contract and prior cycles; no contradiction with prior closure. |
| Architecture Strategist | PASS (anchor route unavailable → same-model inline) — new `073.006-T→073.007-T` edge keeps the graph acyclic and does not couple stream A to stream C; matrix now internally consistent. |
| Security Lens Reviewer | PASS (triggered: credential/secrets) — per-layer escape validation closes the nested-malformed evasion; live path-secret sink now directly test-backed; keyed-over-raw-key revisit removes the sanitized-key collision flaw. |

### Residual / out-of-scope (captured, NOT fixed here)

* H4 raw-source `job_id` confirmation-oracle — accepted residual risk; cycle-3 corrects
  only the revisit trigger (keyed over RAW key), the decision (accept) stands.
* Archived-stash→work-item tool pointer — backlogit limitation; durable prose
  traceability substituted.
* `79BF0AEC`, `E89DC095`, `9D44B6F3`, `E7878B1B`, `95BD0DC7`, `709BDB53` —
  distinct-contract P-021 entries, remain active/archived, out of 064-S scope. No new
  different-contract issue surfaced during cycle 3. **No in-scope P1 remains
  unresolved or silently deferred.**

<!-- plan-review-attempt: 4 -->
<!-- remediation-cycle: 3 -->
<!-- operator-authorized-exceptional-cycle: 064-S -->
<!-- TOOL_DEGRADED: reviewer-subagent-dispatch -->
<!-- TOOL_DEGRADED: anchor-review-model -->
