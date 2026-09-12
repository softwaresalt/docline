# Ship session checkpoint — 062-S / PR #192 — review-fix cycle 3 (final allowed cycle) complete

**Date**: 2026-09-11 / 2026-09-12
**Shipment**: `062-S` (active) · **Feature**: `071-F` (done) · **Tasks**: `071.001-T`..`071.011-T` (all done)
**Branch**: `feat/github-markdown-extension`
**PR**: [#192](https://github.com/softwaresalt/docline/pull/192) — `OPEN`, `MERGEABLE`, HEAD `8f4f815aa049931a46168a0d3c7b97ca5e80d382`
**Operator instruction**: do NOT merge; return new HEAD and evidence only.

## What happened this session

Resumed shipment 062-S / PR #192 to execute **review-fix cycle 3, the final
allowed review-fix cycle**. Operator-reported finding: cycle 2's
`mkdir(exist_ok=False)` atomic-claim redesign required `--dest` to be
strictly absent, so the documented exact operator command failed against
the real external destination (`C:\Source\Docs\tf-unified-dev-docs-normalized`)
because it already existed (empty) from a prior inspection.

### 1. Headline fix (test-first): existing-empty `--dest` via exclusive sentinel claim

Replaced the absent-only `mkdir` claim with an exclusive OS-level
sentinel-file claim (`os.O_CREAT | os.O_EXCL`, new `claim_destination()` /
`release_destination_claim()`). `--execute` now accepts `--dest` absent OR
existing-and-empty, while preserving cycle 2's mutual-exclusion guarantee.
New/updated tests: existing-empty succeeds; existing non-empty still
rejects; dry-run leaves existing-empty unchanged; sentinel removed after
success and failure; two claims cannot coexist.

Ship's own 5-persona local review gate against this fix then found:

- **P0/P1** (3 reviewers converging): `_dest_precheck()` ran before
  `claim_destination()` and wasn't sentinel-aware — a `--dest` actively
  claimed by another invocation was rejected with the generic
  `EXIT_DEST_NOT_EMPTY` instead of the documented, specific
  `EXIT_DEST_ALREADY_EXISTS`. Fixed: `_dest_precheck()` now falls through
  to the authoritative check when the only entry is the live sentinel.
- **P2** (2 reviewers converging): `open()`/`close()` shared one
  `try/except`; a `close()` failure after successful `open()` orphaned
  the sentinel. Fixed: separated, releases on close failure, explicit
  `0o600` mode.

Four out-of-scope findings deferred (P-021): `1EDE36E7`, `1E7CCBF7`,
`E3129374`, `13F7C7C3`.

Commit `eae28b0`, pushed. PR body updated (readiness `READY_WITH_FOLLOWUPS`).

### 2. Post-push ambient CI observation

`pipeline-topology (ambient)` reports `BRANCH_MISMATCH` (branch predates
shipment-derived naming convention). Confirmed pre-existing (identical at
prior HEADs) and non-blocking (no branch protection; workflow conclusion
`success`). Deferred: `ADE96404`. Commit `201fc58` (doc-only), pushed.

### 3. Post-push Copilot shadow-review triage (3 rounds, 7 threads total)

GitHub's Copilot shadow review re-runs on every push. Across three
rounds this session, 7 actionable threads were triaged, replied to, and
resolved:

| Thread | Finding | Disposition |
|---|---|---|
| `3994209535` | fence backtick-in-info-string | out of scope → `C0E88586` |
| `3993438433` + `3994209569` | `--dest` nested under `--source` (duplicate across rounds) | out of scope → `387E5F82` |
| `3994209593` | stale "Exact operator command" design-doc prose | in scope → fixed (§7, plus §9.2/§11.3 audit fixes) |
| `3994209606` | stale PR-readiness-block HEAD reference | in scope → already resolved (crossed in flight) |
| `3994230152` | `--report` colliding with reserved claim-sentinel filename | in scope → fixed, commit `20f91a4` |
| `3994338286` | `guard_write_path()`'s `relative_to` passes when `--report == --dest` | out of scope → `7D71CBEA` |
| `3994371552` | readiness block referenced stale HEAD after `8f4f815` | in scope → already resolved (crossed in flight) |

The `--report`/reserved-sentinel bug (thread `3994230152`) was a real,
deterministic bug in this cycle's own new sentinel-claim mechanism: an
operator `--report` path resolving to exactly the reserved sentinel name
passed containment (trivially inside `--dest`) and would be silently lost
to end-of-run cleanup while still returning exit 0. Fixed test-first: new
`EXIT_REPORT_PATH_RESERVED` exit code, rejection at both the pre-claim and
post-write guard call sites, corrected the `CLAIM_SENTINEL_NAME`
docstring's prior unverified "never collides" claim, new regression test
covering both absent-`--dest` and existing-empty-`--dest` cases. Commit
`20f91a4`, pushed.

A handful of additional Copilot observations were suppressed (no
line-comment thread created) and required no thread action: a
`selection.py` stage-classification edge case, a `normalize.py`
fence-indentation concern related to `C0E88586`, and two `src/docline`
findings (`app.py`, `output_contract.py`) about pre-existing
`.markdown`-extension work already on this branch before this shipment's
commits began — outside 062-S's scope entirely (a different feature
sharing this branch).

Doc-only commit `8f4f815` recorded the final round (§12.7) plus the
`7D71CBEA` stash entry; pushed. No further Copilot review appeared after
this push (verified via a bounded reply-only follow-up with no new
commit).

## Final verification (at HEAD `20f91a4` / doc-only `8f4f815`)

- Targeted HashiCorp suite (`-m "not integration"`): **100 passed, 1
  deselected** (was 99; +1 net new test).
- Full suite (`-m "not integration"`): **2210 passed, 2 skipped, 16
  deselected** (was 2209; +1).
- `ruff check .` / `ruff format --check .`: all clean.
- `uv run pyright scripts/hashicorp_mdx_normalize.py`: 0 errors/warnings.
- `uv run python -m build`: succeeded.
- Exact documented operator command re-run read-only (no `--execute`)
  against the real external `--source`/`--dest`/`--report` paths: exit 0,
  `unresolved_constructs: {}`, 23 products. Real external `--dest`
  (`C:\Source\Docs\tf-unified-dev-docs-normalized`) confirmed **0 entries
  before and 0 entries after** — never touched, this session or ever.
- CI checks on PR: all pass except the pre-existing, non-blocking,
  already-deferred `pipeline-topology (ambient)` check.

## Local Review Readiness (final)

- Reviewed HEAD: `8f4f815` (doc-only; code/test HEAD `20f91a4`)
- Outcome: `READY_WITH_FOLLOWUPS`
- P0=0, P1=0 unresolved
- 8 deferred stash entries total this shipment: `1EDE36E7`, `1E7CCBF7`,
  `E3129374`, `13F7C7C3`, `ADE96404`, `387E5F82`, `C0E88586`, `7D71CBEA`
- 7 GitHub review threads replied to and resolved this session

## State / next steps

- Branch retained: `feat/github-markdown-extension` (per Ship branch
  retention rule — do not switch away while PR is open).
- **Merge NOT performed** — explicit operator instruction. PR #192
  remains open, mergeable, awaiting explicit operator approval.
- Real external destination never touched by any command this session —
  only read-only dry-runs and repo-local `tmp_path`/synthetic-fixture
  tests were used for anything that could write.
- Next session (if any): await operator merge approval; if merge is
  approved, proceed to Step 6 post-merge closure (shipment archival,
  operational-closure, compound-refresh, source-artifact cleanup for
  `062-S`'s source stash/deliberation IDs, compact-context).
