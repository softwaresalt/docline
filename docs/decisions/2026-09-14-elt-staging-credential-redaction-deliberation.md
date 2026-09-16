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

## Operator Contract — 2026-09-15 (FINAL, AUTHORITATIVE — supersedes ALL earlier sections)

> This block is the SINGLE authoritative product contract for 064-S / 073-F and
> SUPERSEDES every earlier section of this deliberation, INCLUDING the
> "Operator-Decision Revision" block below, wherever they conflict. Lower content is
> retained only as a HISTORICAL / REJECTED-alternatives record.

**Product boundary.** Docline MUST NOT inspect/redact source-document body content or
redact/decode ordinary URL paths; branches, path globs, manifest IDs, local paths,
include patterns, and other provenance identifiers are preserved BYTE-FOR-BYTE even if
they contain text like `?token=`, and are never interpreted as credential structures.
Docline redacts ONLY structured source-access credentials from Docline-generated
metadata/stdout/log/warning/error outputs: (1) URL user-info; (2) query-parameter
NAMES in an explicit, case-insensitive recognized credential vocabulary; (3) typed
config fields explicitly designated secret. All benign query params and provenance are
preserved.

**Consensus findings resolution.**

1. **Explicit exact-match vocabulary (replaces all `startswith`).** See H1 below
   (revised): the query-name matcher uses an explicit, case-insensitive, EXACT-match
   vocabulary; the legacy `startswith`/prefix heuristic is REPLACED; legacy/cloud
   variants are individually enumerated; benign preservation covers tokenizer,
   keynote, secretary, authorship, signal, password_policy, pwd_length,
   client_secretary, codec, code_version, passwd_file, refresh_token_ttl + case
   variants.
2. **Bounded decode — query NAMES only, both sanitizer paths.** ≤5 layers, re-check
   after each layer, fail closed past the cap; covers `%70assword`, `%2570assword`, a
   deeper valid case, and over-cap; no path or query-value decoding.
3. **Typed sanitization redesign.** The typed sanitizer sanitizes URL + explicitly-
   secret typed fields and byte-preserves branch / path_glob / manifest ID / local
   path / include fields.
4. **Raise, not sentinel.** See H3 below (revised): compound-key omission RAISES a
   typed, non-leaking exception (no whole-key sentinel, no raw-key echo); keyword-only
   param; bare-URL compat retained only where paths are preserved and structured creds
   sanitized.
5. **Satisfiable A2+B2 composition gate (single merged production task).** 073.009-T is
   the final live default-stdout composition test (userinfo + all recognized new names),
   written first, gating the SINGLE MERGED production task 073.002-T; 073.007-T =
   concern-A userinfo subset, 073.008-T = concern-B WARNING subset. Because A2 and B2
   are ONE atomic code task (2026-09-15 P0 green-gate fix — two separate code tasks could
   not each green the composition gate), 073.009-T and every other test task green
   together when 073.002-T lands; former stream-B code task 073.004-T is retired/merged
   into 073.002-T. Milestones honest; the 2-hour rule yields to the stronger
   per-task-green invariant while the merged task stays one cohesive domain.
6. **LocalFileSource / ManifestLocalSource.** Local paths, include patterns, and
   manifest IDs are PRESERVED byte-for-byte; only explicitly-secret typed fields (none
   present) would be redacted.
7/9/10. **Historical hygiene.** All path / Option C part 2 / work-stream C / H2 /
   H2-C2 material below is HISTORICAL / REJECTED and non-executable. Exactly TWO
   executable streams (A, B). Retired tasks 073.005-T / 073.006-T stay status=blocked,
   out of shipment 064-S, non-destructive. The three removed stream-C edges are
   `073.006-T→073.005-T`, `073.006-T→073.004-T`, `073.006-T→073.007-T`.

**Handoff (Finding 8).** Stage OWNS and COMMITS its own planning/backlog artifacts on
`chore/stage-064-s`. The Orchestrator does NOT commit Stage artifacts; it only
coordinates review, the remote staging gate, and the Ship handoff. Any earlier "left
uncommitted for Orchestrator review" wording is superseded.

## Operator-Decision Revision — 2026-09-15 (AUTHORITATIVE; supersedes the path-redaction decision)

> This section is authoritative and SUPERSEDES the path-embedded-secret redaction
> decision (Option C part 2, work-stream C, and the H2 / H2-C2 grammars) recorded
> later in this deliberation. Where any later section conflicts with this one, THIS
> section wins; the conflicting path material is retained below only as a HISTORICAL
> / REJECTED-alternatives record.

**Authoritative operator decision (064-S / 073-F):**

* Docline MUST NOT scan, interpret, or rewrite source-document content for secrets.
* Ordinary URL paths are source identifiers / content locations and MUST remain
  BYTE-FOR-BYTE unchanged (e.g. `/authentication/overview`, `/tokenizer/config`,
  `/keys/rotation`, `/docs/100%25-off`). Path-secret detection/redaction is REJECTED
  as an upstream DLP concern.
* Docline's responsibility is limited to NOT re-emitting **structured access
  credentials** supplied to connect to a source: URL user-info, recognized credential
  query parameters, and typed config fields designated secret — in metadata,
  stdout/logs, warnings, or errors.

**REJECTED alternatives (recorded with rationale):**

1. **Arbitrary path-embedded secret redaction in `_sanitize_url`** (Option C part 2,
   work-stream C, H2/H2-C2 decode-before-segmentation grammar; tasks
   073.005-T/073.006-T) — **REJECTED.** It required Docline to decode/re-interpret URL
   path content (upstream DLP scope); the marker-gated matcher over-redacts benign
   endpoints (`/authentication/overview`, `/keys/rotation`, `/tokenizer/config`); the
   per-layer percent validation rejects valid literal-percent data (`/docs/100%25-off`);
   and the direct path-secret milestone made the `073.002-T → 073.007-T` contract
   unsatisfiable. Retired non-destructively.
2. **Source-document body / content scanning for secrets** — **REJECTED.** Docline
   never inspects fetched document content; that is upstream DLP responsibility.

**Retained:** Option A (work-stream A), Option C part 1 (work-stream B, query-name
expansion), and the H4/H4-C2 job-ID residual-risk decision (it concerns the raw
`build_source_key` digest of structured access credentials, incl. low-entropy query
`code`/`password` values, so it still applies; the keyed-over-RAW-key revisit trigger
stays coherent). The revised minimal safe contract is: `metadata.source` MUST NOT carry
userinfo or credential query params on any fetch path, while URL PATH components are
preserved byte-for-byte.

**Three cycle-3 P1 blockers resolved by REMOVING the path requirement** (not by adding
path parsing): the unsatisfiable `073.002-T ↔ 073.007-T` path milestone, benign-path
over-redaction, and literal-percent (`%25`) rejection all disappear once path redaction
is dropped.

## Provenance and P-021 Reconciliation

Both entries carry the literal `DEFERRED SCOPE EXPANSION` marker, so the Step 1
precedence rule (P-021) forces this `deliberate` route regardless of shape/size/
priority. Both are `requires_deliberation: true`.

### Source refs (as captured)

| Entry | Kind / prio | shipment | feature | task | PR | thread | comment |
|---|---|---|---|---|---|---|---|
| `0F1A653C` | bug / high | 063-S | 072-F | N/A | #199 impl / #200 closure-narrative | N/A | N/A |
| `06A59B1D` | task / medium | 063-S | 072-F | N/A | #199 impl / #200 closure-narrative | N/A | N/A |

The PR column is the reconciled value (cycle 1): shipment 063-S implemented via
**PR #199**; both entries were published as open deferrals in the closure
narrative that accompanied closure **PR #200**. `thread`/`comment`/`task` remain
truthful `N/A` terminal records (Stage adversarial pre-PR review origin).

### Archived-stash lineage reconciliation (0F1A653C, 06A59B1D → 073-F / 064-S)

Both entries were consumed and archived during the 2026-09-14 harvest
(`.backlogit/archive/stash.jsonl`, `archived_at` 2026-09-14T07:37:48/49Z). Their
forward lineage into the backlog is:

| Archived stash | Became (backlog) | Shipment |
|---|---|---|
| `0F1A653C` (bug/high, default-path sink) | 073-F ▸ stream A ▸ `073.001-T` (test) + `073.002-T` (code) | 064-S |
| `06A59B1D` (task/med, coverage expansion) | 073-F ▸ stream B `073.003-T`+`073.004-T` (query names) and stream C `073.005-T`+`073.006-T` (path-embedded) | 064-S |

> **Final-state note (2026-09-15 final correction):** this table records the original
> 2026-09-14 harvest lineage. Current disposition: stream B's code task `073.004-T` is
> MERGED into the single production task `073.002-T` (retired/blocked, out of manifest);
> stream C (`073.005-T`/`073.006-T`) is REJECTED/retired. Executable manifest = 7 items.

**Tool limitation (reported, not worked around):** backlogit exposes no schema
field or operation to persist an archived-stash → work-item forward pointer.
`stash get`/`stash edit` operate on the ACTIVE stash only (`backlogit stash get
0F1A653C` → `stash entry not found`, because the entry is archived), and
`link add` operates between live artifacts, not archived stash IDs. No
unsupported schema field was invented. The lineage above is therefore recorded as
durable, human-readable traceability in this deliberation, in the plan, in the
Stage session memory, and in the 073-F covering-feature description; the
archive JSONL retains the original entry text verbatim as the immutable source
record. This satisfies P-021 traceability without fabricating tool state.

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
`docs/memory/2026-09-12/stage-195-cycle6-copilot-remediation-memory.md` and
`docs/memory/2026-09-12/stage-195-cycle7-copilot-remediation-memory.md`
independently record both as "genuinely distinct, not subsumed".)

### P-021 late-identifier reconciliation (triggered by N/A source-ref fields)

Recovered from Ship-owned residual-risk records citing the entry IDs. **PR
provenance (corrected during 064-S remediation cycle 1):** the 063-S/072-F work
has TWO distinct PRs and they must not be conflated:

* **PR #199 is the IMPLEMENTATION PR** — the 063-S/072-F feature merge to `main`
  at reviewed HEAD `f1f5f8f` (`3933dfc Merge pull request #199 … 063-s-sanitize-credential-bearing-source-key-corrected`).
  This is the PR by which shipment 063-S actually shipped.
* **PR #200 is the CLOSURE PR** — the post-merge closure documentation
  (`7e82bbb chore: post-merge closure for 063-S … (#200)`; the canonical
  machine-readable record `docs/closure/063-S-072-F-post-merge-closure.md`
  carries `closure_pr: 200`). PR #200 shipped no product code; it published the
  closure narrative + runtime verification.
* The 063-S closure narrative record
  `docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-closure.md`
  (see its "Reconciled Deferred Findings" table) carries **both** `0F1A653C` and
  `06A59B1D` as *open* deferred findings of the 063-S shipment.
* Adversarial-review records under `docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-*adversarial-review*.md`
  list both as explicitly out-of-scope deferred findings.

**Reconciled association:** shipment 063-S → implementation **PR #199** (reviewed
HEAD `f1f5f8f`); the deferred-finding provenance was published through the
closure narrative that accompanied closure **PR #200**. **thread = N/A and
comment = N/A STAND as truthful terminal records** — these findings were surfaced
by Stage adversarial multi-model review of 063-S staging artifacts on 2026-09-12
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
* Prior Stage memory (`docs/memory/2026-09-12/stage-195-cycle6-copilot-remediation-memory.md`)
  notes the typed path already covers
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

> **Path-redaction portion REJECTED by the 2026-09-15 FINAL operator contract.** Only
> the query-param NAME expansion portion of this option was adopted (see the Decision
> contract below); Docline leaves URL path components byte-for-byte unchanged. The
> path-embedded-secret text below is retained as historical option analysis only.

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
originally three width-isolated work-streams — now TWO EXECUTABLE streams after the
2026-09-15 operator decision retired stream C (path-embedded secrets); see the top
Operator-Decision Revision section. (Historical note: 064-S review-fix cycle 1 split
the original stream B into query-name stream B and path-secret stream C to satisfy the
2-hour rule; stream C is now rejected/retired.)

**Work-stream A — 0F1A653C (acute, high):** Adopt **Option A**. Thread the typed
`sanitize_source_key(config)` output into `create_staging_job` via an optional
`sanitized_source` parameter; keep `job_id` from the raw `build_source_key`. This
closes the default-path stdout/log credential sink while preserving job-ID
determinism and staying width-isolated from work-stream B. Test-first
(characterization test proving the leak, then the fix).

**Work-stream B — 06A59B1D query-name expansion (hardening, medium):** Adopt
**Option C**, part 1. Additively expand `_CREDENTIAL_PARAM_PREFIXES` (`password`,
`pwd`, `passwd`, `client_secret`, `refresh_token`, `code`) with **case-insensitive
exact-equality** matching for the newly added names (H1) — not just `code` — to
avoid the benign near-match false positives; per the FINAL Operator Contract
(Finding 1) the legacy `startswith` heuristic is REPLACED by an explicit exact-match
vocabulary (legacy/cloud variants individually enumerated), preserving coverage parity
for real credential names while eliminating the prefix false positives. Test-first.

**Work-stream C — 06A59B1D path-embedded secrets — REJECTED / RETIRED (2026-09-15
operator decision):** ~~Adopt Option C part 2. Add marker-gated path-embedded secret
redaction in `_sanitize_url` per the H2 grammar~~. **This work-stream is REJECTED and
retired non-destructively** (tasks 073.005-T/073.006-T set to blocked, removed from
shipment 064-S). Docline leaves URL path components unchanged; path-secret detection
is an upstream DLP concern. See the top Operator-Decision Revision section.

**Sequencing (real dependencies only):** all test tasks are authored first
(test-first) and the SINGLE MERGED production task `073.002-T` lands after ALL of them:
`073.002-T→{073.001-T,073.003-T,073.007-T,073.008-T,073.009-T}`. The final live
default-stdout composition gate `073.009-T` (A2+B2) is a genuine test-first prerequisite
(Finding 5); because A2 and B2 are ONE atomic code task (2026-09-15 P0 green-gate fix),
completing `073.002-T` greens the composition gate and every other test task together in
a single verifiable step. Former separate stream-B code task `073.004-T` is
retired/merged into `073.002-T` (edges removed, out of shipment). Stream C is retired,
so its former `073.006-T→073.004-T` behavioral edge and all stream-C test-first edges are
removed (2026-09-15 operator decision). The first-cut B-on-A ordering edge was already
removed (H5). The merged task remains a single cohesive credential-redaction domain;
width isolation yields to the stronger per-task-green invariant.

### Minimal safe contract (invariants)

1. `metadata.source` (and therefore anything derived/printed from it) MUST NOT
   contain userinfo or query-string credentials on ANY fetch path (default or
   execute). URL PATH components are preserved BYTE-FOR-BYTE (2026-09-15 operator
   decision: path-embedded secret redaction is REJECTED; the former "no path-embedded
   secret" clause here is superseded).
2. `job_id` MUST remain derived from the raw `build_source_key` (determinism /
   cache-path stability preserved; identical between default and execute paths).
3. No change to `create_staging_job`'s existing string-only behavior for
   genuine bare URL/path strings when `sanitized_source` is not supplied — but
   the fallback MUST fail closed on compound source-key prefixes (see the
   hardened API contract below); it may never silently pass a compound
   credentialed key through the no-op branch.
4. Coverage expansion is strictly additive — it may only redact more, never less —
   and must not introduce false-positive corruption of benign params/paths.

## Remediation cycle 1 — hardened contract (064-S review BLOCKED → resolved)

Standard review + a 4-reviewer adversarial review returned BLOCKED on the
first-cut plan. The findings below are **same-contract-surface completions**
under P-021 C1 (the exact credential-redaction contract this batch already
owns), not different-contract work, so they are resolved here rather than
deferred. Each maps to the plan's implementation units and task acceptance
criteria.

### H1 — Credential query-parameter name grammar (fail-closed, testable)

`_is_credential_param` previously matched by case-insensitive `startswith`
against `_CREDENTIAL_PARAM_PREFIXES`. That prefix heuristic over-redacted benign
near-matches (`tokenizer`/`keynote`/`secretary`/`authorship`/`signal`). Per the FINAL
Operator Contract (Finding 1) the `startswith` heuristic is REPLACED by an explicit
exact-match vocabulary — the "KEEP startswith for existing markers" rule below is
SUPERSEDED. The FINAL grammar:

* **Legacy/cloud markers** (individually enumerated, case-insensitive EXACT match):
  `token`, `access_token`, `auth_token`, `refresh_token`, `api_key`, `apikey`, `key`,
  `secret`, `client_secret`, `auth`, `authorization`, `sig`, `signature`,
  `x-amz-credential`, `x-amz-signature`, `x-amz-security-token`, `x-goog-signature`,
  `x-goog-credential`, `awsaccesskeyid`. The names present in the current
  `_CREDENTIAL_PARAM_PREFIXES` constant (`token`, `access_token`, `key`, `api_key`,
  `secret`, `auth`, `sig`, `signature`, `x-amz-credential`, `x-amz-signature`,
  `x-amz-security-token`, `x-goog-signature`) are preserved by individual enumeration;
  the real-credential names previously caught only by the `startswith("auth")` prefix
  (`auth_token`, `authorization`) are enumerated to keep prior coverage; and
  `refresh_token`, `apikey`, `client_secret`, `x-goog-credential`, `awsaccesskeyid` are
  the intended additional legacy/cloud names. Each real credential-name variant is
  enumerated in its own right, so coverage parity/expansion for real credentials is
  preserved WITHOUT the prefix false positives — `tokenizer`/`keynote`/`secretary`/
  `authorship`/`signal` no longer match.
* **Completeness boundary (Finding 7):** this vocabulary is NOT claimed universally
  complete. Names outside it — vendor-specific credential params not enumerated, and
  suffixed/prefixed variants of real names that the retired `startswith` heuristic used
  to catch (e.g. `token_v2`, `access_token2`, `my_api_key`) — are INTENTIONALLY NOT
  redacted absent explicit product support. This is an accepted residual (recorded in
  Risks and Mitigations), not a silent gap; benign prefix fixtures assert it.
* **Newly added markers** (`password`, `pwd`, `passwd`, `client_secret`,
  `refresh_token`, `code`): use **case-insensitive EXACT equality**, NOT
  `startswith`. Delimiter-boundary (`_`) matching is explicitly REJECTED because
  the benign fixtures `password_policy`, `pwd_length`, and `code_version` all
  carry a `_` after the marker and MUST NOT be redacted — exact equality is the
  only rule consistent with every benign fixture.
* **Percent-encoded markers**: unchanged bounded-decode contract. `_is_credential_name`
  applies up to `_MAX_CREDENTIAL_DECODE_LAYERS` (5) `unquote` layers and re-tests
  the grammar on each layer; if still transforming after 5 layers it fails closed
  (treats as credential). New markers ride this decode loop for free.

**Fixtures (exact expected outputs):**

| Param name | Decision | Rationale |
|---|---|---|
| `password`, `PWD`, `passwd`, `client_secret`, `refresh_token`, `code` | REDACT | exact new-marker match (case-insensitive) |
| `token`, `access_token`, `api_key`, `X-Amz-Signature` | REDACT | exact vocabulary match (each is an individually enumerated credential name) |
| `auth_token` | REDACT | enumerated in its own right (`auth_token`/`access_token` are listed explicitly; matches by exact equality, NOT by an `auth`/`token` prefix) |
| `Passwd`, `PASSWD`, `Refresh_Token`, `REFRESH_TOKEN` | REDACT | case-varied exact new-marker match (case-insensitive) — proves redaction is case-insensitive for `passwd`/`refresh_token`, not just `pwd` |
| `password_policy`, `pwd_length`, `code_version` | KEEP | `_`-suffixed benign; exact match does not fire |
| `Password_Policy`, `PWD_Length`, `Codec`, `Code_Version` | KEEP | case-varied variants of the existing benign near-matches; exact match still does not fire |
| `client_secretary` | KEEP | `client_secret`+`ary`, no exact match; `secret` matches only by exact equality and does not fire |
| `Client_Secretary` | KEEP | case-varied benign near-match; exact match does not fire |
| `tokenizer`, `keynote`, `secretary`, `authorship`, `signal` (and case variants) | KEEP | legacy-marker false positives under the retired `startswith` heuristic (`token`/`key`/`secret`/`auth`/`sig` prefixes); now preserved because matching is EXACT (Finding 1) |
| `codec` | KEEP | `code`+`c`, exact-only marker does not fire |
| `passwd_file`, `Passwd_File`, `PASSWD_HASH` | KEEP | `passwd`+`_…` benign near-match (finding #3), case-varied; exact match does not fire |
| `refresh_token_ttl`, `Refresh_Token_TTL`, `REFRESH_TOKEN_EXPIRY` | KEEP | `refresh_token`+`_…` benign near-match (finding #3), case-varied; exact match does not fire |
| `%70assword` (→`password`) | REDACT | bounded percent-decode then exact match |

### H2 — Path-embedded secret grammar (fail-closed, testable) — REJECTED / HISTORICAL

> **REJECTED by the 2026-09-15 operator decision.** The grammar below is retained as a
> historical / rejected-alternatives record only. Docline leaves URL path components
> unchanged; there is no path matcher, no `<path-redacted>` sentinel, and no path
> decoding in executable scope.

`_sanitize_url` reconstructs the URL with `parsed.path` untouched. The hardened
grammar redacts secrets embedded in the URL PATH component, marker-gated, per
`/`-delimited segment, reusing the SAME credential-name matcher as H1 (single
source of truth — this is why stream C consumes stream B, a genuine dependency):

1. Split `parsed.path` on `/` into segments, preserving leading/empty segments
   and separators exactly (replacement-boundary safety).
2. For each segment, apply bounded percent-decode (≤5 layers, same contract as
   H1) and case-insensitive matching:
   * **`marker=value` segment** (contains `=`, name before `=` is a credential
     marker): replace the value in place → `name=<redacted>`; preserve the
     original (possibly percent-encoded) marker name bytes.
   * **bare marker segment** (whole decoded segment is a credential marker, no
     `=`) **immediately followed by another segment**: the following segment is
     the marker-associated value → replace it with `<redacted>`; preserve the
     marker segment.
   * **bare marker segment with NO following segment** (trailing `/token`): KEEP
     unchanged — the associated secret value is absent, so there is no leak, and
     redacting a legitimate `/token` endpoint path would corrupt a benign path.
   * **benign segment** (no marker): KEEP byte-for-byte.
3. **Bounded decoding / fail-closed:** if a segment still transforms after 5
   decode layers, treat it as marker-bearing and redact its value
   (fail closed). If the URL cannot be parsed/segmented safely (malformed URL,
   `urlparse`/`unquote` raising), fail closed by redacting the whole path
   component to the `<path-redacted>` sentinel rather than returning it
   unchanged.

**Exact expected outputs (path component):**

| Input path | Output path |
|---|---|
| `/token/SECRET` | `/token/<redacted>` |
| `/token=SECRET` | `/token=<redacted>` |
| `/Token/SECRET` | `/Token/<redacted>` (case-insensitive marker; original casing kept) |
| `/%74oken/SECRET` | `/%74oken/<redacted>` (decoded `token`; encoded marker bytes kept) |
| `/%74oken=SECRET` | `/%74oken=<redacted>` |
| `/client_secret/hunter2` | `/client_secret/<redacted>` (new marker via shared matcher; needs stream B) |
| `/a/token/SECRET/b` | `/a/token/<redacted>/b` (only offending value replaced) |
| `/api/v1/data` | `/api/v1/data` (benign, unchanged) |
| `/codec/data` | `/codec/data` (benign; `codec` is not `code`) |
| `/token` (trailing, no value) | `/token` (no associated value; unchanged) |
| deeply nested `>5` decode layers | segment value redacted (fail closed) |
| unparseable / malformed URL | path → `<path-redacted>` (fail closed) |

Query-string credentials remain handled by the existing `_is_credential_param`
filter in `_sanitize_url`; H2 adds ONLY path-component handling. Userinfo
stripping is unchanged.

> **Cycle-2 supersession (finding #1/#9):** the segmentation ORDERING above
> (split-on-literal-`/` then decode) is superseded by the **decode-before-
> segmentation** algorithm in `## Remediation cycle 2` → `H2-C2`, which closes the
> percent-encoded structural-delimiter gap (`%2F`→`/`, `%3D`→`=`), pins malformed-
> escape / multilayer / over-cap fail-closed outputs, and fixes the exact `/token/`
> trailing-empty behavior. C1/C2 and 073.005-T/073.006-T are reconciled to H2-C2.

### H3 — Hardened `create_staging_job` API (resolves unsafe `None` fallback + position ambiguity)

The first-cut plan added `sanitized_source: str | None = None` as a trailing
POSITIONAL-or-keyword parameter whose `None` fallback ran `sanitize_source(source)`
— the exact no-op-on-compound-keys path that leaks. Two problems: (a) positional
ambiguity (a caller could bind it by position after `content_type`); (b) the
fallback preserves the known unsafe compound-key path. Verified caller inventory:
one PRODUCTION caller (`orchestrate_fetch`) plus several existing TEST callers in
`tests/fetch/test_staging.py` that pass **bare** URL/path strings positionally
(`create_staging_job("http://example.com", ".cache")`, `…, http_status=200)`,
etc.). A required parameter would break those bare-string tests, so the invariant
is preserved by construction instead:

* Make `sanitized_source` **keyword-only** (declare after `*`): removes all
  positional-binding ambiguity and proves positional compatibility with every
  existing call (max 2 positional args today).
* Fallback contract when `sanitized_source is None`:
  * If `source` begins with a known COMPOUND source-key prefix (`web_crawl:`,
    `manifest_url:`, `github_repo:`, `manifest_git:`, `manifest_local:`,
    `local_file:`) → **fail closed** by RAISING a typed, non-leaking exception
    (e.g. `CredentialRedactionError`) whose `str()` echoes neither the raw key nor
    any credential substring (the whole-key sentinel fallback is REMOVED per
    Finding 4; never call the no-op `sanitize_source` on a compound key). This
    removes the known unsafe path and never substitutes a redaction sentinel for a
    raised error.
  * Else (genuine bare URL/path string) → existing `sanitize_source(source)`
    behavior, preserving backward compatibility for the existing bare-string
    test callers (which never pass compound keys).
* `orchestrate_fetch` ALWAYS passes `sanitized_source=sanitize_source_key(config)`,
  so the default production path never relies on the fallback at all.

This is invariant-preserving where it matters: a compound credentialed key can
never reach `metadata.source` through the fallback, while legitimate bare-string
callers are untouched.

### H4 — Deterministic raw-source `job_id`/cache-path oracle (explicit decision: accepted residual risk)

`job_id = make_job_id(build_source_key(config))` hashes the RAW (credential-
bearing) source key with SHA-256 truncated to 16 hex chars (64 bits). Reviewers
flagged a theoretical confirmation-oracle: an observer holding an emitted
`job_id` could hash candidate source keys to confirm a guess.

**Decision: remediate by design intent NOT changed; accept as narrowly-reasoned
residual risk.** Reasoning:

* SHA-256 is preimage-resistant; the truncated digest is not reversible. A
  confirmation oracle requires the attacker to already possess the ENTIRE raw
  key (host + options + the high-entropy secret). For a real secret/token
  (high entropy) this is computationally infeasible.
* Deriving `job_id` from the SANITIZED key instead would (a) break invariant 2
  (cross-path `job_id`/cache-path determinism and stability), (b) force a cache
  migration/invalidation, and (c) risk cache-poisoning collisions when two
  distinct-credential/same-structure sources sanitize to an identical key.
* The emitted artifact leaks the job_id (a one-way digest), never the credential.

**Tests / compatibility implications recorded:** A2 asserts `job_id`/`cache_path`
are byte-identical before/after (determinism guard); no cache-format migration;
a plan note documents that `job_id` is a non-reversible digest and is not a
credential sink. This is the same contract surface (job-ID determinism is core to
this shipment), so no new P-021 entry is warranted.

> **Cycle-2 supersession (finding #5):** the preimage-resistance argument above is
> INSUFFICIENT on its own for low-entropy `password`/`code` values. See
> `## Remediation cycle 2` → `H4-C2` for the low-entropy dictionary-confirmation
> acknowledgment, exposure assumptions, the compatibility-wins rationale, and the
> explicit rollback/revisit trigger. The decision (accept as narrowly-reasoned
> residual) stands; the JUSTIFICATION is corrected there.

### H5 — Width-isolation re-evaluation (2 streams → 3 streams; artificial edge removed) — see 2026-09-15 revision

> **Post-2026-09-15 operator decision:** stream C (path-embedded secrets) is retired,
> so the EXECUTABLE topology is now TWO width-isolated streams (A and B), each
> test-first, fully independent of each other. The 3-stream analysis below is
> historical; the genuine `073.006-T→073.004-T` C-on-B edge is removed with stream C.
> **Further superseded (2026-09-15 final correction):** the A2/B2 CODE tasks are no
> longer independent — they are MERGED into ONE atomic production task 073.002-T (the P0
> green-gate fix); 073.004-T is retired/blocked. The "two independent code streams"
> phrasing above is historical. Current authoritative topology: the FINAL Operator
> Contract at the top of this file and the plan's Dependency Graph.

With H1 (exact-match grammar for every new name) and H2 (full path-secret
grammar) added, the original single stream-B code task (`_CREDENTIAL_PARAM_PREFIXES`
+ `_is_credential_param` + `_sanitize_url` path redaction in one task) exceeds the
2-hour granularity rule and mixes two distinct behavioral surfaces. Split into
three width-isolated streams, all under 073-F / 064-S:

* **Stream A** — default-path sink (`create_staging_job`/`orchestrate_fetch`):
  `073.001-T` (test) → `073.002-T` (code).
* **Stream B** — query-parameter credential-name expansion + exact-match grammar
  (`_CREDENTIAL_PARAM_PREFIXES`, `_is_credential_param`): `073.003-T` (test) →
  `073.004-T` (code).
* **Stream C** — path-embedded secret redaction grammar (`_sanitize_url`):
  `073.005-T` (test) → `073.006-T` (code).

**Dependency edges (genuine `blocks` only):** `073.002-T→073.001-T`,
`073.004-T→073.003-T`, `073.006-T→073.005-T` (test-first within each stream), and
`073.006-T→073.004-T` (stream C reuses stream B's expanded credential vocabulary +
exact-match matcher as the single source of truth for path-segment marker
detection — a genuine behavioral dependency, since C1's `/client_secret/…` path
case only passes once B2 has added that marker). The first-cut **`073.004-T→073.002-T`
(B-on-A) edge is REMOVED**: it encoded same-file (`staging.py`) contention and
P0-before-P2 risk-ordering, which are execution-sequencing preferences, not
behavioral `blocks` dependencies. Same-file contention is managed by Ship's
sequential execution, not by a backlog edge.

## Remediation cycle 2 — hardened contract (FINAL cycle; 064-S adversarial re-review cycle 1 BLOCKED → resolved)

Post-remediation adversarial re-review (cycle 1) returned **BLOCKED** with four
unique P1 and five P2/P3 findings. All are **same-contract-surface completions**
(P-021 C1) of the credential-redaction contract this batch already owns — none is
different-contract work — so they are resolved here rather than deferred. This is
the FINAL allowed remediation cycle; no in-scope P1 is silently deferred. Stage
authored no product/test code; these are planning-artifact completions that pin the
executable contract Ship will implement.

### H2-C2 — Decode-before-segmentation completion (finding #1; percent-encoded structural delimiters, fail-closed) — REJECTED / HISTORICAL

> **REJECTED by the 2026-09-15 operator decision.** Retained as a historical /
> rejected-alternatives record only; not executable.

Cycle-1 H2 split `parsed.path` on the LITERAL `/` first and decoded each segment
afterward. That ordering leaves a gap: a percent-encoded structural delimiter
hidden INSIDE one literal segment is revealed only AFTER the split, so a
`marker`+value pair encoded as a single segment (`token%2FSECRET`) could evade
per-segment marker detection and leak. Cycle 2 makes the ordering and the
fail-closed behavior authoritative and pins exactly one output per input. This
SUPERSEDES the cycle-1 ordering where they differ and EXTENDS the cycle-1
exact-output table; the plan (Unit C1/C2), 073.005-T, and 073.006-T are all
reconciled to this single grammar.

**Authoritative algorithm (single source of truth for C1/C2):**

1. **Iterative malformed-escape validation (fail closed, EVERY layer).** Validate
   that every `%` in the CURRENT path string begins a well-formed `%[0-9A-Fa-f]{2}`
   escape — performed BEFORE the first decode AND re-performed on the freshly-decoded
   string before each subsequent decode layer (cycle-3 finding F-02). Any
   truncated/invalid escape at ANY layer (`%2`, `%ZZ`, trailing `%`, or one revealed
   only after an outer layer decodes — `%252`→`%2`, `%25ZZ`→`%ZZ`) → the whole path
   component fails closed to the `<path-redacted>` sentinel. Validating only before
   the first decode is INSUFFICIENT: a nested escape whose malformedness is masked by
   an outer valid `%25` (`%252`, `%25ZZ`) passes a single pre-scan and only surfaces
   after one decode layer, so validation and decoding are one interleaved per-layer
   loop.
2. **Bounded iterative decode cap (fail closed on over-cap), re-validated each layer.**
   Iteratively `unquote` up to `_MAX_CREDENTIAL_DECODE_LAYERS` (= 5) layers; before
   EACH layer's decode, re-run the step-1 malformed-escape validation on the current
   string. If the path is STILL changing after 5 layers (a 6th layer would differ) →
   whole path fails closed to `<path-redacted>` (over-cap input).
3. **Decode-before-segmentation.** Segment on `/` using the FULLY-DECODED path so
   decode-introduced `/` delimiters (from `%2F`) ARE treated as structural segment
   boundaries, while retaining a byte-span map back to the ORIGINAL raw
   (still-encoded) path so any preserved (non-redacted) span keeps its exact
   original bytes. Within a segment, a decode-introduced `=` (from `%3D`) is treated
   as the `marker=value` delimiter.
4. **Per-segment marker grammar** (unchanged marker semantics; applied on the
   decoded segmentation):
   * `marker=value` (name before the first `=` is a credential marker): redact the
     value → preserve the ORIGINAL raw marker-name bytes and the original delimiter
     bytes (`=` or its `%3D`/`%3d` encoding) + `<redacted>`.
   * bare marker segment followed by a NON-EMPTY value segment: redact that value →
     `<redacted>`; preserve the marker's original bytes.
   * bare marker segment with an EMPTY adjacent segment or no following segment
     (`/token/`, trailing `/token`): the required non-empty adjacent value is ABSENT
     ⇒ no secret ⇒ KEEP unchanged. Redaction fires ONLY on a non-empty adjacent
     value. If empty adjacent segments precede a later non-empty value under the
     same marker (`/token//SECRET`), that first non-empty value is redacted
     (fail-closed lean).
   * benign segment (no marker): KEEP the original raw bytes byte-for-byte.
5. **Unmappable/ambiguous → fail closed.** If decode-then-resegment cannot be mapped
   back onto the raw byte spans unambiguously, the whole path component fails closed
   to `<path-redacted>`.

**`/token/` trailing-empty rule (findings #1, #9 — authoritative).** Path-value
redaction REQUIRES a non-empty adjacent value. `/token/` = marker `token` followed
by an empty segment (nothing after the final `/`): no secret is present, and
redacting a legitimate `/token/` endpoint would corrupt a benign path ⇒ `/token/`
is KEPT UNCHANGED. This is the "requires non-empty adjacent value" resolution; the
alternative "explicit fail-closed" is not chosen because there is no secret to fail
closed over. (Consistent with the cycle-1 trailing `/token` benign-endpoint rule.)

**Pinned exact outputs (cycle 2; EXTENDS the cycle-1 H2 table):**

| Input path | Output path | Rule |
|---|---|---|
| `/token%2FSECRET` | `/token%2F<redacted>` | `%2F`→`/`; decode-before-segmentation reveals `token`+value; value redacted, encoded marker+delimiter bytes preserved |
| `/token%2fSECRET` | `/token%2f<redacted>` | lowercase-hex encoded `/`; original casing preserved |
| `/token%3DSECRET` | `/token%3D<redacted>` | `%3D`→`=`; `marker=value` grammar; value redacted, encoded `=` preserved |
| `/%74oken%2FSECRET` | `/%74oken%2F<redacted>` | nested: `%74oken`→`token`, `%2F`→`/`; value redacted, encoded bytes preserved |
| `/token%252FSECRET` | `/token%252F<redacted>` | multilayer `%252F`→`%2F`→`/` within cap; value redacted, raw bytes preserved |
| `/token%2/SECRET` | `<path-redacted>` | malformed escape (`%2/`) → fail closed (step 1) |
| `/%ZZ/SECRET` | `<path-redacted>` | malformed escape (`%ZZ`) → fail closed (step 1) |
| `/token/%252` | `<path-redacted>` | nested malformed (finding F-02): `%252`→`%2` truncated after one decode layer; per-layer re-validation fails closed (step 1) |
| `/token/%25ZZ` | `<path-redacted>` | nested malformed (finding F-02): `%25ZZ`→`%ZZ` after one decode layer; per-layer re-validation fails closed (step 1) |
| path still transforming after 5 decode layers | `<path-redacted>` | over-cap → fail closed (step 2) |
| `/token/` | `/token/` | marker + empty adjacent segment; no non-empty value ⇒ KEEP unchanged |
| `/token//SECRET` | `/token//<redacted>` | empty adjacent then non-empty value; first non-empty value redacted (fail-closed lean) |

The cycle-1 pinned outputs (`/token/SECRET`→`/token/<redacted>`, `/token=SECRET`,
`/Token/SECRET`, `/%74oken/SECRET`, `/client_secret/hunter2`, `/a/token/SECRET/b`,
benign `/api/v1/data` & `/codec/data`, trailing `/token`, unparseable →
`<path-redacted>`) remain in force unchanged. Cycle 2 only ADDS the
encoded-structural-delimiter, multilayer, malformed-escape, over-cap, and `/token/`
rows above and fixes the decode/segment ORDERING so all rows hold under one
fail-closed grammar.

### H4-C2 — Low-entropy confirmation-oracle acknowledgment (finding #5)

**Preimage resistance alone does NOT resolve the oracle.** The cycle-1 reasoning
leaned on SHA-256 preimage resistance + high-entropy secrets. That is INSUFFICIENT
for the newly in-scope credential classes: `password` and `code` params can be LOW
entropy (dictionary words, short numeric OTP/`code` values). For a low-entropy
secret, an observer holding an emitted `job_id` CAN mount an offline
dictionary/brute-force confirmation: enumerate candidate raw source keys (host +
fixed options + a guessed low-entropy secret), truncate-hash each, and match the
64-bit digest. Preimage resistance does not prevent this — the search space, not
digest reversibility, is the limiting factor — so the oracle is a REAL (not merely
theoretical) risk for low-entropy credential material.

**Exposure assumptions (what an attacker needs — ALL of):** (a) possession of an
emitted `job_id` (leaked only to LOCAL observers of stdout/logs and the on-disk
cache-directory name — never transmitted to a remote endpoint by this code);
(b) knowledge of the full NON-secret key structure (source kind, host, path, option
ordering) so only the secret is unknown; and (c) a dictionary/keyspace small enough
to enumerate. The `job_id` still leaks only a one-way digest, never the credential
in cleartext.

**Why compatibility still wins (accepted residual — narrowly reasoned, NOT
dismissed as impossible).** Deriving `job_id` from the SANITIZED key would (i) break
invariant 2 (cross-path `job_id`/cache-path determinism shared with the
already-shipped 063-S execute path), (ii) force a cache-key migration/invalidation
of every existing staged job, and (iii) risk cache-poisoning collisions when two
distinct-credential/same-structure sources sanitize to an identical key. The
confirmation oracle requires LOCAL artifact access, which the threat model treats as
a lower tier than the remote/log credential-in-cleartext leak this shipment closes.
The residual is accepted narrowly and explicitly.

**Rollback / revisit trigger (explicit).** Migrate `job_id` derivation to a **keyed
construction over the RAW canonical source key** — i.e. `HMAC(workspace_secret,
build_source_key(config))` computed over the RAW (pre-sanitization) canonical key,
NOT over the sanitized key (cycle-3 finding F-05). Keying over the SANITIZED key is
explicitly REJECTED: two distinct-credential/same-structure sources can sanitize to
an IDENTICAL key, so HMAC-over-sanitized would REINTRODUCE the exact cache-poisoning
collisions that compatibility reason (iii) above guards against, while still failing
to distinguish them. HMAC over the RAW key preserves per-source uniqueness (no new
collisions) AND defeats the offline dictionary-confirmation oracle, because an
observer without the workspace secret cannot recompute the digest from a guessed key.
This migration carries explicit **key-management requirements** (generate and store a
per-workspace HMAC secret outside the cache and outside version control; support
rotation; on rotation treat all existing `job_id`s/cache paths as invalidated) and
**cache-migration requirements** (the keyed `job_id` changes every cache path, so a
one-time cache invalidation/rebuild is required — old and new `job_id`s will not
match). Trigger the migration if ANY of: (a) `job_id`/cache-path values begin to be
emitted to an untrusted REMOTE sink (telemetry upload, shared CI artifact index,
error-reporting service); (b) a high-value low-entropy credential class (e.g. short
numeric OTP `code`) becomes a common configured secret on these paths; or (c) the
operator threat model reclassifies local stdout/cache-dir observers as untrusted.
Until a trigger fires, the determinism/compatibility contract is retained.

### Stream-B title scope correction (finding #8)

The cycle-1 stream-B task TITLES still read "…and path-embedded secrets"
(073.003-T) and "…and redact path-embedded secrets" (073.004-T), even though H5
moved all path-embedded-secret scope to stream C (073.005-T/073.006-T). The titles
are corrected to describe ONLY query credential-name matching; path-secret scope
belongs solely to stream C. Feature 073-F, shipment 064-S, and the plan references
are reconciled to match.

### Live-sink coverage — integration test tasks (finding #2)

Cycle-1's Source-Kind × Sink matrix attributed **live** stdout (SO) coverage to A1
and **live** WARNING/error (WE) coverage to B1, but A1 and B1 are helper/unit-level
tests (A1 calls `orchestrate_fetch` and reconstructs JSON; B1 exercises
`_is_credential_param` directly). Neither drives the live `cli.py:381` stdout sink
or the live `source_keys._remove_credential_query_params` WARNING/error emission.
Two integration test tasks are added under 073-F so every stated live-sink invariant
is backed by an executable test, and A1/B1 are narrowed to their true (helper) level:

* **073.007-T** (stream A, test domain): invoke the live `docline fetch` default
  (non-`--execute`) CLI entrypoint and assert the REAL stdout emitted at
  `cli.py:381` contains no userinfo and no credential query params for all four
  URL-bearing source kinds (userinfo/query milestone green after 073.002-T:
  `073.002-T depends_on 073.007-T`). Cycle-3 finding F-04 adds a DIRECT
  path-embedded-secret fixture asserting exact secret-absence + `/token/<redacted>`
  on the real stdout, so the live-stdout path-secret cell is covered directly rather
  than compositionally; that path-secret assertion is green only after C2 lands
  (test-first: `073.006-T depends_on 073.007-T`, since C2's `_sanitize_url` path
  redaction reaches the default-path stdout via
  `sanitize_source_key`→`_sanitize_url_field`→`sanitize_source`→`_sanitize_url`).
  Cycle-3 finding F-01 narrows A1/073.001-T to helper-level in-memory
  `metadata.source` + reconstructed JSON only (A1's live-stdout wording removed; the
  live stdout sink is solely 073.007-T).
* **073.008-T** (stream B, test domain): assert the live WARNING/error text produced
  via the execute.py exception/log composition
  (`_scrub_exception_for_logging`/`_scrub_exception_message`/
  `_exception_scrub_replacements`/`_sanitize_exception_text`, which chains the shared
  `source_keys._remove_credential_query_params` matcher and emits through the
  `_log.exception(...)` sink — the 059-S/063-S WARNING/error path) drops the FULL
  set of newly added credential NAMES
  (`password`/`pwd`/`passwd`/`client_secret`/`refresh_token`/`code`/`apikey`/
  `x-goog-credential`/`awsaccesskeyid`) for EACH of the four URL-bearing source kinds
  (WebCrawlSource, ManifestUrlSource, GitHubRepoSource, ManifestGitSource) — explicit
  all-four coverage matching the four matrix rows that attribute BI to it (cycle-3
  finding F-03; parametrized 4 kinds × 9 names, within the 2-hour test-domain
  boundary), not a single source-kind-agnostic case. It ALSO asserts error-output
  PROVENANCE byte-preservation: `config.branch` / `config.path_glob` / manifest
  `config.id` / local `path` / `include` — which the execute.py composition
  INDEPENDENTLY passes through `sanitize_source_id`/`_sanitize_exception_text` — are
  preserved BYTE-FOR-BYTE in the composed WARNING/error text, so only structured
  URL/typed credentials are removed and non-credential provenance is never mangled.
  Green only after the single merged production task 073.002-T lands (test-first:
  `073.002-T depends_on 073.008-T`; the execute.py provenance-preservation change is
  the 4th file in 073.002-T's scope).

EX (exception CAUSE/CONTEXT chain) coverage stays honestly `n/a` for these URL paths
— the exception cause/context CHAIN-object scrubbing sinks (`95BD0DC7`, `709BDB53`,
`_clone_scrubbed_exception`/PEP-678 `__notes__`/ExceptionGroup traversal) are separate
unreachable 063-S residuals, NOT claimed or tested here. This is DISTINCT from the WE
column: the exception MESSAGE composition that feeds the `_log.exception(...)`
WARNING/error TEXT (`_scrub_exception_message` in execute.py) IS in scope for both
credential-name redaction AND provenance byte-preservation, and is tested by
BI/073.008-T. The EX `n/a` refers only to the unreachable cause/context chain-object
scrubbing, not to the reachable execute.py message-composition sink. No overclaim
remains.

### Cycle-2 finding dispositions

| # | Finding (severity) | Disposition | Where resolved |
|---|---|---|---|
| C2-P1-1 | Path-secret grammar incomplete where percent-decoding introduces structural delimiters; `/token/` undefined | PLANNING_CONTRACT_FIXED — decode-before-segmentation grammar, pinned fail-closed outputs for `%2F`/`%3D`/multilayer/malformed/over-cap, exact `/token/` rule | H2-C2 (this section); plan Unit C1/C2 + criterion 4; 073.005-T/073.006-T ACs |
| C2-P1-2 | Live WARNING/stdout coverage attributed to helper-only tests | PLANNING_CONTRACT_FIXED — added integration test tasks 073.007-T (live stdout) + 073.008-T (live WARNING new-names); A1/B1 narrowed; EX honestly n/a | "Live-sink coverage" (this section); plan matrix + dependency graph |
| C2-P1-3 | Missing benign case-varied near-match fixtures for `passwd`/`refresh_token` | PLANNING_CONTRACT_FIXED — H1 table + 073.003-T ACs add `passwd_file`/`refresh_token_ttl` and case-varied variants of all benign near-matches | H1 fixtures table; 073.003-T ACs |
| C2-P1-4 | Unqualified `FIXED` in planning-only reporting | RESOLVED_IN_STAGING_ARTIFACTS — cycle-1 disposition tokens requalified to `PLANNING_CONTRACT_FIXED`/`RESOLVED_IN_STAGING_ARTIFACTS`/`PLANNED` in plan + memory | plan cycle-1 table; cycle-1 memory; this table |
| C2-P2-5 | Job-ID oracle record too narrow (preimage-only) | RESOLVED_IN_STAGING_ARTIFACTS — H4-C2 adds low-entropy dictionary confirmation, exposure assumptions, compatibility rationale, rollback/revisit trigger | H4-C2 (this section); plan criterion 5 |
| C2-P2-6 | Missing `## Constitution Check` | PLANNING_CONTRACT_FIXED — added mapping applicable/non-applicable principles + residual risk | plan `## Constitution Check` |
| C2-P3-7 | Stale provenance in stage-073 memory (PR #200 as impl) | RESOLVED_IN_STAGING_ARTIFACTS — corrected to PR #199 impl / #200 closure | docs/memory/2026-09-14/stage-073-elt-credential-redaction-session.md |
| C2-P2-8 | Stream-B task titles claim path-secret scope | PLANNING_CONTRACT_FIXED — titles narrowed to query credential-name matching; 073-F/064-S/plan reconciled | "Stream-B title scope correction" (this section); backlog records |
| C2-P3-9 | Exact `/token/` behavior undefined | PLANNING_CONTRACT_FIXED — non-empty-adjacent-value requirement (KEEP `/token/`); folded into H2-C2 | H2-C2 `/token/` rule |

### Residual / out-of-scope (captured, NOT fixed here)

* H4 raw-source `job_id` confirmation-oracle — accepted residual risk with the
  cycle-2 low-entropy justification + explicit rollback trigger (H4-C2).
* Archived-stash→work-item tool pointer — backlogit limitation; durable prose
  traceability substituted.
* `79BF0AEC`, `E89DC095`, `9D44B6F3`, `E7878B1B`, `95BD0DC7`, `709BDB53` —
  distinct-contract P-021 entries, remain active/archived, out of 064-S scope. No
  new different-contract issue surfaced during cycle 2. **No in-scope P1 remains
  unresolved or silently deferred.**

## Remediation cycle 3 — operator-authorized exceptional cycle (final-cycle residuals → resolved)

Cycle 2 was recorded as the FINAL allowed remediation cycle, and the dark-factory run
correctly HALTED at the review cap rather than deferring or auto-applying another fix
pass. The **operator then explicitly authorized ONE additional bounded Stage
correction/re-review cycle** for shipment 064-S (scope held exactly to 064-S / 073-F).
This section is that operator-authorized exceptional cycle; it supersedes cycle 2's
"FINAL cycle" language solely by that explicit authorization. Scope is unchanged; no
related P-021 entry is absorbed; Stage authored only planning/backlog artifacts (that
earlier cycle left them uncommitted; the FINAL 2026-09-15 operator-contract correction
is committed by Stage on `chore/stage-064-s` — see the top Operator Contract, Finding
8). All five final-cycle residuals are
resolved here as same-contract-surface completions (P-021 C1); none deferred.

### Cycle-3 finding dispositions

| # | Finding (sev) | Disposition | Where resolved |
|---|---|---|---|
| F-01 (P1) | A1/073.001-T still overclaim live CLI stdout + source-kind coverage | PLANNING_CONTRACT_FIXED — A1/073.001-T restricted to helper-level in-memory `metadata.source` + reconstructed `model_dump` JSON; live-stdout wording removed; source kinds aligned exactly to the four AI/matrix use; live stdout kept SOLELY in 073.007-T; plan matrix SO column cites only AI/073.007-T (A1 reconstructed-JSON moved to M) | plan Unit A1 + matrix + notes; 073.001-T ACs |
| F-02 (P1) | Percent escapes validated only before the first decode, not after every layer | PLANNING_CONTRACT_FIXED — iterative per-layer malformed-escape validation (before AND after every decode layer); pinned nested-malformed fail-closed rows `/token/%252`→`<path-redacted>` (`%252`→`%2`) and `/token/%25ZZ`→`<path-redacted>` (`%25ZZ`→`%ZZ`); bounded multilayer + over-cap consistent across deliberation H2-C2, plan Unit C1/C2 + criterion 4, 073.005-T/073.006-T | H2-C2 steps 1–2 + pinned table (this doc); plan; 073.005-T/073.006-T |
| F-03 (P1) | 073.008-T does not exercise all four URL-bearing source kinds the WE matrix claims | PLANNING_CONTRACT_FIXED — 073.008-T + plan Unit BI exercise the live WARNING/error path for all four URL-bearing source kinds × the full new-name vocabulary (9 names; final-correction round extended this from the original six to the complete set and added execute.py error-output provenance byte-preservation) (within the 2-hour test-domain boundary); matrix and task now agree | Live-sink coverage bullet (this doc); plan Unit BI + matrix; 073.008-T ACs |
| F-04 (P1) | Live-stdout path-secret matrix cell covered compositionally, not directly | PLANNING_CONTRACT_FIXED — 073.007-T + plan Unit AI add a DIRECT path-embedded-secret fixture (exact secret-absence + `/token/<redacted>`) on the real `cli.py:381` stdout; matrix SO path-secret cell cites AI/073.007-T direct; genuine test-first edge `073.006-T depends_on 073.007-T` added (acyclic; stream A code stays decoupled from stream C) | Live-sink coverage bullet (this doc); plan Unit AI + matrix + dependency graph; 073.006-T/073.007-T |
| F-05 (P3) | Job-ID revisit proposal recommends HMAC over the SANITIZED key (retains collisions) | RESOLVED_IN_STAGING_ARTIFACTS — H4-C2 rollback/revisit trigger corrected to a keyed construction (HMAC) over the RAW canonical source key with explicit key-management + cache-migration requirements; HMAC-over-sanitized explicitly rejected (reintroduces same-structure cache-poisoning collisions) | H4-C2 trigger (this doc); plan criterion 5 + Constitution Check residual |

### Residual / out-of-scope (cycle 3 — captured, NOT fixed here)

* H4 raw-source `job_id` confirmation-oracle — accepted residual risk; cycle 3
  corrects only the revisit trigger (keyed over the RAW key), the decision (accept)
  stands.
* Archived-stash→work-item tool pointer — backlogit limitation; durable prose
  traceability substituted.
* `79BF0AEC`, `E89DC095`, `9D44B6F3`, `E7878B1B`, `95BD0DC7`, `709BDB53` —
  distinct-contract P-021 entries, remain active/archived, out of 064-S scope. No new
  different-contract issue surfaced during cycle 3. **No in-scope P1 remains
  unresolved or silently deferred.**

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
