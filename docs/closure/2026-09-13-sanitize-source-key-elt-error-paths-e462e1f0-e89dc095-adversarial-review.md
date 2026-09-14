# Adversarial Review — E462E1F0 / E89DC095 Closure Pass

**Shipment:** 063-S / Feature 072-F — "Sanitize credential-bearing source_key on ELT error/persistence paths"
**Branch:** `feat/063-s-sanitize-credential-bearing-source-key-on-elt-error-persistence-paths`
**PR:** #198
**Mode:** report-only (single-extended-cycle, operator-authorized; **no code or test changes were applied by this review**)
**Reviewers:** 3
**Date:** 2026-09-13

**Scope reviewed (this diff only):**
- `src/docline/elt/source_keys.py` — `_URL_SCHEME_RE`, `_is_url_shaped`, new `_has_strict_authority_marker`, new `_userinfo_has_marker`, updated `_contains_userinfo_marker` / `_strip_userinfo`
- `tests/elt/test_source_keys.py` — new classes `TestUrlShapeGateLooseAuthorityUserinfoGuard` (E462E1F0) and `TestUrlShapeGateUnderscoreScheme` (E89DC095)

Explicitly out of scope (already-recorded, deferred stash findings, not re-litigated): `0F1A653C`, `06A59B1D`, `A6D7EEB9`, `96E6C3F2`, `7D7222E3`, `95BD0DC7`, `709BDB53`.

---

## Verdict summary

The diff **does close both target findings** as written and verified below (§1). However, this
review independently identified and hand-verified **one new false-negative regression directly
caused by the E462E1F0 fix's chosen mechanism** (bare/colonless credential tokens in malformed
URLs are no longer stripped — F1 below) and **one latent defense-in-depth gap directly enabled
by the E89DC095 fix's chosen mechanism** (docline's own compound key prefixes, all of which
contain `_`, now parse as URL schemes — F2 below). Neither is a pre-existing/deferred finding;
both are residual side effects of *this* diff's specific implementation choices. Recommend
operator review of F1 in particular before treating this closure as final — see §4 for why its
LOW reviewer-count confidence tag understates its real risk.

---

## Phase 1 — Model route assignment

Reviewer count: 3, anchor route (`openai` / `gpt-5.6-sol`, effort `high`) was dispatchable in
this session, so the count-3 "anchor dispatchable" mapping applied: **Anchor + Tier 1 + Tier 3**.
No `models`/`alt_provider`/`alt_family` overrides were supplied; no Reviewer-B slot exists at this
reviewer count, so the alternate-provider substitution rule does not apply.

| Slot | Route | Model | Reasoning effort | Dispatch status |
|---|---|---|---|---|
| Anchor Reviewer | Anchor review route | `gpt-5.6-sol` (`openai`) | `high` | Dispatched successfully — 1 finding |
| Reviewer-A | Tier 1 (fast/cheap) | `claude-haiku-4.5` | default | Dispatched successfully — 3 findings |
| Reviewer-C | Tier 3 (frontier) | `claude-opus-4.8` | default | Dispatched successfully — 2 findings |

All 3 reviewers received identical file content (full current `source_keys.py`, both new test
classes, and relevant pre-existing non-regression tests inlined directly in-prompt — this
session's shell/git tool surface rejected direct `git diff`/`task`-type shell dispatch with an
"agent nesting/depth" error, consistent with the same limitation logged in the prior
`2026-09-13-sanitize-source-key-elt-error-paths-final-confirmation-review.md` pass; inlining
full file content into each reviewer prompt worked around this without needing shell access) and
identical review-focus instructions. All 3 completed and returned structured JSON only; no
reviewer failures occurred. Consensus minimum (≥2) is satisfied 3/3.

**Ruleset:** No `.github/copilot-review-instructions.md` present; built-in ruleset used,
supplemented with the task-specific focus checklist (correctness of both target fixes, regex
character-class safety, bypass-surface analysis, test-quality assessment) supplied identically
to all three reviewers.

---

## §1. Correctness of the two target fixes (orchestrator-verified by direct trace)

### E462E1F0 — corruption of credential-free colon-prefixed `@`-containing identifiers — **CLOSED for the reported shape**

Traced `sanitize_source_id("release:owner@2026")`: `_URL_SCHEME_RE` matches `"release:"` with
0 captured slashes → `_has_strict_authority_marker` returns `False` (loose) →
`_userinfo_has_marker("owner", strict_authority=False)` → no colon in `"owner"` → `False` → not a
marker → value returned byte-for-byte unchanged. Matches the new test
`test_preserves_zero_slash_scheme_identifier_with_colonless_at_userinfo`. Same trace confirms the
1-slash and 4-slash variants and the `"https:owner:secret@2026"` (colon-containing userinfo,
still correctly stripped to `"https:2026"`) non-regression case. **Confirmed fixed** for exactly
the reported bug shape.

### E89DC095 — underscore-containing schemes bypassing detection — **CLOSED for the reported shape**

Traced `sanitize_source_id("custom_scheme://user:pass@host")`: `_URL_SCHEME_RE` now matches
`"custom_scheme:"` (underscore now in the character class) with 2 captured slashes →
`_has_strict_authority_marker` returns `True` → any non-empty userinfo is a marker → `"user:pass"`
stripped → `"custom_scheme://host"`. Matches
`test_strips_userinfo_from_underscore_scheme_url`. **Confirmed fixed** for exactly the reported
bug shape, and composes correctly with the round-3 zero-slash relaxation
(`test_strips_userinfo_from_zero_slash_underscore_scheme_url`).

### Regex character-class safety — **no defect**

`[A-Za-z0-9+_.-]`: the trailing `-` immediately precedes the closing `]`, which is the standard
safe literal-hyphen position (no accidental range is formed with the preceding `.`). No
unintended ranges anywhere in the class (`A-Z`, `a-z`, `0-9` are the only range operators
present; `+`, `_`, `.` are single literals). All 3 reviewers and the orchestrator independently
confirm this is correctly formed.

---

## §2. Majority findings (confidence: MEDIUM — flagged by 2 of 3 reviewers)

### F2 — MAJOR→CRITICAL (conservative) — Widened scheme character class makes every docline-internal compound key prefix parse as a URL scheme, truncating authority detection before a nested credential authority

**File:** `src/docline/elt/source_keys.py` — `_URL_SCHEME_RE` (line 15), `_authority_span` (line
411), `_has_strict_authority_marker` (line 281), `_contains_userinfo_marker` (line 262)

**Reviewer agreement:** Reviewer-A (CRITICAL) and Reviewer-C (MAJOR). Per Phase 3, conflicting
severities resolve to the more conservative: **CRITICAL**.

**Issue:** Every one of docline's own compound source-key prefixes contains an underscore
(`web_crawl`, `github_repo`, `manifest_local`, `manifest_url`, `manifest_git`, `local_file`).
Before this diff, none of them could match `_URL_SCHEME_RE` (underscore excluded), so
`_is_url_shaped` was unconditionally `False` for any string beginning with one of these prefixes,
and `sanitize_source_id`/`_strip_userinfo` treated such strings as fully opaque. After this diff,
all of them match as a "scheme." For a hypothetical call
`sanitize_source_id("web_crawl:https://user:pass@host/x")`, `_URL_SCHEME_RE` matches
`"web_crawl:"` (0 slashes captured — the char immediately after the colon is `h`, not `/`),
`_authority_span` then scans for the first `/`, `?`, or `#` starting right after that match and
stops at the very first `/` inside the nested `https://`, yielding `raw_authority == "https:"` —
which contains no `@`. The nested `user:pass@host` credential is never inspected and the whole
string is returned unchanged, credentials intact.

**Independent verification (orchestrator):** This exact shape is **not reachable through any
current call site**. Every production caller in `source_keys.py` and `execute.py` sanitizes the
URL/id/branch/path_glob field *individually*, via `_sanitize_url_field`/`sanitize_source_id`,
**before** the prefix is concatenated in `_build_crawl_source_key`/f-string construction — the
already-prefixed compound string is never itself re-fed into `sanitize_source_id`. So this is a
**latent defense-in-depth / API-contract-fragility gap** in the general-purpose helper, not an
active leak in the code paths this shipment touches today.

This is directly corroborated by the stash record itself: `E462E1F0`'s own text states
`manifest_url:name@2026` and `web_crawl:team@proj` were "correctly NOT url-shaped and pass through
unaffected (the two schemes actually used by production source_key construction in this
codebase)" — i.e., the *previous* author explicitly relied on "these prefixes never match as a
scheme" as a safety argument. This diff invalidates that specific safety property. Separately,
`E89DC095`'s own text flags this exact residual uncertainty: "this is not independently verified
against every possible caller/config the same way E462E1F0's blast radius was." **This diff does
not add that verification** — the single new test touching a prefixed compound value
(`test_preserves_existing_production_underscore_scheme_prefix`) only exercises a
**credential-free** compound value (`"web_crawl:https://host/x"`), not a credential-bearing one,
so it does not close the gap its own source finding called out.

**Fix (not applied — report-only mode):** Either (a) constrain `_is_url_shaped`/`_authority_span`
to stop scheme recognition at a nested `://` rather than the first slash, so a compound prefix's
authority scan can "see past" an inner scheme boundary, or (b) add an explicit contract note/
assertion that `sanitize_source_id`/`_strip_userinfo` must only ever be called on a single
unprefixed field value, never an already-composed compound key, plus a regression test
(`sanitize_source_id("web_crawl:https://user:pass@host/x")` should either raise/fail-closed or
strip `pass` — currently it silently preserves it).

**Action class:** `gated_auto` — confirm before applying (no deterministic one-line fix; touches
shared authority-detection logic used by every caller).

**Priority score:** MEDIUM(2) × CRITICAL(4) = **8**

---

### F3 — MINOR→MAJOR (conservative) — No test locks the exact strict/loose slash-count boundary, and no test exercises the actual "should still be stripped" bare-token shape

**File:** `tests/elt/test_source_keys.py` — `TestUrlShapeGateLooseAuthorityUserinfoGuard`

**Reviewer agreement:** Reviewer-A (MAJOR) and Reviewer-C (MINOR). Conservative: **MAJOR**.

**Issue:** The new tests cover 0-, 1-, and 4-slash loose-authority cases for colon-less userinfo
(all correctly asserting *preservation* of credential-free identifiers), plus one 0-slash
colon-containing case (asserting correct *stripping*). No test exists at the exact 2-vs-3-slash
boundary where `_has_strict_authority_marker` flips from strict to loose (e.g.
`"scheme:///owner@2026"`), and — more importantly — no test exercises a colon-less userinfo value
under loose authority where the **expected correct behavior is stripping, not preservation**
(i.e., a bare/single-token credential in a malformed URL). This second gap is the reason the F1
regression below shipped without a failing test: every new loose-authority test in this diff is
deliberately shaped to be a "safe, non-credential identifier," so none of them can distinguish
"correctly preserved" from "incorrectly preserved."

**Fix (not applied — report-only mode):** Add a 3-slash boundary case
(`sanitize_source_id("release:///owner@2026") == "release:///owner@2026"`) and, critically, a
case representing a genuine bare-token credential under loose authority that should be stripped
(see F1's reproduction) to lock in the intended trade-off explicitly rather than leaving it as an
implicit, untested side effect.

**Action class:** `gated_auto` — confirm before applying (test-only addition, low mechanical
risk, but the exact assertions require an explicit human decision on F1's disposition first).

**Priority score:** MEDIUM(2) × MAJOR(3) = **6**

---

## §3. Plurality findings (confidence: MEDIUM — more than one but not a strict majority)

None. With 3 reviewers, any finding shared by 2 is already a strict majority (2 > 3/2); there is
no numeric gap in which a plurality-but-not-majority tier could exist at this reviewer count.

---

## §4. Unique findings (confidence: LOW — flagged by exactly 1 reviewer)

### F1 — MAJOR (Anchor Reviewer; independently re-verified TRUE by the orchestrator) — Bare/colon-less credential tokens in malformed (non-`scheme://`) URLs are no longer stripped

**File:** `src/docline/elt/source_keys.py` — `_userinfo_has_marker` (line 301, decision at line
317), `_has_strict_authority_marker` (line 281)

**Reviewer:** Anchor only. **Do not discount this because of the LOW confidence tag** — it is the
single most actionable finding in this review, and the raw agreement-count tier materially
understates its real risk. See rationale below.

**Issue:** `_userinfo_has_marker` requires an internal colon (`":" in raw_userinfo`) before
treating loose-authority (0/1/3+-slash) userinfo as a credential marker. This closes E462E1F0
correctly, but as an unavoidable side effect of that specific mechanism, it also stops treating a
**bare, single-token, colon-less userinfo** as a credential marker under loose authority — even
when it genuinely is a credential.

**Orchestrator-verified trace:** `sanitize_source_id("https:TOKEN@host")` → `_URL_SCHEME_RE`
matches `"https:"` with 0 captured slashes → loose → `raw_userinfo = "TOKEN"`, no colon →
`_userinfo_has_marker` returns `False` → **`"https:TOKEN@host"` is returned completely
unchanged, `TOKEN` intact.** Before this diff (i.e., under the round-3/4 code state that existed
immediately prior to this fix, where "any non-empty userinfo = marker" applied unconditionally
once a value was recognized as URL-shaped, per `_userinfo_has_marker`'s own docstring — "under
strict_authority=True, any non-empty userinfo is a marker (unchanged prior behavior)" —
confirming the pre-diff rule was unconditional, not slash-count-gated), this exact value **would
have been stripped**. This is a genuine new false negative introduced specifically by this diff's
E462E1F0 remediation strategy, not a pre-existing or already-deferred gap.

**Reachability:** This is directly reachable through the production paths this shipment targets.
Both `_sanitize_url_field` (used for every `WebCrawlSource.url`/`GitHubRepoSource.repo_url`/
`ManifestUrlSource.url`/`ManifestGitSource.url` at persistence time) and `_sanitize_exception_text`
(`src/docline/elt/execute.py`, used for ELT exception-message scrubbing before logging) both end
with an unconditional call to `sanitize_source_id(sanitized)`, so any malformed URL missing one or
more of its slashes (a highly plausible real-world typo — e.g. `https:TOKEN@api.example.com`
instead of `https://TOKEN@api.example.com`) with a bare-token credential as userinfo will now
leak that token verbatim into both `metadata.json`'s `source` field and the ELT error log —
exactly the two sinks this shipment (072-F) exists to close. No Pydantic validator restricts
these fields to well-formed URLs, so a malformed-but-plausible value is not rejected upstream.

**Why this was not caught by the new test suite:** every colon-less-userinfo test case added in
this diff (`TestUrlShapeGateLooseAuthorityUserinfoGuard`) is deliberately a *credential-free
identifier* (`release:owner@2026`, etc.), asserting *preservation*. None of them represent the
*credential-bearing* colon-less shape, so the suite cannot distinguish "correctly preserved
identifier" from "incorrectly preserved credential" — see F3.

**Fix (not applied — report-only mode):** This is a genuine design trade-off between two
competing correctness goals (never corrupt credential-free identifiers vs. never miss a genuine
bare-token credential) and deserves an explicit decision rather than an implicit side effect.
Options include: (a) accept the trade-off explicitly and document it (colon-less userinfo under
loose authority is intentionally out of scope, record a new stash entry), or (b) add a secondary
signal beyond "has a colon" — e.g., only relax to "preserve" when the loose-authority scheme name
itself looks identifier-like (contains no dot, i.e. not a plausible real network scheme) — a more
surgical narrowing than the current "colon present or not" heuristic. Either way, this should not
ship silently as an undocumented, untested behavior change.

**Action class:** `gated_auto` (elevated from the literal LOW-confidence default despite the
protocol's routing table only calling out `LOW confidence + CRITICAL` for this treatment;
independent verification confirms this is a real, currently-reachable credential-exposure
regression in the exact target surface of this shipment, which the orchestrator judges warrants
the same elevated handling regardless of the raw agreement-count tier).

**Priority score (mechanical):** LOW(1) × MAJOR(3) = **3** — note this mechanical score ranks
below F2/F3 in the table below; the orchestrator's risk-adjusted recommendation is to treat F1 as
the **top priority for operator decision**, ahead of its mechanical ranking, because it is the
only one of the three findings independently confirmed to be a live, currently-reachable
credential leak rather than a latent/defense-in-depth gap.

---

### F4 — MINOR (Reviewer-A only) — No inline comment documents the underscore widening's interaction with compound-prefix identifiers

**File:** `src/docline/elt/source_keys.py` — line 15 (`_URL_SCHEME_RE`)

Advisory only; add a short comment near `_URL_SCHEME_RE` cross-referencing F2 so a future reader
understands why docline's own prefixes are now scheme-shaped and what constraint that implies for
future callers of `sanitize_source_id`.

**Action class:** `advisory`.

**Priority score:** LOW(1) × MINOR(2) = **2**

---

## §5. Remediation plan (mechanical priority order)

| # | Finding | Confidence | Severity (conservative) | Score | Action class |
|---|---|---|---|---|---|
| 1 | F2 — compound-prefix authority truncation | MEDIUM (Majority, 2/3) | CRITICAL | 8 | `gated_auto` |
| 2 | F3 — missing strict/loose boundary + bare-token test | MEDIUM (Majority, 2/3) | MAJOR | 6 | `gated_auto` |
| 3 | F1 — colon-less loose-authority userinfo no longer stripped | LOW (Unique, 1/3, orchestrator-verified) | MAJOR (risk-elevated) | 3 | `gated_auto` (elevated) |
| 4 | F4 — missing doc comment | LOW (Unique, 1/3) | MINOR | 2 | `advisory` |

**Operator note:** the mechanical ordering above is required by protocol, but the orchestrator's
substantive risk read is F1 > F2 ≈ F3 > F4 — F1 is the only verified-live credential-exposure
regression among the four; F2/F3 are real but currently latent/test-hygiene gaps with no live
call-site exploitation found in this codebase today.

No fixes were applied. Per the operator's explicit "report-only" / "do not propose or make code
changes" directive for this pass, Phase 6 auto-apply and Phase 7 post-remediation re-review are
both skipped in their entirety.

```yaml
post_remediation:
  cycles_run: 0
  cap_reached: false
  residual_findings: 0
  status: "skipped"
  reason: "operator-directed report-only mode; no safe_auto fixes were applied to re-review"
```

---

## §6. Backlog work-item entries (P0/P1 findings)

```yaml
type: bug
title: "F1: colon-less userinfo under loose-authority malformed URL no longer stripped"
description: >
  _userinfo_has_marker's colon-requirement for loose-authority (non-scheme://) userinfo,
  added to fix stash entry E462E1F0, causes a bare/single-token credential in a malformed
  URL (e.g. "https:TOKEN@host", missing one or more slashes) to no longer be recognized as
  a credential marker and therefore not stripped, where it previously was. Reachable via
  _sanitize_url_field (persisted metadata.source) and _sanitize_exception_text (ELT error
  log) for any WebCrawlSource.url / GitHubRepoSource.repo_url / ManifestUrlSource.url /
  ManifestGitSource.url field shaped this way. No Pydantic validator rejects malformed URLs
  upstream.
file: "src/docline/elt/source_keys.py"
line: 317
severity: "MAJOR"
confidence: "LOW (unique, orchestrator-verified live and reachable)"
fix: >
  Decide and document an explicit trade-off: either accept colon-less loose-authority
  userinfo as out of scope (record as a new deferred stash entry with rationale), or add a
  more surgical secondary signal than "colon present" to distinguish genuine bare-token
  credentials from credential-free colon-prefixed identifiers, and add a regression test for
  both the corrected-strip and corrected-preserve cases.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-e462e1f0-e89dc095-adversarial-review.md"
```

```yaml
type: bug
title: "F2: underscore-widened scheme regex makes docline's own compound key prefixes URL-shaped, truncating nested-authority credential detection"
description: >
  Every docline-internal source-key prefix (web_crawl, github_repo, manifest_local,
  manifest_url, manifest_git, local_file) contains an underscore and now matches
  _URL_SCHEME_RE as a scheme (previously none did). If sanitize_source_id/_strip_userinfo
  were ever called directly on an already-prefixed compound key string containing a nested
  scheme://user:pass@host authority, _authority_span truncates its scan at the first slash
  inside the nested URL and never reaches the embedded userinfo, silently preserving the raw
  credential. Not reachable via any current production call site (verified: every caller
  sanitizes the field individually before prefix concatenation), so this is a latent
  defense-in-depth gap, not a live leak today. Directly invalidates a safety property
  (manifest_url:/web_crawl: are not url-shaped) that stash entry E462E1F0 explicitly relied
  on, and does not close the verification gap E89DC095 itself flagged as open.
file: "src/docline/elt/source_keys.py"
line: 411
severity: "CRITICAL (conservative aggregate; latent/non-live today)"
confidence: "MEDIUM (majority, 2/3 reviewers)"
fix: >
  Either constrain _authority_span/_is_url_shaped to recognize a nested "://" boundary rather
  than stopping at the first slash after any scheme match, or add an explicit contract
  assertion/docstring that these helpers must only be called on a single unprefixed field
  value, plus a regression test for sanitize_source_id() called directly on a
  credential-bearing compound-prefixed string.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-e462e1f0-e89dc095-adversarial-review.md"
```

```yaml
type: task
title: "F3: add strict/loose slash-count boundary and bare-token regression tests to TestUrlShapeGateLooseAuthorityUserinfoGuard"
description: >
  New loose-authority tests for the E462E1F0 fix only cover credential-free identifiers
  (asserting preservation); none cover the exact 2-vs-3-slash strict/loose boundary or a
  colon-less bare-token credential that should be stripped, which is why the F1 regression
  shipped without a failing test.
file: "tests/elt/test_source_keys.py"
severity: "MAJOR"
confidence: "MEDIUM (majority, 2/3 reviewers)"
fix: >
  Add a 3-slash boundary preservation case and a bare-token loose-authority stripping case
  (pending the F1 design decision) to close the coverage gap.
linked_review: "docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-e462e1f0-e89dc095-adversarial-review.md"
```

---

## §7. Raw reviewer output (verbatim JSON)

**Anchor Reviewer (`gpt-5.6-sol`, effort `high`):**
```json
[
  {
    "severity": "MAJOR",
    "rule": "credential-redaction-regression",
    "file": "src/docline/elt/source_keys.py",
    "line": 222,
    "issue": "Loose-authority handling now preserves colonless userinfo in malformed URLs. Values such as `https:TOKEN@host`, `https:/TOKEN@host`, and `https:///TOKEN@host` retain `TOKEN`; the previous implementation stripped them. Percent-encoded `user%3Apass` is similarly missed.",
    "fix": "Preserve credential-free identifiers such as `release:owner@2026`, but continue stripping or fail-closed redacting colonless/encoded userinfo for credential-bearing URL schemes. Add regression tests for zero-, one-, and exactly three-slash malformed URLs."
  }
]
```

**Reviewer-A (`claude-haiku-4.5`, Tier 1):**
```json
[
  {
    "severity": "CRITICAL",
    "rule": "compound-prefix-authority-truncation-bypass",
    "file": "src/docline/elt/source_keys.py",
    "line": 228,
    "issue": "Adding underscore to scheme character class enables compound prefixes (e.g., 'web_crawl:') to match as schemes, truncating authority-span scanning before nested URL authorities are reached. Input 'web_crawl:https://user:pass@host/x' will NOT detect credentials: regex matches 'web_crawl:' with 0 slashes, authority_start jumps to position after colon, authority_end stops at first '/' (in nested 'https://'), resulting in authority='https://' with no '@' found and credentials undetected/unstripped.",
    "fix": "Either: (1) reject compound identifiers in _contains_userinfo_marker by refusing to treat scheme matches with 0 slashes as authority delimiters, OR (2) add regression test for 'web_crawl:https://user:pass@host/x' to catch this bypass, OR (3) document that compound-prefix identifiers are not supported as inputs to sanitize_source_id()."
  },
  {
    "severity": "MAJOR",
    "rule": "missing-test-coverage-strict-boundary",
    "file": "tests/elt/test_source_keys.py",
    "line": 0,
    "issue": "New test classes cover 0, 1, 4+ slash cases for colonless userinfo (E462E1F0) but lack explicit coverage of the strict-authority boundary: exactly 2 slashes with colonless @-userinfo should strip credentials (strict=True), while 3 slashes should NOT (strict=False). No test validates 'scheme://colonless_token@host' vs 'scheme:///colonless_token@host' behavior.",
    "fix": "Add test: assert sanitize_source_id('custom_scheme://token@host') == 'custom_scheme://host' (2 slashes, strict, should strip colonless), and add test: assert sanitize_source_id('custom_scheme:///token@host') == 'custom_scheme:///token@host' (3 slashes, loose, colonless not stripped)."
  },
  {
    "severity": "MINOR",
    "rule": "regex-character-class-documentation",
    "file": "src/docline/elt/source_keys.py",
    "line": 14,
    "issue": "Regex character class [A-Za-z0-9+_.-] is syntactically correct (hyphen at end is literal), but the addition of underscore enables previously-impossible scheme patterns (e.g., 'web_crawl:' from source-key construction tokens) that now match as URL schemes. No inline comment documents this behavioral change or the interaction with compound identifiers.",
    "fix": "Add comment above regex explaining that underscore support (E89DC095 fix) enables compound prefixes to match as schemes, and that callers must not pass compound-prefix identifiers to sanitize_source_id if they contain nested URLs with credentials."
  }
]
```

**Reviewer-C (`claude-opus-4.8`, Tier 3):**
```json
[
  {
    "severity": "MAJOR",
    "rule": "scheme-class-widening-truncates-nested-authority",
    "file": "src/docline/elt/source_keys.py",
    "line": 15,
    "issue": "Adding `_` to `_URL_SCHEME_RE` makes docline's own compound key prefixes (web_crawl:, manifest_url:, manifest_git:, manifest_local:, github_repo:, local_file:) match as URL schemes. For a compound value like `web_crawl:https://user:pass@host/x` passed to the public `sanitize_source_id`, `_authority_span` sets authority_start after the outer `web_crawl:` and stops the scan at the inner `//`, yielding authority `https:` (no `@`). The nested `user:pass@host` credential is missed and the value is returned unmodified. This false-negative is directly created by the scheme-class widening for real production prefixes. It matches the pre-diff leak outcome and is mitigated in the normal sanitize_source_key flow (URLs are sanitized before compound keys are assembled), so it is primarily a defense-in-depth gap on the public entry point — but the diff newly makes every underscore-bearing docline prefix parse as a scheme.",
    "fix": "When the matched scheme is immediately followed by a nested `scheme://` authority (or the computed host segment itself contains `://`), recurse into or reject the nested authority; alternatively constrain scheme recognition so known compound key prefixes are not treated as URL schemes before authority extraction."
  },
  {
    "severity": "MINOR",
    "rule": "missing-strict-loose-boundary-test",
    "file": "tests/elt/test_source_keys.py",
    "line": 1,
    "issue": "New tests cover 0-, 1-, 2- (via pre-existing https://TOKEN@host) and 4-slash colon-less loose userinfo, but not the exact 3-slash case — the precise point where `_has_strict_authority_marker` flips from strict (slashes==2) to loose (slashes>=3). A regression at this boundary (e.g. `release:///owner@2026` incorrectly stripped, or `https:///user@host` mis-handled) would be uncaught.",
    "fix": "Add a regression case at the 3-slash boundary for colon-less userinfo, e.g. assert `sanitize_source_id('release:///owner@2026') == 'release:///owner@2026'`, to lock the strict/loose flip point."
  }
]
```

---

## Quality-criteria checklist

- [x] All 3 reviewer instances completed before aggregation (Phase 3).
- [x] All three confidence tiers represented (Majority: F2, F3; Unique: F1, F4). No Consensus
      (HIGH, 3/3) findings existed this round.
- [x] No P0/P1 finding omitted from the remediation plan (§5) or backlog entries (§6).
- [x] Output file written even though report-only mode applied no fixes.
- [x] ≥2 reviewer instances returned results (3/3).
- [x] Post-remediation re-review correctly skipped (no `safe_auto` fixes were applied, per
      explicit operator report-only directive).
- [x] Recursion cap not applicable (0 cycles run).
