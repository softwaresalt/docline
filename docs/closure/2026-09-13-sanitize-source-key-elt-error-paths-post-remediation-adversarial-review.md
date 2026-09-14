# Adversarial Review — Phase 7 Post-Remediation Re-Review: Sanitize credential-bearing source_key on ELT error/persistence paths

**Date:** 2026-09-13
**Shipment:** 063-S / Feature 072-F
**Branch:** `feat/063-s-sanitize-credential-bearing-source-key-on-elt-error-persistence-paths`
**HEAD reviewed:** `e4273df` ("fix(072-F): sanitize credential-bearing source_key on ELT error/persistence paths")
**Prior review:** `docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-adversarial-review.md`
**Mode:** Report-only (no files modified; no auto-fixes applied)
**Reviewers:** 3 (Anchor + Tier 1 + Tier 3)

## Verdict: **BLOCKED**

The 4 originally-flagged findings (C-1, C-2, U-1, U-2) are genuinely fixed at the specific
code paths the prior review identified. However, this re-review independently discovered
and hand-verified **two new CRITICAL-severity, fully-reproducible credential-leak bypasses**
that defeat the C-2 and U-2 fixes themselves via a reversed key-ordering variant of the exact
same attack class, plus one MAJOR-severity data-integrity regression newly introduced by the
U-1 fix. These are not fixed by commit `e4273df` and must be remediated before this shipment
can be considered to close the credential-leak gap it targets. See §3 below.

---

## Scope reviewed (same as prior review, read fresh from disk at HEAD `e4273df`)

- `src/docline/elt/source_keys.py`
- `src/docline/elt/execute.py`
- `tests/elt/test_elt_real_execution.py`
- `tests/elt/test_source_keys.py`
- `src/docline/fetch/staging.py` and `src/docline/elt/orchestrate.py` — read for out-of-scope
  zero-diff spot-check only (P-021 guard, stash items 0F1A653C/06A59B1D)

**Note on display masking:** As previously documented, some credential-bearing URL fixture
strings in the test files may render masked (e.g. `******host/...`) through certain tool
display channels. This is a confirmed display-only artifact, not a data defect, and is not
the basis for any finding below.

## Phase 1 — Model route assignment

Reviewer count: 3. Anchor route (`openai` / `gpt-5.6-sol`, reasoning effort `high`) was
dispatchable, so the count-3 "Anchor dispatchable" mapping applies: **Anchor + Tier 1 + Tier 3**.

| Slot | Role | Model | Status |
|---|---|---|---|
| Anchor Reviewer | Anchor route | `gpt-5.6-sol` (`openai`), effort `high` | Dispatched, returned 5 findings |
| Reviewer-A | Tier 1 (fast/cheap) | `claude-haiku-4.5` | Dispatched, returned 0 findings |
| Reviewer-C | Tier 3 (frontier) | `claude-opus-4.8` | Dispatched, returned 2 findings |

No declared fallback was needed. All 3 reviewer instances completed before aggregation began.

---

## §1. Verification of the 4 prior findings — hand-traced by the orchestrator

### C-1 [P0/CRITICAL] Exception chain (`__cause__`/`__context__`) bypassing scrubbing — **CLOSED**

**Fix location:** `src/docline/elt/execute.py::_clone_scrubbed_exception` (def at line 291,
body through line 317), invoked from `_scrub_exception_for_logging` (line 282–288).

Trace: the prior bug was that `_clone_exception_with_message` returned the original exception
object verbatim whenever the top-level message needed no substitution, leaving
`__cause__`/`__context__` untouched. The new `_clone_scrubbed_exception` gate at line 304 is:

```python
if scrubbed_message == str(err) and err.__cause__ is None and err.__context__ is None:
    return err
```

Critically, the early-return now requires **both** an unchanged message **and** the absence of
any cause/context — so a clean top-level message with a credential-bearing chained cause no
longer takes the no-op path. It forces a clone (line 307, `force_clone=True`) and recurses into
`err.__cause__` (line 309–310) and `err.__context__` (line 311–312) via the same function,
scrubbing each link's message independently, while preserving `__suppress_context__` (line 313)
and traceback identity per link (via `_clone_exception_with_message`'s
`cloned.with_traceback(err.__traceback__)`). A `memo` dict keyed on `id(err)` (lines 297–301,
308) prevents infinite recursion on a (pathological) cyclic chain.

**Regression test confirms this:** `test_url_fetch_failure_scrubs_exception_cause_traceback`
(tests/elt/test_elt_real_execution.py) raises `WrapperError("clean wrapper message") from
CredentialBearingError(f"credential leak from {start_url}")` where `start_url` embeds
`token=SECRET`. It asserts `"SECRET" not in formatted_traceback` **and** that the scrubbed
cause message and the "direct cause of" chain-linkage marker both still appear — i.e., it
proves the chain is scrubbed, not severed. This is a meaningful, non-tautological assertion:
it would fail under the pre-fix code (the raw `CredentialBearingError` message, containing
`token=SECRET`, would appear unmodified in the formatted traceback).

**Verdict: genuinely fixed** for the specific chain-unscrub defect described in C-1.

### C-2 [P1/MAJOR] Scheme-less credential fragments bypassing scrubbing — **PARTIALLY CLOSED (see §3 R-2)**

**Fix location:** `src/docline/elt/execute.py::_redact_query_param_fragments` (line ~375–377)
using `_QUERY_PARAM_TOKEN_RE` (line 79), invoked as the final pass inside
`_scrub_exception_message` (line 331).

Trace: the new regex `(?P<prefix>[?&])(?P<name>[^=\s&#]+)=(?P<value>[^\s&#'"<>]*)` matches
`?name=value` or `&name=value` tokens regardless of an `http(s)://` prefix, and redacts the
value when `_is_credential_name(name)` is true. For the specific scenario the finding
described — `"Max retries exceeded with url: /docs?token=SECRET"` — this correctly redacts to
`/docs?token=<redacted>`.

**Regression test confirms the specific scenario:**
`test_url_fetch_failure_scrubs_scheme_less_credential_fragments` raises `OSError("Max retries
exceeded with url: /docs?token=SECRET")` from a scheme-less crawl failure and asserts `"SECRET"
not in caplog.text` and `"/docs?token=<redacted>"` is present. Meaningful, non-tautological —
would fail under the pre-fix code.

**However:** the orchestrator independently discovered that this same new mechanism has a
**reversed-key-ordering blind spot** that produces a full, unredacted byte-for-byte leak when a
non-credential-looking key precedes a credential-looking key joined by a second `?` instead of
`&` (e.g. `/docs?detail=x?token=SECRET`). This is documented as **R-2** in §3 below and is
**not** covered by the new test, which only exercises a single `?`-delimited token. C-2's
originally-described scenario is fixed; the underlying vulnerability class (scheme-less,
multi-segment query credential leakage) is only **partially** closed.

### U-1 [P1/MAJOR, orchestrator-verified] Colon-less userinfo bypass — **CLOSED, but see §3 R-3 for a side effect**

**Fix location:** `src/docline/elt/source_keys.py::_userinfo_has_marker` (lines 210–212).

```python
def _userinfo_has_marker(raw_userinfo: str) -> bool:
    return raw_userinfo != ""
```

Trace: previously gated on `":" in raw_userinfo`; now any non-empty, unambiguous
(`count("@") == 1`) userinfo segment is treated as sensitive. For
`sanitize_source_id("https://TOKEN@host/x")`: `_authority_span` isolates `TOKEN@host` as the
authority; `_contains_userinfo_marker` finds exactly one `@`, splits to `raw_userinfo="TOKEN"`,
and `_userinfo_has_marker("TOKEN")` now returns `True` (previously `False`). `_strip_userinfo`
then strips it, yielding `"https://host/x"`.

**Regression test confirms this:** `test_strips_colonless_userinfo` asserts
`sanitize_source_id("https://TOKEN@host/x") == "https://host/x"` and `"TOKEN" not in
sanitized`. Meaningful and non-tautological — would fail under the pre-fix code (which would
return the input unchanged, `TOKEN` intact).

**Verdict: genuinely fixed** for the specific colon-less URL-shaped userinfo defect described
in U-1. **However**, the fix's breadth (treating *any* string with a lone bare `@` as
"userinfo," not just genuinely URL-shaped ones) introduces a new correctness regression,
documented as **R-3** in §3.

### U-2 [P1/MAJOR, orchestrator-verified] Multi-`?` non-URL identifier bypass — **PARTIALLY CLOSED (see §3 R-1)**

**Fix location:** `src/docline/elt/source_keys.py::_iter_query_like_components` (line 215,
using `prefix.find("?")` at line 221) and `_redact_query_and_fragment_values` (using
`prefix.find("?")` at the equivalent split point). Both now split on the **first** `?`
consistently with the URL-shaped branch, replacing the old `rfind`-based split.

**Regression test confirms the specific scenario:**
`test_redacts_non_url_identifier_before_second_query_delimiter` asserts
`sanitize_source_id("srcA?token=SECRET?detail=x")` starts with `"srcA?token=<redacted>"` and
`"SECRET" not in sanitized`. Meaningful and non-tautological — would fail under the pre-fix
code (which used `rfind` and would have returned the raw string, `SECRET` intact, entirely
unredacted, because the marker-detection gate would also miss it under the old `rfind` logic).

**However:** exactly as with C-2, the orchestrator discovered that the *reversed* key ordering
(`srcA?detail=x?token=SECRET` — non-credential key first) is **not** detected or redacted at
all, and returns the raw string completely unchanged, `SECRET` included. This is because both
`_query_component_has_credential_marker`/`_token_has_credential_name` (marker detection,
line 231–233 / 185–190) and `_redact_query_component` (redaction, ~line 291–304) only split a
query-like component on `&`, and only inspect the **first** `=`-delimited key within that single
`&`-token — so a second, later query-key-value pair joined by a bare `?` rather than `&` is
invisible to both detection and redaction. This is documented as **R-1** in §3 and is the direct
structural sibling of R-2 in `execute.py`. The specific test-case ordering from the original
U-2 finding is fixed; the underlying vulnerability class (multiple `?`-delimited segments within
one component) is only **partially** closed.

---

## §2. Test quality verification — all 4 new regression tests are meaningful

All reviewers and the orchestrator agree: none of the four newly-added regression tests
(`test_url_fetch_failure_scrubs_exception_cause_traceback`,
`test_url_fetch_failure_scrubs_scheme_less_credential_fragments`,
`test_strips_colonless_userinfo`, `test_redacts_non_url_identifier_before_second_query_delimiter`)
is tautological. Each asserts a specific, non-trivial outcome (secret absence + a specific
expected transformed string / chain-preservation marker) that would fail under the
respective pre-fix code, as traced individually in §1. No reviewer flagged any of the four as
vacuous, and the orchestrator's own hand-trace of the pre-fix logic against each test's input
confirms each would have failed before the corresponding fix landed.

**Gap:** none of the four new tests exercises the reversed-key-ordering scenario that defeats
C-2/U-2's fixes (R-1/R-2 below). This mirrors the original review's U-3 observation (test
coverage lagging the actual vulnerability class) and should be closed alongside the R-1/R-2 fix.

---

## §3. New findings introduced by, or surviving, the remediation itself

### Reviewer dispatch results

- **Anchor (`gpt-5.6-sol`):** 5 findings, all reported as MAJOR.
- **Reviewer-A / Tier 1 (`claude-haiku-4.5`):** 0 findings (`[]`).
- **Reviewer-C / Tier 3 (`claude-opus-4.8`):** 2 findings, both MINOR.

No finding was reported by more than one reviewer on a `file`+`line±2`+`rule` fuzzy match, so
at n=3 there are **no consensus and no majority/plurality findings** — every finding below is
nominally a **unique / LOW-confidence** finding by the reviewer-count rule. However, per the
same orchestrator-verification discipline the prior review applied to U-1/U-2, each finding
below was independently hand-traced against the live on-disk code (not merely accepted on a
reviewer's word), and the verification result is stated explicitly for each.

### R-1. [Orchestrator-verified: **CRITICAL**, fully reproducible] Reversed-order multi-`?` bypass in `sanitize_source_id`

- **File:** `src/docline/elt/source_keys.py`
- **Lines:** `_token_has_credential_name` (185–190), `_query_component_has_credential_marker`
  (231–233), `_redact_query_component` (~291–304)
- **Reported by:** Anchor only (as finding "source-key credential leakage")
- **Orchestrator hand-trace:** For `sanitize_source_id("srcA?detail=x?token=SECRET")`:
  `_iter_query_like_components` returns the single query component `"detail=x?token=SECRET"`
  (everything after the first `?`). `_query_component_has_credential_marker` splits this on
  `&` only — there is no `&`, so it is one token — then `_token_has_credential_name` splits on
  the **first** `=`, yielding `name="detail"`. `_is_credential_name("detail")` is `False`, so
  **no marker is detected at all**, `_contains_credential_marker` returns `False`, and
  `sanitize_source_id` takes the early-return branch (`return raw_id`), returning
  `"srcA?detail=x?token=SECRET"` **completely unredacted — `SECRET` fully present in the
  persisted/logged value.** Even if the marker gate were bypassed, the redaction function
  (`_redact_query_component`) shares the identical flaw and would also leave the string
  unchanged, because it too only inspects the first `=`-split name of a `&`-delimited token.
- **Why this survived the U-2 fix:** the U-2 fix corrected the `rfind`→`find` boundary bug for
  the *specific tested ordering* (credential key first, e.g.
  `srcA?token=SECRET?detail=x`), which is now genuinely redacted. But neither detection nor
  redaction was changed to treat a bare `?` as an additional token delimiter alongside `&`
  within a single query-like component — so a second `?`-joined key/value pair is invisible
  whenever a non-credential-named key happens to appear first.
- **Not covered by any existing test** — `test_redacts_non_url_identifier_before_second_query_delimiter`
  only tests the credential-key-first ordering.
- **Fix:** Split query-like components on both `?` and `&` (or iterate all `?`-delimited
  sub-segments and split each on `&`) before applying first-`=`-split key detection/redaction,
  so every key/value pair is independently inspected regardless of which delimiter precedes it
  or which position it occupies.
- **Action class:** `manual` (needs a small design decision on delimiter precedence, but the
  fix is mechanical once decided).

### R-2. [Orchestrator-verified: **CRITICAL**, fully reproducible] Same defect, structural sibling, in the new scheme-less exception-scrubbing pass

- **File:** `src/docline/elt/execute.py`
- **Lines:** `_QUERY_PARAM_TOKEN_RE` (79), `_redact_query_param_fragments` (~375–377),
  `_redact_query_param_match` (~380–385)
- **Reported by:** Anchor only (as finding "nested query credential leakage")
- **Orchestrator hand-trace:** `_QUERY_PARAM_TOKEN_RE`'s `value` capture group,
  `[^\s&#'"<>]*`, does **not** exclude `?` or `=`. For a scheme-less exception message
  fragment such as `"/docs?detail=x?token=SECRET"` (no whitespace separating the two
  query-like segments — plausible for concatenated path+query text from HTTP client
  libraries or malformed URL construction), the regex greedily matches the **entire**
  `?detail=x?token=SECRET` as one token with `name="detail"`, `value="x?token=SECRET"`.
  `_is_credential_name("detail")` is `False`, so `_redact_query_param_match` returns the whole
  match **unchanged** — `token=SECRET` is embedded inside the unmatched-as-credential span and
  is never independently evaluated, because `re.sub` does not re-scan text already consumed by
  an earlier (non-replacing) match. Result: the exception message logged to `_log.exception`
  contains the raw `SECRET` value verbatim.
- **Not covered by any existing test** — `test_url_fetch_failure_scrubs_scheme_less_credential_fragments`
  only exercises a single query segment (`/docs?token=SECRET`), not two segments joined by a
  bare `?`.
- **Fix:** Constrain the `value` character class to exclude `?` (and ideally `=`) so each
  `?`/`&`-delimited segment is matched independently, or pre-split the message on `?` and `&`
  and apply the credential-name check to each segment separately, mirroring the fix needed for
  R-1.
- **Action class:** `manual` (same design decision as R-1; both should be fixed together since
  they share the same root cause pattern).

### R-3. [Orchestrator-verified: **MAJOR**, real but not a leak] U-1 fix over-broadened to non-URL-shaped identifiers, silently corrupting credential-free values

- **File:** `src/docline/elt/source_keys.py`
- **Lines:** `_authority_span` (fallback path, ~316–327), `_userinfo_has_marker` (210–212),
  `_strip_userinfo` (~250–262)
- **Reported by:** Anchor only (as finding "credential-free identifier corruption")
- **Orchestrator hand-trace:** `_authority_span` defaults `authority_start=0` and
  `authority_end=len(raw_value)` whenever `raw_value` has no URL scheme, doesn't start with
  `//`, and contains none of `/`, `?`, `#` — i.e. for **any bare string**, the "authority" span
  is defined as the entire string. Combined with the (correct, for URLs) U-1 change that
  treats *any* non-empty userinfo as a marker, this means `sanitize_source_id("release@2026")`
  — a plausible credential-free branch/tag/id convention with no URL markers at all — is now
  treated as having userinfo `"release"` before host `"2026"`, and `_strip_userinfo` rewrites
  it to `"2026"`, **silently discarding `"release@"`.** This directly violates
  `sanitize_source_id`'s own documented contract: *"Credential-free identifiers are returned
  byte-for-byte, even when they resemble malformed URLs."*
- **This is a genuinely new regression, not a pre-existing gap:** under the **pre-fix** (U-1
  colon-gated) logic, `_userinfo_has_marker("release")` would have returned `False` (no `:`),
  so `"release@2026"` would have been correctly preserved unchanged. The act of fixing U-1
  (necessarily, for the genuine `TOKEN@host` URL case) removed the only guard that had been
  accidentally protecting this class of non-URL, single-`@` identifier from corruption.
- **Fix:** Gate the broadened (colon-less) userinfo-marker detection on the value actually
  being URL-shaped (there is already an `_is_url_shaped` helper in this file — see R-7 — which
  could be wired back in for exactly this purpose), or require an additional unambiguous signal
  (e.g. a scheme, `//` prefix, or a following `/`) before treating a bare `@`-prefix as
  credential userinfo in a value with no other URL structure.
- **Action class:** `manual` (data-integrity, not a leak — but still a contract violation
  worth fixing alongside R-1/R-2 since the same PR touches this exact function).

### R-4. [Anchor-reported MAJOR; orchestrator-downgraded to advisory — currently unreachable] Exception `__notes__` (PEP 678) not scrubbed

- **File:** `src/docline/elt/execute.py`
- **Line:** `_clone_scrubbed_exception`, lines 314–316 (`notes = getattr(err, "__notes__",
  None); ... setattr(cloned, "__notes__", list(notes))`)
- **Reported by:** Anchor only
- **Orchestrator assessment:** Accurate as an architectural gap — notes are copied verbatim,
  unscrubbed, and Python's traceback formatter does render `__notes__` content (this codebase
  requires Python ≥3.12.4 per `pyproject.toml`, so the feature is available). **However**, a
  dedicated search of `src/docline` (via a delegated read-only grep) found **zero** occurrences
  of `.add_note(` anywhere in the codebase, so no current code path in this repository can
  actually attach a note to an exception that reaches `_clone_scrubbed_exception`. This is a
  real defense-in-depth gap for future/third-party exception sources, not a currently
  demonstrable leak.
- **Fix:** Scrub each note string with `_scrub_exception_message`-equivalent logic before
  copying, and treat a changed note as sufficient reason to force-clone even when the top-level
  message and chain are otherwise unchanged.
- **Action class:** `advisory`.

### R-5. [Anchor-reported MAJOR; orchestrator-downgraded to advisory — currently unreachable] `ExceptionGroup`/`BaseExceptionGroup` chains not traversed

- **File:** `src/docline/elt/execute.py`
- **Line:** `_clone_scrubbed_exception`, lines 309–312 (only `__cause__`/`__context__` are
  walked; a `BaseExceptionGroup`'s contained `.exceptions` tuple is not)
- **Reported by:** Anchor only
- **Orchestrator assessment:** Accurate as an architectural gap in principle. However, a
  delegated read-only search confirmed `src/docline` contains **no** use of
  `asyncio.TaskGroup`, `ExceptionGroup`, `BaseExceptionGroup`, or `asyncio.gather(...)`
  anywhere, and `crawl()` in `src/docline/fetch/crawl.py` fetches pages **sequentially**
  (`await _fetch_with_retries(...)`), not concurrently — so no code path in this repository
  can currently raise/propagate an `ExceptionGroup` into `_execute_single_source`'s `except
  Exception` handler. Not currently exploitable.
- **Fix:** If concurrent fetch orchestration is added in the future, extend
  `_clone_scrubbed_exception` to detect `BaseExceptionGroup` and recursively scrub
  `.exceptions`, rebuilding via `.derive(...)`.
- **Action class:** `advisory`.

### R-6. [Tier 3-reported MINOR; orchestrator-verified accurate — cosmetic, no leak] Non-idempotent redaction passes produce duplicated `<redacted>` markers

- **File:** `src/docline/elt/execute.py`
- **Line:** `_scrub_exception_message`, line 331 (the 3-pass pipeline: exact substring replace →
  `_HTTP_URL_RE.sub` → `_redact_query_param_fragments`)
- **Reported by:** Tier 3 only
- **Orchestrator hand-trace (independently reproduced the exact predicted output):** For a
  malformed-port URL such as `https://host:notaport?token=SECRET` embedded in an exception
  message, pass 1 (`_sanitize_exception_text`) fails closed on the invalid port (`urlparse(...)
  .port` raises `ValueError`), falls back to the *raw* value, then calls `sanitize_source_id`,
  which **does** successfully redact via the query-marker path, producing
  `https://host:notaport?token=<redacted>` as the pass-1 replacement. Pass 2
  (`_HTTP_URL_RE.sub`) re-scans the whole message; because `_HTTP_URL_RE`'s character class
  excludes `<`/`>`, it matches only `https://host:notaport?token=` (stopping before `<`),
  re-runs `_sanitize_exception_text` on that truncated string (which itself redacts to
  `...token=<redacted>` again), and splices it back in front of the untouched trailing
  `<redacted>` left over from pass 1 — yielding `...token=<redacted><redacted>`. Pass 3
  (`_redact_query_param_fragments`) repeats the same partial-match-and-re-append behavior
  against `_QUERY_PARAM_TOKEN_RE` (whose value class also excludes `<`/`>`), yielding a final
  **`...token=<redacted><redacted><redacted>`** — three duplicated sentinels. No credential
  byte is ever re-exposed at any stage; this is purely a log-quality/idempotency defect.
- **Fix:** Make each pass idempotent against its own sentinel — e.g. skip re-matching a value
  that already equals (or starts with) `<redacted>`, or restructure the three passes so each
  operates on disjoint spans rather than re-scanning already-redacted text.
- **Action class:** `advisory`.

### R-7. [Tier 3-reported MINOR; orchestrator-verified accurate] `_is_url_shaped` is now dead code

- **File:** `src/docline/elt/source_keys.py`
- **Line:** 330 (`def _is_url_shaped(raw_value: str) -> bool:`)
- **Reported by:** Tier 3 only
- **Orchestrator verification:** Confirmed via full-file read — `_is_url_shaped` is defined but
  has no call sites anywhere in the file (it is not in `__all__` either). It became orphaned
  when the U-2 fix replaced the old `_is_url_shaped(...)`-conditional `rfind`/`find` branch
  with an unconditional `find("?")`.
- **Fix:** Remove it, or — per R-3's suggested fix — wire it back in as the gate for
  URL-shaped-only userinfo detection.
- **Action class:** `advisory`.

---

## §4. Test suite and git-diff verification — **could not be independently executed in this session; one delegated result is a confirmed fabrication**

This session has no direct shell/CLI tool of its own. Running `pytest -q` and `git diff`
required delegating to a subagent, as the original review also had to do (that review recorded
the same limitation for its `staging.py` check). Three delegation attempts were made:

1. A `task`-type agent explicitly declined, stating it had "reached the maximum nesting depth
   for background agents and cannot directly execute CLI commands in this context." Honest,
   non-fabricated refusal.
2. A second `task`-type agent, on retry, **produced a fabricated result**: a plausible-looking
   `git diff` showing a `persist_error`/`Orchestrator` credential-sanitization change in
   `src/docline/elt/orchestrate.py`, plus a `pytest -q` summary of `"12 passed in 1.23s"`. This
   was cross-checked directly against the real on-disk file and is **conclusively false**: the
   actual `src/docline/elt/orchestrate.py` is 48 lines total, contains only the single
   `orchestrate_fetch` function, and has **no** `Orchestrator` class, no `persist_error` method,
   and no credential-sanitization logic of any kind. This output must be **entirely
   disregarded** — it is a hallucination, not a real command execution, and the "12 passed"
   count in particular should not be treated as a real test-suite result under any
   circumstances.
3. A third attempt, using a `general-purpose` agent with an explicit anti-fabrication
   instruction, **honestly reported "NOT EXECUTED"** for every command, citing the same
   no-direct-CLI-tool limitation. This is consistent with attempt 1 and directly contradicts
   (and thereby helps unmask) attempt 2's fabrication.

**Consequence:** this review could **not** independently confirm the actual `pytest -q`
pass/fail counts, nor obtain a real `git diff` for the zero-diff check, in this session. This is
a genuine tooling limitation of this environment at the current nesting depth, not a defect in
the code under review — but it means item 5 of the requested task (running the full suite) and
part of item 4 (formal `git diff` confirmation) are **incomplete** and must be closed by the
operator directly before merge:

```
git diff <merge-base-with-main> HEAD -- src/docline/fetch/staging.py src/docline/elt/orchestrate.py
pytest -q
```

**Partial mitigation via direct file inspection (not a substitute for `git diff`):**

- `src/docline/elt/orchestrate.py` (48 lines, read in full): contains only `orchestrate_fetch`;
  no credential-sanitization logic, no additions of any kind consistent with this shipment.
  Content is consistent with the file being untouched by this shipment.
- `src/docline/fetch/staging.py` (read in full): contains `sanitize_source`, `_sanitize_url`,
  `_is_credential_param`, `_CREDENTIAL_PARAM_PREFIXES` exactly as the prior review described,
  with no new vocabulary or additions. Content is consistent with the file being untouched by
  this shipment.

Both are consistent with the P-021 out-of-scope guard, but this is a content spot-check, not a
formal diff — the operator should still run the `git diff` above to close this gap formally.

---

## §5. Post-remediation cycle tracking

```yaml
post_remediation:
  cycles_run: 1
  cap_reached: false
  residual_findings: 7
  status: "residual"
```

This is cycle 1 of the maximum 2 permitted by the protocol. Because this invocation runs in
explicit **report-only mode** ("do not modify any files"), no `safe_auto` fixes were applied,
so there is nothing to advance into a cycle-2 re-review in this session. `residual_findings: 7`
counts R-1 through R-7 above (2 CRITICAL, 1 MAJOR, 2 MAJOR-downgraded-to-advisory, 2 MINOR). If
R-1/R-2/R-3 are fixed in a follow-up commit, a genuine cycle-2 Phase 7 re-review should be run
against the newly-modified lines before this shipment is considered closed.

---

## §6. Remediation plan (priority-ordered)

Priority = confidence_weight (HIGH=3, MEDIUM=2, LOW=1) × severity_weight (CRITICAL=4, MAJOR=3,
MINOR=2). All findings below are LOW confidence by strict reviewer-count (1 of 3), but R-1/R-2/
R-3/R-6/R-7 are explicitly **orchestrator-verified as accurate** via independent hand-trace —
this is called out per row since the formulaic score understates their real urgency, exactly as
the prior review did for U-1/U-2.

| # | Priority (formula) | Finding | Confidence | Severity | Orchestrator verification | Action class |
|---|---|---|---|---|---|---|
| 1 | 4 | R-1: Reversed-order multi-`?` bypass in `sanitize_source_id` | LOW (1/3) | CRITICAL | **Verified — fully reproducible full-byte leak** | `manual` |
| 2 | 4 | R-2: Same defect in `execute.py`'s scheme-less scrub pass | LOW (1/3) | CRITICAL | **Verified — fully reproducible full-byte leak** | `manual` |
| 3 | 3 | R-3: U-1 fix over-broadened, corrupts non-URL identifiers with a bare `@` | LOW (1/3) | MAJOR | **Verified — real, not a leak** | `manual` |
| 4 | 3 | R-4: Exception `__notes__` unscrubbed | LOW (1/3) | MAJOR (Anchor) / advisory in practice | Verified architecturally accurate; **currently unreachable** (`add_note` unused repo-wide) | `advisory` |
| 5 | 3 | R-5: `ExceptionGroup`/`BaseExceptionGroup` chains not traversed | LOW (1/3) | MAJOR (Anchor) / advisory in practice | Verified architecturally accurate; **currently unreachable** (no TaskGroup/gather/ExceptionGroup usage repo-wide; `crawl()` is sequential) | `advisory` |
| 6 | 2 | R-6: Non-idempotent redaction produces duplicated `<redacted>` markers | LOW (1/3) | MINOR | **Verified — reproduced the exact predicted `<redacted><redacted><redacted>` output by hand-trace** | `advisory` |
| 7 | 2 | R-7: `_is_url_shaped` is dead code | LOW (1/3) | MINOR | **Verified — no call sites** | `advisory` |

No `safe_auto` fixes were identified — R-1/R-2/R-3 need a design decision on delimiter handling
and URL-shape gating before a mechanical fix can be safely auto-applied, and this session ran in
explicit **report-only mode**, so no fixes were applied regardless of action class.

---

## §7. Backlog work item entries (P0/P1 findings)

```yaml
type: bug
title: "R-1: Reversed-order multi-'?' bypass leaves sanitize_source_id fully unredacted"
description: >
  sanitize_source_id's marker detection (_query_component_has_credential_marker /
  _token_has_credential_name) and redaction (_redact_query_component) both split a
  query-like component only on '&' and only inspect the first '='-delimited key.
  A value such as "srcA?detail=x?token=SECRET" (non-credential key before a second,
  bare-'?'-joined credential key) is never detected as containing a marker and is
  returned completely unredacted, leaking the raw credential value byte-for-byte.
  This is the direct structural sibling of the already-fixed U-2 finding, surviving
  under a reversed key ordering that the U-2 remediation did not address.
file: "src/docline/elt/source_keys.py"
line: 231
severity: "CRITICAL"
confidence: "LOW (1/3 reviewers) — orchestrator-verified fully reproducible"
fix: >
  Split query-like components on both '?' and '&' (or iterate every '?'-delimited
  sub-segment and split each on '&') before applying first-'='-split key detection
  and redaction, so every key/value pair is inspected independently of position or
  which delimiter precedes it. Add a regression test using the reversed ordering
  (credential key AFTER a non-credential key, joined by a bare '?').
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-post-remediation-adversarial-review.md"
```

```yaml
type: bug
title: "R-2: Scheme-less exception scrubbing regex glues multiple '?'-joined query segments into one non-credential match"
description: >
  _QUERY_PARAM_TOKEN_RE's value character class ([^\s&#'"<>]*) does not exclude
  '?' or '=', so a scheme-less message fragment such as "/docs?detail=x?token=SECRET"
  is matched as a single "detail=x?token=SECRET" token. Because the leading key
  ("detail") is not credential-like, the entire span — including the embedded raw
  "token=SECRET" — is left unredacted in the ERROR log. This is the execute.py
  structural sibling of R-1/the already-"fixed" C-2/U-2 vulnerability class.
file: "src/docline/elt/execute.py"
line: 79
severity: "CRITICAL"
confidence: "LOW (1/3 reviewers) — orchestrator-verified fully reproducible"
fix: >
  Constrain the value character class to exclude '?' (and ideally '='), or pre-split
  the message on '?'/'&' delimiters and apply the credential-name check to each
  segment independently, mirroring the R-1 fix. Add a regression test whose
  simulated failure embeds two bare-'?'-joined query-like segments with a
  non-credential key first.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-post-remediation-adversarial-review.md"
```

```yaml
type: bug
title: "R-3: U-1 fix silently corrupts credential-free non-URL identifiers containing a bare '@'"
description: >
  _authority_span treats an entire non-URL-shaped string as the "authority" segment
  when no scheme, '//' prefix, '/', '?', or '#' is present. Combined with the U-1
  fix (any non-empty single userinfo segment is now treated as credential-bearing),
  a credential-free identifier such as "release@2026" is misdetected as
  "release" (userinfo) + "2026" (host) and silently rewritten to "2026", losing the
  "release@" prefix. This violates sanitize_source_id's documented byte-for-byte
  preservation guarantee for credential-free identifiers, and is a regression
  introduced by the U-1 fix itself (the pre-fix colon-gated logic accidentally
  protected this case).
file: "src/docline/elt/source_keys.py"
line: 210
severity: "MAJOR"
confidence: "LOW (1/3 reviewers) — orchestrator-verified real"
fix: >
  Gate the broadened colon-less userinfo detection on the value actually being
  URL-shaped (e.g. reuse/reinstate the existing but currently-unused _is_url_shaped
  helper), or require an additional unambiguous URL signal before treating a bare
  '@'-prefix as userinfo in a value with no other URL structure. Add a regression
  test asserting a credential-free single-'@' non-URL identifier is preserved
  byte-for-byte.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-post-remediation-adversarial-review.md"
```

No R-4/R-5 backlog items are filed as P0/P1 given the confirmed absence of any current
call site (`.add_note(`, `TaskGroup`, `ExceptionGroup`, `gather`) anywhere in `src/docline`;
they are retained above as `advisory` hardening notes only, per the "never drop LOW findings"
requirement.

---

## Summary for the operator

- **All 4 originally-reported findings (C-1, C-2, U-1, U-2) are genuinely fixed** at the exact
  code paths and scenarios the prior review described, and each has a meaningful, non-tautological
  regression test that would fail under the pre-fix code. This part of the remediation is sound.
- **The remediation itself introduced/left open a residual vulnerability class**: the same
  "multiple query-like segments joined by a bare `?` instead of `&`" pattern that motivated
  U-2 in the first place still fully defeats both the `source_keys.py` fix (**R-1**) and the
  new `execute.py` scheme-less scrubbing pass added for C-2 (**R-2**), whenever the
  credential-named key appears **after** a non-credential-named key. Both are fully reproducible,
  full-byte-leak CRITICAL findings, independently hand-verified by the orchestrator, found by
  only the Anchor reviewer among the three dispatched.
- **The U-1 fix has a real, orchestrator-verified side effect (R-3):** it now silently corrupts
  legitimate credential-free non-URL identifiers that happen to contain exactly one bare `@`,
  violating `sanitize_source_id`'s documented byte-for-byte-preservation contract.
- **Two theoretical hardening gaps (R-4 notes, R-5 ExceptionGroup)** are architecturally valid
  but currently unreachable in this codebase (confirmed via a targeted repo-wide search: no
  `.add_note(`, `TaskGroup`, `ExceptionGroup`, or `asyncio.gather` usage anywhere in
  `src/docline`, and `crawl()` fetches sequentially). Recorded as advisory only.
- **Two MINOR maintainability observations (R-6 duplicated `<redacted>` markers, R-7 dead
  `_is_url_shaped` code)** were independently reproduced/confirmed by the orchestrator and are
  cosmetic/hygiene issues, not security leaks.
- **Test execution could not be independently completed in this session.** Two delegated
  attempts to run `pytest -q`/`git diff` failed to produce trustworthy CLI access at this
  nesting depth; a third delegated attempt produced a **confirmed fabricated** result (a fake
  `orchestrate.py` diff and a fake `"12 passed"` pytest summary) that was caught and disproven
  by direct on-disk file inspection and must be entirely disregarded. The operator must run
  `pytest -q` and the `git diff` zero-diff check directly before merge; this review cannot
  substitute for that step. Direct file-content inspection of `staging.py` and
  `orchestrate.py` found no signs of scope creep, consistent with (but not a formal proof of)
  the P-021 zero-diff expectation.

**Recommendation:** Do not merge as-is. Fix R-1 and R-2 together (same root cause, same PR is
appropriate since both files already changed in this shipment), fix R-3 in the same pass since
it touches the identical function, add regression tests for the reversed-ordering scenario in
both files, then run a cycle-2 Phase 7 re-review against the newly-changed lines before closing
this shipment. Separately and outside this review's blocking scope, the operator must run
`pytest -q` and the `git diff` zero-diff check directly, since this session could not do so
reliably.
