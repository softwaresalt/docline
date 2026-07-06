---
title: "Closure — 051-F Swagger 2.0 → OpenAPI 3.x pre-conversion"
status: verified
feature: 051-F
merged_pr: 139
merge_sha: c6dd151
date: 2026-07-05
---

Added a Swagger 2.0 → OpenAPI 3.x pre-conversion stage so a single ingestion
path renders both spec generations via the existing 050-F 3.x renderer, with no
parallel 2.0 code path and no new dependency.

## Delivered

- `readers/openapi/convert.py::swagger2_to_openapi3` — a pure, cycle-safe
  transform: `swagger`→`openapi`; `definitions`→`components.schemas`;
  body/formData params→`requestBody`; non-body param `type`→`schema`; response
  `schema`→`content`; `host`/`basePath`/`schemes`→`servers`;
  `securityDefinitions`→`securitySchemes`; local `#/definitions|parameters|responses/X`
  refs rewritten to `#/components/...`.
- `read_openapi_spec` converts a 2.0 root before rendering; `_is_openapi_staged`
  now accepts 2.0 (re-opening the 050-F 3.x-only gate, correct now that 2.0 is
  pre-converted).

## Verification

- 14 converter unit tests + reader/process tests (self-contained 2.0 renders
  operation + schema docs with resolved local links; staged 2.0 ingests).
- Runtime: real `fabric-rest-api-specs` → **1,849** docs (661 operations +
  1,188 schemas), where it previously produced **0**. Written into the operator's
  `C:\Source\Docs\docline\powerbi\fabric-rest-api-specs` target, completing the
  earlier blocked deliverable.
- Gates: ruff clean, pyright (venv) 0 errors, pytest 1519 passed / 6 skipped,
  format clean.
- Adversarial + Copilot review: `051-F-swagger-to-openapi-review.md`. Copilot
  raised 3 findings on PR #139 — a non-mapping-response robustness fix (job could
  otherwise abort), plus formData/basic-auth test coverage (added), and a
  declined path-level-body edge (rare; documented). All resolved; re-review clean.

## Known limitation (carried forward)

fabric's split-file operation and schema docs are produced but not cross-linked:
`swagger.json` references `./definitions.json#/...` externally, and external/
split-file `$ref` resolution is the deferred, security-bounded follow-up
(`D9AC2CD6`). Both node sets exist; operation→schema edges arrive when that
resolver ships. A P3 (path-level body/formData param distribution) is also noted
for a future spec that needs it.
