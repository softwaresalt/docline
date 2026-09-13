# Adversarial Review — Final Confirmation Pass

**Shipment:** 063-S / Feature 072-F — "Sanitize credential-bearing source_key on ELT error/persistence paths"
**Reviewed commit:** `ec22a89` (HEAD), branch `feat/063-s-sanitize-credential-bearing-source-key-on-elt-error-persistence-paths`
**Review cycle:** 3rd and final review-fix cycle per Ship circuit breaker ("Review-fix cycles per task: 3")
**Mode:** report-only, read-only. No source or test files were modified by this review.
**Date:** 2026-09-13

---

## 0. Final Verdict

# 🔴 BLOCKED

This shipment **cannot** be marked done in its current state. All three independent
reviewers, working from separate contexts and different model tiers, independently
hand-traced the same live, unredacted credential-leak path (**C-1**) that survives
the R-1/R-2 remediation landed in `ec22a89`. A second, independently-verified full
bypass (**U-1**) was found by one reviewer and confirmed correct by the author of
this report via manual trace. Both are reachable through ordinary, unvalidated
manifest/config input (no upstream Pydantic validation restricts these `str`
fields), and both defeat the exact threat model this feature exists to close
(credential-bearing `source_key` persisted to `metadata.json` and/or logged on ELT
error paths).

The R-1/R-2/R-3 remediation in `ec22a89` is **correct but incomplete**: it fixed the
`?`-as-separator gap in `sanitize_source_id`'s internal splitter
(`source_keys.py`) and in `execute.py`'s `_QUERY_PARAM_TOKEN_RE`, and it correctly
scoped userinfo (`@`) detection to genuine URL structures (R-3, confirmed clean by
all three reviewers). But it did not touch the third code path that shares the same
bypass class: the primary URL-*value*-field sanitizer, `sanitize_source` /
`_sanitize_url` in `src/docline/fetch/staging.py`, which every `WebCrawlSource.url`,
`GitHubRepoSource.repo_url`, `ManifestUrlSource.url`, and `ManifestGitSource.url`
flows through before persistence and before exception-message scrubbing.

Per the explicit instruction for this pass, R-4, R-5, and R-6 are **not**
re-litigated on whether they should be fixed — their prior scope classification
(deferred backlog stash entries 95BD0DC7, 709BDB53, 6076A65E) is confirmed intact
and unaffected by the R-1/R-2/R-3 changes (see §5). This BLOCKED verdict rests
entirely on newly-confirmed findings C-1 and U-1, which are in-scope regressions of
the very vulnerability class (`srcA?detail=x?token=SECRET`-style bypass) this
review pass was chartered to confirm closed.

**Because this is nominally the 3rd/final allowed review-fix cycle**, this
BLOCKED verdict should be escalated per the Ship pipeline's circuit-breaker
exception path (e.g., a follow-up remediation task/shipment scoped specifically to
`staging.py`'s `sanitize_source`/`_sanitize_url` and to the `_contains_userinfo_marker`
ambiguous-authority gate, or explicit human sign-off to ship with these two P0s
documented as known residual risk) rather than being silently marked READY to avoid
exceeding the cycle count. Correctness of a credential-sanitization feature is not
negotiable against a process cap.

---

## 1. Reviewer Roster / Model Route Assignment

Requested: `reviewers: 3`. Per the count-specific mapping for 3 reviewers with a
dispatchable anchor route: **Anchor Reviewer + Reviewer-A (Tier 1) + Reviewer-C
(Tier 3)**. No `models` override was supplied, so the default mapping applied. No
`alt_provider`/`alt_family` override applies at this reviewer count (no Reviewer-B
slot exists in the 3-reviewer anchor-dispatchable mapping).

| Slot | Route | Model | Reasoning effort | Dispatch status |
|---|---|---|---|---|
| Anchor Reviewer | Anchor review route | `gpt-5.6-sol` (`openai`) | `high` | Dispatched successfully — no fallback needed |
| Reviewer-A | Tier 1 (fast/cheap) | `claude-haiku-4.5` | default | Dispatched successfully |
| Reviewer-C | Tier 3 (frontier) | `claude-opus-4.8` | default | Dispatched successfully |

All 3 reviewer instances completed and returned structured JSON findings only, per
protocol. No reviewer failures occurred; the consensus-minimum requirement
(≥ 2 completed reviewers) is satisfied with 3/3.

**Ruleset:** No `.github/copilot-review-instructions.md` was found in this
repository. The built-in harness review ruleset was used, supplemented with the
task-specific verification checklist (R-1/R-2/R-3 correctness, `_is_url_shaped`
regression check, independent edge-case hunting, R-4/R-5/R-6 stability
confirmation) supplied identically to all three reviewers.

**Execution note:** This session's tool surface did not expose shell/Python
execution to either this orchestrator or its dispatched subagents (repeated
attempts to run `git`/`python -c` verification snippets were rejected by the
runtime with "agent nesting/depth" errors). All findings below are therefore based
on **rigorous, independent manual code tracing** by three separately-contexted
reviewers plus the orchestrator, cross-checked against exact line numbers and
stdlib semantics (`urllib.parse.urlparse`/`parse_qsl`/`urlencode`/`quote_plus`),
not live execution. Confidence is HIGH for the consensus finding precisely because
three independent traces (different models, different framing) converged on
character-for-character identical output predictions.

---

## 2. Consensus Findings (confidence: HIGH — flagged by all 3 reviewers)

### C-1 — CRITICAL — Reversed multi-`?` bypass survives in the URL-value-field sanitization pipeline (`staging.py`), leaking credentials into both persisted `source_key` and exception-message scrubbing

**Files:** `src/docline/fetch/staging.py` (`sanitize_source`, `_sanitize_url`, lines ~54–106) · `src/docline/elt/source_keys.py` (`_sanitize_url_field`, lines 159–167; `_remove_credential_query_params`, lines 170–183) · `src/docline/elt/execute.py` (`_sanitize_exception_text`, ~line 359; `_scrub_exception_message`, lines 323–334)

**Rule:** credential-redaction completeness / bypass-of-fixed-vulnerability-class

**Reviewer agreement:** Anchor (CRITICAL, `staging.py:112`), Reviewer-A/Tier 1
(CRITICAL ×2, `source_keys.py:157`/`:266`), Reviewer-C/Tier 3 (CRITICAL ×2,
`source_keys.py:126` and `execute.py:320`). All three independently produced the
same byte-for-byte predicted output.

**Issue:** The R-1/R-2 remediation added `?`-as-separator handling **only** to:
1. `source_keys.py`'s `_QUERY_COMPONENT_SEPARATOR_RE` / `_split_query_component_preserving_separators`, which is exclusively reachable through `sanitize_source_id()` (used for `id`, `branch`, `path_glob` — i.e. non-URL *identifier* fields), and
2. `execute.py`'s `_QUERY_PARAM_TOKEN_RE`, reachable only through `_redact_query_param_fragments()` at the tail of `_scrub_exception_message()`.

Neither fix touched `src/docline/fetch/staging.py`'s `sanitize_source()` /
`_sanitize_url()`, which remains the **first-pass processor for every genuine URL
value field** — `WebCrawlSource.url`, `GitHubRepoSource.repo_url`,
`ManifestUrlSource.url`, `ManifestGitSource.url` — via
`source_keys.py::_sanitize_url_field()`, and is also called directly by
`execute.py::_sanitize_exception_text()` for exception-message scrubbing.
`_sanitize_url()` uses stdlib `urlparse()` + `parse_qsl()`, both of which split the
query **only on `&`** (this is standards-compliant per RFC 3986 — a literal `?`
inside the query component is syntactically valid and is *not* a delimiter — but it
means the credential-redaction logic here has no `?`-aware boundary at all).

**Confirmed exact trace** (verified independently by all three reviewers and by
the orchestrator; all field types are plain `str` with no Pydantic URL validator,
per direct model inspection, so no upstream check rejects this input):

Input: `WebCrawlSource(type="web_crawl", url="https://host/x?detail=x?token=SECRET")`

1. `urlparse("https://host/x?detail=x?token=SECRET")` → `query = "detail=x?token=SECRET"` (only the **first** `?` delimits query-start; everything after is the query string verbatim, including the second literal `?`).
2. `parse_qsl("detail=x?token=SECRET", keep_blank_values=True)` → splits only on `&` (none present) → single pair `("detail", "x?token=SECRET")` (splits on **first** `=` only, so the embedded `?token=SECRET` becomes part of the *value*, not a new key).
3. `_is_credential_param("detail")` → `False` (not a credential-prefix name) → pair is **kept**.
4. `urlencode([("detail", "x?token=SECRET")])` (via `quote_plus`) → `"detail=x%3Ftoken%3DSECRET"` — the literal `?` and `=` are percent-encoded to `%3F`/`%3D`, but the alphanumeric characters `SECRET` are **not** escaped and remain literal.
5. `_sanitize_url()` returns `"https://host/x?detail=x%3Ftoken%3DSECRET"`.
6. Back in `_sanitize_url_field()`, `_remove_credential_query_params()` re-splits this **already-mangled** string on `&` only, finds one token `"detail=x%3Ftoken%3DSECRET"`, name `"detail"` is not credential-like, so it is kept unchanged.
7. **Final `sanitize_source_key(config)` output:**
   `"web_crawl:https://host/x?detail=x%3Ftoken%3DSECRET"` — **the literal string `SECRET` is persisted unredacted** into `job.metadata.source` / `metadata.json`.

The same root cause defeats exception-message scrubbing: `_sanitize_exception_text()` calls `sanitize_source()` first (same percent-encoding step, same leak), then feeds the *already-mangled* string into `sanitize_source_id()` as a second pass. Because the embedded `?` is now the inert text `%3F` (not the character `?`), `_QUERY_COMPONENT_SEPARATOR_RE` (`r"([&?])"`) no longer matches it, so `sanitize_source_id()`'s marker scan sees a single component with name `"detail"` and does **not** re-split to find `token=`. `SECRET` survives verbatim in exception logs (`_log.exception(...)`) for any `WebCrawlSource`, `GitHubRepoSource`, `ManifestUrlSource`, or `ManifestGitSource` whose URL is shaped this way.

**Reachability:** This is not a contrived/malicious-only input. Any manifest
author (or any URL containing a legitimately unencoded `?` deep in a query value —
e.g. copy-pasted from a system that embeds a sub-resource reference without
re-escaping it) can trigger this. All affected fields are plain `str` with zero
Pydantic validation (confirmed directly against `models.py`/`manifest_models.py`).
The existing test suite (`test_source_keys.py`,
`test_url_fetch_failure_scrubs_scheme_less_credential_fragments`) only exercises
the reversed-`?` bypass through the **scheme-less identifier** path
(`sanitize_source_id`) and the **standalone regex** path (`_redact_query_param_fragments` on a fragment that is *not* itself URL-shaped/matched by `_HTTP_URL_RE`), never through a genuine `config.url`/`config.repo_url` field. This gap is therefore completely uncovered by tests.

**Fix (not applied — report-only mode):** Route URL-field sanitization through a
`?`-aware credential scan **before** any percent-encoding/`urlencode` step —
either by applying the same `_split_query_component_preserving_separators` /
`_redact_query_component` logic used by `sanitize_source_id` directly to the raw
query string in `staging.py::_sanitize_url()` (so both callers share one hardened
implementation), or by re-ordering `_sanitize_exception_text`/`_sanitize_url_field`
to redact literal `?`-delimited tokens prior to calling `sanitize_source()`. Add
end-to-end regression tests asserting `"SECRET"` is absent from
`sanitize_source_key()` output and from `caplog.text` for all four URL-bearing
source types with a `?detail=x?token=SECRET`-shaped URL.

**Action class:** `manual` (cross-cutting shared-utility change; not a mechanical
one-line fix; `staging.py::sanitize_source` may have other callers outside the ELT
module that must not regress).

**Priority score:** HIGH(3) × CRITICAL(4) = **12**

---

## 3. Majority Findings (confidence: MEDIUM — flagged by 2 of 3 reviewers)

### M-1 — R-4/R-5 "currently unreachable" characterization holds for first-party code, but the boundary is narrower than the stash language implies

**Files:** `src/docline/elt/execute.py` (`_clone_scrubbed_exception`, lines 294–320)

**Reviewer agreement:** Anchor (rated MAJOR, framed as actively reachable via a
progress-callback boundary calling `err.add_note(...)` or raising an
`ExceptionGroup`) and Reviewer-C/Tier 3 (rated MINOR, framed as a confirmed-clean
re-verification with an explicit latent-risk caveat for third-party/callback code).
Per Phase 3's conflict rule, the more conservative (higher) severity is recorded.
Reviewer-A/Tier 1 did not address this area.

**Issue:** Both reviewers confirm, independently, that **zero** `add_note(`,
`TaskGroup`, `ExceptionGroup`, or `asyncio.gather`/`gather(` call sites exist
anywhere under `src/`, so R-4 and R-5 remain architecturally unreachable **as the
first-party codebase stands today**, and the R-1/R-2/R-3 diff did not touch
`_clone_scrubbed_exception`'s traversal logic at all — no new regression was
introduced. However, `_clone_scrubbed_exception` copies `__notes__` verbatim
(line 317–319, no scrubbing applied) and does not special-case
`BaseExceptionGroup.exceptions`, so if any **external dependency** invoked through
`execute.py` (the crawl runner, `fetch_github_files`, or a caller-supplied
`progress` callback) ever attaches a credential-bearing note via `add_note()`, or
raises/wraps an `ExceptionGroup` with a credential-bearing child, the current
implementation would silently pass it through unredacted. This is a **latent**
gap in a currently-closed door, not a currently-open one.

**Disposition:** Per the explicit task instruction, this is **not** re-litigated
as to whether it should be fixed now. The classification of R-4/R-5 as "currently
architecturally unreachable" is **confirmed accurate for the code as it exists at
`ec22a89`**, and is **not newly exploitable as a side effect of the R-1/R-2/R-3
changes** (both reviewers explicitly checked and found no interaction). This
finding is recorded as a documentation-precision note for stash entries 95BD0DC7 /
709BDB53: the "unreachable" qualifier should be understood as "unreachable given
today's first-party call sites," not "structurally impossible to trigger via any
dependency," so a future dependency-version bump that starts calling `add_note()`
internally would silently reopen this gap without any code change on docline's
side.

**Action class:** `advisory` (no shipment-blocking action; recommend a one-line
clarification to the existing backlog stash entries' acceptance language at a
convenient future touch-point).

**Priority score:** MEDIUM(2) × MAJOR(3) = **6** (informational; not a blocker)

---

## 4. Unique Findings (confidence: LOW — flagged by exactly 1 reviewer)

These are preserved per protocol even though each was found by only one reviewer.
The orchestrator independently re-verified U-1 and U-2 by hand-tracing the exact
code paths cited; both are assessed as genuine, live gaps, not false positives.

### U-1 — CRITICAL (orchestrator-elevated from reviewer's MAJOR rating) — Ambiguous (`@`-count ≠ 1) authority silently bypasses the userinfo fail-closed path, producing a **complete, unredacted** credential leak

**File:** `src/docline/elt/source_keys.py` — `_contains_userinfo_marker` (lines 202–210, gate at line 207) and `_strip_userinfo` (fail-closed `ValueError` at the matching `raw_authority.count("@") != 1` check)

**Reviewer:** Anchor only. Independently re-verified by the orchestrator via full manual trace.

**Issue:** `_contains_userinfo_marker()` requires `raw_authority.count("@") == 1` to
consider the authority "marked" as containing userinfo:

```python
def _contains_userinfo_marker(raw_value: str) -> bool:
    if not _is_url_shaped(raw_value):
        return False
    raw_authority = _authority_segment(raw_value)
    if raw_authority.count("@") != 1:
        return False          # <-- treated as "no credential marker"
    raw_userinfo, _ = raw_authority.split("@", 1)
    return _userinfo_has_marker(raw_userinfo)
```

`_strip_userinfo()` has a *separate* fail-closed `ValueError` for the exact same
ambiguous condition (`count("@") != 1` → raise, caught by `sanitize_source_id`'s
`try`/`except ValueError` to return the `_SOURCE_ID_REDACTED` sentinel) — but that
fail-closed path is **only reachable if `_contains_credential_marker()` first
returns `True`**, and `_contains_userinfo_marker()`'s own gate returns `False` for
exactly the ambiguous (`≠ 1`) case. Net effect: `sanitize_source_id()`'s very first
line, `if not _contains_credential_marker(raw_id): return raw_id`, short-circuits
and returns the **entire identifier byte-for-byte unchanged** whenever the
authority has 0 or 2+ `@` characters and no credential-named query parameter is
present. The fail-closed `ValueError` path in `_strip_userinfo` for the
2+-`@` case is **dead code** — it can never execute, because the marker gate
upstream of it already filters out precisely the condition that would trigger it.

**Concrete trace:** `sanitize_source_id("https://user:pass@evil@host/x")`
(a realistic shape — e.g. an email-address-as-username auth pattern such as
`https://user@company.com:mypassword@host.com/path` naturally produces two `@`
characters in the authority) →
`_authority_segment` = `"user:pass@evil@host"` (2 `@`s) →
`_contains_userinfo_marker` returns `False` (count ≠ 1) →
no credential-named query param either → `_contains_credential_marker` returns
`False` → **`sanitize_source_id` returns the input completely unchanged**:
`"https://user:pass@evil@host/x"` — `user:pass` leaks in full, worse than the
documented fail-closed sentinel behavior, and worse than simply doing nothing
(the docstring promises "a fail-closed sentinel when redaction cannot be
completed safely," but no fail-closed path is ever reached here).

**Reachability:** `sanitize_source_id()` is used for `ManifestUrlSource.id`,
`ManifestGitSource.id`, `ManifestLocalSource.id`, `GitHubRepoSource.branch`,
`GitHubRepoSource.path_glob`, `ManifestGitSource.branch`. The existing test suite
explicitly exercises URL-*shaped* `id` values (e.g.
`"https://host/source?token=IDSECRET"` is a parametrized test case), confirming
this class of input is an intended/supported shape for these fields — not an
out-of-contract edge case. **Not reachable** via the primary `_sanitize_url_field`
path (that path rebuilds `netloc` purely from `urlparse(...).hostname`/`.port`,
unconditionally discarding username/password regardless of `@` count, so
`WebCrawlSource.url`/`GitHubRepoSource.repo_url`/etc. are safe from this specific
variant) — the exposure is specifically through `sanitize_source_id()`'s
identifier fields.

**Fix (not applied):** Change `_contains_userinfo_marker` to treat *any* nonempty
authority containing `@` as a marker (not just count == 1), so the existing
fail-closed `ValueError` path in `_strip_userinfo` is actually reached for
ambiguous authorities, restoring the intended "redact or fail closed to sentinel"
guarantee instead of silently returning the raw identifier.

**Action class:** `gated_auto` — per Phase 5 ("LOW confidence + CRITICAL →
gated_auto, unusual enough to flag despite single source") — confirm before
applying, but treat as P0 given verified full-credential-leak severity.

**Priority score:** LOW(1) × CRITICAL(4) = **4**

---

### U-2 — MAJOR — Quote/angle-bracket-adjacent credential values are not fully redacted by `_QUERY_PARAM_TOKEN_RE` / `_HTTP_URL_RE` boundary matching

**File:** `src/docline/elt/execute.py` — `_QUERY_PARAM_TOKEN_RE` (line 81, value group `[^?\s&#'\"<>]*`) and `_HTTP_URL_RE` (line 78, `[^\s'\"<>]+`)

**Reviewer:** Anchor only.

**Issue:** Both the URL-span regex and the fallback query-token regex exclude
quote and angle-bracket characters from their matched span, on the reasonable
assumption that those characters terminate a URL/token embedded in a larger
message (e.g. `f"failed to fetch <{url}>"`). But because the value group also
permits a **zero-length match** (`*` quantifier), a credential value that is
immediately quote- or bracket-wrapped is matched as an *empty* value, and the
literal credential text immediately following is left completely untouched.

Orchestrator-verified trace: for message text
`'Failed to fetch https://host/x?token="SECRET"'`:
1. `_HTTP_URL_RE` matches only `https://host/x?token=` (stops at the `"`), and
   `_sanitize_exception_text()` sanitizes just that substring — `sanitize_source()`
   sees `query = "token="` (blank value), `_is_credential_param("token")` is
   `True`, so the empty pair is dropped entirely → substituted text becomes
   `"https://host/x"`.
2. The unmatched remainder of the original message, `'"SECRET"'` (quote + literal
   credential + quote), is **not touched** by the substitution at all and is
   concatenated back verbatim.
3. Final message: `'Failed to fetch https://host/x"SECRET"'` — **`SECRET` leaks
   bare, immediately adjacent to the sanitized URL**, with no `token=` prefix
   remaining nearby to catch a reader's eye, and no further regex pass catches it
   because there is no longer a `?`/`&` boundary preceding it.

This is a pre-existing gap in the original C-2 (Round 1) regex design, not a
new regression introduced by the R-1/R-2/`?`-separator change (the quote/bracket
exclusion in the value character class predates this round). It is flagged here
because it is a genuine, currently-live leak path surfaced during this
independent final-pass hunt, and is directly analogous in spirit to the class of
bug this shipment exists to close.

**Fix (not applied):** Do not allow the value group to match a zero-length span
immediately followed by an excluded delimiter (quote/angle-bracket) when the name
is credential-like — either require at least one value character before treating
the match as "fully consumed," or explicitly extend the match to consume a
quoted/bracketed value (`"..."`, `'...'`, `<...>`) as a single unit for redaction
purposes.

**Action class:** `manual` (regex redesign, needs care to avoid over-matching).

**Priority score:** LOW(1) × MAJOR(3) = **3**

---

### U-3 — MINOR — `_is_url_shaped`'s bare `//`-prefix rule still over-triggers userinfo stripping on non-URL identifiers

**File:** `src/docline/elt/source_keys.py` — `_is_url_shaped` (line ~325: `return raw_value.startswith("//") or _URL_SCHEME_RE.match(raw_value) is not None`)

**Reviewer:** Reviewer-C/Tier 3 only.

**Issue:** `_is_url_shaped` treats *any* string starting with `//` as URL-shaped,
regardless of whether a genuine authority/host follows. A non-URL identifier that
merely happens to start with `//` and contains exactly one `@` (e.g.
`"//comment@author"`) is still routed through `_strip_userinfo`, which strips the
`comment` segment, corrupting a credential-free identifier: orchestrator-verified
trace — `sanitize_source_id("//comment@author")` → `_is_url_shaped` → `True` →
authority = `"comment@author"` (count `@` == 1) → `_strip_userinfo` returns
`"//author"`. This is a narrower recurrence of the R-3 problem class
(over-broad `@`-based corruption of non-URL data) that the `_is_url_shaped` gate
did not fully close, though the specific `"release@2026"`-style case explicitly
targeted by R-3 is confirmed fixed (no scheme, doesn't start with `//`).

**Severity note:** This is a **data-corruption** concern (a legitimate,
credential-free identifier gets mangled), not a credential-leak concern — `job_id`
is still derived from the raw, un-mangled `build_source_key()`, so this only
affects the human-readable/persisted sanitized key, not job identity or
determinism.

**Fix (not applied):** Tighten `_is_url_shaped` to require either a real scheme
(`scheme://`) or a `//`-prefixed authority that also resembles a host token (e.g.
contains a `.` or is followed by a port/path boundary) before triggering userinfo
stripping, or restrict the bare-`//` branch to fields that are documented to
accept protocol-relative URLs.

**Action class:** `advisory`.

**Priority score:** LOW(1) × MINOR(2) = **2**

---

## 5. R-4 / R-5 / R-6 Re-Confirmation (explicitly not re-litigated for scope)

| ID | Original characterization | Confirmed status at `ec22a89` | New exploitability from R-1/R-2/R-3 changes? |
|---|---|---|---|
| R-4 | `__notes__`/PEP 678 unscrubbed, currently unreachable (no `add_note(` call sites) | **Confirmed** — zero `add_note(` call sites in `src/` (checked directly; both Anchor and Tier 3 independently re-verified). `_clone_scrubbed_exception` still copies `__notes__` verbatim without scrubbing. | **No.** The R-1/R-2/R-3 diff did not touch `_clone_scrubbed_exception`'s note-handling logic. See M-1 for a documentation-precision nuance (unreachable via first-party code, not structurally impossible via a dependency). |
| R-5 | ExceptionGroup/PEP 654 chains not traversed, currently unreachable (no `TaskGroup`/`ExceptionGroup`/`gather` usage) | **Confirmed** — zero occurrences of `TaskGroup`, `ExceptionGroup`, `asyncio.gather`, or `gather(` anywhere under `src/docline/elt/` (or more broadly under `src/`, per both reviewers' independent checks). | **No.** Same reasoning as R-4; see M-1. |
| R-6 | Non-idempotent redaction can produce duplicated `<redacted><redacted>` markers, cosmetic/no-leak | **Confirmed cosmetic** — Reviewer-C/Tier 3 hand-traced the exact duplication mechanism (`_QUERY_PARAM_TOKEN_RE`'s value class stops at `<`, so re-running the regex over an already-redacted `token=<redacted>` produces `token=<redacted><redacted>` with no additional information disclosed). The `'"<>` exclusion in the value character class predates the R-1/R-2 `?`-separator change and is unaffected by it. | **No** for the duplicated-marker scenario specifically. **Note:** the *same* regex boundary condition that makes R-6 cosmetic is the root cause of the newly-identified U-2 (quote/bracket-adjacent unredacted leak) — R-6 itself (bare marker duplication) remains correctly characterized as leak-free; U-2 is a distinct, adjacent gap in the same regex and is tracked separately above. |

**Conclusion:** R-4, R-5, and R-6 remain correctly characterized as originally
classified. None has become newly live or newly exploitable as a side effect of
the R-1/R-2/R-3 remediation. No action is required against these three items for
this shipment; the existing backlog stash entries (95BD0DC7, 709BDB53, 6076A65E)
stand as-is, with the M-1 documentation-precision note recorded above for future
convenience.

---

## 6. Remediation Plan (ordered by priority = confidence_weight × severity_weight)

| # | Finding | Confidence | Severity | Priority | Action class | File(s) |
|---|---|---|---|---|---|---|
| 1 | C-1 — URL-field multi-`?` bypass (staging.py) | HIGH (3) | CRITICAL (4) | **12** | `manual` | `src/docline/fetch/staging.py`, `src/docline/elt/source_keys.py`, `src/docline/elt/execute.py` |
| 2 | M-1 — R-4/R-5 boundary documentation nuance | MEDIUM (2) | MAJOR (3) | 6 | `advisory` | `src/docline/elt/execute.py` (no code change; stash-entry wording only) |
| 3 | U-1 — Ambiguous-authority (`@`-count ≠ 1) full userinfo bypass | LOW (1) | CRITICAL (4) | 4 | `gated_auto` | `src/docline/elt/source_keys.py` |
| 4 | U-2 — Quote/bracket-adjacent value not redacted | LOW (1) | MAJOR (3) | 3 | `manual` | `src/docline/elt/execute.py` |
| 5 | U-3 — Bare `//`-prefix over-triggers userinfo stripping | LOW (1) | MINOR (2) | 2 | `advisory` | `src/docline/elt/source_keys.py` |

No fixes were applied in this pass (explicit report-only/read-only instruction).
Phase 7 (post-remediation re-review) is **not applicable** this cycle: no
`safe_auto` fixes were made, and the operator explicitly instructed report-only
mode, overriding the skill's default auto-apply-and-re-review behavior.

```yaml
post_remediation:
  cycles_run: 0
  cap_reached: false
  residual_findings: 5
  status: "skipped"
  reason: "Operator instructed report-only/read-only mode; no fixes were applied per explicit task instruction, so no post-remediation re-review was performed."
```

---

## 7. Backlog Work Item Entries (P0/P1 findings)

```yaml
type: bug
title: "credential-redaction-completeness: URL-value-field sanitization (staging.py) does not close the R-1/R-2 multi-`?` bypass"
description: >
  sanitize_source()/_sanitize_url() in src/docline/fetch/staging.py splits query
  strings only on '&' (via urlparse+parse_qsl), so a credential hidden behind an
  earlier non-credential-named query parameter whose value embeds a literal
  second '?' (e.g. https://host/x?detail=x?token=SECRET) survives unredacted into
  both the persisted sanitize_source_key() output (for WebCrawlSource.url,
  GitHubRepoSource.repo_url, ManifestUrlSource.url, ManifestGitSource.url) and
  execute.py's _sanitize_exception_text() exception-message scrubbing path. The
  R-1/R-2 fix landed in ec22a89 only hardened source_keys.py's identifier
  splitter and execute.py's _QUERY_PARAM_TOKEN_RE, not this shared upstream
  function.
file: "src/docline/fetch/staging.py"
line: 89
severity: "CRITICAL"
confidence: "HIGH"
fix: >
  Apply a '?'-and-'&'-aware credential scan/redaction to the raw query string in
  _sanitize_url() before percent-encoding/urlencode, or share the hardened
  splitter from source_keys.py across both callers. Add regression tests for all
  four URL-bearing source types with a reversed-'?' bypass URL.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-final-confirmation-review.md"
```

```yaml
type: bug
title: "credential-redaction-completeness: ambiguous multi-'@' authority bypasses userinfo fail-closed path entirely"
description: >
  _contains_userinfo_marker() in src/docline/elt/source_keys.py returns False
  whenever an authority's '@' count is not exactly 1, which short-circuits
  sanitize_source_id() to return the raw identifier completely unchanged
  (including any embedded userinfo credentials) instead of reaching
  _strip_userinfo()'s intended fail-closed ValueError/sentinel path for
  ambiguous authorities. Realistic trigger: an email-address-as-username auth
  pattern such as https://user@company.com:pass@host/x, which naturally
  produces two '@' characters.
file: "src/docline/elt/source_keys.py"
line: 207
severity: "CRITICAL"
confidence: "LOW"
fix: >
  Treat any nonempty authority containing '@' (not just count == 1) as a
  credential marker in _contains_userinfo_marker, so the existing fail-closed
  ValueError path in _strip_userinfo is actually reached for ambiguous
  authorities.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-final-confirmation-review.md"
```

```yaml
type: bug
title: "credential-redaction-completeness: quote/bracket-adjacent credential values escape _QUERY_PARAM_TOKEN_RE redaction"
description: >
  _QUERY_PARAM_TOKEN_RE's value capture group ([^?\s&#'\"<>]*) permits a
  zero-length match immediately before a quote or angle-bracket character, so a
  credential value wrapped in quotes/brackets (e.g. token="SECRET") is replaced
  with an empty <redacted> marker while the literal credential text immediately
  following remains untouched in the exception message.
file: "src/docline/elt/execute.py"
line: 81
severity: "MAJOR"
confidence: "LOW"
fix: >
  Prevent the value group from matching a zero-length span when immediately
  followed by an excluded delimiter for a credential-like name; extend matching
  to consume quoted/bracketed values as a single redactable unit.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-final-confirmation-review.md"
```

---

## 8. Summary for the Operator

* **3/3 reviewers, independently, hand-traced the identical unredacted-credential
  output** for the same crafted input against the primary URL-field sanitization
  path. This is the highest possible confidence signal this protocol can produce
  and it points at a real, currently-shipped gap.
* The gap exists because the R-1/R-2 remediation was scoped to the two files it
  touched (`source_keys.py`, `execute.py`) without extending the same `?`-aware
  logic to the shared `staging.py::sanitize_source` dependency that both files
  call into for URL-value fields — an easy scope miss to make across two
  remediation cycles focused primarily on the identifier path.
* A second, independently-discovered and orchestrator-verified full-bypass
  (U-1) means the shipment currently has **two** live paths capable of leaking a
  raw credential string verbatim, not one.
* R-3's core fix (the `_is_url_shaped` gating) is confirmed correct and
  non-regressive: `"release@2026"` passes through byte-identical, and
  `https://user:pass@host/path?token=SECRET` remains fully redacted, by all three
  reviewers' independent traces.
* R-4/R-5/R-6 remain correctly characterized as previously classified; no action
  needed against them for this shipment.
* Given the circuit-breaker's 3-cycle cap has now been reached, this finding
  should be routed through the appropriate exception/escalation path rather than
  triggering an unplanned 4th automatic review-fix cycle.
