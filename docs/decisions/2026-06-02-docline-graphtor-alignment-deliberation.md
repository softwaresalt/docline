---
title: "Align docline markdown output with graphtor-docs ingestion contract"
description: "Deliberation on how to decompose, sequence, and ship docline changes that make its markdown output ingestable by graphtor-docs without re-normalization."
topic: "docline → graphtor-docs ingestion contract alignment"
depth: "deep"
decision_status: "decided"
promoted_to: "plan"
linked_artifacts:
  - "docs/scratch/2026-06-02-docline-graphtor-alignment-gap-analysis.md"
  - "docs/plans/2026-06-02-docline-graphtor-alignment-plan.md"
source_stash:
  - "C9DCDF9A"
tags:
  - "schema"
  - "frontmatter"
  - "chunking"
  - "readers"
  - "fetch"
  - "graphtor-docs"
  - "contract"
---

## Problem Frame

docline currently emits markdown via several reader pipelines (HTML, PDF, DOCX, VTT, ADR, Wiki) and a YAML frontmatter schema that diverged from what `graphtor-docs` (Rust MCP server with CozoDB chunk store + HNSW vector index + doc_edges graph) actually consumes. The gap analysis at `docs/scratch/2026-06-02-docline-graphtor-alignment-gap-analysis.md` inventories 11 concrete gaps (G1-G11) and proposes an 8-feature decomposition (F1-F8).

The problem is two-fold:

1. **Contract drift**: docline's frontmatter, path representation, chunk-relevant heading structure, and content-fingerprinting are not aligned with the fields and invariants graphtor-docs needs (`description`, `content_sha256`, forward-slash `source_path`, H1/H2/H3 chunk boundaries, `schema_version`).
2. **Reader-side semantic loss**: reader output strips signal that graphtor-docs uses to produce high-quality chunks and graph edges — DOCX style/list/table structure, PDF layout, HTML semantic regions (figures, captions, sitemap-discovered pages, canonicalized URLs), and staging-time HTTP metadata.

**Who cares**: graphtor-docs ingestion consumers (RAG / agent retrieval), docline maintainers, and any future ingest target that follows the same chunking contract.

**Constraints**:

* docline's existing output schema is consumed by other internal flows; changes MUST be backward-compatible (versioned schema, namespaced additions).
* No edits to `graphtor-docs` itself — contract is one-directional (docline conforms).
* TDD is non-negotiable; every feature/task ships with red-first tests.
* CLI and MCP parity must hold for any new flag or behavior.

**Success criteria**:

* `graphtor-docs` can ingest a docline-emitted directory of markdown and produce chunks with deterministic `chunk_id`, populated `description`, populated `doc_edges`, and stable rerun (content_sha256 short-circuits unchanged content).
* docline's existing consumers continue to work without modification (frontmatter additions are additive; `docline:` namespace isolates tool-specific fields).
* An E2E integration test demonstrates the round-trip.

**Out of scope**:

* Changes to graphtor-docs.
* New reader formats (e.g., EPUB) beyond the four already in scope.
* OCR fallback for scanned PDFs (separate work).
* Embedding generation inside docline (graphtor-docs owns embedding).

## Research Findings

### Codebase signals

* `src/docline/schema/models.py` defines `BaseFrontmatter`; `src/docline/schema/library.py` defines Wiki/Web/Adr/Transcript variants. Frontmatter currently lacks `description`, `content_sha256`, `schema_version`, and path representation is platform-native.
* `src/docline/process/assemble.py` produces final markdown; no heading-hierarchy validation step exists.
* `src/docline/readers/docx.py` does not consult `<w:pStyle>`, list numbering, or `<w:tbl>` structure.
* `src/docline/readers/pdf.py` flattens to plain text without layout analysis.
* `src/docline/fetch/html_extract.py` strips `<figure>`/`<figcaption>` and image alt text.
* `src/docline/fetch/crawl.py` exists but does not perform sitemap discovery or canonical-URL deduplication.
* `src/docline/fetch/staging.py` records HTTP metadata but does not propagate `http_status`, `content_type`, `final_url`, `fetched_at` into `WebFrontmatter`.

### Contract signals (graphtor-docs)

* `serde_yaml::FrontmatterRaw { title, description }` — `description` is required for chunk metadata.
* Chunker uses H1/H2/H3 as chunk boundaries; H4-H6 fold into the parent chunk. Markdown with H2-before-H1 produces malformed chunks.
* `chunk_id = SHA-256(reconstructed_content + "\0" + source_path)` with **forward-slash** `source_path`. Backslashes break chunk stability across OS.
* Markdown features used: tables, footnotes, strikethrough.

### Prior learnings

`docs/compound/` is empty — no prior solutions to consult.

### Risk surface

The work spans schema (cross-cutting), four readers (independent), fetch (HTML/crawl), process (assemble + validation), tests, and docs. It changes a public output contract. Plan hardening is therefore mandatory (Step 3.2 P-006 gate).

## Options Evaluated

### Option A — Single-shipment "big-bang" alignment (all of F1-F8)

Ship all 8 features in one shipment, one PR.

* **Pros**: contract aligned in one merge; integration test (F8) validates the full surface at once; no half-aligned intermediate state.
* **Cons**: very large PR (≥30 tasks across 6 subsystems); review fatigue and CI risk; cross-cutting blast radius; any single failing reader blocks the entire shipment.
* **Effort**: high (≥60 hours human-equivalent decomposed into ≥30 tasks).
* **Fit**: poor — violates the 2-hour task rule indirectly by bundling many independent subsystems and produces an oversized release unit.

### Option B — Two-shipment foundation-then-readers split (F1+F2+F7+G1-G2-G7 first; F3-F6+F8 second)

Ship the foundation (shared schema with `description`/`content_sha256`/`schema_version`/`source_path` forward-slash + heading validator + content hashing) first. Then a second shipment for reader-specific quality (DOCX styles, PDF layout, HTML semantic regions, sitemap, integration tests).

* **Pros**: foundation lands quickly and is independently valuable; existing readers immediately start emitting contract-compliant frontmatter even without per-reader semantic improvements; reduces blast radius per merge; second shipment can iterate on reader quality with the foundation already verified.
* **Cons**: graphtor-docs ingestion will be "syntactically correct but semantically thin" between shipments — DOCX tables, PDF layout, HTML figures are not yet preserved; readers will need a second pass.
* **Effort**: medium per shipment (≈20-25 hours each); total higher than Option A due to coordination.
* **Fit**: strong — matches docline's incremental shipping pattern, keeps PR sizes manageable, gives users a quickly-shippable foundation MVP, and the second shipment is well-bounded.

### Option C — Three-shipment foundation / fetch+HTML / readers+integration split

Foundation (F1+F2+F7) → Fetch and HTML quality (F3+G6 + staging metadata in F7) → Reader quality + integration (F4+F5+F8).

* **Pros**: smallest individual PRs; each subsystem stable independently.
* **Cons**: longest end-to-end timeline; integration test (F8) only meaningful at the end of all three; foundation-only state lingers longest; coordination overhead high.
* **Effort**: low per shipment but higher total (≈3 × 15-20 hours).
* **Fit**: moderate — over-decomposes the work for the value gained.

### Option D — Foundation MVP only (ship F1+G2+G7 + minimal integration smoke test; queue F2-F6+F8 as a sequel)

Ship the schema-and-hashing foundation alone as the operator suggested ("F1 alone as a foundation MVP and queue F2-F8 as a sequel"). Reader-specific work and full E2E integration test stay in the stash as a separately-planned follow-on.

* **Pros**: smallest possible first PR; lowest risk; fastest delivery of contract-compliant frontmatter; allows operator to observe graphtor-docs behavior with thin semantics before committing to reader rework.
* **Cons**: no immediate user-visible improvement in chunk quality for DOCX/PDF/HTML beyond hashing; second cycle is non-trivial to plan once initial assumptions are validated; risk of stalling the readers work indefinitely.
* **Effort**: low for first shipment (≈12-15 hours); deferred effort for sequel.
* **Fit**: strong for risk-averse delivery, weaker for end-to-end goal achievement within a single planning cycle.

## Trade-off Comparison

| Criterion | A (big-bang) | B (foundation+readers split) | C (three-shipment) | D (foundation MVP only) |
|---|---|---|---|---|
| Per-PR size | XL | M / M | S / S / S | S |
| Review risk | High | Moderate | Low | Lowest |
| Blast radius per merge | High | Moderate | Low | Low |
| Time to contract compliance | Long (single merge) | Foundation soon, full later | Slow incremental | Foundation soon, full TBD |
| Graphtor ingest works end-to-end | After single merge | After 2nd shipment | After 3rd shipment | Only after deferred sequel |
| Coordination overhead | Low | Moderate | High | Lowest now / High later |
| Operator-facing complexity per release | High | Moderate | Low | Low |
| Risk of stalling the work | Low | Low | Moderate | High |
| Alignment with 2-hour task rule | Strained (size) | Good | Good | Good |
| Alignment with docline shipping cadence | Poor | Strong | Moderate | Strong (short-term) |

## Decision

**Adopt Option B: two-shipment foundation-then-readers split.** This shipment (the one being staged now — Shipment 10) executes the **full F1-F8 contract alignment as one cohesive release**.

### Resolution of explicit operator questions

> *"Should F1 also include G7 hashing or split it?"*

**Include G7 in F1 (combined "shared frontmatter + content hashing" feature).** Rationale:

* `content_sha256` is a *frontmatter field* added to `BaseFrontmatter`; conceptually it belongs in the shared-schema feature.
* The hashing helper (`compute_content_sha256(body_bytes) -> str`) is one small utility — splitting it into its own feature creates a feature without a coherent unit of value (a hash function with no consumer).
* Tests for G1 frontmatter validation naturally exercise G7 (the field must round-trip).

> *"Should F4 PDF layout be deferred to a follow-up shipment?"*

**Keep F4 in this shipment but split it into two phases**: F4a (phase-1 font-size histogram heuristic — required, deterministic, no new heavy dependency) and F4b (phase-2 opt-in `docling` layout analyzer — additive, behind a CLI flag). F4b is intentionally low-risk because it is opt-in; deferring it would leave an unused integration surface and slow PDF improvements. The phases are separate tasks under one feature so reviewers can land F4a even if F4b regresses.

> *"Should we ship F1 alone as a foundation MVP and queue F2-F8 as a sequel?"*

**No.** Option D (foundation-only) was rejected because:

* The operator's explicit goal is "markdown emitted by docline ingests directly into graphtor-docs CozoDB/HNSW without re-normalization." That goal is not met by foundation alone — DOCX flatness, PDF flatness, HTML figure loss, and missing sitemap/canonicalization remain blockers.
* The integration test (F8) only becomes meaningful when readers actually emit semantically faithful markdown; deferring it leaves the contract unverified end-to-end.
* The risk of "stalling at foundation" is real and well-known in this codebase pattern.
* Per-task scope and the harden gate already address Option D's risk-aversion motivation without sacrificing end-to-end value.

### What this shipment delivers

This shipment is **Shipment 10 (010-S): "docline ⇄ graphtor-docs ingestion contract alignment"** and decomposes the gap analysis into the following features:

* **F1 — Shared frontmatter schema + content hashing** (G1 + G7): adds `description`, `content_sha256`, `source_path` (POSIX), `chunk_strategy`, `schema_version`; namespaces docline-only fields under `docline:` mapping; emits JSON Schema artifacts.
* **F2 — POSIX path normalization helper + integration into source_path** (G2): adds `posixify_path()` helper in `src/docline/paths.py` and routes all `source_path` emissions through it.
* **F3 — Heading hierarchy validation in assemble** (G3): adds `validate_heading_hierarchy()` and integrates into `assemble_markdown`; new typed `HeadingHierarchyError`.
* **F4 — DOCX style/list/table fidelity** (G4): maps `<w:pStyle>` → H1-H6; emits ordered/unordered lists from `<w:numPr>`; emits GFM tables from `<w:tbl>`.
* **F5 — PDF layout-aware extraction** (G5): F5a font-size histogram heuristic (default); F5b opt-in `docling` layout analyzer (behind flag).
* **F6 — HTML semantic preservation + sitemap + URL canonicalization** (G6): preserves `<figure>`/`<figcaption>` and `<img alt>`; adds `fetch/sitemap.py`; adds `fetch/url_canonical.py`; deduplicates by canonical URL.
* **F7 — Staging metadata propagation to WebFrontmatter + optional chunk anchors** (G8 + G9): promotes `http_status`/`content_type`/`final_url`/`fetched_at` to `WebFrontmatter`; adds opt-in `assemble.emit_chunk_anchors` flag emitting `<a id="chunk-{NNNN}"></a>`.
* **F8 — Cross-tool contract design doc + E2E integration test suite** (G10 + G11): writes `docs/design-docs/graphtor-docs-ingestion-contract.md` + README link; adds `tests/integration/test_graphtor_ingest_contract.py` under `pytest -m graphtor_integration`.

### Dependency edges (informs harvest)

```text
F1 ──► F3, F4, F5, F6, F7, F8
F2 ──► F1, F6, F8
F4 ──► F8
F5 ──► F8
F6 ──► F8
F7 ──► F8
F3 ──► F8
```

Effectively: F1 + F2 must land first; F3-F7 are largely independent of each other (separate readers / process surfaces); F8 sits downstream of all reader features.

## Rejected Alternatives

* **Option A (big-bang)** rejected: PR size and review fatigue dominate the marginal benefit of a single merge.
* **Option C (three-shipment)** rejected: coordination cost exceeds the marginal blast-radius reduction; F8 integration test loses early value.
* **Option D (foundation-only MVP)** rejected: explicit end-to-end goal is not met; risk of stalling readers indefinitely; integration test gets deferred to an undefined cycle.
* **Splitting F1 and G7** rejected: artificial separation creates a feature with no consumer.
* **Deferring F4 entirely** rejected: PDF is the lowest-fidelity reader today; deferring it leaves the largest semantic gap unaddressed.
* **Doing F8 last only**: kept — F8 must run against the fully-assembled feature set; placing it last is correct.

## Unresolved Questions

These flow into the plan as Open Questions / Spike candidates:

1. **F5b (`docling` layout)** — does the existing `docling` Python dependency expose a stable API at the pinned version, or does adoption require a version bump? (Answered during impl-plan; spike if uncertain.)
2. **F4 lists with multi-level numbering** — DOCX `<w:numPr>` can express deeply nested lists; what is the minimal-fidelity contract that graphtor-docs needs? (Likely: flatten to GFM ordered/unordered; defer multi-level rendering as a follow-up if needed.)
3. **F1 schema_version policy** — set initial `schema_version: "1.0"` and bump rules? Recommended: SemVer with additive minor bumps for new optional fields, major bumps for breaking changes; documented in F8's contract doc.
4. **F6 canonical URL strategy** — collapse trailing slashes? lowercase scheme/host? strip fragments? (Standard RFC 3986 normalization, decided in impl-plan.)
5. **Test fixture provenance** — do we need real graphtor-docs binary in CI for F8, or a fixture-based simulator? Recommended: fixture-based round-trip in default CI; opt-in real-binary test under `pytest -m graphtor_integration`.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| F1 schema additions break existing consumers of `BaseFrontmatter` | Medium | High | All new fields are optional with sensible defaults; `docline:` namespace isolates tool-specific fields; `schema_version` declared; backward-compat test fixture pinned. |
| F2 POSIX path change alters existing emitted `source_path` values | Medium | Medium | Treat as a contract change; rollout requires re-ingest; called out in F8 contract doc; controlled via `schema_version` bump. |
| F4 DOCX behavior regresses simple documents | Medium | Medium | Characterization tests pin current behavior before implementing; new structured emissions added behind incremental tests. |
| F5 PDF layout changes degrade documents that worked before | Medium | High | Phase 1 default-on heuristic must pass a fixture corpus equal to current behavior; phase 2 opt-in only behind flag. |
| F6 sitemap discovery widens crawl scope unintentionally | Medium | High | Sitemap discovery respects existing `config_dir` containment, robots.txt, and explicit allowlists; default OFF or gated by explicit config. |
| F8 integration test flakes in CI | Low | Medium | Use deterministic fixtures; mark real-binary test as opt-in. |
| Plan-harden bypass | Low | High | P-006 gate is mandatory; this artifact explicitly declares `Requires plan hardening: yes` for downstream impl-plan. |
| Cross-OS path test gaps | Medium | Medium | Path tests parameterized on Windows-style + POSIX inputs; CI matrix already runs on Windows + Linux. |

## Constitution Check

| Principle | Compliance |
|---|---|
| I. Safety-First Python | All new code requires type hints; ruff/pyright gates apply. |
| II. Test-First Development | TDD harness required per F1-F8; harness-architect skill invoked first by Ship. |
| III. Workspace Isolation | F6 sitemap discovery respects `config_dir` containment. |
| IV. CLI Containment | All path emissions resolve via POSIX helper; no out-of-tree writes. |
| V. Structured Observability | Frontmatter additions (`http_status`, `final_url`, `fetched_at`) increase observability. |
| VI. Single Responsibility | F5b `docling` is opt-in; no new mandatory heavy dependency. |
| VII. Destructive Approval | No destructive operations introduced. |
| VIII. Safety Modes | Plan hardening required — strict-safety `ProposedAction` set captured in plan. |
| IX. Git-Friendly Persistence | YAML frontmatter remains the schema medium; deterministic ordering. |
| X. Context Efficiency | Tests are tier-scoped; integration test gated by marker. |
| XI. Merge Commit History | Standard branch + merge-commit workflow per ship's PR lifecycle. |

**Requires plan hardening: yes** (cross-cutting; public output contract change; multi-reader blast radius).
