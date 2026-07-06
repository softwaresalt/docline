---
title: "Adversarial review — 050-F OpenAPI/Swagger source-type ingestion (v1)"
type: review
date: 2026-07-05
feature: 050-F
status: reviewed
reviewers:
  - constitution
  - python
  - correctness
  - maintainability
  - security
  - architecture
  - agent-native-parity
  - scope-boundary
---

Adversarial multi-persona review of the 050-F OpenAPI/Swagger ingestion feature,
performed before opening the pull request. Personas were applied directly (no
subagent spawn surface in this environment); each lens was walked over the full
diff (`src/docline/readers/openapi/*`, `app.py`, `router.py`, `types.py`,
tests, README).

## Findings

| # | Severity | Persona | Finding | Resolution |
|---|---|---|---|---|
| 1 | P1 | Correctness | YAML specs parse response status codes as **integer** keys (`200:`); `_render_responses` stringified keys for sorting then re-indexed the dict with the string → `KeyError`. JSON specs (string keys) masked it; the parity test used JSON. | **Fixed** — normalize to `{str(key): value}` before sort/index. Regression tests added: `test_render_operation_integer_status_keys` and `test_read_yaml_spec_with_integer_status_codes`. |
| 2 | P3 | Correctness | Path-level `parameters` (shared across a path item's operations) are not merged into each operation; only operation-level parameters render. | **Accepted for v1** — documented limitation. Per-operation params are the common case; path-level merge is a candidate for the deferred-scope follow-up (stash `D9AC2CD6`). |
| 3 | P3 | Maintainability | `classify_source(content=...)` OpenAPI branch is exercised by tests but not called by production code (the process pass uses the lower-level `detect_openapi_file`). | **Accepted** — `classify_source` is the semantic classifier and the natural home for `SourceKind.OPENAPI`; `detect_openapi_file` is the I/O helper on the file-scan hot path. Both share `is_openapi_spec`. Consistent with the pre-existing test-only usage of `classify_source`. |
| 4 | P3 | Security | Content-sniff reads the whole file before the substring fast-reject; a pathologically large staged `.json` could pressure memory during the scan. | **Accepted for v1** — staged files are trusted-local (produced by `docline fetch`); consistent with existing readers. Fast-reject added to skip the (expensive) YAML parse for non-spec files. |

## Persona notes (no actionable findings)

- **Constitution**: type hints on all public interfaces; Google-style docstrings;
  typed `OpenApiError` hierarchy (no bare `except`); no new dependency
  (PyYAML + pydantic reused, Principle VI); TDD red→green followed per task.
- **Security**: `yaml.safe_load` only (no arbitrary object construction); external
  and split-file `$ref` are left unresolved, never fetched (SSRF boundary held —
  Principle III); output slugs are sanitized to `[A-Za-z0-9._-]` and every write
  passes through `safe_workspace_path` (defense in depth against path traversal).
- **Agent-native parity**: CLI `process` and MCP `process` both delegate to
  `execute_process`; parity proven by `test_cli_and_mcp_produce_identical_output`;
  manifest advertises the path.
- **Architecture**: new `readers/openapi/` subpackage has clean internal module
  boundaries (detect / errors / loader / render / reader); the `execute_process`
  integration is an isolated branch that leaves the PDF/DOCX/MD parts machinery
  untouched; no import cycles.
- **Scope boundary**: all changes are within the OpenAPI feature; pre-existing
  unrelated working-tree edits (`.gitignore`, `uv.lock`) were deliberately
  **not** staged.

## Gate results (pre-PR)

- `ruff check .` — passed
- `pyright` (venv-activated) — 0 errors on changed files
- `pytest` — 1499 passed, 6 skipped (full suite); +2 regression tests added post-review
- `ruff format --check .` — clean

## Runtime verification recommendation

Mode: **manual/API**. The feature is a pure ingestion transform with no network
or runtime service surface. `test_cli_and_mcp_produce_identical_output` already
exercises the end-to-end CLI + MCP process path against a staged spec, which is
the affected runtime surface. No browser verification applicable. No
strict-safety destructive-action classification required (no deletes, migrations,
or contract changes to existing outputs — the change is purely additive).
