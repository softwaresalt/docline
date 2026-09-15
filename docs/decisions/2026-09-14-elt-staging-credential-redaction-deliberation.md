---
title: "ELT staging credential redaction: default-fetch sink + coverage expansion"
description: "Deliberation for deferred-scope-expansion entries 0F1A653C (default-path credential sink) and 06A59B1D (redaction coverage expansion)"
topic: "Close the default (non --execute) docline fetch credential sink and expand staging credential redaction coverage"
depth: "deep"
decision_status: "decided"
promoted_to: "plan"
linked_artifacts:
  - "docs/plans/2026-09-14-elt-staging-credential-redaction-plan.md"
tags:
  - "security"
  - "credential-redaction"
  - "elt-staging"
  - "p-021-deferred-expansion"
---

## Provenance and P-021 Reconciliation

Both entries carry the literal `DEFERRED SCOPE EXPANSION` marker, so the Step 1
precedence rule (P-021) forces this `deliberate` route regardless of shape/size/
priority. Both are `requires_deliberation: true`.

### Source refs (as captured)

| Entry | Kind / prio | shipment | feature | task | PR | thread | comment |
|---|---|---|---|---|---|---|---|
| `0F1A653C` | bug / high | 063-S | 072-F | N/A | N/A | N/A | N/A |
| `06A59B1D` | task / medium | 063-S | 072-F | N/A | N/A | N/A | N/A |

### P-021 duplicate detection (UNCONDITIONAL — clean scan, both entries)

Ran the unconditional duplicate scan over the active stash (44 entries) and the
backlog index. Three other entries touch the same sanitizer surface but are
**genuinely distinct concerns, not duplicates**:

* `E89DC095` — `_URL_SCHEME_RE` excludes underscore in scheme names (source_keys.py).
* `9D44B6F3` — `_sanitize_url_field` leading-whitespace guard misses Unicode Cf chars.
* `E7878B1B` — redundancy between `_remove_credential_query_params` and
  `_strip_reversed_query_credentials`.

None describe the `orchestrate_fetch`/`create_staging_job` string-arg default-path
sink (0F1A653C) or the `_CREDENTIAL_PARAM_PREFIXES` vocabulary/path-embedded
expansion (06A59B1D). **Clean duplicate scan recorded for both target entries;
no merge, no archive-of-duplicate required.** (Prior Stage memory
`stage-195-cycle6/7` independently records both as "genuinely distinct, not
subsumed".)

### P-021 late-identifier reconciliation (triggered by N/A source-ref fields)

Recovered from Ship-owned residual-risk records citing the entry IDs:

* 063-S merged as **PR #200** (HEAD `7e82bbb` "post-merge closure for 063-S … (#200)").
* The 063-S closure record
  `docs/memory/2026-09-13-sanitize-source-key-elt-error-paths-closure.md`
  (lines 133-134) carries **both** `0F1A653C` and `06A59B1D` as *open* deferred
  findings of the 063-S shipment.
* Adversarial-review records (2026-09-13-*) list both as explicitly out-of-scope
  deferred findings.

**Reconciled association:** shipment 063-S → PR **#200** (residual-risk PR
association recovered via the closure record). **thread = N/A and comment = N/A
STAND as truthful terminal records** — these findings were surfaced by Stage
adversarial multi-model review of 063-S staging artifacts on 2026-09-12
(pre-PR / not a PR-review comment), so no review-thread or comment identifier
ever existed. **task = N/A STANDS** — both are distinct un-tasked sinks, not
063-S work items (072.001-T/072.002-T/072.003-T are strictly `_execute_single_source`
scoped). Reconciliation updated the entries in place (no second entry created);
this is a non-blocking enrichment.

## Problem Frame

`docline fetch` has two code paths:

* **`--execute` path**: `cli.py` → `_exec` → `execute_fetch` → `_execute_single_source`
  (execute.py). 063-S/072-F fixed this sink: it builds `job_id` from the raw
  `build_source_key(config)` but persists `metadata.source = sanitize_source_key(config)`
  (the typed sanitizer) and writes the sanitized value to `metadata.json` and logs.
* **DEFAULT (non `--execute`) path**: `cli.py:369` → `orchestrate_fetch`
  (orchestrate.py:47) → `create_staging_job(build_source_key(config), staging_dir)`.
  This sink was **NOT** touched by 063-S (verified: 072.001-T/002-T/003-T only touch
  `_execute_single_source`).

### Validation against HEAD (`7e82bbb`)

**0F1A653C — CONFIRMED (with one refinement):**
* `orchestrate.py:47` calls `create_staging_job(build_source_key(config), staging_dir)`. ✔
* `create_staging_job` (staging.py:158-161) sets `job_id = make_job_id(source)` and
  `metadata.source = sanitize_source(source)` — the **string** sanitizer. ✔
* `sanitize_source` (staging.py:59-89) has no branch for the compound
  `web_crawl:` / `manifest_url:` prefixes: none of file://, http(s)://, `/`, `\`,
  or a drive-letter matches, so it **returns the raw string unchanged** (line 89). ✔
  The credentialed key (userinfo + `?token=…`) therefore survives into `metadata.source`.
* `cli.py:381` prints `json.dumps([job.model_dump(mode="json") for job in jobs])` →
  the unsanitized `metadata.source` is **emitted to stdout**. ✔
* **Refinement:** on the DEFAULT path, `create_staging_job` does not itself write
  `metadata.json` (only `_execute_single_source` writes the file). The live sink on
  the default path is therefore **stdout/logs** (cli.py:381), not an on-disk
  `metadata.json`. The persisted-metadata leak in the entry text describes the execute
  path, already closed by 063-S. The stdout/log credential leak on the default path is
  real, confirmed, and high-severity. `create_staging_job` has exactly **one caller**
  (`orchestrate_fetch`), so the fix is tightly bounded.

**06A59B1D — CONFIRMED:**
* `_CREDENTIAL_PARAM_PREFIXES` (staging.py:12-25) contains token/access_token/key/
  api_key/secret/auth/sig/signature/x-amz-*/x-goog-signature. It **omits**
  `password`, `pwd`, `passwd`, `client_secret`, `refresh_token`, `code`
  (note: `secret` prefix does NOT match `client_secret`; `refresh_token` is unmatched). ✔
* `_sanitize_url` (staging.py:92-118) reconstructs the URL with `parsed.path`
  **unchanged** → path-embedded secrets are not redacted. ✔
* **Blast radius CONFIRMED:** `_is_credential_param`/`_CREDENTIAL_PARAM_PREFIXES` is
  imported and used by `source_keys.py:_remove_credential_query_params`
  (lines 395/402), which is part of `_sanitize_url_field` → the **typed** sanitizer
  (`sanitize_source_key`) used on the 059-S WARNING path and the 063-S execute path.
  Expanding the shared list widens redaction on BOTH the string and typed paths.

## Research Findings

* 063-S established the reusable typed sanitizer contract
  `sanitize_source_key(config: SourceConfig) -> str` (source_keys.py:83), which the
  execute path applies as: `job_id = make_job_id(build_source_key(config))` +
  `metadata.source = sanitize_source_key(config)`. This is the proven, in-repo
  pattern to reuse for the default path.
* The entry's concern that "the typed-config sanitizer cannot be applied verbatim
  because `create_staging_job` receives a STRING, not a `SourceConfig`" is real for
  the function *signature*, but the caller (`orchestrate_fetch`) **does** hold the
  typed `config`. The resolution is to thread the already-sanitized typed value into
  `create_staging_job`, not to re-derive sanitization from the string.
* Prior Stage memory (`stage-195-cycle6`) notes the typed path already covers
  web_crawl + manifest_url URL fields; manifest_local is filesystem-only
  (path-secret = 06A59B1D territory).

## Options Evaluated

### Option A (0F1A653C): Thread the typed sanitized key into `create_staging_job`

Add an optional `sanitized_source: str | None = None` parameter to
`create_staging_job`. When provided, use it for `metadata.source`; keep `job_id`
derived from the raw `source`. `orchestrate_fetch` passes
`sanitize_source_key(config)`.

* **Pros:** Reuses the proven 063-S typed sanitizer; preserves `job_id`
  determinism (raw key, identical to the execute path); backward-compatible
  (default `None` → existing `sanitize_source` fallback); single caller → tiny
  blast radius; does NOT touch the shared string sanitizer or the prefix list, so
  it is width-isolated from 06A59B1D; closes the stdout sink through the one
  `metadata.source` field (no cli.py change needed).
* **Cons:** Adds one optional parameter to a shared helper.
* **Effort:** low. **Fit:** excellent.

### Option B (0F1A653C rejected): Teach the string `sanitize_source` to parse compound prefixes

Make `sanitize_source` recognize `web_crawl:`/`manifest_url:` compound keys and
sanitize the embedded URL.

* **Cons:** Re-implements compound-key parsing already solved by the typed path;
  the module explicitly flags compound-prefix scheme matching as a *separate*
  deferred gap (E89DC095/E462E1F0 territory); higher regression surface; would
  duplicate logic. **Rejected.**

### Option C (06A59B1D): Additively expand the shared prefix list + redact path-embedded secrets, with false-positive guards

Add `password`, `pwd`, `passwd`, `client_secret`, `refresh_token` to
`_CREDENTIAL_PARAM_PREFIXES`; treat `code` carefully (prefix-match risks
false positives like `codec`/`code_version`) — use exact/anchored matching for
`code` rather than a broad prefix. Redact path-embedded secrets in `_sanitize_url`
only when a credential marker is present in a path segment (marker-gated, mirroring
the typed path's fail-closed style), not a blanket path redaction.

* **Pros:** Strictly additive redaction (can only redact more, never less);
  benefits both string and typed paths via the shared `_is_credential_param`.
* **Cons/risks:** False positives if prefixes are too broad (esp. `code`); path
  redaction must not corrupt benign path segments → needs marker-gating.
* **Effort:** low-medium. **Fit:** good, with the guardrails above.

## Trade-off Comparison

| Criterion | A (thread typed key) | B (parse string) | C (expand coverage) |
|---|---|---|---|
| Reuses proven contract | Yes (063-S typed) | No | Yes (shared `_is_credential_param`) |
| Blast radius | 1 caller | string sanitizer + regressions | shared list → 2 paths (intended) |
| job_id determinism preserved | Yes | Yes | N/A |
| False-positive risk | None | Low-med | Medium (mitigated by guards) |
| Width isolation | Clean (no prefix-list touch) | Couples to C | Clean (no orchestrate touch) |

## Decision (contract)

**Both entries support implementation. Proceed to plan.** One covering feature,
two width-isolated work-streams, sequenced.

**Work-stream A — 0F1A653C (acute, high):** Adopt **Option A**. Thread the typed
`sanitize_source_key(config)` output into `create_staging_job` via an optional
`sanitized_source` parameter; keep `job_id` from the raw `build_source_key`. This
closes the default-path stdout/log credential sink while preserving job-ID
determinism and staying width-isolated from work-stream B. Test-first
(characterization test proving the leak, then the fix).

**Work-stream B — 06A59B1D (hardening, medium):** Adopt **Option C**. Additively
expand `_CREDENTIAL_PARAM_PREFIXES` (`password`, `pwd`, `passwd`, `client_secret`,
`refresh_token`) with anchored matching for `code` to avoid false positives, and
add marker-gated path-embedded secret redaction in `_sanitize_url`. Test-first.

**Sequencing (real dependency):** B lands after A. Both mutate `staging.py`; A is
the acute live sink (P0-class) and must land + verify first; A also reroutes the
default path through the shared `_is_credential_param`, so B's expansion then also
covers the default path. This is a genuine code-contention + risk-ordering
dependency, recorded as an explicit backlog edge (not prose only): B-code
depends-on A-code.

### Minimal safe contract (invariants)

1. `metadata.source` (and therefore anything derived/printed from it) MUST NOT
   contain userinfo, query-string credentials, or path-embedded secrets on ANY
   fetch path (default or execute).
2. `job_id` MUST remain derived from the raw `build_source_key` (determinism /
   cache-path stability preserved; identical between default and execute paths).
3. No change to `create_staging_job`'s existing string-only behavior when
   `sanitized_source` is not supplied (backward compatible).
4. Coverage expansion is strictly additive — it may only redact more, never less —
   and must not introduce false-positive corruption of benign params/paths.

## Rejected Alternatives

* Option B (parse compound prefixes in the string sanitizer) — see above.
* Combining A and B into a single change — violates width isolation and couples
  the acute P0 fix to the medium blast-radius hardening; rejected in favor of two
  sequenced tasks per stream.
* Absorbing any related stash entry (E89DC095/9D44B6F3/E7878B1B) — out of scope by
  operator directive and P-021; left active in the stash.

## Unresolved Questions / Out-of-scope captures

* Exact marker set for path-embedded secret detection in `_sanitize_url` is a small
  design detail resolved during B implementation (mirror the typed path's
  `_contains_credential_marker` style); no blocker.
* No NEW out-of-scope issue discovered during this deliberation beyond the three
  already-stashed distinct entries. If one surfaces during implementation, capture
  under P-021 rather than expanding this batch.

## Risks and Mitigations

* **Risk:** `code` prefix over-redacts benign params → **Mitigation:** anchored/exact
  match for `code`, covered by an explicit false-positive test.
* **Risk:** signature change to `create_staging_job` breaks a caller → **Mitigation:**
  verified exactly one caller (`orchestrate_fetch`); parameter is optional/defaulted.
* **Risk:** path redaction corrupts legitimate paths → **Mitigation:** marker-gated
  redaction, not blanket; regression test on credential-free paths.
