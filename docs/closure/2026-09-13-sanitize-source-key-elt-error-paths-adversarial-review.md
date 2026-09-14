# Adversarial Review: Sanitize credential-bearing source_key on ELT error/persistence paths

**Date:** 2026-09-13
**Shipment:** 063-S / Feature 072-F
**Branch:** `feat/063-s-sanitize-credential-bearing-source-key-on-elt-error-persistence-paths`
**Mode:** Report-only (no files modified; no auto-fixes applied)
**Reviewers:** 3 (Anchor + Tier 1 + Tier 3)

## Scope reviewed

- `src/docline/elt/source_keys.py` (modified, entire file)
- `src/docline/elt/execute.py` (modified — `_execute_single_source`, `_scrub_exception_for_logging`, `_scrub_exception_message`, `_exception_scrub_replacements`, `_sanitize_exception_text`, `_clone_exception_with_message`, `_fetch_url`, `CrawlStagedNothingError`)
- `tests/elt/test_elt_real_execution.py` — only `test_url_fetch_failure_logs_source_key_and_job_id` + `read_metadata_text`
- `tests/elt/test_source_keys.py` (new file, entire file)
- `src/docline/fetch/staging.py` read for out-of-scope zero-diff verification only

**Note on display masking:** Several credential-bearing URL fixtures in the test files (e.g. `https://user:pass@host/...`) render as `******host/...` through this session's tool display channel. This is a documented display-only artifact, confirmed non-defective by direct on-disk inspection and by the fact that the real pytest suite exercises the literal bytes. No finding below is based on this rendering artifact.

## Phase 1 — Model route assignment

Reviewer count: 3. Anchor route (`openai` / `gpt-5.6-sol`) was dispatchable, so the count-3 "Anchor dispatchable" mapping applies: **Anchor + Tier 1 + Tier 3** (no Tier 2 slot at this count, so the `anthropic` / `claude-opus-4.8` alternate-provider default was not applicable — it only overrides the Tier 2/Reviewer-B slot, which isn't in the 3-reviewer mapping).

| Slot | Role | Model | Reasoning effort | Status |
|---|---|---|---|---|
| Anchor Reviewer | Anchor route | `gpt-5.6-sol` (`openai`) | `high` | Dispatched |
| Reviewer-A | Tier 1 (fast/cheap) | `claude-haiku-4.5` | default | Dispatched |
| Reviewer-C | Tier 3 (frontier) | `claude-opus-4.8` | default | Dispatched |

No declared fallback was needed — all 3 slots dispatched successfully and returned parseable JSON.

## Phase 3 methodology note

Two findings were reported by all three reviewers describing the **same underlying defect** but anchored on line numbers that diverge by more than the nominal ±2 fuzzy-match window (e.g. one reviewer cited the helper's `def` line, another cited the vulnerable `return` statement, another cited the regex's usage site). Both were verified by direct on-disk line inspection to be the same root cause in the same function chain. They are classified as **consensus (3/3)** on semantic-identity grounds rather than strict line-distance grounds; this is disclosed here for auditability. All other findings matched cleanly on `file` + `line ± 2` + `rule`.

---

## 1. Consensus findings (HIGH confidence — flagged by all 3 reviewers)

### C-1. [P0 / CRITICAL] Credential leak via untouched exception chain (`__cause__`/`__context__`) bypasses all scrubbing

- **File:** `src/docline/elt/execute.py`
- **Line:** 341–344 (`_clone_exception_with_message`), specifically the early-return at **line 344** (`return err`)
- **Reviewers:** Anchor (MAJOR), Tier 1 (CRITICAL), Tier 3 (MAJOR) → conservative severity = **CRITICAL**
- **Issue:** `_clone_exception_with_message` only replaces the message when `message != str(err)`. When the top-level `str(err)` does **not** contain a recognized raw credential substring (the common case for wrapped/chained errors, e.g. a generic `ConnectionError`/`CrawlStagedNothingError` wrapping a lower-level client exception), the function returns the **original, unmodified exception object** verbatim. That object's `__cause__`/`__context__` chain — which may hold a nested exception whose own `str()` embeds the raw credentialed URL/query string — is left completely intact. `_log.exception(..., exc_info=(type(logged_error), logged_error, err.__traceback__))` passes this exception straight to Python's logging/traceback formatter, which **recursively walks and prints `__cause__`/`__context__`** ("The above exception was the direct cause of the following exception…"). This bypasses every scrubbing layer in this shipment for any case where the credential lives only in a chained exception rather than the top-level message.
- **Verification:** Confirmed by direct inspection — `type(err)(message)`/`RuntimeError(message)` clones in the "changed" branch also do not explicitly carry forward `__cause__`/`__context__` (they default to `None` on the fresh instance), so the *clone* branch is accidentally safe by omission, while the *no-op* branch (line 344) is the actual leak vector. Neither branch has a deliberate, correct chain-handling policy.
- **Fix:** Never return the original exception object for logging purposes. Always construct a exception for `exc_info` and explicitly sever/scrub the chain — e.g. recursively scrub `__cause__`/`__context__` messages (reusing `_scrub_exception_message` per link) before attaching them to the clone, or explicitly set `__cause__ = None`, `__context__ = None` on whatever exception object is ultimately logged, on **both** branches, not just the "message changed" branch.
- **Action class:** `manual` (security-sensitive; needs a design decision on whether to scrub nested chain messages or sever the chain entirely).

### C-2. [P1 / MAJOR] Scheme-less/reformatted credential fragments bypass both scrubbing layers

- **File:** `src/docline/elt/execute.py`
- **Lines:** 296 (`_HTTP_URL_RE.sub(...)` fallback), 52–55 region (`_HTTP_URL_RE` definition), 288–296 (`_scrub_exception_message`)
- **Reviewers:** Anchor (MAJOR), Tier 1 (MAJOR), Tier 3 (MINOR) → conservative severity = **MAJOR**
- **Issue:** `_scrub_exception_message` has exactly two defenses: (1) exact substring replacement of the raw config field values, and (2) a regex fallback (`_HTTP_URL_RE = re.compile(r"https?://[^\s'\"<>]+")`) that requires a literal `http(s)://` scheme prefix. Many HTTP client libraries (requests/urllib3-style `ConnectionError`/`MaxRetryError` formatting is the canonical example) render connection/timeout failures with only the **path+query** fragment (e.g. `Max retries exceeded with url: /docs?token=SECRET`), with no scheme or host. Such a fragment is not byte-identical to `config.url` (defense 1 fails) and has no `http(s)://` prefix (defense 2 fails), so a credential query parameter can pass through both layers completely unredacted into the ERROR log.
- **Fix:** Add a scheme-independent redaction pass that scans for `[?&]{credential-name}=...` tokens directly in the exception text (reusing `_is_credential_name`/`_redact_query_component`-style logic from `source_keys.py`) rather than relying solely on full-URL substring/regex matching.
- **Action class:** `gated_auto` (mechanical fix using existing helper vocabulary, but should be confirmed against a realistic library-error fixture before merging).

---

## 2. Majority findings (MEDIUM confidence — flagged by >50% of reviewers)

None. No finding was flagged by exactly 2 of 3 reviewers as a strict majority.

## 3. Plurality findings (MEDIUM confidence)

None applicable at 3 reviewers (plurality requires >1 but not a strict majority, which at n=3 collapses to the same threshold as majority). No findings in this bucket.

---

## 4. Unique findings (LOW confidence — flagged by exactly one reviewer)

All four unique findings were independently re-verified by the orchestrator via direct line-by-line inspection of the on-disk files (not merely accepted on the reviewer's word). Two are confirmed real; one is confirmed real but narrower in exploitability than stated; one is assessed as a likely false positive.

### U-1. [P1 / MAJOR — verified accurate] `sanitize_source_id` misses single-token (colon-less) userinfo credentials

- **File:** `src/docline/elt/source_keys.py`
- **Lines:** 201–207 (`_contains_userinfo_marker`), 210–222 (`_userinfo_has_marker`)
- **Reviewer:** Anchor only
- **Issue:** `_userinfo_has_marker` only treats userinfo as credential-bearing when it contains a `:` (at any of up to 5 percent-decode layers). A bare-token userinfo such as `https://TOKEN@host/x` (the common GitHub-PAT-in-URL convention, `https://<PAT>@github.com/...`) never contains `:`, so `_userinfo_has_marker("TOKEN")` returns `False`, `_contains_credential_marker` returns `False`, and `sanitize_source_id` takes the early-return branch (`return raw_id` at line 117) — returning the string **completely unredacted**, token included.
- **Orchestrator verification:** Confirmed by hand-tracing the code. **Scope caveat:** this gap is in `sanitize_source_id`, used for `id`/`branch`/`path_glob` fields and as a secondary defense-in-depth pass inside `_sanitize_exception_text` (applied *after* `sanitize_source()` already unconditionally strips all userinfo via `urlparse().hostname`, colon or not). The primary `config.url`/`config.repo_url` fields are therefore **not** exposed to this specific gap — only a URL-shaped `id`/`branch`/`path_glob` value would be. Realistic manifests rarely put full URLs in those fields, which lowers (but does not eliminate) practical exploitability. It is nonetheless a genuine contract violation: `sanitize_source_id`'s docstring promises general credential-marker detection without this colon caveat, and the test suite (`test_redacts_percent_encoded_userinfo`) only exercises the colon-containing case.
- **Fix:** Treat any single, unambiguous userinfo segment (`raw_authority.count("@") == 1`) as sensitive regardless of whether it contains `:`, and strip/redact it; reserve the fail-closed sentinel for genuinely ambiguous (multi-`@`) authorities.
- **Action class:** `manual`.

### U-2. [P1 / MAJOR — verified accurate] Multiple `?` characters in a non-URL identifier defeat credential-marker detection entirely

- **File:** `src/docline/elt/source_keys.py`
- **Line:** 231 (`query_index = prefix.find("?") if _is_url_shaped(raw_value) else prefix.rfind("?")`), reused identically in `_redact_query_and_fragment_values`
- **Reviewer:** Anchor only
- **Issue:** For values that are not URL-shaped (no scheme, doesn't start with `//`), `_iter_query_like_components` uses `rfind("?")` — it treats only the text **after the last** `?` as the query component. For an identifier such as `srcA?token=SECRET?detail=x`, only `detail=x` is scanned/redacted; `token=SECRET` sits entirely inside the "base" portion (`prefix[:query_index]`) that is never inspected for markers and never redacted by `_redact_query_and_fragment_values` either (same `rfind` split is reused there). Because no marker is found, `_contains_credential_marker` returns `False` and `sanitize_source_id` returns the **entire raw string unchanged**, including `token=SECRET`.
- **Orchestrator verification:** Confirmed by hand-tracing both `_iter_query_like_components` (detection) and `_redact_query_and_fragment_values` (redaction) — both share the same `rfind` boundary bug, so even a value that *is* detected via some other means would still leak the pre-last-`?` segment unredacted.
- **Fix:** Split on the **first** `?` (consistent with URL-shaped handling) or scan every `?`-delimited segment for markers/redaction, not just the final one.
- **Action class:** `manual`.

### U-3. [P2 / MINOR — verified accurate] Integration test never exercises the scheme-less/chained-cause failure modes (corroborates C-1/C-2)

- **File:** `tests/elt/test_elt_real_execution.py`
- **Line:** ~379–384, ~426 (`fake_crawl`/`fake_fetch_github` simulated exceptions, and the final assertion block)
- **Reviewer:** Anchor only (substance also embedded, without a separate JSON entry, in Tier 3's C-2 finding)
- **Issue:** Every simulated failure in `test_url_fetch_failure_logs_source_key_and_job_id` constructs its exception by interpolating the **exact raw** `config.url`/`repo_url` string directly into the message (e.g. `OSError(f"simulated crawl failure for {start_url}")`, `GitHubFetchError(f"Network error fetching {repo_url}: branch={branch}")`). This guarantees the naive substring-replace defense always succeeds, and never exercises: (a) a scheme-less/reformatted credential fragment (the exact scenario in C-2), or (b) a chained `__cause__`/`__context__` exception carrying the raw credential while the top-level message is clean (the exact scenario in C-1). The test therefore provides no regression coverage for either consensus P0/P1 finding.
- **Fix:** Add at least one case where the simulated failure raises via `raise Wrapper(...) from OriginalErrorWithCredentialInMessage(...)` and one where the message contains only a `path?token=SECRET`-shaped fragment, then assert the secret is absent from `caplog.text`.
- **Action class:** `advisory` (test-gap; should be added alongside the C-1/C-2 fixes, not standalone).

### U-4. [DISPUTED — orchestrator assesses as likely FALSE POSITIVE] "Tautological" assertion claim in `test_source_keys.py`

- **File:** `tests/elt/test_source_keys.py`
- **Line:** ~54–65 (`test_manifest_url_source_uses_sanitized_ids`)
- **Reviewer:** Tier 1 only
- **Claim as reported:** "Test constructs the expected redacted value with hardcoded `<redacted>` placeholders... tautologically guarantees the expected value format, making it pass even if `sanitize_source_key` were to return the raw input unchanged."
- **Orchestrator verification — disputed:** This does not hold up. The assertion is `sanitized == f"manifest_url:{expected_id}:https://example.com/docs"`, where `expected_id` is a **specific, hard-coded, credential-free string** (e.g. `"https://host/source?token=<redacted>"`) that is **not equal** to the corresponding raw `id` fixture (e.g. `"******host/source?token=IDSECRET"`). If `sanitize_source_key` returned the raw `id` unchanged, this equality would fail, not pass — the assertion is a strict content check, not a tautology. This appears to be an incorrect claim from the Tier 1 (fast/cheap) reviewer rather than a real defect. Retained here per the "never drop LOW findings" requirement, but flagged as disputed so it is not actioned without independent re-confirmation.
- **Action class:** `advisory` — recommend disregarding pending a second independent confirmation; do not create a backlog fix item for this one without re-verifying against the live test run.

---

## 5. Verified-clean checks (no defect found by any reviewer, orchestrator spot-checked)

- **Determinism (review focus #2):** No reviewer found any accidental sanitization creeping into `build_source_key`/`make_job_id` call sites. `_execute_single_source` computes `source_key = build_source_key(config)` and `job_id = make_job_id(source_key)` from the **raw**, unsanitized key; `sanitized_source_key` is a separate, independently computed value used only for `metadata.source` and the log call. `tests/elt/test_source_keys.py::test_does_not_change_raw_build_source_key` and `::test_preserves_raw_job_id_input_for_new_variants` explicitly assert `raw_before == raw_after` and `make_job_id(raw_before) == make_job_id(raw_after)`. No defect identified.
- **Blast radius (review focus #3):** All three reviewers were instructed to verify `src/docline/fetch/staging.py` shows no diff and to check for other missed call sites of the old `sanitize_source()` at metadata/log sinks; none reported a violation. Orchestrator directly read `staging.py` and confirmed its content matches the pre-existing `sanitize_source`/`_sanitize_url`/`_is_credential_param`/`_CREDENTIAL_PARAM_PREFIXES` implementation with no vocabulary expansion — consistent with the 06A59B1D out-of-scope guard. (Note: an automated `git diff` check could not be executed as part of this session due to a tooling limitation in the delegated shell-check agent; this is a residual verification gap the operator should close with a direct `git diff HEAD -- src/docline/fetch/staging.py` before merge.)
- **Out-of-scope stash 0F1A653C** (default-fetch string-arg leak sink via `orchestrate_fetch`/`create_staging_job`): not touched by any file in scope; no reviewer flagged it as touched.

---

## Remediation plan (priority-ordered)

Priority = confidence_weight (HIGH=3, MEDIUM=2, LOW=1) × severity_weight (CRITICAL=4, MAJOR=3, MINOR=2).

| # | Priority | Finding | Confidence | Severity (P#) | Action class |
|---|---|---|---|---|---|
| 1 | 12 | C-1: Exception chain (`__cause__`/`__context__`) bypasses scrubbing | HIGH | CRITICAL (P0) | `manual` |
| 2 | 9 | C-2: Scheme-less credential fragments bypass both scrub layers | HIGH | MAJOR (P1) | `gated_auto` |
| 3 | 3 | U-1: Colon-less userinfo bypass in `sanitize_source_id` | LOW | MAJOR (P1) | `manual` |
| 4 | 3 | U-2: Multi-`?` non-URL identifier defeats marker detection | LOW | MAJOR (P1) | `manual` |
| 5 | 3 | U-4: Disputed "tautological assertion" claim | LOW | MAJOR (P1, disputed) | `advisory` — verify before acting |
| 6 | 2 | U-3: Test gap for scheme-less/chained-cause coverage | LOW | MINOR (P2) | `advisory` |

Ties at priority 3 ordered by file path (`src/docline/elt/source_keys.py` before `tests/elt/test_source_keys.py`), then by original finding order.

No `safe_auto` fixes were identified — every P0/P1 finding here requires either a design decision (chain-handling policy) or human confirmation before applying, and this session ran in explicit **report-only mode**, so **no fixes were applied** regardless of action class.

---

## Backlog work item entries (P0/P1 findings)

```yaml
type: bug
title: "C-1: Exception chain (__cause__/__context__) bypasses ELT credential scrubbing"
description: >
  _clone_exception_with_message in src/docline/elt/execute.py returns the original
  exception object unmodified (line 344) whenever the top-level exception message
  needs no substitution. That object's __cause__/__context__ chain is left intact
  and unscrubbed. Python's logging/traceback formatter recursively prints chained
  cause/context exceptions, so a credential embedded only in a nested/wrapped
  exception (not the top-level message) leaks into the ERROR log despite this
  shipment's scrubbing.
file: "src/docline/elt/execute.py"
line: 344
severity: "CRITICAL"
confidence: "HIGH"
fix: >
  Never log the original exception object directly. Recursively scrub
  __cause__/__context__ messages before attaching to the object passed as
  exc_info, or explicitly sever the chain (__cause__ = None, __context__ = None,
  __suppress_context__ = True) on every code path, not only the "message changed"
  branch. Add a regression test that raises via `raise X(...) from
  CredentialBearingError(...)` with a clean top-level message.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-adversarial-review.md"
```

```yaml
type: bug
title: "C-2: Scheme-less/reformatted credential fragments bypass ELT exception scrubbing"
description: >
  _scrub_exception_message in src/docline/elt/execute.py only redacts credentials
  via (a) exact substring replacement of raw config field values and (b) a
  _HTTP_URL_RE regex fallback requiring an http(s):// scheme prefix. HTTP client
  libraries commonly format connection/timeout errors with only a path+query
  fragment (e.g. "Max retries exceeded with url: /docs?token=SECRET"), which
  matches neither defense, leaking the credential query parameter unredacted.
file: "src/docline/elt/execute.py"
line: 296
severity: "MAJOR"
confidence: "HIGH"
fix: >
  Add a scheme-independent redaction pass over the full exception text that scans
  for "[?&]{credential-name}=..." tokens using the existing
  _is_credential_name/_redact_query_component vocabulary, independent of whether a
  URL scheme is present. Add a test whose simulated failure embeds the credential
  only as a bare path+query fragment.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-adversarial-review.md"
```

```yaml
type: bug
title: "U-1: sanitize_source_id misses colon-less (single-token) userinfo credentials"
description: >
  _userinfo_has_marker in src/docline/elt/source_keys.py only flags userinfo as
  credential-bearing when it contains ':' (at any decode layer). A bare-token
  userinfo such as "https://TOKEN@host/x" (the common credential-in-URL
  convention) is never detected, so sanitize_source_id returns it byte-for-byte
  unredacted when such a value appears in an id/branch/path_glob field. (Primary
  config.url/repo_url fields are protected via a separate function and are not
  exposed to this specific gap.)
file: "src/docline/elt/source_keys.py"
line: 204
severity: "MAJOR"
confidence: "LOW"
fix: >
  Treat any unambiguous single userinfo segment as sensitive regardless of colon
  presence; strip/redact it rather than gating detection on ':'.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-adversarial-review.md"
```

```yaml
type: bug
title: "U-2: Multiple '?' characters in a non-URL identifier defeat sanitize_source_id marker detection"
description: >
  _iter_query_like_components (and the redaction counterpart
  _redact_query_and_fragment_values) use rfind("?") for non-URL-shaped values,
  scanning only the text after the LAST '?'. A value like
  "srcA?token=SECRET?detail=x" leaves "token=SECRET" entirely inside the
  unscanned/unredacted "base" segment, so sanitize_source_id returns the whole
  string unchanged, including the credential.
file: "src/docline/elt/source_keys.py"
line: 231
severity: "MAJOR"
confidence: "LOW"
fix: >
  Split on the first '?' (consistent with the URL-shaped branch) or scan every
  '?'-delimited segment for markers/redaction rather than only the final one.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-adversarial-review.md"
```

```yaml
type: bug
title: "U-4 (DISPUTED — verify before actioning): possible tautological assertion in test_manifest_url_source_uses_sanitized_ids"
description: >
  Tier 1 reviewer claimed the parametrized assertion in
  test_manifest_url_source_uses_sanitized_ids tautologically passes even if no
  redaction occurred. Orchestrator re-verification finds the assertion compares
  against a specific hard-coded expected string that differs from the raw input
  in every credential-bearing case, so it is NOT tautological as described. This
  entry is included only to satisfy "every P0/P1 finding must appear in the
  remediation plan" — recommend closing as not-a-defect after a second
  independent confirmation, rather than modifying the test.
file: "tests/elt/test_source_keys.py"
line: 60
severity: "MAJOR (disputed)"
confidence: "LOW"
fix: "Re-verify independently; likely no action needed."
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-adversarial-review.md"
```

---

## Phase 7 — Post-remediation re-review

```yaml
post_remediation:
  cycles_run: 0
  cap_reached: false
  residual_findings: 0
  status: "skipped"
```

This invocation ran in explicit **report-only mode** ("do not modify any files"), which overrides the protocol default of auto-applying `safe_auto` fixes. No fixes were applied in Phase 6, so there is nothing to re-review in Phase 7; the phase is recorded as `skipped` rather than `clean` to distinguish "no fixes were attempted" from "fixes were applied and verified clean."

---

## Summary for the operator

- **2 consensus (HIGH-confidence) findings**, both real, both requiring code changes before this shipment can be considered to fully close the credential-leak gap it targets: (1) the exception-chain bypass (P0/CRITICAL) is the more severe of the two, because it defeats the *entire* scrubbing mechanism whenever the credential lives in a wrapped/chained exception rather than the top-level message; (2) the scheme-less-fragment bypass (P1/MAJOR) is a narrower but still realistic gap given common HTTP client error formatting.
- **2 unique findings, orchestrator-verified as real** (colon-less userinfo bypass, multi-`?` identifier bypass) — both in `sanitize_source_id`, both lower practical exploitability than the consensus findings because the primary URL fields are protected by the separate `sanitize_source()`/`_sanitize_url_field` path, but both are genuine contract violations of `sanitize_source_id`'s stated guarantee.
- **1 unique test-gap finding** corroborating the consensus findings (no regression coverage for either).
- **1 unique finding is disputed** and assessed as very likely incorrect on direct re-verification — flagged rather than silently dropped, per protocol.
- Determinism (`build_source_key`/`make_job_id` untouched) and blast-radius (`staging.py` zero-diff, no missed call sites) checks passed with no defects identified by any reviewer, though the `staging.py` diff was not independently confirmed via `git diff` in this session due to a tooling limitation — operator should confirm directly before merge.
