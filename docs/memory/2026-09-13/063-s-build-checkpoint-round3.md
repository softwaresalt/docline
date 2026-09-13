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

## Next steps

1. Confirm CI green on HEAD `c0982f5`.
2. Poll the P-018 `autoharness gate copilot-review` gate per the §1.2 back-off cadence.
   **This was the final allowed review-fix cycle** — if Copilot produces a 4th round of
   NEW findings, Ship must STOP and present the PR to the operator with those findings
   listed, per the "Review comment fix cycles: 3" circuit breaker. Do not attempt a 4th
   fix cycle.
3. Once the gate is `SATISFIED`/`NOT_APPLICABLE`: run P-014 §1.9 readiness gate.
4. Present PR readiness summary to operator; wait for explicit merge approval
   (`merge_approval_pre_authorized: false`, `admin_fallback_pre_authorized: false`).
5. Remain on feature branch until merge confirmed.
6. Post-merge: Step 6 closure protocol (post-merge branch, operational-closure,
   shipment-reconcile safe-close, P-020 compact-context, source-artifact cleanup, backlog
   index resync, closure PR + operator approval).
