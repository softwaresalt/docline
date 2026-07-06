---
title: "OpenAPI deferred-beyond-v1 residuals (D9AC2CD6) — corpus-grounded triage"
type: spike
date: 2026-07-06
time_box: "1h"
conclusion: "partial-proceed"
confidence: "high"
linked_parent_work_item: "055-F"
promoted_to: ["055-F"]
supersedes_stash: "D9AC2CD6"
tags:
  - "openapi"
  - "pagination"
  - "azure-rest-api-specs"
  - "graphtor"
  - "triage"
---

## Problem frame

Stash `D9AC2CD6` is the low-priority OpenAPI epic holding the four
"deferred-beyond-v1" items that survived after the external/split-file `$ref`
line was promoted to `053-F`. The operator asked to move these residuals
forward. Rather than stage all four speculatively, this spike grounds each item
against the **real corpus already on disk** (`C:\Source\Docs\fabric-rest-api-specs`,
1,079 JSON files including ~131 Swagger 2.0 specs) and dispositions each with
evidence. Building renderer support for extensions that **do not occur** in any
available corpus would violate Constitution VI (no speculative additions).

## Residual inventory and corpus grounding (measured 2026-07-06)

| # | Residual | Corpus signal | Disposition |
|---|---|---|---|
| 1 | API versioning / monikers | `api-version` appears in **1** file; monikers are an `azure-rest-api-specs` multi-version README-tag concept, not a per-spec field in the fabric corpus | **Defer** — no single-corpus grounding; revisit only with a multi-version azure sweep |
| 2a | **Pagination (`x-ms-pageable`)** | **52** files carry operation-level `x-ms-pageable` (`nextLinkName: continuationUri`, optional `itemName`) | **Promote → 055-F** |
| 2b | Long-running operations (LRO, `x-ms-long-running-operation`) | **0** files | **Defer** — zero grounding in the available corpus |
| 3 | Security-scheme deep render | **0** files declare `securityDefinitions`; the existing `_render_security` already renders per-operation `security` requirements (scheme + scopes) | **Defer** — nothing to deep-render here; current behavior is sufficient |
| 4 | Corpus-wide `azure-rest-api-specs` sweep | Operational/scale verification, not a renderer capability; the fabric single-repo corpus already ingests at scale (1,849 docs, 78% op→schema cross-link) | **Defer (operational)** — revisit when the operator wants a full `azure-rest-api-specs` ingest |

## Why only pagination proceeds

`x-ms-pageable` is the sole residual with real, quantified prevalence (52 files,
~40% of specs) and a clear graphtor value: it identifies **collection/list
operations** and the field to follow for the next page (`continuationUri`) plus
the field holding page items (`itemName`). Surfacing it lets a downstream graph
distinguish pageable list endpoints from single-resource endpoints and encode
traversal semantics.

The extension shape is uniform and simple:

```json
"x-ms-pageable": { "nextLinkName": "continuationUri", "itemName": "value" }
```

`nextLinkName` is always present; `itemName` is optional. The renderer change is
a small additive `_render_pagination(op)` block appended to `render_operation`
— no schema changes, no new subsystem.

The other three code residuals (versioning, LRO, security deep-render) have
**zero or near-zero** occurrences in any corpus docline can currently reach, so
building them now would be speculative. They remain documented here so they are
discoverable the moment a corpus that exercises them is ingested. Residual #4 is
an operational ingest, not a code feature, and is out of scope for a renderer
change.

## Recommended approach (055-F, v1 scope)

Add a **Pagination** section to `render_operation` in
`src/docline/readers/openapi/render.py`:

- Read `op.get("x-ms-pageable")`; when present and a mapping, emit:

  ```markdown
  ## Pagination

  Pageable: yes
  - Next-page field: `continuationUri`
  - Items field: `value`
  ```

- Omit `Items field` when `itemName` is absent. Emit nothing when the extension
  is missing (section-omission parity with the other blocks).
- Preserve CLI/MCP parity (both render via `render_operation`).
- TDD: unit tests for present/absent/`itemName`-missing cases; a fabric-corpus
  assertion that at least one known pageable operation renders the section.

Out of scope: LRO, versioning/monikers, security deep-render, azure-wide sweep
(all deferred above with rationale).

## Outcome

- `x-ms-pageable` pagination rendering promoted to feature **055-F** (one task).
- Residuals #1, #2b, #3, #4 deferred with documented, evidence-backed rationale.
- Stash `D9AC2CD6` fully dispositioned and archived; this doc is the durable
  record of the deferred items.
