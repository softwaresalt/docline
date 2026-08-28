---
type: session-memory
agent: stage
date: 2026-08-27
branch: chore/stage-055-s
pr: 166
cycle: 9
head_before: 546a256
---

# Stage — PR #166 cycle-9 review remediation (round 3 of 3)

Final review-fix cycle before convergence evaluation. Two unresolved Copilot
threads on HEAD `546a256` reconciled. Scope: planning/backlog/plan/memory
artifacts + backlogit relationship operations only. No source/test/workflow/
harness/agent/.gitignore edits. Operator edits in `.autoharness/config.yaml`,
`.github/agents/_orchestrator.agent.md`, `.github/agents/_ship.agent.md`, and
`.gitignore` left untouched and NOT staged.

## Finding 1 — request-shape contract must validate JSON-RPC `id` type

MCP 2026-07-28 `RequestId` permits only a JSON string or number. Object, array,
boolean, and `null` ids are invalid → `-32600` and MUST NOT be echoed (error
frame carries `id:null`). An ABSENT id stays an id-less notification (silent); a
present `null` id is `-32600` (not a notification). Request-shape validation runs
in the single shared `dispatch()` BEFORE `_meta` extraction / era classification /
version negotiation / method routing, so both eras inherit the guard and a
malformed id can never surface as `-32022`/`-32602`/`-32601` or a wrapped result.

Reconciled across (no budgets breached):

- `064.005-T` (red harness): invalid-id cases added as parametrized rows to the
  existing `-32600` request-shape set — scenario budget stays 3.
- `064.002-T` (impl): id-type guard added as inline clauses in `dispatch()` —
  ≤4-function transport budget holds.
- `064-F` DoD: JSON-RPC conformance clause extended with id-type + `id:null`.
- Plan `docs/plans/2026-08-27-mcp-stdio-server-plan.md`: request-shape paragraph,
  T1b summary, DoD conformance line, top-summary cycle-9 sentence, new
  `### Cycle-9 review remediation` subsection + verdict.
- Dual-era records `064.021-T` / `064.022-T`: modern-path ordering made
  test-bound (see adversarial-review remediation below).

### Adversarial-review P1 (remediated in-cycle)

Reviewer flagged that the pre-routing ordering was asserted but NOT test-bound on
the MODERN path (`064.005-T` is legacy-only). Fix:

- `064.021-T` scenario (c): added a parametrized modern (`_meta`-bearing)
  malformed-id row — a modern request with a malformed id, even when `_meta`
  carries an unsupported version or unknown method, must return `-32600` + `id:null`
  with NO modern wrapper. Still 3 scenarios (row in-place).
- `064.022-T`: added a "Request-shape precedence (cycle-9)" acceptance criterion —
  shared dispatch validates request-shape (incl. id-type) before `_meta` extraction /
  `-32022` / `-32602` / era routing / `-32601`. No new function; ≤2 files, <5
  functions unchanged.

Two independent reviewers (rubber-duck, Correctness Reviewer) confirmed closure:
ordering coherent (valid-id unknown-method still `-32601`; pre-initialize reject
and modern negotiation preserved), notification-vs-null-id consistent, budgets
intact, cross-surface consistent. No remaining P0/P1.

## Finding 2 — unsupported semantic-link frontmatter on `061.001-T`

`061.001-T` carried a `links:` YAML frontmatter block (unsupported per
`.github/instructions/backlogit-yaml-header-tooling.instructions.md`). Removed the
block. The two intended `informs` relationships (`061.001-T → 060.001-T`,
`061.001-T → 060.002-T`) already existed durably in `item_links` (created via a
prior `link add`; verified with `link list` + SQL). No duplicate links.

NOTE (tool behavior): `backlogit sync` re-materializes db-only links back INTO
frontmatter (`migrate db-only links ... written=2`). To keep the committed
artifact clean, the `links:` block was removed AFTER the last sync and NOT synced
again before commit. A future `sync` by Ship will round-trip the block back into
frontmatter as db-only-link materialization — this is tool-managed state outside
the commit; the relationship store itself remains correct and queryable.

## Verification

- Backlog index: `sync` OK (393 artifacts, 0 parse failures).
- `doctor`: 168 issues, ALL pre-existing `archived_from_self_ref` on unrelated
  archived items (034–040); none in 061/064 scope; no orphans/dup-IDs/cycles.
- Dependency chain 064.*: 25 edges / 26 nodes, ACYCLIC. Edited-task edges intact
  (002→019, 005→001, 021→020, 022→021).
- Shipment `055-S`: covering feature `064-F` + 26 tasks, status queued; all edited
  tasks are members.
- `item_links` 061.001-T: both `informs` links present (queryable).

## Next steps

- Ship claims shipment `055-S` (do not push/reply/resolve/merge from Stage).
- On future sync, expect `061.001-T` frontmatter links round-trip (tool-managed).
