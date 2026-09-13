---
title: "Source-key credential sanitization on ELT error/persistence paths"
date: 2026-09-12
agent: stage
kind: implementation-plan
source: docs/decisions/2026-09-12-source-key-credential-sanitization.md
stash_id: D6E758F5
covering_release_unit: chore
revision: R7
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
| Percent-encoded credential parameter names recognized (no encoding bypass) | `sanitize_source_id` marker detection classifies parameter names on a single-`unquote` decoded view mirroring `parse_qsl` (utf-8, `errors="replace"`, no `.port`); encoded-key surgical redaction + double-encoded / malformed-percent regressions (Unit 1, Unit 2, R7) |
| Do not change `job_id` determinism | Keep `make_job_id(source_key)` on raw key; sanitize only metadata/log (Unit 3) |
| No credential in `metadata.source` or ERROR log (incl. traceback) | Route both sinks through helper; assert against `caplog.text` (Units 2, 3) |
| Redaction observed before production change | Author failing redaction test first (Unit 2 before Unit 3) |
| Non-crawl keys unchanged (github_repo deferred) | Prefix-restricted pass-through + tests (Unit 1) |

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
       URL sentinel `<source-url-redacted>` instead of propagating. Then **recompose** the key
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
       NOT expand the list; that expansion stays deferred as stash `06A59B1D`). **[R7] Classify
       parameter names on the decoded view, not the raw bytes:** the URL sanitizer this helper must
       stay consistent with classifies names AFTER `parse_qsl` percent-decoding
       (`src/docline/fetch/staging.py:109-115`), so detection percent-decodes each parameter-name
       token with EXACTLY ONE `urllib.parse.unquote` pass mirroring `parse_qsl`'s own semantics
       (`encoding="utf-8"`, `errors="replace"`), so an encoded credential key such as
       `%74oken=IDSECRET` (decodes to `token`) IS recognized. The single decode pass is bounded and
       terminating (NO decode-until-stable loop): a DOUBLE-encoded key (`%2574oken`, which decodes
       once to the literal `%74oken`, not `token`) is NOT a marker -- identical to how the URL
       sanitizer leaves it -- so id and URL handling stay consistent and credential-free ids are not
       over-redacted. `errors="replace"` makes malformed / non-UTF8 percent sequences (`%zz`, a
       truncated `%e0`) total and non-throwing. The decoded view is used for DETECTION ONLY (see (c)
       for redaction over the raw bytes); detection never calls `urllib` `.port`;
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
     - For ALL other config types (`LocalFileSource`, `GitHubRepoSource`, `ManifestLocalSource`,
       `ManifestGitSource`) return `build_source_key(config)` **byte-identical** (github_repo token
       handling is DEFERRED, not implemented here).
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
  fragment retained, malformed port preserved with no port parse). (3) non-crawl configs (`GitHubRepoSource`, `LocalFileSource`) returned byte-identical
  AND an empty-option credentialed `WebCrawlSource` sanitized. **[R7] Encoded-credential-name id scenarios (added):** (g) a percent-encoded credential-name id `srcA?%74oken=IDSECRET` (opaque, no scheme) AND its URL-shaped form `https://host/x?%74oken=IDSECRET` -- each decodes to `token` on the detection view -> SURGICALLY redacted to `srcA?%74oken=<redacted>` / `https://host/x?%74oken=<redacted>` (raw encoded key bytes preserved, only the value redacted over the raw string), `IDSECRET` ABSENT; (h) a DOUBLE-encoded id `srcA?%2574oken=IDSECRET` (decodes ONCE to the literal `%74oken`, not `token`) -> returned VERBATIM byte-for-byte, consistent with the URL sanitizer's own single-pass `parse_qsl` decode (pins the bounded single decode; no decode-until-stable loop); (i) a credential-free id carrying a malformed / non-UTF8 percent sequence (`srcA?note=%zz`, `srcA?b=%e0%80`) -> `unquote(..., errors="replace")` does not raise, no credential name matches, id returned VERBATIM; (j) a percent-encoded userinfo id `https://user%3Apass@host/x` (decodes to `user:pass@`) -> userinfo marker detected on the decoded view and stripped from the raw id, credential ABSENT.
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
  message like `OSError("Network down")`; (c2) add a `ManifestUrlSource` whose `id` is a NON-URL-form credential-bearing string (`srcA?token=IDSECRET`, no scheme) and assert `IDSECRET` is ABSENT from both `caplog.text` and the written `metadata.json` (R5 regression for the non-URL-form-id closure); (c3) [R6] add a MALFORMED credentialed config whose URL would make `_sanitize_url` raise (`https://host:notaport?token=SECRET`) and assert `_execute_single_source` does NOT crash with a sanitizer `ValueError` (it proceeds to the normal fetch-failure path) and `SECRET` is ABSENT from both `caplog.text` and `metadata.json` (R6 totality/fail-closed regression); (c4) [R7] add a percent-encoded credential-name manifest `id` (`srcA?%74oken=IDSECRET`, opaque) and assert `IDSECRET` is ABSENT from both `caplog.text` and `metadata.json` -- proving decoded-name detection closes the encoding bypass (the raw marker scan would miss `%74oken`); (d) assert `job_id == make_job_id(build_source_key(config))`
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
- **Decoded-name marker detection (R7)** -- `sanitize_source_id()` classifies credential parameter
  names on a single-`unquote` decoded view mirroring `parse_qsl` (utf-8, `errors="replace"`, no
  `.port`), so a percent-encoded credential key (`%74oken` -> `token`) is recognized and cannot
  bypass the marker gate, while the decode is DETECTION-ONLY (returned id built from raw bytes) and
  the single pass keeps id/URL handling consistent for double-encoded and malformed sequences without
  over-redaction or non-termination. Reuses the existing vocabulary (no expansion; `06A59B1D` stays
  deferred).
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
- **Caveat:** `github_repo:` tokens are OUT OF SCOPE -> P-021 deferral watch, pass-through only.
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
