---
shipment: 051-S
title: "Closure record — OpenAPI/Swagger source-type ingestion design spike (049-F)"
status: verified
merge_sha: 8059eba
merged_pr: 134
---

## Scope delivered

Feature `049-F` is a time-boxed design spike (stash `F8E142A1`) for a first-class
OpenAPI/Swagger ingestion path. Deliverable: a decision artifact, no reader code.

| Item | Delivered |
|---|---|
| `049-F` | `docs/decisions/2026-07-04-openapi-swagger-source-type-spike.md` — problem frame grounded in the current reader architecture (`router.classify_source`, extension-driven dispatch, `BaseFrontmatter`/`BaseDocument` output contract, two-phase fetch/process, `.json` process-skip), the key finding that OpenAPI is a *structured-render* not a *layout-extract* source, recommended design defaults, three options with rejections, a T1–T6 build decomposition (each ≤2h, single-domain, with a verifiable milestone), risks, and a **PROCEED** recommendation. |

## Verification

- Feasibility confirmed against `main`: no new dependency needed (`PyYAML>=6,<7`
  and `pydantic>=2,<3` already present); the render model fits the existing
  output contract; content-sniff detection avoids the `.json` process-skip
  collision.
- Adversarial self-review (constitution, architecture, scope, agent-native
  parity, security) passed. The security lens added an explicit note that the
  deferred external-`$ref` resolver is a path-traversal/SSRF boundary
  (Principle III containment) so the follow-up task cannot silently reintroduce
  the risk.
- Stash `F8E142A1` annotated with the spike link and PROCEED verdict; it stays
  active and harvestable into a build feature once the operator confirms the
  per-operation granularity and v1 scope boundary.

## Copilot review

Clean — the review covered the current HEAD with zero unresolved threads.

## Follow-up (not this shipment)

The build feature (T1–T6: detection, loader + local `$ref`, operation renderer,
schema renderer + edges, frontmatter/assembly, CLI/MCP parity) runs as its own
dedicated shipment after the operator green-lights per-operation granularity.
Deferred beyond v1: external/split `$ref` resolution, Swagger 2.0, API
versioning/monikers, corpus-wide `azure-rest-api-specs` sweep.
