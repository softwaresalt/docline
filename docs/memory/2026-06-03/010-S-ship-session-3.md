---
type: ship-session-checkpoint
session_id: 010-S-ship-session-3
shipment: 010-S
feature: 010-F
date: 2026-06-03
branch: feat/docline-graphtor-alignment
head_sha: a04b877
status: complete
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

## Final summary — 010-S complete (39/39)

* **Session-3 contribution**: 19 tasks (010.021-T → 010.039-T) plus the
  010.034/010.035 recovery sequence.
* **Cumulative 010-S contribution**: 39 / 39 tasks archived.
  * Session 1: 1 task (010.001-T groundwork).
  * Session 2: 19 tasks (010.002-T → 010.020-T).
  * Session 3: 19 tasks (010.021-T → 010.039-T) + recovery.
* **PA-1 (BaseFrontmatter v1 extension)**: `ActionResult: applied` @ `d18d4d9`.
* **PA-2 (POSIX path migration)**: `ActionResult: applied` @ `fc9e2ca`.
* **Recovery**: 010.034-T archive recovered + 010.035-T impl committed
  retroactively after lifecycle slip; see commits `d878efa`, `f0dd767`,
  `05e7483`.

### F-block status (all COMPLETE)

| Block | Scope | Status |
| --- | --- | --- |
| F1 | Frontmatter v1 field set + docline namespace | COMPLETE |
| F2 | POSIX `source_path` normalization | COMPLETE |
| F3 | Heading-hierarchy validator + chunk-boundary rules | COMPLETE |
| F4 | DOCX reader + style mapping | COMPLETE |
| F5 | PDF heuristic + docling opt-in layout engine | COMPLETE |
| F6 | Content SHA-256 + manifest plumbing | COMPLETE |
| F7 | Chunk anchor emission (opt-in `emit_chunk_anchors`) | COMPLETE |
| F8 | Graphtor ingestion contract tests + opt-in real-binary suite | COMPLETE |

### P2 advisories honored in flight

* `defusedxml` adoption for DOCX parsing (010.015-T).
* JSON Schema `$schema` + `$id` declarations on emitted schemas (010.005-T).
* SSRF defense-in-depth on URL fetch path (010.030-T).

### Pre-existing issues (out of scope, not blocking)

* Stash `CE758832` — Windows pytest tmp `PermissionError` noise; mitigated
  in-session via `--basetemp=logs/pytest-tmp`. Tracked for separate cleanup.

### Final artifacts (invocation 7)

| Task | Commit | Description |
| --- | --- | --- |
| 010.037-T | `14419c3` | Red-first graphtor ingestion contract test suite (`graphtor_integration` marker) |
| 010.038-T | `51d7654` | Register `graphtor_integration` marker in `pyproject.toml` |
| 010.039-T | `82a7669` | Opt-in real-binary round-trip suite + `tests/fixtures/real_binary/README.md` |

Archive commits: `a2047e5`, `7b69d07`, `a04b877`.

### Next phase

Execution complete. The next phase is a **separate Ship session**:

1. `review` skill → identify P0/P1 findings on the feature branch.
2. `fix-ci` skill → remediate any failures.
3. `pr-lifecycle` skill → open PR.
4. Operator merge approval (P-014 gate).
5. `runtime-verification` skill → validator manifest evidence.
6. `operational-closure` skill → releasability evidence.
7. Post-merge closure protocol (knowledge graduation, shipment close).

**Recommended next session action**: invoke the `review` skill against
`feat/docline-graphtor-alignment` to surface findings before opening the PR.

