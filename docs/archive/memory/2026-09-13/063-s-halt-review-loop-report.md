# 063-S — Ship HALT: Review-Fix Loop Terminated (Non-Converging Pattern)

**Date**: 2026-09-13
**Shipment**: 063-S (feature 072-F)
**PR**: #198 (`https://github.com/softwaresalt/docline/pull/198`)
**Current HEAD**: `0447851` (all CI checks green)
**Mode**: DARK FACTORY MODE — `merge_approval_pre_authorized: false`,
`admin_fallback_pre_authorized: false`

## Decision: HALT the Copilot review-remediation loop, present to operator

After 7 rounds of Copilot review output on PR #198, Ship is halting further reactive
capture/reply/resolve/push cycles and presenting the current state to the operator, per
the "Review comment fix cycles: 3" circuit breaker (already exhausted at round 3) and
the demonstrated non-convergence of rounds 4-7.

## Full round-by-round history

| Round | Findings | Disposition |
|---|---|---|
| 1 | 1 (credential leak) | Fixed (pre-session) |
| 2 | 3 (credential leak variants) | Fixed (pre-session) |
| 3 | 4 (unterminated delimiter, malformed-scheme leaks ×2, percent-encoded separator) | 3 fixed (`c0982f5`), 1 deferred (`A6D7EEB9`) — **review-fix-cycle circuit breaker (3) exhausted here** |
| 4 | 2 (fragment-only leak, nested-URL-value leak) | Both deferred, no code fix (`96E6C3F2`, `7D7222E3`) — compliant with circuit breaker |
| 5 | 1 (non-URL identifier corruption — **regression from round 3's own fix**) | Deferred as HIGH-priority residual risk (`E462E1F0`) — same-contract-surface/C3(i) in-scope, held back solely by circuit breaker |
| 6 | 2 (underscore-scheme credential leak; stale doc count) | Leak deferred as HIGH-priority residual risk (`E89DC095`); doc-staleness fixed directly (docs-only, no cycle cost) |
| 7 | 2 (BOTH: doc count staleness on the checkpoint files updated in round 6) | **NOT actioned — loop halted here** |

## Why round 7 is a stop point, not another defer-capture cycle

Both round-7 findings (`PRRT_kwDOSsAX4c6h8fzS`, `PRRT_kwDOSsAX4c6h8fzg`) are Copilot
noticing that the memory-checkpoint documentation's stated count of deferred entries
(written in the round-6 commit) is already one behind the true count, because capturing
`E89DC095` in that same round-6 push made the just-written "4 additional entries" claim
stale by the time Copilot's review completed. This is a **provably non-converging
pattern**: any commit that states "N entries as of now" will, if reviewed against a
timeline where a subsequent commit adds an (N+1)th entry, be flagged as stale — and
since responding to a staleness finding by editing the count is itself a new commit
that could be superseded by the next captured entry, this cannot terminate via reactive
fixing. It is a bookkeeping/documentation-accuracy concern, not a credential-leak or
correctness defect in shipped code. Ship is deliberately NOT reacting to round 7 to avoid
an unbounded push/poll loop.

**These 2 threads remain unresolved on GitHub as of this checkpoint** — left for
operator awareness per the circuit breaker's "Present PR with remaining unresolved
comments listed for operator" action, rather than reflexively resolved.

## Current, accurate, FINAL accounting of deferred/residual-risk entries (10 total)

**Pre-PR local adversarial review (5, all LOW priority, from `docs/archive/memory/2026-09-13/063-s-build-checkpoint.md`)**:
- `95BD0DC7` (R-4): exception `__notes__` unscrubbed — verified architecturally unreachable today (no `add_note()` call sites in repo).
- `709BDB53` (R-5): `ExceptionGroup` chains not traversed — verified architecturally unreachable today (no `TaskGroup`/`ExceptionGroup`/`gather` usage in repo).
- `6076A65E` (R-6): non-idempotent redaction can produce duplicated `<redacted>` sentinels — cosmetic log-quality only, no credential exposure.
- `4CEE1EA5` (U-3): bare `//`-prefix rule over-triggers on a narrow non-URL identifier shape — data corruption only, no credential leak; `build_source_key`/job identity unaffected.
- `1B5CEF80` (M-1): documentation-precision wording note on R-4/R-5 — advisory only.

**PR-review (Copilot) findings, rounds 3-6 (5, from this session)**:
- `A6D7EEB9` (round 3, medium): percent-encoded query separators (`%26`/`%3D`) hide nested credential pairs — genuinely out-of-scope per P-021 C1 (requires a decode-and-rescan mechanism, not a regex extension).
- `96E6C3F2` (round 4, medium): fragment-only credentials (`#token=SECRET`) bypass `_HTTP_URL_RE`/`_QUERY_PARAM_TOKEN_RE` — deferred by circuit breaker; plausibly mechanical if fresh cycle budget existed.
- `7D7222E3` (round 4, medium): nested URL-as-query-value (`redirect=https://user:pass@evil`) bypasses outer-authority-only scrub — out-of-scope per C1 AND circuit breaker; related to `A6D7EEB9`.
- **`E462E1F0` (round 5, HIGH)**: round 3's own `_URL_SCHEME_RE` relaxation (`:/{1,2}` → `:/*`) now also treats non-URL identifiers containing a scheme-like colon prefix + `@` as URL-shaped, silently corrupting them (e.g. `release:owner@2026` → `release:2026`). **Verified same-contract-surface / C3(i) — would normally be a MANDATORY fix, deferred SOLELY due to the circuit breaker.** Verified NOT exploitable via either real production source_key scheme (`manifest_url:`/`web_crawl:`, both underscore-containing and thus unaffected).
- **`E89DC095` (round 6, HIGH)**: `_URL_SCHEME_RE`'s character class excludes underscore, so an underscore-containing scheme (e.g. `custom_scheme://user:pass@host`) is NOT recognized as URL-shaped and its credentials pass through unsanitized. **Verified same-contract-surface / C3(i) — would normally be a MANDATORY fix, deferred SOLELY due to the circuit breaker.** Not confirmed reachable via any real configured docline source_key scheme today, but not as exhaustively ruled out as `E462E1F0`.

## Residual risk assessment for operator decision

`E462E1F0` and `E89DC095` are the two findings that most warrant explicit operator
attention before merge: both are **verified, reproducible** bugs in the exact
`_URL_SCHEME_RE`/`_is_url_shaped` helper this shipment's round-3 fix modified, and both
would **normally be mandatory in-scope fixes** per P-021 C3(i) rather than deferral
candidates — they are being deferred **only** because the review-fix-cycle circuit
breaker (3) was already exhausted in round 3, before either was discovered. Neither is
known to be exploitable via a real, currently-configured docline `source_key` scheme
(the two production schemes, `manifest_url:`/`web_crawl:`, both contain underscores and
are unaffected by the URL-shape detection either bug depends on), but both represent
generalization gaps in the sanitizer's stated guarantees that a determined/adversarial
input could reach if a future scheme or caller introduces an underscore-containing or
bare-scheme-with-`@` identifier shape.

## PR state at halt point

- HEAD: `0447851`
- CI: all checks green (pyright, ruff lint, ruff format, pytest 2314/17, sdist+wheel, ci gate, pipeline-topology).
- `mergeStateStatus`: `BLOCKED` (GitHub-reported; corresponds to the 2 unresolved round-7 threads plus branch-protection review requirements).
- `reviewDecision`: none yet recorded.
- Carry-forward diff (`0F1A653C`/`06A59B1D` timestamp normalization): confirmed intact, byte-identical, unstaged, uncommitted — 2 lines changed only.
- 10 total deferred/residual-risk stash entries recorded across pre-PR and PR-review phases, none implemented, all requiring Stage deliberation per their `requires_deliberation: true` flags (except `1B5CEF80`, a documentation-wording note).

## What Ship needs from the operator

1. **Disposition of the 2 open round-7 threads** (`PRRT_kwDOSsAX4c6h8fzS`,
   `PRRT_kwDOSsAX4c6h8fzg`): both are documentation-count-staleness nitpicks on Ship's own
   memory-checkpoint files, not code defects. Options: (a) accept as an acknowledged,
   inherent documentation-lag artifact and leave unresolved/reply-only without further
   editing loops, (b) authorize one bounded final documentation correction with explicit
   instruction to NOT react to any further staleness findings after that, or (c) another
   disposition.
2. **Awareness/decision on `E462E1F0` and `E89DC095`**: both are verified, same-contract-
   surface, would-normally-be-mandatory fixes, deferred only by the circuit breaker.
   Options: (a) accept as documented residual risk and proceed toward merge as-is
   (both are inert against current real production schemes), (b) explicitly authorize a
   new, separately-scoped follow-up work unit through Stage (per P-021 C6) to close them
   before this ships, or (c) explicitly authorize Ship to fix them now as a deliberate,
   bounded exception to the circuit breaker (acknowledging P-021 C4's caution that this
   is not something Ship can self-authorize).
3. **Merge approval**: once the operator's direction on (1) and (2) is applied (or
   explicitly waived), Ship will complete the P-014 §1.9 readiness gate and the P-018
   copilot-review gate, then present final PR readiness and wait for explicit merge
   approval. `merge_approval_pre_authorized: false` / `admin_fallback_pre_authorized:
   false` remain in force — no auto-merge, no admin fallback, under any circumstance.

## Next steps (blocked on operator input above)

Ship remains on the feature branch, has made no further pushes since `0447851`, and will
not open another reactive documentation/code cycle without explicit operator direction.

## Resolution (2026-09-13, operator-authorized bounded extension)

The operator reviewed this halt report and issued an explicit, tightly-bounded
authorization covering exactly the two open items above, with merge and admin fallback
both explicitly withheld:

1. **`E462E1F0`/`E89DC095` (item 2, option (c))**: the operator authorized Ship to fix
   both as a deliberate, one-time, bounded exception to the circuit breaker — extending
   the review-fix budget by exactly ONE additional cycle, not an unbounded re-opening.
2. **Round-7 threads (item 1, option (b))**: the operator authorized exactly ONE final
   bounded checkpoint-count correction, with an explicit instruction not to react to any
   further staleness findings after that.
3. Both authorizations were explicit, scoped, and did not extend to any other deferred
   entry (`0F1A653C`, `06A59B1D`, `A6D7EEB9`, `96E6C3F2`, `7D7222E3` remain out of scope
   and untouched).

**Fix applied**: `E462E1F0` and `E89DC095` were both fixed in commit `c547f93` on this
branch. The fix replaced the previously-proposed "colon-in-userinfo" heuristic with a
known-scheme allowlist gate for loose-authority (non-`//`, non-exactly-two-slash)
matches, matching Copilot's own suggested remediation direction. A mandated 3-reviewer
adversarial review of the draft fix (see
`docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-e462e1f0-e89dc095-adversarial-review.md`)
caught a live false-negative regression (F1) in an earlier iteration of the fix before
it was committed; the committed design (known-scheme allowlist) closes both target
findings without that regression, verified via new regression tests plus direct
hand-tracing of every case in this report and in the adversarial review. All quality
gates (ruff check, ruff format --check, pyright, full pytest, `python -m build`) passed
against the committed fix.

A third finding from that same adversarial review, F2 (a latent, non-live compound-
prefix authority-truncation gap — verified NOT reachable via any current production
call site), was out of scope for this bounded cycle per P-021 C1 (it requires a
materially different authority-span re-architecture, not a mechanical extension of the
just-applied allowlist). It was captured as stash entry `BF028CAE` via the standard
threadless-path P-021 C2 procedure for Stage triage/deliberation, and is NOT part of
the operator's `E462E1F0`/`E89DC095` authorization.

**Round-7 checkpoint correction**: `docs/archive/memory/2026-09-13/063-s-build-checkpoint.md`
and `docs/archive/memory/2026-09-13/063-s-build-checkpoint-round3.md` were both corrected to
account for `E89DC095` (the "4 additional"/"9 total" → "5 additional"/"10 total"
discrepancy the two round-7 threads flagged), with an explicit note that `E462E1F0` and
`E89DC095` are now fixed (this commit) rather than open residual risks — this is the
one bounded correction the operator authorized; per the operator's explicit
instruction, Ship will NOT react further to any subsequent count-only feedback on these
files.

**In-flight after this Resolution section is committed** (per the operator's explicit
instruction, this file is intentionally not re-edited to chase the exact final state
below — doing so would reproduce the same non-converging documentation-lag pattern this
halt report itself describes): commit the docs correction (including this section),
push, reply to and resolve the two round-7 threads referencing the pushed commit, wait
for CI, run the P-018 `autoharness gate copilot-review` gate, update the PR body's
`## Local Review Readiness` block, and run the P-014 §1.9 readiness gate. **Merge is
NOT authorized** (`merge_approval_pre_authorized: false`, `admin_fallback_pre_authorized:
false` remain in force). Any new substantive (non-count-only) finding surfaced during
this remaining work is classified per P-021 and halted/deferred, not fixed, per the
operator's explicit "do not enter another reactive review-fix loop" instruction. The
authoritative record of the final HEAD, CI status, P-018 verdict, and open-thread count
is Ship's final report to the operator for this session, and the PR's own updated
Local Review Readiness block — not a further edit to this file.
