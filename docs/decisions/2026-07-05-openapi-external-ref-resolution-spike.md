---
type: spike
date: 2026-07-05
time_box: "1h"
conclusion: "proceed"
confidence: "high"
linked_parent_work_item: "053-F"
promoted_to: ["053-F"]
supersedes_stash: "D9AC2CD6 (external-ref line)"
tags:
  - "openapi"
  - "ref-resolution"
  - "cross-link"
  - "graphtor"
  - "security"
---

## Problem frame

The 050-F/051-F OpenAPI ingestion renders one document per operation and per
schema, and emits an `operation → schema` graph edge only when the reference is
**local** (`#/components/schemas/X`): the renderer turns it into a relative
Markdown link and `resolve_cross_doc_links` harvests it as a typed edge. But the
Microsoft `fabric-rest-api-specs` corpus **splits every service across files** —
a `swagger.json` operation references its schema externally
(`"$ref": "./definitions.json#/definitions/TenantSettings"`, or
`../common/definitions.json#/definitions/ErrorResponse`). The renderer only
links `#/components/schemas/` refs, so every external ref renders as an empty
cell and produces no edge. This spike quantifies the gap against the real corpus
and scopes the fix.

## Measurements (real corpus, 2026-07-05 ingest)

Source — 131 Swagger 2.0 spec files, 4,385 total `$ref`:

| Ref class | Count | Share | Resolves today? |
|---|---|---|---|
| local (`#/…`) | 1,027 | 23% | yes |
| **external structural** (`file.json#/definitions|parameters|responses/…`) | **2,450** | **56%** | **no** |
| external example (`…/examples/*.json`, x-ms-examples) | 908 | 21% | n/a (never rendered) |

External structural split by layer:

| Layer | Files | External structural refs | Becomes |
|---|---|---|---|
| paths-bearing (`swagger.json`) | 54 | **2,033** | operation → schema edges |
| definitions-only (`definitions.json`) | 77 | 417 | cross-file schema → schema edges |

External ref *shapes* (security surface): 1,636 same-dir (`./`), 1,722
parent-dir (`../common/…`), **0 absolute paths, 0 URLs**, 922 distinct target
files. → The resolver needs **file-path containment**, not URL fetching; the
URL-deny gate is defense-in-depth for arbitrary corpora.

Produced output (1,849 docs):

| Doc type | Count | With ≥1 cross-link today |
|---|---|---|
| operations | 661 | **0 (0%)** — 0 operation→schema links |
| schemas | 1,188 | 710 (60%) — 973 intra-file schema→schema links |

The operation layer and schema layer are two disconnected islands.

## Value proposition

Resolving the 2,450 external structural refs:

* Referential coverage **23% → 79%** (the residual 21% are example refs,
  intentionally unresolved).
* Structural edges **973 → ~3,423 (≈3.5×)**.
* Operation docs with schema links **0% → ~100%** (~2,033 operation→schema
  edges + ~417 cross-file schema→schema edges).

For graphtor's unified-DB test this is the difference between a bag of 1,849
nodes and an actual API knowledge graph: only with these edges can graphtor
answer "which operations return `TenantSettings`?" or "what is the request
contract for `POST /domains/assign`?", and only then can RAG hop from an
operation doc to its schema shape.

## Codebase impact

| Area | Change | Size |
|---|---|---|
| `readers/openapi/loader.py` | Load a relative target file (relative to the referring file), path-contained; deny URL refs; cross-file cycle guard; apply 051-F fragment mapping to 2.0 targets | moderate |
| `docline/paths.py` (reuse) | `safe_workspace_path` / `PathContainmentError` for `../` containment; URL-deny gate | small, NON-NEGOTIABLE |
| `readers/openapi/reader.py` | Corpus/bundle view: map `(target file, pointer)` → the schema doc `relative_path` that target produces, so external refs become correct cross-file links | **main new architecture** |
| `readers/openapi/render.py` | `_schema_type_summary` links resolved external refs, not just `#/components/schemas/` | small |

No output-contract change: resolved external refs become ordinary relative
Markdown links harvested by the existing `resolve_cross_doc_links`.

## Security boundary (elevated risk)

* **File containment (NON-NEGOTIABLE):** every file ref resolves through
  `safe_workspace_path`; `../`, absolute, and symlink escapes above the
  workspace root are rejected (`PathContainmentError`). Principle III/IV.
* **URL refs denied:** any `http(s)`-valued `$ref` is refused, never fetched
  (SSRF). The fabric corpus has zero URL refs; the gate protects arbitrary
  corpora.
* Express the resolver as a `ProposedAction` with `ActionRisk: high` when
  strict-safety is active.

## Recommendation

**PROCEED** as scoped feature **053-F**. v1 = local relative-file refs only,
within the workspace root, URL-deny, examples-skip, cross-file cycle guard.
Highest-leverage OpenAPI follow-up: converts ~56% of currently-dead references
into exactly the operation↔schema edges the graph is missing, is tractable (no
URL fetching needed for the target corpus, containment primitive already
exists), and is the one security-boundary item — hence operator green-light on
scope before build.

## Decomposition (feature 053-F)

* **T1** — external file-ref resolver + security containment (loader/paths):
  relative-file load, `safe_workspace_path` containment, URL-deny, cross-file
  cycle guard, 2.0 fragment mapping. Unit tests incl. traversal + URL rejection.
* **T2** — cross-file schema doc-path mapping + renderer link emission
  (reader/render): a two-file fixture cross-links operation → external schema.
* **T3** — directory/process integration + fabric runtime verification: re-ingest
  `fabric-rest-api-specs`, assert operation cross-link coverage 0% → ~100% and
  report the edge delta.
