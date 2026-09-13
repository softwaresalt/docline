---
title: "Source-key credential sanitization on ELT error/persistence paths"
date: 2026-09-12
agent: stage
kind: implementation-plan
source: docs/decisions/2026-09-12-source-key-credential-sanitization.md
stash_id: D6E758F5
covering_release_unit: chore
revision: R8
---

# Implementation Plan: Source-key credential sanitization (stash D6E758F5)

Source document: `docs/decisions/2026-09-12-source-key-credential-sanitization.md`

> **Revision R2** — revised after plan-review round 1 (FAIL: two P1s). Changes: (a) URL
> isolation now anchors on the URL scheme (`://`) and is restricted to the `web_crawl:` /
> `manifest_url:` prefixes only, closing the manifest_url silent-no-op leak and the colon-in-id
> ambiguity; (b) implementation units reordered to test-first so the redaction contract is
> observed red before the production wiring; (c) shared option-key constant + right-anchored
> suffix peel; (d) redaction verified against full log output (`caplog.text`, incl. traceback);
> (e) Constitution Check section added; (f) credential-list expansion explicitly deferred as a
> documented residual to hold strict D6E758F5 scope.

> **Revision R3** — revised after Copilot review on PR #194 (thread `PRRT_kwDOSsAX4c6hzYmm`).
> The R2 scheme-anchored string parse could not reliably resolve the manifest_url ambiguity:
> `ManifestUrlSource.id` is an unrestricted `str` (`src/docline/elt/manifest_models.py:65`) and the
> composed key is `manifest_url:<id>:<url>:<options>` (`src/docline/elt/source_keys.py:32-40`), so an
> `id` containing `http://`/`https://` defeats the "first scheme after prefix" anchor. The sanitizer
> contract is changed to **consume the typed `SourceConfig`** — sanitize `config.url` and recompose
> the key via the existing builder grammar (`_build_crawl_source_key`) — removing all string-parse
> ambiguity. `job_id` still hashes the raw `build_source_key(config)` (determinism invariant
> unchanged). The decision doc and tasks 072.001-T/072.002-T/072.003-T are updated to match.

> **Revision R4** -- revised after Copilot review on PR #195 (thread
> `PRRT_kwDOSsAX4c6hz0Jq`, comment `PRRC_kwDOSsAX4c7uR7ht`). R3 removed the string-parse
> *URL-isolation* ambiguity, but the typed recompose still placed `ManifestUrlSource.id` (an
> unrestricted `str`, `src/docline/elt/manifest_models.py:65`) VERBATIM into the recomposed
> `manifest_url:<id>:<url>:...` key, so a credential-bearing `id` (a scheme-bearing string carrying
> userinfo or `?token=...`) still leaked into `metadata.source` and the ERROR log even when
> `config.url` was sanitized -- violating the Requirements Trace no-credential-in-`metadata.source`-or-ERROR-log requirement. The contract is
> refined so the safe representation ALSO routes `config.id` through `sanitize_source()` for
> `ManifestUrlSource` before recompose; a credential-bearing-id scenario is added to Unit 1.
> `job_id` still hashes the raw `build_source_key(config)` (determinism invariant unchanged). The
> decision doc and task 072.001-T are updated to match.

> **Revision R5** -- revised after Copilot review on PR #195 (threads `PRRT_kwDOSsAX4c6h0OMq` /
> `PRRT_kwDOSsAX4c6h0OM1`, decision line 93 / plan line 123). R4 routed `config.id` through
> `sanitize_source()`, but that is a NO-OP for an unrestricted, non-URL-form `id` (e.g.
> `srcA?token=SECRET`): `sanitize_source()` only redacts strings it recognizes as a URL or absolute
> path and otherwise returns the string verbatim, so the token still reached `metadata.source` and
> the ERROR log -- a residual that CONTRADICTS the no-credential invariant. The contract is refined
> to apply **ID-specific credential redaction INDEPENDENT of URL detection** to the `id` segment (a
> `sanitize_source_id()` helper: strip `user:pass@` userinfo + redact credential-named `key=value`
> fragments using the existing `_CREDENTIAL_PARAM_PREFIXES` vocabulary, NOT expanding it), closing
> the non-URL-form-id gap rather than documenting it as an accepted exception. A non-URL
> credential-bearing-id regression case is added to Unit 1 (unit) and Unit 2 (integration). `job_id` still hashes the raw
> `build_source_key(config)` (determinism invariant unchanged). The decision doc, feature card
> 072-F, and tasks 072.001-T/072.002-T/072.003-T are updated to match. Also removes the R2
> `_CRAWL_OPTION_KEYS` shared-constant add/refactor: the typed-config recompose reuses the existing
> `_build_crawl_source_key`/`_crawl_option_parts` builder directly, so the separate parse path that
> the shared constant guarded no longer exists (plan/task/source realigned).

> **Revision R6** -- revised after Copilot review on PR #195 cycle 3 (unresolved threads
> `PRRT_kwDOSsAX4c6h0dUG`, plan line 129, and `PRRT_kwDOSsAX4c6h0dUO`, plan line 142). Two
> same-contract-surface findings on the R5 `sanitize_source_id` / `sanitize_source_key` contract:
> (1) the helper is NOT total for an unrestricted `str` -- `sanitize_source()` / `_sanitize_url()`
> reads `parsed.port`, which raises `ValueError` for a malformed URL-shaped value such as
> `https://host:notaport`; because Unit 3 calls `sanitize_source_key(config)` while building
> `metadata` BEFORE the fetch `try` (and again in the exception logger), a raising sanitizer would
> crash `_execute_single_source` or mask the original fetch failure; (2) the R5 "preserved
> byte-for-byte" guarantee for a credential-free `id` CONTRADICTS step (a) "apply `sanitize_source()`",
> which rewrites absolute-path/`file://` ids to `<local-path-redacted>` and drops URL fragments, so a
> credential-free id such as `/source-a` cannot be preserved. The contract is refined so
> `sanitize_source_id()` is TOTAL, non-throwing, and MARKER-GATED: it no longer delegates to
> `sanitize_source()`; it detects credential markers with a non-throwing string/regex scan, returns a
> credential-free id VERBATIM (byte-for-byte) regardless of shape, redacts only recognized credential
> fragments/userinfo when a marker is present, and FAILS CLOSED to `<source-id-redacted>` for a
> marker-bearing input it cannot surgically redact. `sanitize_source_key()` wraps the `config.url`
> sanitize fail-closed (a malformed URL yields `<source-url-redacted>` rather than raising), so the
> whole helper is total and safe to call before the fetch `try` and inside the logger. `job_id` still
> hashes the raw `build_source_key(config)` (determinism invariant unchanged). The decision doc,
> feature card 072-F, and tasks 072.001-T/072.002-T/072.003-T are updated to match.

> **Revision R7** -- revised after Copilot review on PR #195 cycle 4 (operator remediation
> cycle 5; unresolved threads `PRRT_kwDOSsAX4c6h05Dd`, task `072.001-T` line 18, comment db
> `3998103338`, and `PRRT_kwDOSsAX4c6h05Ds`, plan lines 174/178, comment db `3998103357`). Two
> same-contract-surface findings on the R6 `sanitize_source_id` marker scan: the marker detector
> classifies credential parameter names over the RAW id bytes, but the URL sanitizer it must stay
> consistent with classifies names AFTER `parse_qsl` percent-decoding
> (`src/docline/fetch/staging.py:109-115`). So a percent-encoded credential key such as
> `%74oken=IDSECRET` -- which `parse_qsl` decodes to the recognized `token=IDSECRET` -- has no raw
> key matching the vocabulary, the R6 no-marker branch returns the id VERBATIM, and `IDSECRET` leaks
> into `metadata.source` and the ERROR log (both the URL-shaped `id` and the opaque non-URL `id`).
> The contract is refined so `sanitize_source_id()` marker detection classifies parameter names on a
> DECODED VIEW using the SAME semantics `parse_qsl` uses -- exactly one `urllib.parse.unquote` pass,
> `encoding="utf-8"`, `errors="replace"`, never `.port` -- so an encoded credential name is
> recognized. The decode is used for DETECTION ONLY: the returned id is still built from the ORIGINAL
> raw bytes (credential-free id VERBATIM; a marker-bearing fragment surgically redacted in place with
> its raw, possibly-encoded key preserved and only the value replaced by `<redacted>`;
> `<source-id-redacted>` only when surgical redaction cannot complete). The single decode pass mirrors
> `parse_qsl` exactly, so a DOUBLE-encoded key (`%2574oken`, which decodes once to the literal
> `%74oken`, not `token`) is NOT treated as a marker -- identical to how the URL sanitizer leaves it
> -- keeping id and URL handling consistent, avoiding over-redaction of credential-free ids, and
> guaranteeing termination (no decode-until-stable loop). `errors="replace"` makes malformed /
> non-UTF8 percent sequences (`%zz`, a truncated `%e0`) total and non-throwing (they decode to
> replacement characters, match no credential name, and the credential-free id is returned verbatim).
> The helper stays TOTAL, non-throwing, and marker-gated; `job_id` still hashes the raw
> `build_source_key(config)` and the `_CREDENTIAL_PARAM_PREFIXES` vocabulary is NOT expanded (that
> stays deferred as `06A59B1D`). The decision doc, feature card 072-F, and tasks
> 072.001-T/072.002-T/072.003-T are updated to match.

> **Revision R8** -- revised after Copilot review on PR #195 cycle 5 (operator remediation cycle 6;
> unresolved threads `PRRT_kwDOSsAX4c6h1D4y`, plan line 260, and `PRRT_kwDOSsAX4c6h1D4t`, plan line
> 235). SUPERSEDES the R7 single-`unquote` detection above: that single pass mirrored `parse_qsl` and
> inherited its single-layer blind spot, so a DOUBLE-encoded credential key (`%2574oken=IDSECRET`,
> decoding once to literal `%74oken`) was returned VERBATIM and leaked `IDSECRET` on BOTH the id and
> url paths. Detection now runs a BOUNDED multi-layer `unquote` decode (fixed point or
> `_MAX_CREDENTIAL_DECODE_LAYERS = 5`), matches a credential marker at ANY layer (so double- and
> multi-layer encodings are recognized and surgically redacted over the raw bytes), and FAILS CLOSED
> (redacts) when a name is still decoding at the cap; termination is guaranteed (each pass removes >=1
> decodable escape) and the helper stays total (`errors="replace"`). A source-fact audit also brings
> the remaining same-sink URL-bearing variants `github_repo:` and `manifest_git:` (both reach
> `_execute_single_source` via `_fetch_github`) plus `manifest_local` id INTO the typed-config
> sanitizer (new task `072.004-T`), subsuming/closing the former `79BF0AEC` github_repo deferral.
> `job_id` still hashes the raw `build_source_key(config)`; `_CREDENTIAL_PARAM_PREFIXES` is NOT
> expanded (`06A59B1D` deferred) and `_sanitize_url` in `staging.py` is unchanged (059-S boundary
> held). The decision doc, feature card 072-F, tasks 072.001-T/072.002-T/072.003-T, and new task
> 072.004-T are updated to match.

## Problem Frame

`_execute_single_source` (`src/docline/elt/execute.py:203`) computes
`source_key = build_source_key(config)` (prefixed key embedding the raw URL for crawl sources),
then `job_id = make_job_id(source_key)` (`sha256(source_key)[:16]`). It writes
`metadata.source = sanitize_source(source_key)` to `metadata.json` and, on failure, calls
`_log.exception("... source_key=%s job_id=%s", source_key, job_id)`.

`sanitize_source()` (`src/docline/fetch/staging.py:59`) only sanitizes strings starting with
`http(s)://`, `file://`, or an absolute path. A `web_crawl:`/`manifest_url:`-prefixed key hits
none of those branches, so it is a no-op: the raw URL (userinfo + credential query params) leaks
to both `metadata.json` (persistence) and the ERROR log.

**Invariant:** `make_job_id` MUST keep hashing the exact raw `source_key`. Only the
metadata/log representation may be sanitized.

## Requirements Trace

| Requirement (from decision doc) | Implementation action |
|---|---|
| Sanitize embedded URL inside prefixed source keys | Add `sanitize_source_key()` in `source_keys.py` (Unit 1) |
| Correctly isolate the URL for BOTH web_crawl and manifest_url | Sanitize the typed `config.url` and recompose via `_build_crawl_source_key`; no string parse (Unit 1) |
| No credential in the manifest_url `id` segment (URL-shaped OR non-URL-form) | Marker-gated `sanitize_source_id(config.id)` credential redaction independent of URL detection before recompose; scheme-bearing AND non-URL credential-bearing-id cases (Unit 1, R6) |
| Helper is TOTAL / fail-closed -- never raises for arbitrary unrestricted `str` (malformed URL/id yields a redacted fallback, not an exception) | Fail-closed wrapper around the `config.url` sanitize + non-throwing marker-gated `sanitize_source_id`; malformed-input unit + integration regression (Units 1, 2, R6) |
| Credential-free IDs preserved verbatim (absolute paths, `file://`, fragment-bearing URLs) | `sanitize_source_id` returns the id byte-for-byte when no credential marker is present -- no `sanitize_source()` path/fragment mangling (Unit 1, R6) |
| Percent-encoded credential parameter names recognized at EVERY decode layer (no single- OR multi-layer encoding bypass) | `sanitize_source_id` and the URL guard classify parameter names over a BOUNDED multi-layer `unquote` decode (fixed point or `_MAX_CREDENTIAL_DECODE_LAYERS = 5`, utf-8, `errors="replace"`, no `.port`); a marker matched at ANY layer redacts the value over the raw bytes, and a name still decoding at the cap FAILS CLOSED; encoded-key, double-encoded (now surgically redacted), deep-encoded fail-closed, malformed-percent, and URL-path multi-layer regressions (Unit 1, Unit 1b, Unit 2, R8) |
| Do not change `job_id` determinism | Keep `make_job_id(source_key)` on raw key; sanitize only metadata/log (Unit 3) |
| No credential in `metadata.source` or ERROR log (incl. traceback) | Route both sinks through helper; assert against `caplog.text` (Units 2, 3) |
| Redaction observed before production change | Author failing redaction test first (Unit 2 before Unit 3) |
| Every same-sink URL-bearing source variant sanitized (`web_crawl`, `manifest_url`, `github_repo`, `manifest_git`); only filesystem keys pass through | Typed-config sanitize of url/id/branch/path components for WebCrawl/ManifestUrl/GitHubRepo/ManifestGit; `local_file` and `manifest_local` path components byte-identical (path-embedded-secret residual deferred as `06A59B1D`) (Unit 1, Unit 1b) |

## Constitution Check

Mapped against `.github/instructions/constitution.instructions.md` (actual principle names):

- **I. Safety-First Python:** satisfied — pure helper + call-site swap; reuses the vetted
  `sanitize_source()` primitive; no unsafe constructs.
- **II. Test-First Development (NON-NEGOTIABLE):** satisfied — the failing redaction test (Unit 2)
  precedes production wiring (Unit 3); each unit is single-domain and within the 2-hour rule.
- **III. Workspace Isolation and Security Boundaries:** central purpose — remove the credential
  leak from logs (incl. traceback) and persisted `metadata.json`; verified against full
  `caplog.text` and the written file.
- **IV. CLI Workspace Containment (NON-NEGOTIABLE):** n/a — no path/containment change.
- **V. Structured Observability:** preserved — ERROR log keeps `source_key`/`job_id` context in
  sanitized form and retains `exc_info` (traceback kept, not dropped).
- **VI. Single Responsibility:** satisfied — dedicated `sanitize_source_key()`; `sanitize_source()`
  semantics untouched.
- **VII. Destructive Command Approval (NON-NEGOTIABLE):** n/a — no destructive/irreversible step;
  historical `metadata.json` not rewritten.
- **VIII. Explicit Safety Modes:** applied — strict-safety enabled; plan hardened (see `## Plan
  Hardening`).
- **IX. Git-Friendly Persistence:** n/a — no schema/serialization change.
- **Determinism (Technical Constraint):** `job_id` raw-key hashing invariant pinned by an explicit
  raw-key recomputation assertion (Unit 2) plus the parity characterization (Unit 3).

## Implementation Units

### Unit 1 — Add `sanitize_source_key()` with ID-specific credential redaction (code; test-first)
- **Changes:**
  1. Add `sanitize_source_key(config: SourceConfig) -> str` in `src/docline/elt/source_keys.py`
     that consumes the **typed config** (not the composed key string). No new option-key constant is
     introduced: the sanitizer reuses the existing `_build_crawl_source_key`/`_crawl_option_parts`
     builder directly (the typed-config recompose removes the separate parse path the R2
     `_CRAWL_OPTION_KEYS` constant was meant to guard, so it is unnecessary):
     - For the two leak-scoped crawl configs (`WebCrawlSource`, `ManifestUrlSource`), sanitize the
       typed `config.url` via the existing public `sanitize_source()` (import from
       `docline.fetch.staging`; reuse -- do not duplicate `_CREDENTIAL_PARAM_PREFIXES`) inside a
       **fail-closed wrapper (R6):** `sanitize_source()` / `_sanitize_url()` reads `parsed.port`,
       which raises `ValueError` for a malformed URL-shaped value such as `https://host:notaport`, so
       the call is guarded -- on any `ValueError` (or other parse failure) it yields a fully-redacted
       URL sentinel `<source-url-redacted>` instead of propagating. **[R8] Multi-layer URL guard:** because `_sanitize_url`'s own `parse_qsl` decodes only ONE layer, also scan the URL's query parameter names with the same bounded multi-layer decode primitive (see (a)); if a credential marker is revealed at any layer beyond the first (a double+-encoded credential name the single-pass `_sanitize_url` would leave un-redacted, e.g. `%2574oken=SECRET`) OR a name is still decoding at the cap, FAIL CLOSED -- yield `<source-url-redacted>` for the whole URL segment rather than the partially-sanitized url. This closes the URL-path double-encoding leak WITHOUT modifying the shared `_sanitize_url` or `_CREDENTIAL_PARAM_PREFIXES` (059-S blast radius and the `06A59B1D` vocabulary boundary both held). Then **recompose** the key
       through the same `_build_crawl_source_key(prefix, sanitized_url, ...)` path that
       `build_source_key` uses, so the sanitized key is grammar-identical to the raw key except for
       the URL segment. This is immune to the `manifest_url:<id>:<url>` ambiguity even when `<id>`
       itself contains a URL scheme, because no composed string is parsed.
     - **`sanitize_source_key()` is TOTAL / fail-closed (R6):** because both the URL-sanitize step
       above and the id-sanitize step below never raise, `sanitize_source_key(config)` NEVER raises
       for any config, including a malformed URL-shaped `config.url` or `config.id`. This is required
       because Unit 3 calls `sanitize_source_key(config)` while constructing `metadata` BEFORE the
       fetch `try`, and again inside the exception logger: a raising sanitizer would otherwise crash
       `_execute_single_source` (instead of producing the normal incomplete-staging-job / fetch
       failure) or mask an original fetch failure in the logger. (Closes PR #195 Copilot finding
       `PRRT_kwDOSsAX4c6h0dUG`.)
     - **`ManifestUrlSource.id` marker-gated credential redaction (R6):** the recomposed manifest_url
       prefix is `manifest_url:<id>` and `id` is an unrestricted `str` that may be scheme-bearing OR
       a non-URL-form string carrying credentials (userinfo or `?token=...`, e.g. `srcA?token=SECRET`).
       Build the prefix from a credential-redacted id (`f"manifest_url:{sanitize_source_id(config.id)}"`)
       where `sanitize_source_id(raw_id: str) -> str` is TOTAL, non-throwing, and MARKER-GATED. It
       does NOT delegate to `sanitize_source()` (whose absolute-path/`file://` redaction and fragment
       drop would mangle a credential-free id, and whose `_sanitize_url()` can raise). Instead:
       (a) **detect credential markers** with a non-throwing scan over a DECODED VIEW of the id --
       `user:pass@` (or `user@`) userinfo before a host, and any `key=value` fragment whose key
       (case-insensitive) matches the EXISTING `_CREDENTIAL_PARAM_PREFIXES` vocabulary (reuse -- do
       NOT expand the list; that expansion stays deferred as stash `06A59B1D`). **[R8] Classify parameter names over a BOUNDED, FAIL-CLOSED MULTI-LAYER decode, not a single pass:** a single `unquote` pass (R7) mirrored `parse_qsl` but INHERITED its single-layer blind spot -- a DOUBLE-encoded credential key such as `%2574oken=IDSECRET` decodes once to the literal `%74oken` (not `token`), so R7 returned it verbatim and the raw string still carried the literal secret `IDSECRET` into `metadata.source` and the ERROR log (PR #195 Copilot finding `PRRT_kwDOSsAX4c6h1D4y`; the URL path shared the leak because `_sanitize_url` re-encodes `%2574oken=IDSECRET` unchanged). Detection now runs a bounded decode loop over each parameter-name token: `layer_0 = raw_name`; `layer_{i+1} = urllib.parse.unquote(layer_i, encoding="utf-8", errors="replace")`; stop when a FIXED POINT is reached (`layer_{i+1} == layer_i`) or after `_MAX_CREDENTIAL_DECODE_LAYERS = 5` passes, whichever comes first. A name is a credential MARKER when `_is_credential_param` matches at ANY layer, so single- AND multi-layer percent-encodings of a credential key (`%74oken`, `%2574oken`, ...) are all recognized. **Termination is guaranteed:** every non-fixed-point pass strictly removes at least one decodable `%HH` escape, so the loop stabilizes within (number of nested valid escapes) passes, hard-bounded by the layer cap; the helper is bounded, total, and deterministic. `errors="replace"` makes malformed / non-UTF8 percent sequences (`%zz`, a truncated `%e0`) total and non-throwing (they reach a fixed point, match no credential name, and a credential-free id is returned verbatim). **[R8] Fail closed on residual encoding ambiguity:** if the loop hits the `_MAX_CREDENTIAL_DECODE_LAYERS` cap WITHOUT reaching a fixed point (the name is still decoding, so the fully-decoded name cannot be proven credential-free), treat the fragment as a marker and redact its value -- never pass it through; a name that reaches a fixed point still carrying literal `%` bytes (undecodable invalid escapes such as `%zz`) is NOT ambiguous and, absent a marker at any layer, is preserved verbatim. The decoded view is used for DETECTION ONLY (see (c) for redaction over the raw bytes); detection never calls `urllib` `.port`;
       (b) **no marker -> return `raw_id` byte-for-byte** (verbatim), so a credential-free id of ANY
       shape -- an absolute path such as `/source-a`, a `file://` value, or a fragment-bearing URL
       such as `https://host/x#frag` -- is preserved exactly (Closes PR #195 Copilot finding
       `PRRT_kwDOSsAX4c6h0dUO`); (c) **marker present -> surgical, non-throwing redaction** via pure
       regex over the raw string: strip `user:pass@` userinfo and rewrite each recognized credential
       `key=value` to `key=<redacted>`, preserving all other bytes, so `srcA?token=SECRET` ->
       `srcA?token=<redacted>` and `https://u:p@host/x?token=T#frag` ->
       `https://host/x?token=<redacted>#frag`; (d) **marker present but redaction cannot complete
       (any internal error) -> FAIL CLOSED** to the fully-redacted sentinel `<source-id-redacted>`
       -- never the raw value, never raising. This CLOSES the R4/R5 gaps (non-URL-form-id no-op AND
       the throwing-parser and byte-preservation contradictions) with no accepted residual. Only the
       RAW `build_source_key(config)` (unsanitized id + url) is fed to `make_job_id`, so `job_id`
       determinism is unchanged. (Closes PR #195 Copilot findings `PRRT_kwDOSsAX4c6h0dUG` /
       `PRRT_kwDOSsAX4c6h0dUO`.)
     - **[R8] Extend the sanitized contract to EVERY same-sink URL-bearing variant.** The source-fact
       audit (see the R8 cycle section below) confirms `_execute_single_source`
       (`src/docline/elt/execute.py:222-256`) routes ALL config types through `build_source_key(config)`
       into the same `metadata.source` + ERROR-log sinks, and that `GitHubRepoSource`
       (`github_repo:{repo_url}@{branch}:{path_glob}`) and `ManifestGitSource`
       (`manifest_git:{id}:{url}@{branch}`) are BOTH URL-bearing and fetched via `_fetch_github`
       (`execute.py:246`). So they are sanitized here, NOT deferred:
       - `GitHubRepoSource`: sanitize `config.repo_url` via the same fail-closed `sanitize_source()`
         wrapper (+ the R8 multi-layer URL guard) used for crawl urls, marker-gate `config.branch`
         and `config.path_glob` via `sanitize_source_id`, and recompose
         `github_repo:{sanitized_repo_url}@{sanitized_branch}:{sanitized_path_glob}`. This SUBSUMES
         and CLOSES the former `79BF0AEC` github_repo deferral (reconciled/archived this cycle).
       - `ManifestGitSource`: credential-redact `config.id` via `sanitize_source_id`, sanitize
         `config.url` via the fail-closed url wrapper (+ R8 guard), marker-gate `config.branch`, and
         recompose `manifest_git:{sanitized_id}:{sanitized_url}@{sanitized_branch}`. Closes PR #195
         Copilot finding `PRRT_kwDOSsAX4c6h1D4t`.
       - `ManifestLocalSource`: credential-redact `config.id` via `sanitize_source_id` for uniform
         id handling across all manifest variants; `config.path` and `config.include` stay
         byte-identical (filesystem components; path-embedded-secret redaction remains the
         separately deferred `06A59B1D` residual).
       - `LocalFileSource`: return `build_source_key(config)` **byte-identical** (filesystem paths;
         no URL-credential sink; absolute-path disclosure is the separately deferred `06A59B1D` residual).
       The git-variant coverage is authored as **Unit 1b** (task `072.004-T`) to hold each task
       within the 2-hour rule; Unit 1 (task `072.001-T`) delivers the core helper, the R8 bounded
       multi-layer decode primitive, and the crawl (`WebCrawlSource` / `ManifestUrlSource`) coverage.
     - Keep `_build_crawl_source_key` / `_crawl_option_parts` AS-IS as the single builder grammar
       reused by both `build_source_key` and the sanitizer, so there is no separate parse grammar to
       drift and no option-suffix peel is needed; no new `_CRAWL_OPTION_KEYS` constant is introduced.
       Add `sanitize_source_key` and `sanitize_source_id` to `__all__`; update the module docstring
       to reflect the added safe-representation role.
- **Files:** `src/docline/elt/source_keys.py`, `tests/elt/test_source_keys.py` (new).
- **Tests (3 scenario groups, parametrized):** (1) crawl URL redaction + fail-closed: a `web_crawl:`
  config with userinfo + `?token=SECRET` + options -> token + userinfo ABSENT, prefix + option
  suffixes preserved; AND [R6] a MALFORMED URL (`https://host:notaport?token=SECRET`, where
  `_sanitize_url`'s `parsed.port` would raise) -> `sanitize_source_key()` returns WITHOUT raising,
  `SECRET` ABSENT, URL segment is the `<source-url-redacted>` sentinel. (2) `ManifestUrlSource.id`
  handling, parametrized over: (a) a scheme-bearing credential `id` (userinfo + `?token=IDSECRET`),
  (b) a NON-URL-form credential `id` (`srcA?token=IDSECRET`, no scheme) -- in both, `IDSECRET` +
  userinfo ABSENT while the non-credential id/prefix/options are preserved (proves redaction is
  independent of URL detection); (c) [R6] a MALFORMED URL-shaped credential-bearing `id`
  (`https://u:p@host:notaport?token=IDSECRET`) -> SURGICALLY redacted to `https://host:notaport?token=<redacted>` without raising
  (`sanitize_source_id()` is marker-gated and does NOT parse ports): userinfo + `IDSECRET` ABSENT,
  the recognized token fragment redacted, the malformed `:notaport` preserved byte-for-byte (no port
  parse, no `ValueError`, and NOT the `<source-id-redacted>` sentinel, which is reserved for a
  marker-bearing `id` whose surgical redaction cannot complete); (d) [R6] a credential-free
  absolute-path `id` (`/source-a`), (e) [R6] a credential-free fragment-bearing URL `id`
  (`https://host/x#frag`), and (f) [R6] a credential-free MALFORMED URL-shaped `id`
  (`https://host:notaport`, no marker) each returned VERBATIM (byte-for-byte, no path-redaction,
  fragment retained, malformed port preserved with no port parse). (3) a CREDENTIAL-FREE `GitHubRepoSource` and `LocalFileSource` returned byte-identical (a credential-free github_repo stays byte-identical even after Unit 1b; credentialed `github_repo` / `manifest_git` coverage and their redaction assertions live in Unit 1b / `072.004-T`)
  AND an empty-option credentialed `WebCrawlSource` sanitized. **[R7] Encoded-credential-name id scenarios (added):** (g) a percent-encoded credential-name id `srcA?%74oken=IDSECRET` (opaque, no scheme) AND its URL-shaped form `https://host/x?%74oken=IDSECRET` -- each decodes to `token` on the detection view -> SURGICALLY redacted to `srcA?%74oken=<redacted>` / `https://host/x?%74oken=<redacted>` (raw encoded key bytes preserved, only the value redacted over the raw string), `IDSECRET` ABSENT; (h) [R8] a DOUBLE-encoded id `srcA?%2574oken=IDSECRET` (decodes over two layers -> `%74oken` -> `token`, recognized at layer 2 by the bounded multi-layer scan) -> SURGICALLY redacted to `srcA?%2574oken=<redacted>` (raw double-encoded key bytes preserved, only the value redacted), `IDSECRET` ABSENT -- closing the R7 single-pass encoding bypass (PR #195 finding `PRRT_kwDOSsAX4c6h1D4y`); (h2) [R8] a DEEP-encoded id whose credential name is still decoding at the `_MAX_CREDENTIAL_DECODE_LAYERS` cap -> value redacted (FAIL CLOSED on residual ambiguity), secret ABSENT; (i) a credential-free id carrying a malformed / non-UTF8 percent sequence (`srcA?note=%zz`, `srcA?b=%e0%80`) -> `unquote(..., errors="replace")` does not raise, no credential name matches, id returned VERBATIM; (j) a percent-encoded userinfo id `https://user%3Apass@host/x` (decodes to `user:pass@`) -> userinfo marker detected on the decoded view and stripped from the raw id, credential ABSENT.
- **Posture:** test-first. Reuses vetted `sanitize_source` without altering it.

### Unit 2 — Author failing redaction test (tests; test-first RED)
- **Changes:** Update `test_url_fetch_failure_logs_source_key_and_job_id` in
  `tests/elt/test_elt_real_execution.py` to encode the redaction contract BEFORE the call-site
  is wired: (a) keep asserting `job_id in record.message` and `exc_info is not None`; (b) assert
  the persisted `metadata.source` equals `sanitize_source_key(config)`; (c) add a
  credential-bearing crawl URL (userinfo + `?token=SECRET`) and assert the literal `SECRET` /
  userinfo substrings are ABSENT from `caplog.text` (the FULL rendered record incl. traceback)
  AND from the written `metadata.json` text — the injected crawl failure MUST raise an exception
  whose message embeds the credentialed `config.url` (e.g. an error carrying `start_url`), so the
  `caplog.text` traceback assertion is a genuine RED and is NOT vacuously satisfied by a URL-free
  message like `OSError("Network down")`; (c2) add a `ManifestUrlSource` whose `id` is a NON-URL-form credential-bearing string (`srcA?token=IDSECRET`, no scheme) and assert `IDSECRET` is ABSENT from both `caplog.text` and the written `metadata.json` (R5 regression for the non-URL-form-id closure); (c3) [R6] add a MALFORMED credentialed config whose URL would make `_sanitize_url` raise (`https://host:notaport?token=SECRET`) and assert `_execute_single_source` does NOT crash with a sanitizer `ValueError` (it proceeds to the normal fetch-failure path) and `SECRET` is ABSENT from both `caplog.text` and `metadata.json` (R6 totality/fail-closed regression); (c4) [R7] add a percent-encoded credential-name manifest `id` (`srcA?%74oken=IDSECRET`, opaque) and assert `IDSECRET` is ABSENT from both `caplog.text` and `metadata.json` -- proving decoded-name detection closes the encoding bypass (the raw marker scan would miss `%74oken`); (c5) [R8] add a DOUBLE-encoded credential-name manifest `id` (`srcA?%2574oken=IDSECRET`) and a `github_repo`/`manifest_git` config whose credentialed url uses a double-encoded credential key, asserting the secret value is ABSENT from both `caplog.text` and `metadata.json` -- proving the bounded multi-layer decode closes the encoding bypass on the id AND url paths and across the git variants; (d) assert `job_id == make_job_id(build_source_key(config))`
  recomputed independently from the raw credentialed key — this pin, NOT the credential-free parity
  test, is the raw-hash oracle: an impl that hashes the SANITIZED key MUST fail this assertion.
- **Files:** `tests/elt/test_elt_real_execution.py`.
- **Tests:** the updated test itself; authored to FAIL (RED) against current code.
- **Posture:** test-first RED — locks redaction + traceback + determinism contract before wiring.

### Unit 3 — Wire the call-site to green (code; GREEN)
- **Changes:** In `_execute_single_source`, set
  `metadata = SourceMetadata(source=sanitize_source_key(config), ...)` and change the
  `_log.exception(...)` argument from `source_key` to `sanitize_source_key(config)`. Keep
  `job_id = make_job_id(source_key)` on the raw key. If Unit 2's `caplog.text` assertion reveals
  the `exc_info` traceback re-leaks the raw URL (a crawl exception embedding `config.url`), close
  it within this same ERROR sink by SCRUBBING the raw URL out of the logged exception (sanitize or
  wrap the exception message so the rendered traceback carries no credential). Do NOT drop
  `exc_info`: Unit 2 keeps asserting `exc_info is not None`, so the traceback MUST remain present
  but credential-free. Bounded to this file and this ERROR path (still D6E758F5 scope).
- **Files:** `src/docline/elt/execute.py`.
- **Tests:** Units 1 + 2 turn green; existing `test_web_crawl_orchestrate_and_execute_share_job_key`
  stays green (job-key parity / determinism).
- **Posture:** GREEN — smallest wiring that satisfies the pre-authored contract.

## Dependency Graph

- Unit 2 depends on Unit 1 (test imports `sanitize_source_key`).
- Unit 3 depends on Unit 2 (wiring turns the pre-authored red test green).
- No cycles. Order: **1 -> 2 -> 3** (helper -> failing redaction test -> wiring). Test-first
  ordering satisfied: redaction observed red (Unit 2) before the production change (Unit 3).

## Decisions and Rationale

- **Dedicated `sanitize_source_key()` (not extending `sanitize_source`)** — keeps the general
  bare-source sanitizer untouched (also used by `create_staging_job`), lowest regression risk.
- **Typed-config consumption + builder recompose (R3)** — sanitizes the typed `config.url` and
  recomposes via `_build_crawl_source_key`, eliminating the manifest_url positional no-op and ALL
  scheme-in-id / colon-in-id string-parse ambiguity (no composed string is parsed); keeps
  github_repo out of scope (deferred).
- **Reuse the existing builder, no new option-key constant** — the sanitizer recomposes via the
  existing `_build_crawl_source_key`/`_crawl_option_parts` rather than re-parsing, so no separate
  parse grammar exists to drift; the R2 `_CRAWL_OPTION_KEYS` shared constant is unnecessary under
  the typed-config recompose and is not introduced.
- **Total / fail-closed marker-gated `sanitize_source_id` (R6)** -- the id sanitizer never delegates
  to the throwing `sanitize_source()` / `_sanitize_url()` path; it is non-throwing over any `str`,
  preserves credential-free ids verbatim (of ANY shape, including a malformed URL-shaped
  `https://host:notaport`, since it does NOT parse ports), surgically redacts recognized credential
  markers, and fails closed to `<source-id-redacted>` ONLY for a marker-bearing id whose surgical
  redaction cannot complete (never for a merely-malformed id); the separate `config.url` sanitize is
  wrapped fail-closed to `<source-url-redacted>` on a malformed URL. The helper is thus safe to call
  before the fetch `try` and inside the exception logger without crashing or masking.
- **Bounded multi-layer decoded-name marker detection (R8)** -- `sanitize_source_id()` and the URL
  guard classify credential parameter names over a BOUNDED multi-layer `unquote` decode (fixed point
  or `_MAX_CREDENTIAL_DECODE_LAYERS = 5`, utf-8, `errors="replace"`, no `.port`), matching a marker
  at ANY layer, so single- AND multi-layer percent-encoded credential keys (`%74oken`, `%2574oken`,
  ...) are recognized rather than bypassing the gate (supersedes the R7 single-pass view, which
  leaked double-encoded keys). Detection is DETECTION-ONLY (value built from raw bytes; a
  marker-bearing fragment surgically redacted with its raw encoded key preserved); the loop is
  bounded/terminating (each pass removes >=1 decodable escape) and fails closed (redact) when a name
  is still decoding at the cap. Reuses the existing vocabulary (no expansion; `06A59B1D` stays
  deferred).
- **Same-sink URL-bearing coverage extended to git variants (R8)** -- the source-fact audit confirms
  `github_repo:` and `manifest_git:` keys reach the identical `_execute_single_source` metadata/log
  sinks, so both are brought into the typed-config sanitizer (repo_url/url sanitized;
  id/branch/path_glob marker-gated) rather than passed through. This subsumes and closes the former
  `79BF0AEC` github_repo deferral (reconciled/archived this cycle); only filesystem keys
  (`local_file:`, `manifest_local:` path components) remain byte-identical, with path-embedded-secret
  redaction still the separately deferred `06A59B1D` residual.
- **Sanitize representation, not the hashed key** — only way to satisfy both "no leak" and
  "job_id determinism" simultaneously.

## Risks and Caveats

- **Risk (eliminated by the R3 typed-config contract):** the R2 string-parse risks — manifest_url
  URL mis-isolation, an `id` containing `http(s)://` defeating the scheme anchor, and a URL
  path/query `:key=` colliding with the option-suffix grammar — no longer apply: the sanitizer
  consumes the typed `config.url` and recomposes via `_build_crawl_source_key`, so no composed
  string is parsed and there is no option-suffix peel. **Residual:** `sanitize_source()`
  URL-sanitization semantics still apply to the isolated `config.url` (userinfo + credential query
  params) and are covered by the Unit 1 scenarios (incl. an uppercase-scheme URL).
- **Risk (CLOSED by the R6 marker-gated, fail-closed refinement):** R4's `sanitize_source()`-only
  routing was a NO-OP for a non-URL-form credential-bearing `id`, and the R5 refinement, while
  redacting such ids, still (a) delegated to `sanitize_source()` -- whose `_sanitize_url()` reads
  `parsed.port` and RAISES `ValueError` on a malformed value such as `https://host:notaport`,
  crashing `sanitize_source_key(config)` at the pre-`try` metadata build or masking a fetch failure
  in the logger (PR #195 Copilot finding `PRRT_kwDOSsAX4c6h0dUG`) -- and (b) contradicted its own
  "preserved byte-for-byte" claim, since `sanitize_source()` rewrites absolute-path/`file://` ids to
  `<local-path-redacted>` and drops URL fragments (PR #195 Copilot finding `PRRT_kwDOSsAX4c6h0dUO`).
  **Mitigation (closes both):** `sanitize_source_id()` is now TOTAL, non-throwing, and MARKER-GATED
  -- it does not delegate to `sanitize_source()`; it returns a credential-free id VERBATIM
  (byte-for-byte) regardless of shape, redacts only recognized credential fragments/userinfo when a
  marker is present, and FAILS CLOSED to `<source-id-redacted>` for a marker-bearing input it cannot
  surgically redact. `sanitize_source_key()` wraps the `config.url` sanitize fail-closed (malformed
  URL -> `<source-url-redacted>`), so the whole helper never raises. Unit 1 and Unit 2 assert
  totality, verbatim preservation, and fail-closed behavior. `job_id` still hashes the raw key. This
  reuses the current `_CREDENTIAL_PARAM_PREFIXES` vocabulary WITHOUT expanding it (that expansion is
  separately deferred as `06A59B1D`).
- **Risk (CLOSED by the R7 decoded-name detection):** the R6 marker scan classified credential
  parameter names over the RAW id bytes, so a percent-encoded credential key (`%74oken=IDSECRET`,
  decoding to `token`) matched nothing and the no-marker branch returned the id verbatim, leaking
  `IDSECRET` into `metadata.source` and the ERROR log (PR #195 threads `PRRT_kwDOSsAX4c6h05Dd` /
  `PRRT_kwDOSsAX4c6h05Ds`). **Mitigation:** detection now percent-decodes parameter names with exactly
  one `unquote` pass mirroring `parse_qsl` (utf-8, `errors="replace"`, no `.port`) before matching,
  so encoded credential names are recognized; the decode is detection-only (redaction still operates
  over the raw bytes, preserving the encoded key and redacting only the value), the single pass leaves
  a double-encoded key un-redacted exactly as the URL sanitizer does (no over-redaction, guaranteed
  termination), and `errors="replace"` keeps malformed/non-UTF8 percent sequences total and
  non-throwing. Unit 1 and Unit 2 add encoded-key, double-encoded, malformed-percent, and
  encoded-userinfo regressions. `job_id` still hashes the raw key; vocabulary unchanged (`06A59B1D`
  deferred).
- **Risk (CLOSED by the R8 bounded multi-layer detection):** the R7 single-`unquote` view mirrored
  `parse_qsl` and inherited its single-layer blind spot -- a DOUBLE-encoded credential key
  (`%2574oken=IDSECRET`, decoding once to literal `%74oken`) matched nothing, so the id/URL was
  returned with the literal `IDSECRET` value intact in `metadata.source` and the ERROR log (PR #195
  finding `PRRT_kwDOSsAX4c6h1D4y`; the URL path shared the leak because `_sanitize_url` re-encodes
  `%2574oken=IDSECRET` unchanged). **Mitigation:** detection now runs a bounded multi-layer decode
  (fixed point or `_MAX_CREDENTIAL_DECODE_LAYERS = 5`), matches a marker at ANY layer, surgically
  redacts the value over the raw bytes (double-encoded key preserved, `IDSECRET` absent), and FAILS
  CLOSED (redacts) on a name still decoding at the cap; termination is guaranteed (each pass removes
  >=1 escape). Unit 1/1b/2 add double-encoded, deep-encoded fail-closed, and URL-path multi-layer
  regressions. `job_id` still hashes the raw key; vocabulary unchanged (`06A59B1D` deferred).
- **Risk (CLOSED by the R8 same-sink coverage):** `github_repo:` (deferred `79BF0AEC`) and
  `manifest_git:` (PR #195 finding `PRRT_kwDOSsAX4c6h1D4t`) were pass-through, so a token in a git
  repo URL reached the same sinks. **Mitigation:** both are now sanitized by the typed-config helper
  (Unit 1b / `072.004-T`); `79BF0AEC` is reconciled/archived as subsumed. **Residual (still
  deferred, holds scope):** `0F1A653C` (the string-arg `create_staging_job` default-fetch sink, a
  materially distinct call path) and `06A59B1D` (vocabulary expansion + path-embedded secrets,
  cross-path blast radius) remain active deferrals.
- **Risk:** `exc_info` traceback re-leaks the URL. **Mitigation:** Unit 2 asserts absence against
  `caplog.text` (full record incl. traceback), forcing Unit 3 to close the traceback path.
- **Risk:** silently changing `job_id`. **Mitigation:** determinism assertion + parity test.
- **Documented residual (NOT fixed here, holds scope):** `_CREDENTIAL_PARAM_PREFIXES` omits
  `password`/`pwd`/`passwd`/`client_secret`/`refresh_token`/`code`, and `_sanitize_url` does not
  redact path-embedded secrets. Expanding that shared list would alter the 059-S WARNING-path
  sanitizer too, widening blast radius beyond D6E758F5 -> **deferred** and recorded as a P-021
  watch; carried to closure as a known partial-redaction limitation.
- **Documented residual — parallel default-fetch sink (NOT fixed here, holds scope):** the
  non-`--execute` `docline fetch` path (`orchestrate_fetch` -> `create_staging_job`,
  `src/docline/fetch/staging.py:161`) has the IDENTICAL `sanitize_source()` no-op leak, persisting
  the raw credentialed key to `metadata.json` and stdout (`cli.py:381`). This shipment fixes only
  `_execute_single_source` per strict D6E758F5 scope -> **deferred**, captured as stash **0F1A653C**
  (high). Surfaced by the Stage adversarial multi-model review (2026-09-12).
- **Caveat (updated R8):** `github_repo:` tokens are now IN SCOPE and sanitized (Unit 1b / `072.004-T`); the former `79BF0AEC` deferral is reconciled/archived as subsumed.
- **Caveat:** pre-existing `metadata.json` files are not rewritten (historical-artifact note to
  closure).

## Plan Hardening Signals (REQUIRED)

- public API, schema, or contract change: **absent** — internal helper; `metadata.source` string
  content changes for credentialed URLs but the field/schema is unchanged.
- security, auth, permission, or compliance-sensitive behavior: **PRESENT** — credential-leak
  remediation touching secrets handling in logs and persisted metadata.
- migration, backfill, destructive/irreversible step: **absent** — no data migration; previously
  persisted `metadata.json` files are not rewritten.
- external integration / operator checkpoint / external dependency: **absent**.
- high runtime, rollout, or rollback risk: **absent** — pure function + call-site swap; trivially
  revertible.

**Requires plan hardening: yes** (security/secrets signal present; strict-safety enabled).

## Runtime Verification and Closure

- **Runtime surface changed:** ELT fetch background execution (ERROR log output + persisted
  `metadata.json`). No CLI/API signature change.
- **Runtime verification:** run elt/staging tests; confirm a credentialed crawl URL yields a
  `metadata.json` and ERROR log (incl. traceback) with the token/userinfo redacted and the
  sanitized host/path retained; confirm `job_id` matches the pre-fix value for the same config.
- **Operational closure:** note that pre-fix `metadata.json` files may still contain unsanitized
  keys (historical artifacts, not backfilled) and record the deferred credential-list/path-secret
  residual + github_repo deferral for Ship/operator awareness.

## Plan Hardening

**Hardening required:** yes. Trigger: security/secrets-sensitive behavior — remediation of a
credential leak into logs (ERROR, incl. traceback) and persisted metadata (`metadata.json`).
strict-safety enabled -> risky actions classified below.

### Protected invariants
- `make_job_id(source_key)` input bytes unchanged -> `job_id` determinism + cache-path sharding
  preserved. Any diff to the string fed to `make_job_id` is a hardening violation.
- `sanitize_source()` / `_sanitize_url()` behavior for bare sources unchanged (no edits there);
  `create_staging_job` callers unaffected.
- The credential-prefix list stays the single source of truth via reuse, not duplication; it is
  NOT expanded in this shipment (deferred residual).

### Learnings and instructions consulted
- `docs/compound/2026-09-08-backlogit-task-wit-may-not-define-size-complexity.md` (sizing probe).
- `docs/compound/2026-08-31-harness-artifacts-lf-and-raw-byte-checksums.md` (hash over canonical
  bytes, not display form — reinforces the sanitize-representation-not-hash decision).
- `docs/compound/2026-06-04-pydantic-namespace-merge-vs-overwrite.md` (persisted-metadata mutation
  caution).
- `.github/instructions/strict-safety.instructions.md`, `ci-security.instructions.md`,
  `technology-python.instructions.md`. Compound grep for credential/redact = no prior fix.

### Risky action classification (ProposedAction / ActionRisk)
- **ProposedAction:** change the string content persisted to `metadata.json` and emitted to the
  ERROR log (incl. handling of `exc_info` traceback) for credentialed crawl keys.
  - **ActionRisk:** LOW. No schema/field change; no destructive/irreversible step; no historical
    rewrite. Reversible via single-commit revert.
  - **Approval needed:** no (non-destructive; within dark-mode pre-authorized scoped code PR).
  - **ActionResult (expected):** credentials absent from both sinks + traceback; sanitized
    host/path retained; `job_id` unchanged.
- No destructive/migration/backfill actions proposed.

### Verification depth
- Determinism precheck: capture `job_id` for a fixed `web_crawl` config; assert identical after
  (Unit 3 + `..._share_job_key`).
- Redaction proof: Unit 2 asserts literal token/userinfo ABSENT from `caplog.text` (full record)
  AND `metadata.json`.
- Pass-through: Unit 1 asserts non-crawl prefixes byte-identical.

### Rollback
- Single-commit revert restores prior behavior; no state to unwind. Trigger: any `job_id`
  determinism regression or staging-path test failure.

### Review-gate capability risks carried forward
- Plan review MUST emit literal `dispatch_mode:` and `decision:` markers.
- Security Lens Reviewer required (secrets handling); if cross-model/anchor dispatch unavailable,
  declare degradation and apply its rubric inline — do NOT skip.

**Unresolved operator decisions blocking safe execution:** none.

## Plan Review

<!-- plan-review-attempt: 1 -->
dispatch_mode: multi-agent
decision: FAIL

Round 1 review (superseded by round 2 below after plan revision R2). Recorded for audit trail.

- Dispatch: multi-agent. Personas run as subagents: Security Lens Reviewer, Python Reviewer,
  Scope Boundary Auditor, Architecture Strategist, Constitution Reviewer, Learnings Researcher.
- Gate: FAIL — two P1 findings.

Findings:
- **P1 (Python Reviewer):** manifest_url URL isolation via positional split would feed
  `<id>:<url>` into `sanitize_source()` (no-op) -> credential still leaks. Anchor on URL scheme.
- **P1 (Constitution Reviewer):** test-first ordering gap — redaction assertions ordered after the
  production wiring; contract not observed red first.
- **P2 (Security Lens):** `exc_info` traceback may re-leak URL; assert against `caplog.text` not
  just `record.message`.
- **P2 (Python/Architecture):** right-anchored option-suffix peel + shared option-key constant to
  avoid mis-split and build/parse drift.
- **P2 (Security Lens):** credential-param list omits `password`/`client_secret`/`refresh_token`.
- **P2 (Constitution):** missing Constitution Check section.
- **P3:** module docstring/`__all__` update; path-embedded-secret residual acknowledgement.
- Scope Boundary Auditor: CLEAN (github_repo correctly deferred, no creep).
- Learnings Researcher: no relevant prior art; no P0/P1.

Resolution: plan revised to R2 — scheme-anchored prefix-restricted isolation (P1a), test-first
reorder 1->2->3 (P1b), `caplog.text` redaction assertion (P2), shared `_CRAWL_OPTION_KEYS` +
right-anchored peel (P2), Constitution Check added (P2), credential-list expansion + path-secret
deferred as documented residual (P2/P3 — holds strict scope).

<!-- plan-review-attempt: 2 -->
dispatch_mode: multi-agent
decision: PASS

Round 2 review of revision R2 (re-evaluation of the round-1 findings against the revised plan).

- Dispatch: multi-agent (round-1 persona findings re-evaluated against R2; same persona rubric
  set: Constitution, Python, Scope Boundary, Learnings always-on; Architecture + Security Lens
  cross-model/triggered). Security Lens triggered by secrets handling and covered.
- Plan hardening: required (security signal) and satisfied — `## Plan Hardening` present with
  strict-safety `ProposedAction`/`ActionRisk` classification.

Persona coverage (R2):
| Persona | Mode | Result |
|---|---|---|
| Constitution Reviewer | subagent (round 1) -> re-evaluated R2 | P1 (test-first) RESOLVED; P2 (Constitution Check) RESOLVED |
| Python Reviewer | subagent (round 1) -> re-evaluated R2 | P1 (manifest_url no-op) RESOLVED; P2 split/drift RESOLVED |
| Scope Boundary Auditor | subagent | CLEAN (unchanged) |
| Architecture Strategist | subagent (anchor-eligible) | P3 advisories addressed (shared constant, docstring) |
| Security Lens Reviewer | subagent | P2 caplog.text RESOLVED; credential-list + path-secret residual DEFERRED + documented |
| Learnings Researcher | subagent | no prior art; no P0/P1 |

Gate: PASS — no P0/P1 remain. Residual P2 (credential-list expansion, path-embedded secrets) is
an explicitly documented out-of-scope residual + P-021 deferral watch, not a blocking gap for the
D6E758F5 leak fix. P3 advisories incorporated. Runtime verification and operational closure
expectations are present. Plan is harvest-ready.

## Adversarial Multi-Model Review (Stage, pre-staging-PR gate 2)

Operator requires, before every PR, BOTH (1) standard multi-persona review and (2) explicit
adversarial multi-model review. Gate (1) = plan-review rounds 1–2 above (FAIL -> PASS). Gate (2)
recorded here: Stage-owned adversarial review of the exact local staging diff `origin/main..HEAD`
(reviewed HEAD `bd93a406`, pre-remediation).

- **Reviewers (independent models/providers, parallel):** Anthropic `claude-opus-4.8`, OpenAI
  `gpt-5.6-sol`, Google `gemini-3.8-flash`, xAI `grok-4.6`. Verdicts: 3 BLOCK, 1 PASS. All
  findings adjudicated by Stage against the actual source (`source_keys.py`, `staging.py`,
  `execute.py`, `orchestrate.py`, tests) before disposition.
- **Consensus findings resolved in Stage-owned artifacts (this diff):**
  - P1 — unacknowledged second live leak sink (`orchestrate_fetch`/`create_staging_job` default
    `docline fetch` path). VERIFIED against source. Disposition: closure claims scoped to
    `_execute_single_source`; sink captured as deferral stash `0F1A653C` (NOT triaged into 063-S).
  - P1 — determinism test net too weak (parity test uses a credential-free URL). Disposition:
    Unit 2 AC(d) strengthened to an independent raw-key `make_job_id` recomputation oracle.
  - P1 — traceback re-leak under-specified + Unit 2/Unit 3 `exc_info` contradiction. Disposition:
    Unit 3 mandates SCRUB (keep `exc_info`); Unit 2 requires a credentialed-URL-bearing exception.
  - P2 — decision `P-021 Deferral Watch` said "None" vs plan/memory. Disposition: reconciled;
    three deferrals captured as stash `0F1A653C`/`79BF0AEC`/`06A59B1D`.
  - P2 — `## Constitution Check` mapped invented principle names. Disposition: remapped to the
    actual constitution (I Safety-First Python … VII Destructive Approval …).
  - P3 — stale "splits a prefixed key" (decision Option B), sub-epic prose, 063-S EOF blank line,
    archive `harvested_artifact_id`, scheme-in-id/uppercase robustness. Disposition: all fixed.
- **Residual after remediation:** the three captured deferrals (`0F1A653C` high, `79BF0AEC`,
  `06A59B1D`) remain out-of-scope for 063-S by operator P-017 scope freeze; no P0/P1 remain in the
  staged artifacts. Gate (2): PASS.

## PR #195 Copilot Remediation (Revision R4)

Copilot review on PR #195 (thread `PRRT_kwDOSsAX4c6hz0Jq`, comment `PRRC_kwDOSsAX4c7uR7ht`,
`docs/plans/...-plan.md` line 99) flagged that the R3 typed-config recompose still placed
`ManifestUrlSource.id` (an unrestricted `str`) VERBATIM into the recomposed
`manifest_url:<id>:<url>:<options>` key, so a credential-bearing `id` leaked into `metadata.source`
and the ERROR log even when `config.url` was sanitized.

- **Classification (P-021 C1):** IN SCOPE — same-contract-surface finding on this Stage-owned plan
  artifact (source-key credential sanitization). Fixed in-cycle; not deferred.
- **Fix (R4):** the safe representation ALSO routes `config.id` through `sanitize_source()` for
  `ManifestUrlSource` before recompose (`manifest_url:{sanitize_source(config.id)}`); Unit 1
  scenario 2 is strengthened to a credential-bearing-`id` case asserting the `id` credential is
  absent from the recomposed key. `make_job_id` still hashes the raw `build_source_key(config)` —
  determinism invariant unchanged.
- **Artifacts updated:** this plan (Requirements Trace, Unit 1, Risks, revision note), the decision
  doc (Option B R4 refinement, Chosen Direction, Done Looks Like), and tasks 072.001-T / 072.002-T
  / 072.003-T (CONTRACT label + AC(2)).
- **Known residual (SUPERSEDED by R5 — now CLOSED):** R4 left a documented residual that
  `sanitize_source()` no-ops on a non-URL-form credential-bearing `id`. PR #195 cycle-2 review
  (threads `PRRT_kwDOSsAX4c6h0OMq` / `PRRT_kwDOSsAX4c6h0OM1`) correctly flagged this as contradicting
  the no-credential invariant; R5 closes it with ID-specific credential redaction independent of URL
  detection (see the Cycle 2 section below).
- **Independent review:** Correctness Reviewer (targeted, this diff) — leak closure, determinism
  invariant, cross-artifact consistency, and source-fact accuracy all confirmed; one P3
  (residual-vector mischaracterization) raised and remediated in the same cycle. Verdict: PASS.

## PR #195 Copilot Remediation — Cycle 2 (Revision R5)

Cycle-2 Copilot review on PR #195 raised four unresolved same-contract-surface findings on the
Stage-owned R4 artifacts:

- `PRRT_kwDOSsAX4c6h0OMq` (decision line 93) and `PRRT_kwDOSsAX4c6h0OM1` (plan line 123): routing
  `config.id` through `sanitize_source()` overstates closure — a non-URL-form `id` such as
  `srcA?token=SECRET` is a no-op and still leaks to `metadata.source` and the ERROR log; require
  validation/rejection or ID-specific redaction independent of URL detection, with a regression case.
- `PRRT_kwDOSsAX4c6h0OM9` (`.backlogit/queue/072-F.md` line 21): the feature card is stale (labels
  the helper R3, describes sanitizing only `config.url`).
- `PRRT_kwDOSsAX4c6h0ONH` (`.backlogit/queue/072.001-T.md` line 18): the task says to "keep"
  `_CRAWL_OPTION_KEYS`, but that constant does not exist; plan Unit 1 required adding it — a
  task/plan contract drift.

- **Classification (P-021 C1):** all four IN SCOPE — same-contract-surface findings on Stage-owned
  planning artifacts for feature 072-F / shipment 063-S. Fixed in-cycle; none deferred; no P-021 C2
  capture required.
- **Fix (R5) — credential closure:** the safe representation applies ID-specific credential
  redaction INDEPENDENT of URL detection to `config.id` (`sanitize_source_id`): strip userinfo +
  redact credential-named `key=value` fragments using the existing `_CREDENTIAL_PARAM_PREFIXES`
  vocabulary (not expanded), so `srcA?token=SECRET` -> `srcA?token=<redacted>`. The R4 non-URL-form
  residual is CLOSED, not documented as an exception. Unit 1 scenario 2 is parametrized to add a
  non-URL-form credential-id regression case. `make_job_id` still hashes the raw
  `build_source_key(config)` — job-id determinism preserved.
- **Fix (R5) — `_CRAWL_OPTION_KEYS` drift:** removed the R2 shared-constant add/refactor from plan
  Unit 1, the rationale, and task 072.001-T. The typed-config recompose reuses the existing
  `_build_crawl_source_key`/`_crawl_option_parts` builder directly, so the separate parse path the
  constant guarded no longer exists — plan, task, and source realigned (no nonexistent constant
  referenced).
- **Artifacts updated:** this plan (revision R5 note, Requirements Trace, Unit 1, Risks, rationale,
  this section), the decision doc (Option B R5 refinement, Chosen Direction, Done Looks Like),
  feature card 072-F, and tasks 072.001-T / 072.002-T / 072.003-T.
- **Independent review:** Correctness Reviewer (targeted, this diff) — leak closure, determinism
  invariant, cross-artifact consistency, and `_CRAWL_OPTION_KEYS` drift resolution confirmed.
  Verdict: PASS.

## PR #195 Copilot Remediation -- Cycle 3 (Revision R6)

Cycle-3 Copilot review on PR #195 raised two unresolved same-contract-surface findings on the
Stage-owned R5 artifacts, both on the `sanitize_source_id` / `sanitize_source_key` contract:

- `PRRT_kwDOSsAX4c6h0dUG` (plan line 129, comment db `3997932059`): `sanitize_source()` is not
  total for the unrestricted `str` fields used here -- `_sanitize_url()` reads `parsed.port`, which
  raises `ValueError` for a malformed value such as `https://host:notaport`. Because Unit 3 calls
  `sanitize_source_key(config)` while building `metadata` before the fetch `try` (and in the
  exception logger), such a config would crash `_execute_single_source` or mask the original fetch
  failure. Require the helper to fail closed WITHOUT raising (a fully-redacted fallback for malformed
  URLs) plus a regression case.
- `PRRT_kwDOSsAX4c6h0dUO` (plan line 142, comment db `3997932072`): the byte-preservation guarantee
  conflicts with step (a) "apply `sanitize_source()`", which rewrites every absolute-path or
  `file://` value to `<local-path-redacted>` and drops URL fragments, so a credential-free id such
  as `/source-a` cannot be preserved verbatim. Define `sanitize_source_id()` to return the id
  verbatim when no credential marker exists, or narrow the guarantee; synchronize decision/tasks.

- **Classification (P-021 C1):** BOTH IN SCOPE -- same-contract-surface findings on Stage-owned
  planning artifacts for feature 072-F / shipment 063-S (the `sanitize_source_id` /
  `sanitize_source_key` contract). Verified authoritatively against the live PR review threads
  (Copilot login `copilot-pull-request-reviewer`); these are the only two unresolved threads. Fixed
  in-cycle; neither deferred; no P-021 C2 capture required.
- **Fix (R6) -- totality / fail-closed:** `sanitize_source_key()` wraps the `config.url` sanitize
  fail-closed (a `ValueError` from `_sanitize_url`'s `parsed.port` yields `<source-url-redacted>`
  rather than propagating), and `sanitize_source_id()` is TOTAL and non-throwing, so the whole
  helper never raises and is safe to call before the fetch `try` and inside the logger. Closes
  `PRRT_kwDOSsAX4c6h0dUG`.
- **Fix (R6) -- verbatim preservation + marker gating:** `sanitize_source_id()` no longer delegates
  to `sanitize_source()`. It detects credential markers with a non-throwing scan, returns a
  credential-free id byte-for-byte regardless of shape (absolute path, `file://`, fragment-bearing
  URL), redacts only recognized credential fragments/userinfo when a marker is present, and fails
  closed to `<source-id-redacted>` for a marker-bearing input it cannot surgically redact. Closes
  `PRRT_kwDOSsAX4c6h0dUO`. `make_job_id` still hashes the raw `build_source_key(config)` --
  determinism invariant unchanged.
- **Regression scenarios added:** Unit 1 -- malformed `config.url`
  (`https://host:notaport?token=SECRET`) returns without raising with the URL redacted to
  `<source-url-redacted>` (the `config.url` path parses `.port` and is wrapped fail-closed); a
  malformed URL-shaped credential-bearing `id` (userinfo + `?token=IDSECRET`, nonnumeric port) is
  SURGICALLY redacted to `https://host:notaport?token=<redacted>` (marker-gated, no port parse, NOT
  the sentinel); credential-free `/source-a`, `https://host/x#frag`, and a malformed URL-shaped
  `https://host:notaport` preserved verbatim. Unit 2 -- a malformed credentialed config does not crash
  `_execute_single_source` nor mask the fetch failure, with the credential absent from `caplog.text`
  and `metadata.json`.
- **Artifacts updated:** this plan (revision R6 note, Requirements Trace, Unit 1, Unit 2, Risks,
  rationale, this section), the decision doc (Option B R6 refinement, Chosen Direction, Done Looks
  Like), feature card 072-F, and tasks 072.001-T / 072.002-T / 072.003-T.
- **Independent review:** targeted independent review (this diff) -- totality/fail-closed closure,
  verbatim-preservation correctness, determinism invariant, and cross-artifact consistency
  confirmed. Verdict: PASS.

## PR #195 Copilot Remediation -- Cycle 4 (Revision R7)

Cycle-4 Copilot review on PR #195 (operator remediation cycle 5) raised two unresolved
same-contract-surface findings on the Stage-owned R6 artifacts, both on the `sanitize_source_id`
marker-detection contract:

- `PRRT_kwDOSsAX4c6h05Dd` (task `072.001-T` line 18, comment db `3998103338`): the execution task
  repeats the raw-regex marker design with no case for percent-encoded credential names; because the
  existing sanitizer decodes query names before matching, `%74oken=IDSECRET` is semantically a
  recognized `token` parameter, so a literal regex scan can miss it and return the unrestricted id
  unchanged. Requires decoded-name matching plus an acceptance case proving the secret is absent.
- `PRRT_kwDOSsAX4c6h05Ds` (plan lines 174/178, comment db `3998103357`): the raw-regex marker scan
  leaves an encoding bypass in the central no-leak contract. The URL sanitizer classifies names after
  `parse_qsl` decoding (`src/docline/fetch/staging.py:109-115`), but an id such as
  `https://host/x?%74oken=SECRET` has no raw key matching `token`, so the no-marker branch returns it
  verbatim and leaks `SECRET` into metadata and the error log. Classify decoded parameter names
  without accessing `.port`, and add encoded-key regressions for URL-shaped and opaque ids.

- **Classification (P-021 C1):** BOTH IN SCOPE -- same-contract-surface findings on Stage-owned
  planning/backlog artifacts for feature 072-F / shipment 063-S (the `sanitize_source_id` marker
  detector). Verified authoritatively against the live PR review threads at HEAD `11b7d39` (Copilot
  login `copilot-pull-request-reviewer`); a full GraphQL enumeration of all 15 review threads confirms
  these are the ONLY two unresolved threads (no additions since the prior snapshot). Fixed in-cycle
  under the operator's continue-autonomously authorization; NEITHER deferred; no P-021 C2 capture
  required. The erroneously-appended deferral stash entry `C53CF18E` (which had proposed deferring
  exactly this fix) is reconciled as superseded/fixed-in-scope and archived, not carried as a deferral.
- **Fix (R7) -- decoded-name detection:** `sanitize_source_id()` marker detection now classifies
  credential parameter names on a DECODED VIEW using the same semantics `parse_qsl` uses -- exactly
  one `urllib.parse.unquote` pass, `encoding="utf-8"`, `errors="replace"`, never `.port` -- so a
  percent-encoded credential key such as `%74oken=IDSECRET` (decoding to `token`) is recognized. The
  decode is DETECTION-ONLY: the returned id is still built from the ORIGINAL raw bytes -- a
  credential-free id VERBATIM, a marker-bearing fragment surgically redacted in place with the raw
  (possibly-encoded) key preserved and only the value replaced by `<redacted>`, and
  `<source-id-redacted>` only when surgical redaction cannot complete. Closes `PRRT_kwDOSsAX4c6h05Dd`
  / `PRRT_kwDOSsAX4c6h05Ds`.
- **Termination / error behavior (explicit):** exactly one bounded decode pass (NO decode-until-stable
  loop), so a double-encoded key (`%2574oken` -> literal `%74oken`, not `token`) is NOT treated as a
  marker -- identical to the URL sanitizer's own single `parse_qsl` decode, keeping id and URL handling
  consistent and avoiding over-redaction of credential-free ids; `errors="replace"` makes malformed /
  non-UTF8 percent sequences (`%zz`, truncated `%e0`) total and non-throwing; detection never parses
  ports; any internal redaction failure on a marker-bearing id fails closed to `<source-id-redacted>`.
  The helper stays TOTAL, non-throwing, and marker-gated.
- **Regression scenarios added:** Unit 1 -- (g) encoded-key id `srcA?%74oken=IDSECRET` and URL-shaped
  `https://host/x?%74oken=IDSECRET` surgically redacted (encoded key preserved, value `<redacted>`,
  `IDSECRET` absent); (h) double-encoded `srcA?%2574oken=IDSECRET` returned VERBATIM (bounded single
  decode); (i) malformed/non-UTF8 percent (`srcA?note=%zz`, `srcA?b=%e0%80`) credential-free id
  returned verbatim without raising; (j) percent-encoded userinfo `https://user%3Apass@host/x`
  userinfo stripped. Unit 2 -- a percent-encoded credential-name manifest id asserts `IDSECRET` absent
  from `caplog.text` and `metadata.json`.
- **Invariants preserved:** `make_job_id` still hashes the raw `build_source_key(config)` (job-id
  determinism unchanged); `_CREDENTIAL_PARAM_PREFIXES` NOT expanded (vocabulary-expansion stays
  deferred as `06A59B1D`); crawl `config.url` handling unchanged (the URL path already decodes via
  `parse_qsl`, so it was never subject to this bypass).
- **Artifacts updated:** this plan (frontmatter revision R7, Revision R7 note, Requirements Trace,
  Unit 1, Unit 2, Decisions, Risks, this section), the decision doc (Option B R7 refinement, Chosen
  Direction, Done Looks Like), feature card 072-F, and tasks 072.001-T / 072.002-T / 072.003-T.
- **Stash reconciliation:** erroneous active stash entry `C53CF18E` (Ship's out-of-scope deferral of
  this exact fix) archived as superseded/fixed-in-scope; the unrelated pre-existing 3-line
  timestamp-normalization working-copy diff on `0F1A653C` / `79BF0AEC` / `06A59B1D` preserved
  byte-for-byte and excluded from the fix commit.
- **Independent review:** targeted independent correctness/security review (this diff) -- decoded-name
  detection closes the encoding bypass, detection-only decode preserves determinism and verbatim
  credential-free ids, single-pass bound guarantees termination, `errors="replace"` guarantees
  totality, cross-artifact consistency confirmed. Verdict: PASS.

## PR #195 Copilot Remediation -- Cycle 5 (Revision R8)

Cycle-5 Copilot review on PR #195 (operator remediation cycle 6) raised two unresolved
same-contract-surface findings on the Stage-owned R7 plan, verified against the live PR review
threads at HEAD `199e7a4` via a fully-paginated GraphQL enumeration (22 reviews, 18 review threads,
`hasNextPage=false` on both; Copilot login `copilot-pull-request-reviewer`). Exactly TWO threads are
unresolved (no additions since Ship's snapshot):

- `PRRT_kwDOSsAX4c6h1D4t` (plan line 235, comment db `3998169888`): `ManifestGitSource` is URL-bearing
  -- its unrestricted `url` is composed verbatim into `manifest_git:<id>:<url>@<branch>`
  (`src/docline/elt/manifest_models.py:75-92`, `src/docline/elt/source_keys.py:41-42`) and
  `_execute_single_source` persists/logs that key -- but the R7 contract left it in the byte-identical
  pass-through set, so a token in a Git URL reaches the same sinks.
- `PRRT_kwDOSsAX4c6h1D4y` (plan line 260, comment db `3998169896`): the R7 acceptance case (h)
  returned a double-encoded id `srcA?%2574oken=IDSECRET` VERBATIM; decoding the key twice yields the
  recognized `token` marker, so the literal secret is written to `metadata.source` and the ERROR log
  -- an encoding bypass contradicting the plan's no-credential invariant.

### Source-fact audit (read-only; every `build_source_key` component vs. the `_execute_single_source` sinks)

`_execute_single_source` (`src/docline/elt/execute.py:222-256`) computes `source_key =
build_source_key(config)` for ALL config types, writes `metadata.source = sanitize_source(source_key)`,
and on failure logs `source_key` at ERROR -- one shared sink pair for every variant. `build_source_key`
(`src/docline/elt/source_keys.py`) composes:

| Config | source_key grammar | Unrestricted / URL-bearing components | Same sink? | R8 disposition |
|---|---|---|---|---|
| `LocalFileSource` | `local_file:{paths}` | filesystem paths (no URL cred) | yes | byte-identical pass-through (path-secret = `06A59B1D`) |
| `WebCrawlSource` | `web_crawl:{url}:{opts}` | `url` (userinfo+query) | yes | sanitize url + R8 multi-layer guard (already in contract) |
| `GitHubRepoSource` | `github_repo:{repo_url}@{branch}:{path_glob}` | `repo_url` (userinfo/query; git token), `branch`, `path_glob` | yes (`_fetch_github`) | **NOW sanitized (Unit 1b); subsumes `79BF0AEC`** |
| `ManifestLocalSource` | `manifest_local:{id}:{path}:{includes}` | `id` (unrestricted), `path`/`includes` (filesystem) | yes | id marker-gated; path components byte-identical |
| `ManifestUrlSource` | `manifest_url:{id}:{url}:{opts}` | `id`, `url` | yes | sanitize_source_id(id) + sanitize url + R8 guard (already) |
| `ManifestGitSource` | `manifest_git:{id}:{url}@{branch}` | `id`, `url`, `branch` | yes (`_fetch_github`) | **NOW sanitized (Unit 1b); PR #195 `PRRT_kwDOSsAX4c6h1D4t`** |

Audit conclusion: the same-sink URL-bearing set is {`web_crawl`, `manifest_url`, `github_repo`,
`manifest_git`}. R7 covered only the first two; the audit shows the last two reach the identical sinks,
so leaving them pass-through is a piecemeal omission. `local_file` / `manifest_local` are
filesystem-only (no URL-credential sink); their path-embedded-secret exposure stays the separately
deferred `06A59B1D` residual.

### Classification (P-021 C1)

BOTH findings are IN SCOPE -- same-contract-surface defects on the Stage-owned planning/backlog
artifacts for feature 072-F / shipment 063-S (the typed-config `sanitize_source_key` /
`sanitize_source_id` contract and its variant coverage). Per the operator's no-residual-risk
authorization for this cycle, both are fixed in-cycle; NEITHER is deferred; no P-021 C2 capture is
created. A known reachable credential leak (the double-encoding bypass) is not accepted merely because
a different source variant is involved.

### Fix (Revision R8)

1. **Bounded multi-layer decoded-name detection.** `sanitize_source_id()` and the URL guard classify
   credential parameter names over a BOUNDED multi-layer `unquote` decode -- `layer_{i+1} =
   unquote(layer_i, encoding="utf-8", errors="replace")`, stopping at a fixed point or
   `_MAX_CREDENTIAL_DECODE_LAYERS = 5`. A marker matched at ANY layer redacts the fragment value over
   the RAW bytes (encoded key preserved). This supersedes the R7 single pass, which mirrored `parse_qsl`
   and thus leaked double-encoded keys. Empirically confirmed: `parse_qsl("%2574oken=IDSECRET")` ->
   key `%74oken` (unrecognized), value `IDSECRET` retained and re-encoded unchanged, so the single-pass
   URL path leaked too.
2. **Fail-closed on residual ambiguity.** If the decode loop hits the cap WITHOUT reaching a fixed
   point, the name is treated as a marker and its value redacted (never passed through). A fixed-point
   name still carrying invalid `%zz` / non-UTF8 escapes is NOT ambiguous and, absent a marker, is
   preserved verbatim.
3. **Termination / totality.** Each non-fixed-point pass removes >=1 decodable `%HH` escape, so the
   loop stabilizes within the nested-escape count, hard-bounded by the cap; `errors="replace"` keeps
   it non-throwing. Bounded, total, deterministic.
4. **Same-sink coverage extended.** `sanitize_source_key()` now sanitizes `GitHubRepoSource`
   (repo_url + branch + path_glob) and `ManifestGitSource` (id + url + branch), and marker-gates
   `ManifestLocalSource.id`, reusing the same primitive. Only `local_file:` and the filesystem path
   components of `manifest_local:` remain byte-identical.
5. **Invariants preserved.** `make_job_id` still hashes the raw `build_source_key(config)` (job-id
   determinism unchanged); `_CREDENTIAL_PARAM_PREFIXES` is NOT expanded (`06A59B1D` stays deferred);
   `_sanitize_url` in `staging.py` is NOT modified (059-S blast radius held) -- the multi-layer URL
   guard lives in `source_keys.py`.

### Task restructure (2-hour rule)

The expanded contract grows Unit 1 beyond the 2-hour envelope, so the helper work is split:
- **Unit 1 / `072.001-T`** (Size S, Complexity high): core `sanitize_source_key` + `sanitize_source_id`
  + the R8 `_MAX_CREDENTIAL_DECODE_LAYERS` bounded multi-layer decode primitive + fail-closed url
  wrapper + multi-layer URL guard; crawl coverage (`WebCrawlSource`, `ManifestUrlSource`).
- **Unit 1b / `072.004-T`** (NEW; Size S, Complexity medium): extend `sanitize_source_key` to
  `GitHubRepoSource`, `ManifestGitSource`, and `ManifestLocalSource.id`, reusing the Unit 1 primitive;
  depends on `072.001-T`.
- **Unit 2 / `072.002-T`** now depends on both `072.001-T` and `072.004-T` (integration test covers all
  variants incl. double-encoded and git-variant credentialed urls).
- **Unit 3 / `072.003-T`** unchanged (wiring); depends on `072.002-T`.

### Regressions specified

Unit 1: case (h) double-encoded id now SURGICALLY redacted (`srcA?%2574oken=<redacted>`, `IDSECRET`
absent); (h2) deep-encoded-beyond-cap id value redacted (fail closed); URL-path double-encoded query
key redacted / fail-closed via the multi-layer guard. Unit 1b: `github_repo` / `manifest_git`
credentialed repo_url/url + credentialed `id` redacted, credential-free branch/path preserved verbatim.
Unit 2: double-encoded manifest `id` and a git-variant credentialed url assert the secret absent from
`caplog.text` and `metadata.json`.

### Stash reconciliation

`79BF0AEC` (github_repo token/source-key deferral) is now demonstrably SUBSUMED by the R8 same-sink
contract, so it is reconciled/archived as fixed-planned via `backlogit stash archive 79BF0AEC`
(tombstone in `.backlogit/archive/stash.jsonl`; active stash 28 -> 27). The unrelated pre-existing
timestamp-normalization working-copy diff on `0F1A653C` / `06A59B1D` is preserved byte-for-byte
(verified: only `created_at` differs) and EXCLUDED from the fix commit. `0F1A653C` (string-arg
default-fetch sink) and `06A59B1D` (vocabulary expansion) remain active deferrals -- genuinely
distinct surfaces, not subsumed.

### Artifacts updated

This plan (frontmatter R8, Requirements Trace, Unit 1 detection + pass-through, Unit 1b via
`072.004-T`, Unit 2, Decisions, Risks, this section), the decision doc (Option B R8 refinement,
Chosen Direction, Done Looks Like, P-021 Deferral Watch), feature card 072-F, tasks
072.001-T / 072.002-T / 072.003-T + new 072.004-T, and `.backlogit/archive/stash.jsonl` (`79BF0AEC`
tombstone).

### Independent review

Targeted independent correctness + security review (this diff): the bounded multi-layer decode closes
the double-encoding bypass on id AND url paths; fail-closed cap handles pathological nesting;
termination and totality proven; the same-sink audit confirms git-variant coverage is complete and
`79BF0AEC` is subsumed; determinism (raw-key hashing) and the 059-S / `06A59B1D` boundaries held.
Verdict: PASS.
