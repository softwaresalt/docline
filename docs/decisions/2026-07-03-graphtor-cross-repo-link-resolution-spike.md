---
title: "Would docline multi-repo orchestration improve graphtor-docs ingestion?"
type: spike
date: 2026-07-03
time_box: "2h"
conclusion: "pivot"
confidence: "high"
linked_parent_work_item: null
promoted_to: ["queue"]
updated: 2026-07-04
tags:
  - "graphtor"
  - "cross-repo-links"
  - "corpus-orchestration"
---

## Goal

Does graphtor-docs resolve docline's cross-repo (`cross_product`) link edges to
concrete nodes when the union of multiple repos is ingested into one CozoDB — or
does it leave them dangling? Therefore: would docline multi-repo orchestration
(stash `4A650FFD`) lead to better graphtor-docs ingestion outcomes, and where
should cross-repo link resolution live?

## Success Criteria

A source-grounded determination of (a) how graphtor consumes docline link
metadata, (b) whether cross-product absolute paths resolve to nodes across the
ingested union, and (c) a proceed/pivot/defer/abandon recommendation on
`4A650FFD` with a concrete alternative if it pivots.

## Scope Constraints

Read-only investigation of the `graphtor` (`C:\Source\GitHub\graphtor`) and
`docline` source trees. No changes to either tool. No full ingestion run.

## Investigation Approach

1. Confirm how docline emits cross-repo links (`cross_doc_links.py`).
2. Determine whether graphtor consumes docline's `docline.cross_doc_links`
   frontmatter or re-parses body links.
3. Trace graphtor's edge storage (`db/edges.rs`) and link parsing
   (`parse/links.rs`) — are edge targets resolved to nodes?
4. Trace graphtor's traversal (`db/traverse.rs`) and schema (`db/schema.rs`,
   `db/chunks.rs`) — how are edge targets resolved at query time, and across
   what scope?
5. Confirm the source_id model and search for any cross-product / URL-base
   handling.

## Findings

### What Was Discovered

**1. docline already preserves cross-repo links (not the gap).**
`src/docline/process/cross_doc_links.py` classifies links into three buckets and
emits cross-product links (absolute `/fabric/admin`, `/dax/...`) verbatim with
`cross_product: true` in the `docline.cross_doc_links` frontmatter, explicitly
"so graphtor can model them as external graph edges." The raw cross-repo linkage
survives per-repo ingestion.

**2. graphtor IGNORES docline's link frontmatter.**
`src/parse/frontmatter.rs` parses only `title` / `description`; unknown keys
(including the entire `docline.*` namespace) are ignored (per the 2026-06-02
gap-analysis, confirmed by the current parser). graphtor instead re-derives
edges from inline body links `[text](url)` in `src/parse/links.rs`, which stores
the **raw** `target_path` from the URL ("callers may normalise it later").

**3. graphtor edges are unresolved string references.**
`src/db/edges.rs` + `src/db/schema.rs`: the `doc_edges` relation is
`{ src_chunk_id, target_path => link_text, anchor }`. `upsert_edge` stores
`reference.target_path` verbatim as a **string**. There is no ingest-time
resolution of `target_path` to a concrete target `chunk_id` / node.

**4. Traversal is source-scoped and resolves by exact string equality.**
`src/db/traverse.rs::find_related_chunks` (the agent-lookup BFS) resolves each
edge's `target_path` via `chunks_at_path(source_id, target_path)`, which matches
`doc_chunks` where `source_id = seed.source_id AND path = target_path`. It is
**deliberately source-scoped**: "links are resolved within the same `source_id`
as the seed chunk ... prevents identical `source_path` values from different
sources from being incorrectly cross-linked." `doc_chunks.path` is the
"relative document path within the source" (`src/db/chunks.rs`).

**5. One source_id per configured source; no cross-product handling.**
`src/config/source.rs` models each source as one local directory with its own
`id` (= `source_id`). A grep across `src/**/*.rs` found **no** cross-product,
absolute-Learn-URL, URL-base, or moniker resolution anywhere — the only
"absolute path" logic concerns local filesystem globbing.

### Consequence for the operator's workflow

Running one `docline ingest local-dir` per repo (powerbi, fabric, dax, …) →
each repo becomes a **separate `source_id`** in the shared `.db`. A cross-product
edge `/fabric/admin` from a powerbi chunk is:

* stored in `doc_edges` as a raw string target, but
* **never resolved to the fabric node** — traversal only looks within
  `source_id = powerbi` (wrong source) and matches `path` by exact string
  (`/fabric/admin` ≠ any powerbi relative path).

So today the graph is **fragmented at repo/source boundaries** for
agent-traversal purposes, regardless of whether fabric-docs is in the same `.db`.

### Why docline multi-repo orchestration (4A650FFD) alone would NOT fix it

Even if docline resolved `/fabric/admin` → the exact fabric doc during a unified
pass, graphtor still would not connect it, because the blockers are in
graphtor's model:

* traversal is hard-scoped to a single `source_id`, and
* edge resolution is exact-string-match against a chunk's source-relative `path`.

The resolved edge would point across a source boundary that traversal refuses to
cross. **The cross-repo connectivity constraint lives in graphtor-docs, not in
docline.**

### What WOULD achieve cross-repo agent lookup

**Option A — combined single-source ingestion + cross-product normalization
(smallest change, mostly feasible today).** Point ONE graphtor `LocalSource` at
a parent directory containing all repos' docline output (`powerbi/`, `fabric/`,
`dax/` as subdirs, recursive `**/*.md`). All chunks then share one `source_id`,
so intra-source traversal spans every repo. The remaining gap: cross-product
absolute links must be normalized to combined-corpus-relative `path`s (e.g.
`/fabric/admin` → `fabric/admin/….md`) so graphtor's exact-string edge
resolution connects them. That normalization is a **small, targeted** docline
contribution (rewrite `cross_product` link targets given the combined layout) —
far narrower than the full `4A650FFD` "multi-repo orchestration."

**Option B — graphtor-docs enhancement.** Teach graphtor traversal to cross
source boundaries for typed cross-product edges, and resolve absolute Learn URL
paths to nodes via per-source URL-base mappings. Places resolution where the
global node union already lives; more invasive to graphtor.

### What Was Tried and Failed

No dead ends — the source trace was linear and conclusive. A full empirical
ingestion (build the `.db`, inspect edges) was intentionally skipped: the source
model already determines the outcome deterministically (source-scoped traversal
+ string-equality resolution), so a run would only re-confirm it.

### Remaining Unknowns

* Whether powerbi/fabric relative `path` conventions align cleanly enough that a
  cross-product normalizer can deterministically map `/fabric/...` → the combined
  corpus path without per-repo URL-base config (docline does not read
  openpublishing/URL-base config today).
* graphtor's HNSW **vector** search (`db/search.rs`) is not source-scoped like
  graph traversal; semantic (non-graph) cross-repo retrieval may already work.
  Not investigated in depth — relevant if the agent use case is
  embedding-similarity rather than link-graph traversal.

## Recommendation

**Conclusion**: pivot
**Confidence**: high

Do **not** build `4A650FFD` (docline multi-repo orchestration) as specified — on
its own it would not improve graphtor-docs graph connectivity, because
graphtor's traversal is source-scoped and its edges resolve by exact
string-match within a source. The leverage is elsewhere:

1. **First, prototype Option A**: ingest the sibling repos under a single
   graphtor source and add a minimal docline cross-product-link normalizer
   (rewrite `cross_product` targets to combined-corpus-relative paths). Verify a
   powerbi→fabric traversal actually connects.
2. If Option A's normalization proves insufficient (path conventions diverge),
   escalate to **Option B** graphtor-side resolution (URL-base mappings +
   cross-source edge traversal).

Re-scope the `4A650FFD` stash entry from "multi-repo orchestration in docline"
to "cross-product link normalization for combined-source graphtor ingestion,"
and note that the connectivity fix is a coordinated docline + graphtor concern.

## Update — 2026-07-04: canonical-URL refinement and chosen direction

Follow-up investigation (operator: "is a docline contribution complementary to a
graphtor-side fix?") pinned down the exact key mismatch and the enabling work.

### The key mismatch (why cross-product edges structurally can't resolve)

Two verifications closed the loop:

* **graphtor's `doc_chunks.path` is docline's `source_path` frontmatter** — a
  repo-relative **file** path. Confirmed by `src/pipeline/mod.rs`'s fail-closed
  "`{source_id, source_path}` duplicate detection ... files ... declare the same
  `source_path` in their docline frontmatter."
* **docline emits a URL only for web-fetched docs** (`WebFrontmatter.source_url`
  / `final_url`, http(s)-only; `src/docline/schema/library.py`). **Local-dir
  ingestion emits no URL** — only the file path.

So an edge target (`doc_edges.target_path`, a raw link URL like
`/fabric/admin/foo`) is matched against a node key (`doc_chunks.path`, a file
path like `admin/foo.md`). A Learn **URL path** can never equal a **file path**,
so cross-product links cannot resolve — and **graphtor cannot fix this alone**,
because it only ever sees docline's standardized markdown, never the source
repo's `.openpublishing.publish.config.json` / `docfx.json` that defines the
file→URL mapping. **Only docline is positioned to compute the canonical URL.**

### Chosen direction (operator, 2026-07-04): Option B + canonical-URL emission

The cross-repo fix is a **coordinated, two-part** change; multi-repo
orchestration (`4A650FFD` as originally scoped) is **not** part of it:

1. **graphtor (Option B — chosen):** add cross-source cross-product link
   resolution to graph traversal, keyed on a globally-unique `canonical_url`
   index. A precise feature spec was produced for the graphtor agent:
   * New key/relation `doc_url_index { canonical_url => source_id, chunk_id }`
     (or a `canonical_url` column on `doc_chunks`), globally unique.
   * Two-tier resolution in `chunks_at_path` / a new resolver: Tier 1 =
     intra-source exact `path` match (unchanged, preserves the source-pollution
     guard); Tier 2 = if `target_path` is absolute or Tier 1 misses, look up
     `canonical_url == target_path` globally (not source-scoped) →
     `(target_source_id, target_chunk_id)`.
   * `find_related_chunks` enqueues the resolved cross-source chunk with **its
     own** `source_id`; unresolved targets stay dangling (graceful).
   * Optional edge typing `intra_source` vs `cross_product`.
   * Touch points: `src/db/schema.rs` (relation + migration), `src/db/edges.rs`,
     `src/db/traverse.rs`, `src/db/chunks.rs`, `src/parse/frontmatter.rs`.
2. **docline (enabling dependency — reframed from `4A650FFD`):** emit a
   `canonical_url` per doc for local-dir ingestion, derived from each repo's
   openpublishing/docfx base path + `url_path_prefix` + monikers. This is a
   per-repo, per-doc capability — **not** multi-repo orchestration. Caveat:
   canonical-URL derivation has real complexity (monikers, redirect maps,
   documentId path-depot mappings) and likely warrants its own spike before
   implementation.

### Answer to "does multi-repo orchestration enhance graphtor's edge derivation?"

**No.** Running repos together in docline does not give graphtor better keys or
edges. The enabling docline contribution is **canonical-URL emission** (an
independent per-repo feature), which supplies the globally-unique cross-source
key graphtor's Option B resolution needs. graphtor cannot derive that key itself
because it never sees the source repo's publish config.

## Next Steps

* Reframe stash `4A650FFD` from "multi-repo orchestration" to "canonical-URL
  emission for local-dir ingestion" (done 2026-07-04).
* Hand the graphtor Option B feature spec (above) to the graphtor-docs agent.
* Spike the docline canonical-URL derivation (openpublishing/docfx →
  `/product/path` mapping incl. monikers/redirects) before building.
* Check whether graphtor vector search (`src/db/search.rs`, already cross-source)
  already satisfies the agent cross-repo lookup need — may reduce urgency of the
  graph-edge cross-linking work.

## References

* docline: `src/docline/process/cross_doc_links.py` (cross_product emission)
* graphtor: `src/parse/frontmatter.rs` (title/description only; ignores unknown keys)
* graphtor: `src/parse/links.rs` (raw target_path extraction)
* graphtor: `src/db/edges.rs` (`doc_edges { src_chunk_id, target_path => … }`, no resolution)
* graphtor: `src/db/traverse.rs` (`find_related_chunks`, source-scoped, exact-path match)
* graphtor: `src/db/schema.rs`, `src/db/chunks.rs` (`doc_chunks.path` = source-relative)
* graphtor: `src/config/source.rs` (one source_id per local directory)
* Prior: `docs/decisions/2026-06-02-docline-graphtor-alignment-gap-analysis.md`
