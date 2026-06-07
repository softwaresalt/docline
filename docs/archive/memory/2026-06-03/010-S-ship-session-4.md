# 010-S Ship Session 4 — Memory Checkpoint

| Field | Value |
|---|---|
| Date | 2026-06-03 |
| Phase reached | Phase 4 (Copilot review request) — paused at clean boundary |
| Branch | `feat/docline-graphtor-alignment` @ `dabacf4` |
| PR | #19 — <https://github.com/softwaresalt/docline/pull/19> |
| Operator | softwaresalt |

## Work landed this invocation

| Commit | Type | Description |
|---|---|---|
| `284d73c` | test | Updated 2 stale parity assertions for `export_schema` MCP tool |
| `dabacf4` | docs | 010-S structured review artifact (`docs/closure/010-S-review.md`) |

Pushed both commits to `origin/feat/docline-graphtor-alignment`.

## Phase progression

- **[PHASE 0]** Tool gate + index sync + baseline confirmation — `INDEX_SYNC_OK`, branch clean
- **[PHASE 1 → 2]** Review skill (report-only mode): persona analysis across 96-file diff. Findings: 0 P0, 2 P1 (resolved in-cycle), 0 P2 outstanding, 1 P3 advisory. See `docs/closure/010-S-review.md`.
- **[PHASE 2 → 3]** Quality gates all green: ruff ✅, pyright ✅ (0 errors), pytest ✅ (561 passed, 0 failed), ruff format ✅
- **[PHASE 3 → 4]** PR #19 opened with full body referencing PA-1/PA-2, P2 advisories, contract doc, blocks F1-F8
- **[PHASE 4 paused]** Copilot review requested (despite misleading CLI 422 errors — GraphQL confirms it landed); pending review submission

## Review findings detail

### P1 (resolved in cycle, committed at `284d73c`)

1. `tests/parity/test_equivalence.py::test_manifest_tool_names_match_operation_names` — stale assertion expecting 2-tool list, updated to 3 (`["fetch", "process", "export_schema"]`)
2. `tests/parity/test_manifest_parity.py::test_manifest_has_two_tools` — assertion `== 2` updated to `== 3`; function renamed to `test_manifest_has_three_tools`

Root cause: tests not updated when `export_schema` MCP tool was added by 010.005-T. New parity coverage in `tests/parity/test_cli_export_schema.py` already validates the 3-surface contract (CLI ↔ MCP ↔ library byte-equivalence).

### P3 advisory (deferred, non-blocking)

- `src/docline/fetch/sitemap.py` uses stdlib `xml.etree.ElementTree.fromstring`. Not exploitable on sitemap inputs (no DTDs), but inconsistent with the `defusedxml` migration of 010.015-T elsewhere. Future hygiene opportunity.

## §1.9 readiness gate at pause point

GraphQL query result for PR #19 at HEAD `dabacf4`:

```json
{
  "headRefOid": "dabacf4744ccca185994e503078f3ab53e9310c5",
  "reviewDecision": "REVIEW_REQUIRED",
  "reviewRequests": [{"requestedReviewer":{"__typename":"Bot","login":"copilot-pull-request-reviewer"}}],
  "reviews": [],
  "reviewThreads": []
}
```

| Check | State |
|---|---|
| 1 — no pending Copilot review | **PENDING** (Copilot is in reviewRequests) |
| 2 — review covers current HEAD | N/A — no reviews submitted yet |
| 3 — no unresolved Copilot threads | PASS (0 threads) |

Gate verdict: **NOT YET READY** — waiting on Copilot review per §1.9.3 Check 1 instruction "wait using the back-off cadence from §1.2 (max 15 min). Re-run the readiness query after each wait interval."

## Notes on Copilot reviewer-add CLI behavior

`gh pr edit 19 --add-reviewer copilot` and `gh api -X POST .../requested_reviewers -F "reviewers[]=copilot-pull-request-reviewer"` both returned non-zero exit codes with apparent error messages (`'' not found` for the first, HTTP 422 collaborator error for the third). **However, the GraphQL `reviewRequests` query confirms the request DID land** — the request is now in flight. This is a CLI surface UX inconsistency worth noting in future Ship invocations: trust GraphQL state over CLI exit codes for Copilot reviewer-add operations.

Two PR comments were posted documenting this discovery (one initial misdiagnosis flagging a 009-S regression rollback; one correction confirming the request actually landed).

## Outstanding work for next Ship invocation

1. **[Phase 4 continuation]** Poll for Copilot review per §1.2 back-off (2 → 2 → 3 → 3 → 5 min, max 15 min cumulative)
2. **[Phase 4 fix-reply-resolve cycle]** Apply §1.3 to any Copilot findings (max 3 cycles per §1.8)
3. **[Phase 5]** N/A — no GitHub Actions CI configured for this repo (greenfield project)
4. **[Phase 6]** Re-run §1.9 readiness GraphQL gate after Copilot review lands
5. **[Phase 7]** Halt for operator merge approval with §1.9 PASS summary
6. **[Phase 8]** Merge with `gh pr merge 19 --merge --delete-branch`; checkout main; pull; prune
7. **[Phase 9]** runtime-verification skill → `docs/closure/010-S-runtime-verification.md`
8. **[Phase 10]** operational-closure skill → `docs/closure/010-S-docline-graphtor-ingestion-contract-alignment.md`
9. **[Phase 11]** Post-merge closure PR (archive 010-F + 010-S, commit closure docs) → P-014 second approval cycle
10. **[Phase 12]** Final session checkpoint

## Files modified this invocation

- `tests/parity/test_equivalence.py` (1 line)
- `tests/parity/test_manifest_parity.py` (2 lines + function rename)
- `docs/closure/010-S-review.md` (new)
- `docs/scratch/010-S-pr-body.md` (new — PR body source, not committed; ephemeral)
- `docs/scratch/010-S-pr-comment-copilot.md` (new — comment source, ephemeral)
- `docs/scratch/010-S-pr-comment-correction.md` (new — comment source, ephemeral)
- `logs/commit-msg-010-S-parity-fix.txt` (commit message log)
- `logs/commit-msg-010-S-review.txt` (commit message log)

## Backlog state

- Shipment 010-S: `active` (unchanged)
- 010-F: `active` (unchanged)
- All 39 archived tasks: untouched (archive state from prior sessions)
- No new stash entries created (no P2 escalations from this review cycle)

## Lessons learned

1. **Trust GraphQL state, not CLI exit codes**, for Copilot reviewer-add operations on GitHub. `gh pr edit --add-reviewer` and `gh api -X POST requested_reviewers` may exit non-zero while the request actually lands. Confirm via `gh api graphql` query on `reviewRequests.nodes`.
2. **Stale parity assertions** are a recurring risk when new operations are added across CLI/MCP/manifest surfaces. The new operation-specific parity test file (`test_cli_export_schema.py`) correctly extends coverage, but the legacy `test_manifest_parity.py` had hard-coded counts that became stale silently until the test suite caught them. Consider replacing hard-coded counts with derived assertions (e.g., `len(get_manifest().tools) == len(KNOWN_TOOL_NAMES)`) in future refactors. Captured as advisory only — not action item for 010-S.
