# Ship session checkpoint — 062-S / PR #192 — review-fix cycle 2 complete

**Date**: 2026-09-11
**Shipment**: `062-S` (active) · **Feature**: `071-F` (done) · **Tasks**: `071.001-T`..`071.011-T` (all done)
**Branch**: `feat/github-markdown-extension`
**PR**: [#192](https://github.com/softwaresalt/docline/pull/192) — `OPEN`, `MERGEABLE`

## What happened this session

Resumed shipment 062-S / PR #192 to execute **review-fix cycle 2**: fixed 6
numbered findings from a second independent correctness review (2×P1,
2×P2, 2×P3) against the disposable HashiCorp MDX→MD normalizer tooling,
test-first, per explicit operator instructions. After the 6 findings were
fixed and committed, ran Ship's own local review gate (`review` skill,
`mode:report-only`, multi-persona) against the resulting diff — it
surfaced 4 further in-scope, same-contract-surface findings (2 P2, 2 P3),
which were also fixed test-first before finalizing PR readiness.

## Findings fixed (operator's 6, review-fix cycle 2)

1. **P1** — unresolved-construct gate ran after execute writes. Fixed:
   `--execute` now runs a complete read-only preflight first; aborts
   before `--dest` is created unless zero unresolved constructs or
   `--allow-unresolved-mdx`. Report written only after successful
   execution.
2. **P1** — report containment preflight discarded resolved path. Fixed:
   `guard_write_path` re-called immediately before the report write; the
   write uses the returned resolved path. Documented as best-effort, not
   race-free.
3. **P2** — non-atomic destination check. Fixed: `--dest` must be
   ABSENT (not merely empty); claimed atomically via
   `mkdir(exist_ok=False)` immediately before writes. Partial output on
   later failure is left in place, not auto-deleted.
4. **P2** — fence scanner accepted unlimited indentation. Fixed: bounded
   rule — top-level fences 0–3 columns; container/list-indented fences
   within 3 columns of the opener's own indent.
5. **P3** — live-corpus test only type-checked `unresolved_constructs`.
   Fixed: now asserts `== {}` exactly.
6. **P3** — `list_version_entries` could flag >1 `is_latest`. Fixed:
   computes exactly one latest index up front (first stable, else index 0).

Commit: `a898a7c` — `fix(scripts): review-fix cycle 2 for HashiCorp MDX
normalizer (062-S/#192)`

## Findings fixed (Ship's own review gate, 4 additional)

1. **P2** — atomic `--dest` claim caught only `FileExistsError`, not other
   `OSError` variants (permission denial, blocked ancestor, disk
   exhaustion). Fixed: new `EXIT_DEST_CLAIM_FAILED` exit code, clear
   message, no partial output claim (nothing was created).
2. **P2** — report write (`mkdir`/`write_text`) unguarded against
   `OSError` after a successful corpus write. Fixed: new
   `EXIT_REPORT_WRITE_FAILED` exit code, message clarifies corpus output
   already succeeded and is left in place.
3. **P3** — `list_version_entries`'s "ordered latest-first" contract could
   list a same-version prerelease ahead of the stable release it
   supersedes (tied sort keys fell back to input-order preservation).
   `is_latest`/`select_latest_version` were unaffected. Fixed: added
   `_stage_priority()` tie-breaker (stable outranks prerelease) to both
   sort groups.
4. **P3 (docs-only)** — "atomic claim"/"first filesystem mutation" wording
   was slightly overstated for a `--dest` with missing parent
   directories (`mkdir(parents=True, ...)` creates ancestors first,
   non-atomically). Narrowed wording to scope the atomicity guarantee to
   `--dest`'s own final path component only.

Commit: `408dbba` — `fix(scripts): address independent review-gate
findings on cycle 2 (062-S/#192)`

Independent review's final readiness outcome: **`READY`** (P0=0, P1=0,
P2=0, P3=0 unresolved) for HEAD `408dbba97a6c1cf11627cd2d422daf5b7c319941`.

## Quality gates (final, this session)

- `ruff check .` → all checks passed
- `ruff format --check .` → 301 files already formatted
- `pytest --basetemp=build\.pytest-tmp -m "not integration"` → **2205
  passed, 2 skipped, 16 deselected** (up from 2202 at start of session:
  +3 new regression tests from the 4 review-gate findings)
- Targeted HashiCorp suite (`-m "not integration"`): **95 passed, 1
  deselected** (was 92 before the review-gate fixes)
- Real-corpus integration test (`-m integration`, explicit run against
  `C:\Source\Docs\hashicorp-tf-unified-dev-docs\content`): **PASSED**.
  Zero writes, `unresolved_constructs == {}` (0/0), totals identical
  across every run this cycle (5,566 mdx normalized, 59 md copied, 2,139
  assets copied, 1,259 partials skipped, 164 generic copied; 23 products;
  unchanged version selections) — no regression from any cycle-2 fix.
- `uv run pyright src/` → 0 errors, 0 warnings, 0 informations
- `uv run python -m build` → sdist + wheel built successfully

## PR / docs updates

- `docs/design-docs/2026-09-11-hashicorp-mdx-normalization-requirements-evidence.md`:
  added §11 (Review-fix cycle 2, findings 1–6), §11.8 (Ship's own review
  gate findings + fixes), §11.9 (final gate/real-corpus re-verification);
  fixed stale `EXIT_DEST_NOT_EMPTY` / "absent or empty" references in §7
  and §9.2 to reflect the new "absent, atomically claimed" contract;
  updated §10 Traceability test counts (30/43/23).
- PR #192 body updated: added "Review-fix cycle 2" summary section
  (mirroring cycle 1's structure, including the review-gate follow-up
  findings), updated "Local Review Readiness" block (HEAD `408dbba...`,
  outcome `READY`), updated "Tests / gates run" counts, added a
  "Residual risks" section.
- Pushed branch: `7914294..408dbba` → `feat/github-markdown-extension`.

## Branch / merge state

- Still on `feat/github-markdown-extension` (never left it).
- PR #192: `OPEN`, `MERGEABLE`, headRefOid `408dbba97a6c1cf11627cd2d422daf5b7c319941`.
- CI checks were just re-triggered by the push at session end (pending as
  of this checkpoint — not yet observed green for this exact HEAD).
- **No merge occurred and none was requested this session** — explicit
  operator instruction was "do not merge." Per P-014, explicit operator
  approval is required before any future merge step, and CI green +
  §1.9 gate pass must both be (re-)confirmed for this HEAD first.

## Residual risks (surfaced to operator)

- Execute-mode preflight runs `process_corpus()` twice (accepted,
  documented cost for this disposable tool).
- `guard_write_path` containment remains best-effort/non-race-free
  (documented, not overstated).
- Atomic `mkdir(exist_ok=False)` claim narrows but does not eliminate
  every race scenario (documented in module docstring).
- This is disposable, one-off tooling; a first-class docline MDX
  ingestion capability is tracked separately (requirements-evidence doc
  §8, Requirement 11) — not part of this shipment's scope.

## Next steps (for whichever agent/session resumes)

1. Confirm CI is green for HEAD `408dbba97a6c1cf11627cd2d422daf5b7c319941`
   (was pending at session end — poll `gh pr checks 192`).
2. Present PR readiness summary to operator; await explicit merge
   approval (P-014) — do not merge without it.
3. Once approved: re-run the Step 5 last-mile gate re-checks (§1.9,
   P-018 Copilot-review gate if engaged, P-009 merge-commit-strategy
   guardrail) before executing the merge.
4. After merge is confirmed: proceed to Step 6 post-merge closure
   (`post-merge/{feature_slug}` branch, backlog archival via
   `shipment-reconcile`, `operational-closure`, knowledge graduation,
   `compact-context`, backlog index resync) per the Ship agent template.
