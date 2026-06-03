---
type: ship-session-checkpoint
session_id: 010-S-ship-session-2
shipment: 010-S
feature: 010-F
date: 2026-06-02
branch: feat/docline-graphtor-alignment
head_sha: f013481
status: in-progress
agent: ship
---

# Ship session 2 — 010-S docline-graphtor alignment

## Session start state

* Branch: `feat/docline-graphtor-alignment` @ 17282fb (origin synced)
* Shipment 010-S claimed (active)
* 1/39 tasks done from session-1 (`010.001-T`)
* PA-1 **approved** by operator: BaseFrontmatter v1 schema extension
* PA-1 approval scope: "no prior consumers of docline; zero issues with code refactoring"
  applies to schema/contract surface refactors only. PA-2 (POSIX path migration)
  remains in force.

## Strict-safety action record

### PA-1 — BaseFrontmatter v1 extension

* **ProposedAction**: Add `description`, `content_sha256`, `source_path`,
  `chunk_strategy="h1-h2-h3"`, `schema_version="1.0"`, `docline: dict | None = None`
  to `src/docline/schema/models.py::BaseFrontmatter`; reconcile subclasses.
* **ActionRisk**: moderate (schema/contract change with no prior consumers)
* **Approval**: operator-approved on session-2 start
* **ActionResult**: applied (see commits below)

## Tasks attempted this session

| # | Task | Status | Commit | Notes |
|---|------|--------|--------|-------|
---
type: ship-session-checkpoint
session_id: 010-S-ship-session-2
shipment: 010-S
feature: 010-F
date: 2026-06-02
branch: feat/docline-graphtor-alignment
head_sha: 0a9d56b
status: in-progress
agent: ship
---

# Ship session 2 — 010-S docline-graphtor alignment

## Session start state

* Branch: `feat/docline-graphtor-alignment` @ 17282fb (origin synced)
* Shipment 010-S claimed (active)
* 1/39 tasks done from session-1 (`010.001-T`)
* PA-1 **approved** by operator: BaseFrontmatter v1 schema extension
* PA-1 approval scope: "no prior consumers of docline; zero issues with code refactoring"
  applies to schema/contract surface refactors only. PA-2 (POSIX path migration)  remains in force.

## Strict-safety action record

### PA-1 — BaseFrontmatter v1 extension

* **ProposedAction**: Add `description`, `content_sha256`, `source_path`,
  `chunk_strategy="h1-h2-h3"`, `schema_version="1.0"`, `docline: dict | None = None`
  to `src/docline/schema/models.py::BaseFrontmatter`; reconcile subclasses.
* **ActionRisk**: moderate (schema/contract change with no prior consumers)
* **Approval**: operator-approved on session-2 start
* **ActionResult**: applied (see commits below)

### PA-2 — POSIX `source_path` migration

* **ProposedAction**: Route every emitted `source_path` value through
  `posixify_path()` so all docline-emitted frontmatter uses forward-slash POSIX
  paths regardless of the OS that produced the file. Touches
  `process/assemble.py`, `process/output_contract.py`, `fetch/staging.py`, and
  every reader (`readers/html.py`, `readers/pdf.py`, `readers/docx.py`,
  `readers/vtt.py`, `readers/adr.py`, `readers/wiki.py`).
* **ActionRisk**: high (storage-format migration of the public frontmatter
  contract; PA-1's "no prior consumers" carve-out does NOT pre-approve this).
* **Rollback**: revert the routing commit; pure `posixify_path` helper can
  remain unused. Existing emitted manifests would need re-emission to pick up
  the POSIX representation (downstream re-ingest required for
  `schema_version: "1.0"` consumers).
* **Approval**: **pending** — awaiting operator decision.
* **ActionResult**: planned.

## Tasks attempted this session

| # | Task | Status | Commit | Notes |
|---|------|--------|--------|-------|
| 1 | `010.002-T` extend BaseFrontmatter v1 fields | done | `d18d4d9` | PA-1 applied; turned 21/21 v1 contract tests green; no subclass changes required |
| 2 | `010.003-T` reconcile library frontmatter variants | done | `13f1ab3` | docline-only fields moved under `docline:` namespace; 14 new red→green tests; pyright clean |
| 3 | `010.004-T` content_sha256 hashing + assemble wiring | done | `d87fc56` | new `docline.process.hashing` module; SHA-256 helper; assemble pipeline populates `content_sha256`; red-first tests + frontmatter_payload updates; quality gates green on focused paths |
| 4 | `010.005-T` JSON Schema export CLI + regression test | done | `f967244` | `docline export-schema` CLI subcommand; `DoclineMcpServer.export_schema()` MCP method; `docline.schema.export` module with deterministic JSON; regression tests pin shape and idempotency |
| 5 | `010.006-T` document schema regeneration workflow | done | `94e18bf` | new `docs/design-docs/schema-export-workflow.md` covering CLI/MCP/Python surfaces, graphtor-docs consumer contract, and SemVer policy; linked from `README.md` |
| 6 | `010.007-T` red-first posixify_path tests | done | `c8a59b3` | `tests/test_posixify_path.py` parameterized over POSIX, Windows, mixed, drive-letter, UNC, trailing-slash strings, plus `os.PathLike` (`PurePosixPath`, `PureWindowsPath`) and idempotency; failed red on ImportError before 010.008-T |
| 7 | `010.008-T` implement posixify_path helper | done | `9d80ff1` | added `posixify_path()` to `src/docline/paths.py`; `os.fspath` + backslash→forward-slash; 26/26 tests green; pyright + ruff clean on focused paths |

## Circuit breaker state

* Session tasks attempted: 8 (1 carry-over from session-1 + 7 done this session)
* Headroom: 12 tasks before 20-task breaker
* Same-error retries: 0
* Per-task fix attempts: 0
* Session stalls: 0

## Pre-existing issues stashed (not in scope this session)

* Stash `CE758832` — "Investigate pytest tmp PermissionError noise on Windows
  (176+ entries during pytest runs)" — pre-existing Windows-only test
  infrastructure noise unrelated to 010-S; filtered during quality-gate output
  parsing.

## Halt reason

Reached PA-2 gate at task `010.009-T` (F2.T3: route all `source_path` emissions
through `posixify_path`). PA-2 is a **high-risk storage-format migration** of
the public frontmatter contract. The PA-1 approval scope ("no prior consumers")
does **not** extend to PA-2 because PA-2 changes the emitted output shape, not
just an internal refactor. Awaiting explicit operator approval before claiming
`010.009-T`.

