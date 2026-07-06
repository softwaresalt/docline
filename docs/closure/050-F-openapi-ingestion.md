---
title: "Closure — 050-F OpenAPI/Swagger source-type ingestion (v1)"
status: verified
feature: 050-F
merged_pr: 136
merge_sha: 27df3c3
date: 2026-07-05
---

OpenAPI 3.x / Swagger source-type ingestion (v1) shipped. Harvested from spike
`049-F` (verdict PROCEED); operator green-lit per-operation granularity and the
v1 scope boundary on 2026-07-05.

## Delivered

A structured-render ingestion path under `src/docline/readers/openapi/` that
traverses an OpenAPI 3.x object model and emits one Markdown `BaseDocument` per
operation (`doc_type: openapi_operation`) and per named component schema
(`doc_type: openapi_schema`), with `operation → schema` `$ref`s emitted as
relative Markdown links that the existing cross-doc harvester records as typed
graph edges. Wired into `execute_process` as an isolated branch, so CLI
`docline process` and the MCP `process` tool produce identical output.

Tasks T1–T6 (all done/archived): detection + `SourceKind.OPENAPI`; JSON/YAML
loader + cycle-guarded local `$ref` resolver; operation renderer; schema renderer
+ edges; frontmatter/BaseDocument assembly; CLI/MCP parity + manifest + README.

No new dependency (PyYAML + pydantic reused).

## Verification

- Quality gates: `ruff check .` clean, `pyright` (venv-activated) 0 errors on
  changed files, `pytest` 1504 passed / 6 skipped, `ruff format --check .` clean.
- Adversarial multi-persona review before PR (see
  `050-F-openapi-ingestion-review.md`): 1 P1 (YAML integer status-code `KeyError`)
  found and fixed with regression tests.
- Copilot review (PR #136): 3 findings — README `local-dir` usage, Swagger 2.0
  scope-gate correctness, and a DRY duplication — all addressed, replied, and
  resolved. A re-review on the fixed HEAD returned no new findings.
- Runtime surface (CLI + MCP process path) covered by
  `test_cli_and_mcp_produce_identical_output`.

## Scope boundary and follow-ups

v1 is OpenAPI 3.x, single-spec, per-operation, local `#/components/*` `$ref` only.
Swagger 2.0 is detected but deliberately not routed into the 3.x renderer.
Deferred-beyond-v1 work is captured in stash `D9AC2CD6` (external/split `$ref`
with its SSRF/path-containment security boundary, Swagger 2.0 rendering,
versioning/monikers, pagination/LRO, security-scheme deep render, corpus-wide
`azure-rest-api-specs` sweep) plus a documented P3 limitation: path-level shared
`parameters` are not yet merged into each operation.
