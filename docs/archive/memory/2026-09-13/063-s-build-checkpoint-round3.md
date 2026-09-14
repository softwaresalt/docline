# 063-S Build Checkpoint — Copilot Review Round 3 (Final Cycle)

**Date**: 2026-09-13
**Shipment**: 063-S (feature 072-F: Sanitize credential-bearing source_key on ELT error/persistence paths)
**PR**: #198
**Branch**: `feat/063-s-sanitize-credential-bearing-source-key-on-elt-error-persistence-paths`
**Mode**: DARK FACTORY MODE (merge NOT pre-authorized, admin fallback NOT pre-authorized)

## Context

Resumed after compaction. Prior session (rounds 1-2) had already fixed 4 Copilot-review
findings across two remediation cycles. Round 3 (this session) surfaced 4 more findings on
HEAD `8e20a73`, all in the same `source_keys.py`/`execute.py` credential-sanitization surface
this shipment introduces. Per the pr-lifecycle skill's circuit breaker ("Review-fix cycles: 3"),
this was the **final allowed cycle**.

## P-021 classification (all 4 findings)

1. **Unterminated quote/bracket delimiter** (execute.py:87/89) — same-contract-surface,
   mechanical (extend existing alternation with a bounded fallback). **FIXED.**
2. **Malformed scheme, zero slashes** (execute.py:384, `_sanitize_exception_text`) —
   same root cause as #3, same-contract-surface, mechanical (relax `_URL_SCHEME_RE`
   quantifier, a direct continuation of the exact pattern used in cycles 1-2).
   **FIXED.**
3. **Malformed scheme, zero/four+ slashes** (source_keys.py:168, `_sanitize_url_field`) —
   same fix as #2 (shared `_URL_SCHEME_RE`/`_authority_span` helper). **FIXED**, plus a
   necessary companion change: `_sanitize_url_field`'s http(s) branch now also funnels
   through `sanitize_source_id` (previously returned directly from
   `_remove_credential_query_params`), because a malformed 3+-slash scheme still passes the
   naive `startswith("https://")` literal-prefix check even though `urlparse`/
   `staging.sanitize_source` never parse a netloc for it.
4. **Percent-encoded query separators** (source_keys.py:187) — **DEFERRED** (P-021 C2,
   stash entry `A6D7EEB9`). Closing this requires decoding candidate percent-encoded
   separator/assignment sequences within an already-split token's value and re-scanning for
   a nested credential pair, coordinated across two helper functions, without corrupting
   unrelated legitimately-encoded values — a materially different mechanism than a regex
   quantifier/character-class extension, and a genuine design choice (full decode-and-rescan
   vs. `parse_qsl`-based rearchitecture) requiring Stage deliberation.

## Contract change (documented, not a silent regression)

`_is_url_shaped("release:2026")` now returns `True` (previously `False`) since
`_URL_SCHEME_RE` no longer requires at least one slash after the scheme colon. The
BEHAVIORAL guarantee that matters — `sanitize_source_id("release:2026") == "release:2026"`
(no corruption of a credential-free identifier) — is unchanged and explicitly re-verified,
because redaction is gated on an actual `@` being present in the authority segment, not
merely on the `_is_url_shaped` boolean. The affected regression test
(`test_preserves_zero_slash_scheme_value_as_not_url_shaped`) was renamed and its docstring
updated to reflect the corrected contract; no other existing test was touched.

## Verification (independently re-run by Ship, not just trusted from subagent report)

- `python -m py_compile` on both touched source files: clean.
- `ruff check .`: all checks passed.
- `ruff format --check` (scoped to touched files): clean.
- `pyright` (scoped to touched files): 0 errors, 0 warnings.
- `pytest` (full suite): **2314 passed, 17 skipped** (2302 baseline + 12 new tests).
- `python -m build`: succeeded.
- Independent direct-Python reproduction of all 4 findings' exact reported examples,
  before AND after, via boolean substring checks (never trusting masked/redacted display
  output) — all confirmed fixed end-to-end through the real production entry points
  (`_scrub_exception_message`, `_sanitize_url_field`, `_sanitize_exception_text`).
- `git diff --stat -- src/docline/fetch/staging.py src/docline/elt/orchestrate.py`: empty
  (P-021 scope boundary intact, confirmed after every commit this session).

## Incident: subagent stray `git checkout` wiped the P-021 capture entry

During the round-3 delegation, the Python Engineer subagent used an intermediate
`git stash`/`git stash pop` + `git checkout -- .backlogit/stash.jsonl` to compare
before/after state for `.backlogit/`, and the `git checkout` reverted my just-added P-021
deferred-capture entry (originally captured as `20FE675B`) back to the clean HEAD state,
silently discarding it. Caught immediately via `git status --short`/`git diff --stat --
.backlogit/` verification right after the subagent's report (the capture entry was expected
to still be present as an uncommitted addition, and it was not). Recovered by re-running
`backlogit stash add` with the identical text (new entry ID `A6D7EEB9`, since the timestamp
changed) before the code fixes were committed. No data was lost since the entry had never
been committed or referenced externally yet. **Lesson for future cycles**: when delegating
work that might interact with `git stash`, do not assume a subagent's own stash usage is
scoped only to what it explicitly says it will touch — always independently re-verify
`.backlogit/stash.jsonl` state (both the carry-forward diff AND any pending capture
entries) via `git status`/`git diff --stat` immediately after any delegated subagent
returns, before trusting its report.

## Carry-forward diff (0F1A653C / 06A59B1D)

Preserved byte-for-byte throughout this round via the established `git stash push -- .backlogit/stash.jsonl` / (work) / manual timestamp restoration for the 2 affected lines / commit / `git stash pop` procedure. Confirmed intact (exactly 2 insertions / 2 deletions, no other changes) after the round-3 commit (`c0982f5`) and after the push.

## Git state

- Commit `c0982f5` pushed to `origin/feat/063-s-sanitize-credential-bearing-source-key-on-elt-error-persistence-paths`.
- All 4 round-3 Copilot review threads replied-to (citing commit `c0982f5` for the 3 fixed
  findings, stash entry `A6D7EEB9` for the deferred finding) and resolved via GraphQL.
- CI re-triggered on new HEAD; polling in progress.

## Update: Round 4 (circuit breaker exceeded — deferred, not fixed)

After pushing `c0982f5`, the copilot-review gate reported `UNRESOLVED_THREADS` with 2
NEW threads (round 4):

- `PRRT_kwDOSsAX4c6h8Ow0` (execute.py:100/392): fragment-only credential leak
  (`#token=SECRET` bypasses `_HTTP_URL_RE`/`_QUERY_PARAM_TOKEN_RE`, which exclude `#`
  from their delimiter handling).
- `PRRT_kwDOSsAX4c6h8Ow5` (source_keys.py:180/211): nested URL-as-query-value leak
  (`redirect=https://user:pass@evil` bypasses the outer-authority-only scrub in
  `_strip_reversed_query_credentials`).

This is round 4 of Copilot findings, exceeding the review-fix-cycle circuit breaker (3
cycles already consumed: round 1, round 2, round 3). Per P-021 C4, reaching the limit
bars a 4th round of FIXES regardless of whether an individual finding would otherwise
pass the P-021 C1 mechanical-completion test. Per the C4 annotation, remaining findings
at the limit are captured as P-021 deferred entries, not silently expanded into.

**Action taken** (no code changes):
- P-021 discovery lookup (active + archived stash): confirmed no existing entry covers
  either finding.
- Captured 2 new deferred entries via the established carry-forward procedure
  (`git stash push -- .backlogit/stash.jsonl` → `backlogit stash add` ×2 → manual
  timestamp restore on `0F1A653C`/`06A59B1D` → verify clean diff → commit `1ededfc` →
  `git stash pop` → verify carry-forward diff byte-identical):
  - `96E6C3F2` — fragment-only credential leak (execute.py). Noted as plausibly
    mechanical in isolation, but deferred solely due to the circuit breaker (P-021 C4).
  - `7D7222E3` — nested URL-as-query-value leak (source_keys.py). Deferred for both the
    circuit breaker (C4) AND an independent P-021 C1 out-of-scope rationale (recursive
    decode/rescan mechanism, same design-question class as existing entry `A6D7EEB9`).
- Replied to and resolved both threads via GraphQL, citing the deferred entry IDs and
  the circuit-breaker rationale.
- Committed the memory checkpoint update (`9c167f3`).
- Re-polled CI: all green on HEAD `9c167f3`.
- Re-polling the P-018 copilot-review gate for HEAD `9c167f3` (each push re-arms
  Copilot). First poll attempt returned `REVIEW_TIMEOUT` (10 min bound, not a block —
  continuing to poll per §1.2 back-off; this is a docs/backlog-only diff so a 5th round
  of code-level findings is not expected, but the gate must still observe Copilot
  complete a review for this exact HEAD before it is satisfied).

**All 4 round-3 threads and both round-4 threads are now replied-to and resolved on
GitHub.** Deferred entries this shipment now total: `A6D7EEB9` (round 3, percent-encoded
separators), `96E6C3F2` (round 4, fragment leak), `7D7222E3` (round 4, nested URL
value leak) — all citing PR #198 threads, all requiring Stage deliberation, none
implemented.

## Update: Round 5 (genuine regression from round 3's own fix — HIGH-SEVERITY residual risk)

While continuing to poll the copilot-review gate for HEAD `9c167f3` (still the same
code as `c0982f5` — only doc/backlog commits since), Copilot surfaced ONE more thread:

- `PRRT_kwDOSsAX4c6h8W8V` (source_keys.py:15): round 3's `_URL_SCHEME_RE` relaxation
  (`:/{1,2}` → `:/*`) also widened `_is_url_shaped` to match ANY `scheme:value` string
  with zero slashes — including non-URL identifiers that merely contain a scheme-like
  colon prefix. For example `release:owner@2026` (a credential-free identifier) is now
  incorrectly treated as URL-shaped, and userinfo-stripping fires on `owner@`,
  corrupting it to `release:2026` — a genuine violation of the sanitizer's documented
  byte-for-byte-preservation contract for credential-free identifiers.

**Independently verified via direct Python execution** before disposition:
- `release:owner@2026` → `release:2026` (corrupted), `topic:general@v2` → `topic:v2`
  (corrupted), `file:etc@secret` → `file:secret` (corrupted).
- `manifest_url:name@2026` and `web_crawl:team@proj` (the two ACTUAL production
  source_key schemes in this codebase) are correctly NOT url-shaped and pass through
  unaffected — the underscore in each scheme name falls outside
  `_URL_SCHEME_RE`'s `[A-Za-z][A-Za-z0-9+.-]*` character class, so neither is ever
  matched. **No live production source_key scheme is exploitable by this bug today.**
- The existing round-3 regression guards (`release:2026`, `topic:general` — both
  without an `@` sign) did not happen to exercise this combination, which is why
  round-3's own independent verification did not catch it.

**Scope classification — genuinely different from D/E/F**: unlike the prior deferred
findings, this one DOES pass the P-021 C1 same-contract-surface test (it's the exact
`_URL_SCHEME_RE`/`_is_url_shaped` helper round 3 already modified, and the fix is a
further mechanical refinement of the same regex/logic, not a materially different
mechanism). Per C3(i) this would normally be a MANDATORY in-scope fix, not a deferral
candidate. It is deferred SOLELY because the review-fix-cycle circuit breaker (3
cycles) was already fully consumed in round 3, and per C3(ii) a residual-risk record
is required (not merely a routine deferred entry) because deferring a
same-contract-surface completion without one is itself a P-021 violation.

**Action taken** (no code change):
- P-021 discovery lookup (active + archived stash): no existing entry.
- Captured via the established carry-forward procedure (stash push → `backlogit stash
  add` → restore 2 carry-forward timestamps → verify 1-line-only diff → commit
  `6361030` → `git stash pop` → verify carry-forward diff byte-identical) as stash
  entry **`E462E1F0`**, priority **high** (elevated above the other deferred entries
  given it is a verified, reproducible contract violation, even though currently inert
  against real production schemes).
- Replied to and resolved thread `PRRT_kwDOSsAX4c6h8W8V` on GitHub, citing the full
  C1/C3 framing and entry ID `E462E1F0`.

**This finding is flagged PROMINENTLY to the operator** (not just filed as a routine
low-priority follow-up) in the PR readiness presentation, since it is a verified
correctness regression in code introduced during this exact review cycle, and the
operator should have full visibility before deciding whether to approve merge as-is
(accepting documented residual risk, inert against real schemes) or to direct further
action.

Deferred/residual-risk entries from this shipment's PR review now total:
- `A6D7EEB9` (round 3, percent-encoded query separators — genuinely out-of-scope, C1)
- `96E6C3F2` (round 4, fragment-only credential leak — deferred by circuit breaker)
- `7D7222E3` (round 4, nested URL-as-query-value leak — out-of-scope C1 AND circuit breaker)
- `E462E1F0` (round 5, non-URL identifier corruption regression — **in-scope C1/C3(i)
  but deferred by circuit breaker; HIGH priority residual risk; inert against real
  production schemes**)

> **Round-6/round-7 documentation-lag correction (2026-09-13)**: this section was
> written after round 5 and never updated when round 6 surfaced a 5th finding,
> `E89DC095` (underscore-scheme credential leak, same `_URL_SCHEME_RE` character-class
> surface as `E462E1F0`, opposite failure mode). The correct count at round 6/7 is
> **5** deferred/residual-risk entries from this shipment's PR review, not 4; the
> "4 deferred/residual-risk entries" and "its severity classification" references in
> the Next Steps section below predate `E89DC095` and should be read as 5 entries with
> `E462E1F0` **and** `E89DC095` both called out prominently.
>
> **Resolution update (2026-09-13, operator-authorized bounded extension, commit
> `c547f93`)**: `E462E1F0` and `E89DC095` were subsequently both FIXED (not merely
> deferred) via an explicit, tightly-bounded operator authorization for exactly ONE
> additional review-fix cycle after the 3-cycle circuit breaker halted at round 7 — see
> `docs/archive/memory/2026-09-13/063-s-halt-review-loop-report.md`'s Resolution section for the
> full fix disposition. Both stash entries remain in `.backlogit/stash.jsonl` as a
> historical record of the original Copilot findings but no longer describe an open
> residual risk requiring operator merge-time disposition. A separate, distinct P-021
> finding (`BF028CAE`) was captured for a latent, non-live gap (adversarial-review
> finding F2) surfaced by the mandated review of this fix cycle's own diff; it is
> unrelated to this round-6/7 count correction.

## Next steps

1. Continue polling the P-018 `autoharness gate copilot-review` gate for HEAD (next
   push after this checkpoint commit) until it reports `SATISFIED`/`NOT_APPLICABLE`.
   Per the circuit breaker, ANY further NEW finding must also be deferred, not fixed,
   since the 3-cycle fix limit was reached in round 3.
2. Once satisfied: run the P-014 §1.9 readiness gate for the final HEAD (full local
   build evidence already captured via `python -m build`; follow-up handling covers all
   5 deferred/residual-risk entries above (see round-6/7 correction), with `E462E1F0`
   and `E89DC095` called out prominently given their severity classification and
   circuit-breaker-deferred status at the time — both are now fixed per the resolution
   update above).
3. Present PR readiness summary to operator, EXPLICITLY surfacing the `E462E1F0`
   regression as a known, verified, high-severity-class residual risk requiring
   informed operator disposition; wait for explicit merge approval
   (`merge_approval_pre_authorized: false`, `admin_fallback_pre_authorized: false`). Do
   NOT auto-merge or use `--admin`. Do not silently treat operator silence or an
   ambiguous "continue" as authorization for a 4th fix cycle (P-021 C4).
4. Remain on feature branch until merge confirmed.
5. Post-merge: Step 6 closure protocol (post-merge branch, operational-closure,
   shipment-reconcile safe-close, P-020 compact-context, source-artifact cleanup, backlog
   index resync, closure PR + operator approval).
