---
title: "Adversarial review — 051-F Swagger 2.0 → OpenAPI 3.x pre-conversion"
type: review
date: 2026-07-05
feature: 051-F
status: reviewed
reviewers:
  - correctness
  - python
  - constitution
  - security
  - architecture
  - maintainability
  - scope-boundary
---

Adversarial multi-persona review of 051-F before the PR. The feature adds
`readers/openapi/convert.py::swagger2_to_openapi3` (a pure Swagger 2.0 → OpenAPI
3.0.3 transform) and wires it into `read_openapi_spec`, re-opening the process
gate (`_is_openapi_staged`) to accept 2.0 (which 050-F had restricted to 3.x).

## Findings

| # | Severity | Persona | Finding | Resolution |
|---|---|---|---|---|
| 1 | P3 | Correctness | 2.0 response `headers` are carried through with their 2.0 shape (`type` at top level) rather than wrapped in a 3.x `schema`. | **Accepted** — headers are not rendered by the 050-F renderer, so the shape is inert for docline output. Full header conversion belongs with a stricter 3.x-validity pass if ever needed. |
| 2 | P3 | Architecture | External/split-file ref *fragments* (e.g. `./definitions.json#/definitions/X`) are left as `#/definitions/...`, not rewritten to `#/components/schemas/...`. | **Intentional** — external refs are not resolved in v1 (security boundary, stash `D9AC2CD6`); the fragment mapping is that follow-up's responsibility. Local refs ARE rewritten so single-file 2.0 specs cross-link. |
| 3 | P3 | Maintainability | `import copy` is used only for the `info` deep-copy; `_rewrite_refs` already deep-copies. | **Accepted** — explicit and correct; consolidating is cosmetic. |

## Persona notes (no actionable findings)

- **Correctness**: the transform walks the literal JSON tree and never follows
  `$ref` values, so it is inherently cycle-safe (Swagger circular schema refs
  cannot cause infinite recursion). The input mapping is not mutated. Body params
  → `requestBody`; non-body param `type/format/...` → `schema`; response `schema`
  → `content`; missing response descriptions default to `""` (3.x requires one).
- **Security**: pure in-memory transform; no file or network access; external
  refs are preserved unresolved (no SSRF, no traversal).
- **Python/Constitution**: type hints throughout; no new dependency (Principle
  VI); Google-style docstrings; TDD red→green per task.
- **Scope boundary**: the `_is_openapi_staged` gate change deliberately reverses
  the 050-F "3.x-only" restriction — now correct because 2.0 is pre-converted
  before rendering. Change set limited to the OpenAPI subpackage + the app.py
  gate + tests.

## Verification

- Unit: 11 converter tests (`test_convert.py`) covering version, definitions →
  components.schemas, local ref rewrite, servers, param wrapping, body →
  requestBody, response → content, securitySchemes, external-ref preservation,
  definitions-only files.
- Reader/process: a self-contained 2.0 spec renders operation + schema docs with
  resolved local links; `execute_process` ingests a staged 2.0 spec.
- Runtime: re-ingested `C:\Source\Docs\fabric-rest-api-specs` (previously **0**
  output) → **1,849** docs (661 operations + 1,188 schemas), completing the
  earlier operator deliverable into `...\powerbi\fabric-rest-api-specs`.
- Gates: ruff clean, pyright (venv) 0 errors, pytest 1519 passed / 6 skipped,
  format clean.

## Known limitation (carried forward, not a defect)

Operation docs and schema docs from fabric's split files are not cross-linked:
`swagger.json` references `./definitions.json#/...` externally, and external ref
resolution is the deferred `D9AC2CD6` security-boundary follow-up. Both node sets
are produced; the operation→schema edges arrive when that resolver ships.

## Runtime verification recommendation

Mode: **manual** — already exercised end-to-end on the real fabric corpus. No
API/browser surface. No strict-safety destructive-action classification required
(additive ingestion path; no deletes, migrations, or contract changes).
