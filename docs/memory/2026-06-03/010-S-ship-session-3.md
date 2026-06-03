---
type: ship-session-checkpoint
session_id: 010-S-ship-session-3
shipment: 010-S
feature: 010-F
date: 2026-06-03
branch: feat/docline-graphtor-alignment
head_sha: 69cad44
status: in-progress
agent: ship
---

# Ship session 3 — 010-S docline-graphtor alignment

## Session start state

* Branch: `feat/docline-graphtor-alignment` @ `2bfafd1` (origin synced)
* Shipment 010-S claimed (active)
* 20/39 tasks archived from prior sessions (010.001 → 010.020)
* PA-1, PA-2: applied
* Auto-approve scope ACTIVE — operator pre-authorized remaining 19 tasks
* Session-3 circuit breaker: 0/20

## Tasks attempted this session (invocation 1)

| # | Task | Status | Commit | Notes |
|---|------|--------|--------|-------|
| 1 | `010.021-T` F5.T2 red-first PDF font-size heuristic tests | done | `3fc9898` | 8 tests, 3 red assertions for F5.T3 to close, 5 invariants already hold; `--basetemp=logs/pytest-tmp` works around pre-existing Windows tmp PermissionError (stash CE758832) |
| 2 | `010.022-T` F5.T3 PDF font-size histogram heuristic impl | done | `ab229c5` | order-preserving Tf/Tj/TJ/<hex>Tj scanner; top `min(N-1,3)` distinct sizes mapped to H1/H2/H3; smallest size always body; 28/28 PDF tests + 195/195 readers+process+build regression green |
| 3 | `010.023-T` F5.T4 red-first PDF docling opt-in tests | done | `ec81b61` | 6 red assertions for F5.T5: layout_engine kwarg, default-equals-heuristic, docling-unavailable → DependencyUnavailableError, unknown-engine → clear error; pyright silenced with `# type: ignore[call-arg]` until impl lands |

## Cumulative progress

* **23 / 39 tasks done** (sessions 1 + 2 + 3-invocation-1)
* F1 (frontmatter) ✅, F2 (POSIX paths) ✅, F3 (heading validator) ✅, F4 (DOCX) ✅
* F5 (PDF): T1, T2, T3, T4 done — **F5.T5 (010.024-T) is next**
* F6, F7, F8 not started

## Circuit breaker state

* Session tasks attempted: 3
* Headroom: 17 tasks before 20-task breaker
* Same-error retries: 0
* Per-task fix attempts: 1 (010.022-T heading-band edge case; fixed first try)
* Session stalls: 0

## Pre-existing issues stashed (not in scope this session)

* Stash `CE758832` — Windows tmp PermissionError noise; per-test workaround:
  `--basetemp=logs/pytest-tmp` (added to all pytest invocations this session).

## Scope drift to flag at shipment close

* Commit `3fc9898` uses scope `test(readers): ...` — `readers` is **not** in
  the project's allowed scope list (`core, cli, mcp, fetch, process, schema,
  docs`). Already pushed; subsequent commits this session use the correct
  `process` scope. Flag for shipment close-out / commit-message linting in
  a follow-up cleanup.

## Halt reason

Context budget — 3 tasks landed (matches the handoff "1-3 tasks per
invocation" realistic target). Clean stop at the F5.T4 → F5.T5 boundary.
F5.T5 (010.024-T) is a substantive impl task (add `layout_engine` kwarg,
gate docling availability, dispatch to docling reader, propagate to
read_pdf_pages, threading through process pipeline if needed). Better as
the first task of the next invocation with fresh context.

## Next invocation entry

1. Pick up `010.024-T` (F5.T5: implement docling opt-in PDF layout engine).
2. The 6 red tests in `tests/readers/test_pdf_docling_optin.py` define the
   target contract; remove the `# type: ignore[call-arg]` markers as the
   impl lands.
3. Continue F5.T6+ if budget permits.

## Session-3 invocations log

* Invocation 1 (this checkpoint): 3 tasks, +3 cumulative → 23/39.

