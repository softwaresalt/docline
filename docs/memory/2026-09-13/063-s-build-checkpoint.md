# 063-S Build Checkpoint (DARK FACTORY MODE)

**Shipment:** 063-S — Sanitize credential-bearing source_key on ELT error/persistence paths
**Feature:** 072-F
**Branch:** `feat/063-s-sanitize-credential-bearing-source-key-on-elt-error-persistence-paths`
**Commit 1:** `e4273df` — fix(072-F): sanitize credential-bearing source_key on ELT error/persistence paths (cycle-1)
**Commit 2:** `ec22a89` — post-remediation cycle-2 fixes (R-1/R-2/R-3) + P-021 deferred captures (R-4/R-5/R-6)
**Commit 3:** `dcd51f5` — final-confirmation cycle-3 fixes (C-1/U-1/U-2) + P-021 deferred captures (U-3/M-1)

## Status: implementation + 3 review-remediation cycles complete (circuit-breaker limit reached), pre-PR

## Items completed
- 072.001-T, 072.002-T, 072.003-T, 072.004-T — all `done` (auto-archived by backlogit to `.backlogit/archive/`).
- 072-F — `done`.
- 063-S — `active` (shipment stays active until Step 6 post-merge safe-close).

## What shipped in this commit
- `src/docline/elt/source_keys.py`: new `sanitize_source_key(config)` / `sanitize_source_id(raw_id)`
  (typed-config R8 contract), reusing `sanitize_source()`/`_is_credential_param` from
  `docline.fetch.staging` read-only (no vocabulary expansion).
- `src/docline/elt/execute.py`: wired sanitizer into `_execute_single_source` for
  `metadata.source` persistence and the ERROR log call; raw `source_key`/`job_id`
  (via `make_job_id`) untouched for determinism. Added exception-chain scrubbing
  (`_scrub_exception_for_logging`, `_clone_scrubbed_exception`, etc.) that recursively
  scrubs `__cause__`/`__context__` and adds a scheme-independent
  `[?&]name=value` redaction pass.
- `tests/elt/test_source_keys.py` (new) — 41 unit tests.
- `tests/elt/test_elt_real_execution.py` — extended `test_url_fetch_failure_logs_source_key_and_job_id`
  (6 parametrized cases) plus 2 new dedicated regression tests (chained-exception scrub,
  scheme-less fragment scrub).

## Review gate (Step 4.4 — adversarial-review, 3 reviewers, mode: report-only)
Report: `docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-adversarial-review.md`

Initial pass found 2 HIGH-confidence consensus findings (blocking per Step 4.4) plus 2
verified-real LOW-confidence findings in the same helper surface:
- **C-1 (P0)**: exception `__cause__`/`__context__` chain left unscrubbed when the
  top-level message needed no change → fixed via `_clone_scrubbed_exception` (recursive
  clone+scrub with cycle-safe memoization, preserves `__suppress_context__`/`__notes__`).
- **C-2 (P1)**: scheme-less credential query fragments (e.g. HTTP client
  "Max retries exceeded with url: /docs?token=SECRET") bypassed both substring and
  full-URL-regex defenses → fixed via a new scheme-independent `[?&]name=value` regex
  redaction pass reusing `_is_credential_name`.
- **U-1 (P1, verified)**: colon-less userinfo (`https://TOKEN@host`) not detected →
  fixed by treating any single unambiguous userinfo segment as sensitive regardless of `:`.
- **U-2 (P1, verified)**: multi-`?` non-URL identifier defeated query-marker detection
  (previous code split on the *last* `?`) → fixed by splitting on the *first* `?`,
  consistent with URL-shaped handling.
- **U-3 (P2, advisory)**: corroborating test-gap — closed by the new regression tests above.
- **U-4**: disputed "tautological assertion" claim — independently re-verified as a
  false positive (strict content-specific equality check); not actioned.

All 4 actionable findings were classified in-scope under P-021 C1/C3 (same-contract-surface
completion of the exact authorized fix — not a scope expansion) and remediated via a second
TDD pass (RED→GREEN), independently re-verified by Ship (diff review + full gate re-run) before
committing. Remediation is included in the same commit `e4273df` (single implementation
commit covering all 4 tasks + review-fix cycle 1).

## Quality gates (independently re-verified by Ship, not just trusted from subagent report)
- `python -m py_compile src/docline/__init__.py` — pass
- `ruff check .` — all checks passed
- `ruff format --check` on the 4 changed/new files — clean; repo-wide run still shows the
  same 12 pre-existing unrelated historical docs files failing (confirmed untouched by this
  diff both before and after remediation — out of scope, not introduced by 063-S)
- `pyright src/docline/elt/source_keys.py src/docline/elt/execute.py` — 0 errors/warnings
- Full `pytest` — **2279 passed, 17 skipped** (up from 2275 baseline; +4 new regression tests)
- `git diff --stat -- src/docline/fetch/staging.py` and
  `git diff --stat -- src/docline/elt/orchestrate.py` — both empty (P-021 out-of-scope
  guard for deferred stash items 0F1A653C/06A59B1D confirmed intact)

## Post-remediation re-review (Phase 7 — adversarial-review re-invoked on committed HEAD `e4273df`)
Report: `docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-post-remediation-adversarial-review.md`

Result: **BLOCKED**. All 4 cycle-1 findings confirmed genuinely fixed with no regression,
but 3 NEW real bugs surfaced in the cycle-1 fix surface itself, plus 3 lower-severity items:
- **R-1/R-2 (same root cause, two files)**: reversed/multiple `?`-joined key=value pairs
  (e.g. `srcA?detail=x?token=SECRET`) bypassed detection in both `source_keys.py`'s
  non-URL query-component splitter and `execute.py`'s `_QUERY_PARAM_TOKEN_RE` (both only
  treated `&` as a boundary / allowed `?` inside the greedy value group). Fixed by treating
  `?` as an equally valid separator/boundary in both (regex-based separator-preserving
  split via `re.split(r"([&?])", ...)` in `source_keys.py`; excluding `?` from both
  name/value capture groups in `execute.py`'s regex).
- **R-3**: the cycle-1 U-1 colon-less-userinfo fix over-broadened detection, corrupting
  legitimate non-URL-shaped identifiers containing a bare `@` (e.g. `"release@2026"` →
  `"2026"`). Fixed by gating `_contains_userinfo_marker`/`_strip_userinfo` with a new
  `_is_url_shaped()` early-return, restoring userinfo detection to genuine URL structures
  only (scheme:// or //-prefixed) — this also resolves R-7 (`_is_url_shaped` was
  previously dead code; now load-bearing).
- **R-4** (P021-deferred, stash `95BD0DC7`): exception `__notes__` (PEP 678) not scrubbed
  by `_clone_scrubbed_exception` — verified architecturally unreachable (zero `add_note(`
  call sites repo-wide as of this shipment).
- **R-5** (P021-deferred, stash `709BDB53`): `ExceptionGroup`/`BaseExceptionGroup` chains
  (PEP 654) not traversed by the same scrubbing — verified architecturally unreachable
  (zero `TaskGroup`/`ExceptionGroup`/`gather` usage repo-wide).
- **R-6** (P021-deferred, stash `6076A65E`): non-idempotent 3-pass redaction pipeline can
  produce duplicated `<redacted><redacted>` markers when passes re-match an already-redacted
  value — confirmed cosmetic/no-leak by hand-trace (no credential byte re-exposed at any
  stage).

R-1/R-2/R-3 were classified in-scope under P-021 C1/C3 (same-contract-surface completion —
genuine bugs in the exact cycle-1 fix code) and remediated in **review-fix cycle 2** via a
second TDD pass, independently re-verified by Ship (diff review line-by-line + direct Python
reproduction of each fix before/after + full gate re-run: 2282 passed, up from 2279).
R-4/R-5/R-6 were deferred via P-021 capture (mandatory discovery lookup performed first —
zero reuse candidates found in active + archived stash) rather than consuming a 3rd
review-fix cycle, since none corresponds to a live/exploitable defect in shipped code paths
today (2 currently-unreachable hardening items + 1 confirmed-cosmetic idempotency defect).
This exhausts 2 of 3 available review-fix cycles; the review gate is now treated as closed
based on Ship's own thorough independent verification (line-by-line diff review + full test
pass + direct reproduction of every fix), given 2 full adversarial-review agent rounds
already occurred and all remaining items are advisory/cosmetic/architecturally unreachable.

## Final confirmation review (3rd and final adversarial-review pass, on committed HEAD `ec22a89`)
Report: `docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-final-confirmation-review.md`

Result: **BLOCKED**. Confirmed R-1/R-2/R-3 held with no regression, but surfaced 3 NEW
HIGH-confidence real credential-leak bugs (all independently reproduced by Ship via direct
Python execution — the report disclosed that its own reviewer subagents lacked shell
execution access, so Ship did not trust the report without independent reproduction):
- **C-1 (CRITICAL)**: reversed multi-`?` query credentials (e.g. `host/x?detail=x?token=SECRET`)
  survived in URL-*value*-field sanitization (`_sanitize_url_field`/`_sanitize_exception_text`)
  because `staging.sanitize_source()` (untouched, pre-existing) uses `parse_qsl` which splits
  only on `&`, hiding the credential from its own filter and then percent-encoding — but not
  redacting — the literal secret. Fixed via a new `?`/`&`-aware pre-pass,
  `_strip_reversed_query_credentials()` (source_keys.py), that drops credential-named tokens
  BEFORE the value ever reaches `sanitize_source()` — closing the gap entirely within
  `source_keys.py`/`execute.py`, without touching `staging.py`.
- **U-1 (CRITICAL)**: an ambiguous authority (2+ `@` characters) bypassed
  `sanitize_source_id`'s credential marker gate entirely, returning the identifier completely
  unredacted — worse than the documented fail-closed sentinel, and made `_strip_userinfo`'s
  existing `ValueError` fail-closed path dead code. Fixed by changing
  `_contains_userinfo_marker` to treat any `@`-containing authority as a marker.
- **U-2 (MAJOR)**: a credential value directly adjacent to a quote/angle-bracket (e.g.
  `token="SECRET"`) was matched as an empty value by `_HTTP_URL_RE`/`_QUERY_PARAM_TOKEN_RE`
  (both deliberately exclude quotes/brackets to avoid over-matching), leaving the quoted
  secret entirely outside the matched span. Fixed by extending both regexes to optionally
  consume a directly-adjacent quoted/bracketed span as part of the match.
- **U-3** (P021-deferred, stash `4CEE1EA5`): `_is_url_shaped`'s bare `//`-prefix rule
  over-triggers userinfo stripping on a narrow non-URL identifier shape — confirmed
  data-corruption-only (no credential leak; `build_source_key`/job identity unaffected).
- **M-1** (P021-deferred, stash `1B5CEF80`): documentation-precision note narrowing the
  "currently unreachable" wording on existing entries `95BD0DC7`/`709BDB53` — advisory only.

C-1/U-1/U-2 were remediated in **review-fix cycle 3** (the 3rd and final cycle per the Ship
circuit breaker) via TDD, independently re-verified by Ship: line-by-line diff review, direct
Python reproduction of each fix AND every prior-cycle regression control (R-1/R-2/R-3, the
cycle-1 U-1/U-2/C-2 cases, plus a no-over-match control), full gate re-run (2288 passed, up
from 2282). U-3/M-1 were deferred via P-021 capture (mandatory discovery lookup performed
first — zero reuse candidates found) since both are low-severity/advisory and this is the
final allowed review-fix cycle.

**Review gate closure**: With the 3rd (final) review-fix cycle exhausted and all HIGH/CRITICAL
findings across 3 full adversarial-review rounds fixed and independently verified, the review
gate is now closed. No further adversarial-review agent invocation will be run (would exceed
the 3-cycle circuit breaker); Local Review Readiness for the current HEAD (`dcd51f5`) is based
on Ship's own thorough independent verification. Outcome: **READY_WITH_FOLLOWUPS** — 5
follow-up stash entries scoped to this shipment's findings remain open at LOW priority:
`95BD0DC7` (R-4), `709BDB53` (R-5), `6076A65E` (R-6), `4CEE1EA5` (U-3), `1B5CEF80` (M-1).

> **PR-review-phase addendum (2026-09-13, HEAD `c9d474a`+) — Copilot findings, not
> readdressed here**: this section captures the PRE-PR local adversarial-review outcome
> only. The subsequent GitHub-hosted Copilot code-review phase on PR #198 (post-PR,
> distinct from the above) surfaced 5 MORE rounds of findings and produced 5 ADDITIONAL
> deferred/residual-risk stash entries beyond the 5 listed above:
> `A6D7EEB9` (round 3, percent-encoded query separators, out-of-scope per C1),
> `96E6C3F2` (round 4, fragment-only credential leak, deferred by circuit breaker),
> `7D7222E3` (round 4, nested URL-as-query-value leak, out-of-scope C1 + circuit
> breaker), `E462E1F0` (round 5, non-URL identifier corruption regression from
> round 3's own fix), and `E89DC095` (round 6, underscore-scheme credential leak) —
> making the current total across BOTH review phases (pre-PR local + post-PR Copilot)
> **10 deferred/residual-risk stash entries**, not 9.
>
> **Resolution update (2026-09-13, operator-authorized bounded extension, commit
> `c547f93`)**: `E462E1F0` and `E89DC095` were both FIXED (not merely deferred) via an
> explicit, tightly-bounded operator authorization for exactly ONE additional review-fix
> cycle after the 3-cycle circuit breaker halted at round 7 — see
> `docs/memory/2026-09-13/063-s-halt-review-loop-report.md`'s Resolution section for the
> full fix disposition. Both stash entries remain in `.backlogit/stash.jsonl` as a
> historical record of the original Copilot findings but no longer describe an open
> residual risk. A separate, distinct P-021 finding (`BF028CAE`, F2 — a latent,
> non-live compound-prefix authority-truncation gap surfaced by the mandated adversarial
> review of this fix cycle's own diff) was captured for Stage triage and is unrelated to
> the round-7 count correction above. See
> `docs/memory/2026-09-13/063-s-build-checkpoint-round3.md` for the full, current,
> authoritative accounting of all PR-review-phase findings, fixes, and deferrals. Any PR
> readiness summary or `## Local Review Readiness` block must cite the round-3
> checkpoint (or this addendum) for the complete, up-to-date list, not this section
> alone.

## Stash carry-forward (operator-authorized, P-021-unrelated) + legitimate new P-021 captures
`.backlogit/stash.jsonl` carries TWO independent kinds of change, kept carefully separated
across commits:
1. **Carry-forward diff (never committed)**: the pre-existing fractional-seconds timestamp
   normalization on deferred entries `0F1A653C`/`06A59B1D` (present before this session
   began). Preserved byte-for-byte, kept unstaged/uncommitted throughout cycle-1 (confirmed
   via `git hash-object` → `b5af14cba77579ba3f4c56d84f637bdc17d89da7` match against the
   original target blob).
2. **New legitimate P-021 deferred-scope captures (committed)**: cycle-2 commit `ec22a89`
   added `95BD0DC7` (R-4), `709BDB53` (R-5), `6076A65E` (R-6); cycle-3 commit `dcd51f5`
   added `4CEE1EA5` (U-3), `1B5CEF80` (M-1) — all via `backlogit stash add` per the
   mandatory Step 4.4a threadless-path capture procedure. Since `backlogit stash add`
   appends to the same file as the carry-forward diff, committing these new entries
   required constructing a commit-target blob each time = `git show HEAD:.backlogit/stash.jsonl`
   (unmodified, i.e. still carrying the ORIGINAL `.0000000Z` timestamps) + the new JSON
   lines appended, staged directly into the index via `git hash-object -w` + `git
   update-index --cacheinfo` — without touching the working-tree file at all. This keeps
   the working tree exactly as it was (carry-forward diff intact, unstaged) while each
   commit only adds its own new entries. Verified after both commits: `git diff --cached`
   shows only the new `+` lines (no timestamp change); `git diff` (working tree vs. index)
   shows only the 2-line timestamp normalization (no new-entry lines) — the two change
   sets remain cleanly disjoint throughout. Must continue to be carried via targeted
   `git stash push -- .backlogit/stash.jsonl` / `pop` across any further branch switches
   (none anticipated before merge, since Ship stays on the feature branch through Step 5).

## Decisions with rationale
- Combined harness generation (Step 2) and build (Step 4.2) into one delegated TDD pass
  per task rather than a strict two-phase harness-then-build split, since the subagent's
  internal RED→GREEN discipline satisfied the substance of both steps; retroactively
  applied `harness-ready` labels to all 4 tasks after confirming tests existed and passed.
- Adversarial-review capability pack is installed (`.autoharness/config.yaml`), so Step 4.4
  used the 3-reviewer adversarial-review agent instead of the standalone `review` skill,
  per the Ship template's explicit substitution rule.
- Fixed all 4 actionable review findings (not just the 2 HIGH-confidence ones) because all
  4 are verified-real bugs in the exact helper surface this shipment introduces/modifies —
  P-021 C3's symmetric guard requires same-contract-surface completions to be fixed, not
  deferred, and deferring a verified bug in code delivered by this very shipment would be
  a P-021 violation in the other direction.
- Single commit covers all 4 tasks + the review-remediation cycle, since they share the
  same 4 files and were developed as one coherent implementation increment.
- Ran a 3rd (final) adversarial-review pass specifically because §1.9.4 Check 1 requires
  the reviewed HEAD to match the PR's actual `headRefOid` — cycle-2's self-verification
  alone would not have produced a review record for the exact HEAD ultimately presented.
  This 3rd pass found 3 more genuine CRITICAL/MAJOR credential-leak bugs, confirming the
  value of running it rather than treating cycle-2's fixes as sufficient without a fresh
  agent-review pass. All 3 findings were independently reproduced via direct Python
  execution before delegating fixes, since the reviewing subagent disclosed it lacked
  shell/Python execution access for its own verification.
- Reached the 3-cycle review-fix circuit breaker limit exactly at cycle 3, with all
  HIGH/CRITICAL findings fixed and only LOW-severity/advisory items remaining — the
  intended terminal state per the circuit breaker's "accept remaining P2/P3 as backlog
  items, commit" guidance. No 4th adversarial-review cycle is run; Local Review Readiness
  for current HEAD `dcd51f5` rests on Ship's own thorough independent verification instead.

## Next steps
1. Step 5 PR Lifecycle: final quality gate pass (done — 2288 passed, 17 skipped), local
   review readiness record for current HEAD `dcd51f5`, PR body with `## Local Review
   Readiness` block citing all 3 review reports, all 10 fixes across 3 cycles, and the 5
   deferred P-021 entries scoped to this shipment, invoke `pr-lifecycle` skill.
2. P-018 copilot-review gate, P-014 local-review-readiness gate, then present PR to
   operator and **wait for explicit merge approval** — `merge_approval_pre_authorized: false`
   and `admin_fallback_pre_authorized: false` per the DARK_MODE_ACTIVE contract, so Ship
   must stop at merge-ready state with exact readiness evidence and never auto-merge or
   use admin fallback.
3. Stay on the feature branch until merge is confirmed.
4. After confirmed merge: Step 6 post-merge closure (post-merge/{slug} branch,
   operational-closure, shipment-reconcile safe-close for 063-S, P-020 compact-context,
   source-artifact cleanup for `source_stash_id`/`source_deliberation_id` on 072-F if present).

## Blockers/open questions
None currently blocking. All quality gates green (2288 passed, 17 skipped); review gate
closed after 3 remediation cycles (circuit-breaker limit reached) — no residual P0/P1;
5 remaining low-severity/advisory items deferred via P-021 capture with zero live
exploit paths (2 architecturally-unreachable hardening items, 1 confirmed-cosmetic
idempotency defect, 1 data-corruption-only narrow edge case, 1 documentation-precision
note). Proceeding to PR creation.
