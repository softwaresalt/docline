---
title: "docline → graphtor-docs ingestion contract alignment — implementation plan"
description: "Implementation plan for Shipment 10 (010-S): the cohesive F1-F8 feature set that aligns docline's markdown output with the graphtor-docs ingestion contract."
plan_id: "2026-06-02-docline-graphtor-alignment-plan"
source: "docs/decisions/2026-06-02-docline-graphtor-alignment-deliberation.md"
gap_analysis: "docs/scratch/2026-06-02-docline-graphtor-alignment-gap-analysis.md"
shipment_target: "010-S"
date: "2026-06-02"
status: "draft"
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

docline emits markdown via four reader pipelines (`html`, `pdf`, `docx`, `vtt`, plus `adr` and `wiki` specializations) routed through `src/docline/process/assemble.py` and described by frontmatter models in `src/docline/schema/`. The downstream consumer `graphtor-docs` (Rust MCP server, CozoDB chunk store + HNSW + doc_edges graph) requires:

* Frontmatter with `description`, `content_sha256`, `source_path` (forward-slash), `chunk_strategy`, `schema_version`.
* H1/H2/H3 as chunk boundaries (H4-H6 fold into parent); no H2-before-H1.
* Deterministic `chunk_id = SHA-256(reconstructed_content + "\0" + source_path)` with POSIX `source_path`.
* Markdown features: tables, footnotes, strikethrough.

docline's current emissions diverge across 11 named gaps (G1-G11) inventoried in `docs/scratch/2026-06-02-docline-graphtor-alignment-gap-analysis.md`. This plan implements the resolution from the deliberation: a single cohesive shipment that delivers all eight features (F1-F8) addressing all eleven gaps.

## Requirements Trace

| Requirement (gap) | Implementation unit | Verifying tests |
|---|---|---|
| G1 — shared frontmatter additions, `docline:` namespace, JSON Schema export | F1 unit set | `tests/schema/test_frontmatter_v1.py`, JSON Schema regression test |
| G2 — POSIX path helper, route all `source_path` through it | F2 unit set | `tests/test_posixify_path.py`, parameterized Windows + POSIX inputs |
| G3 — heading hierarchy validation + `HeadingHierarchyError` | F3 unit set | `tests/process/test_heading_validation.py` |
| G4 — DOCX styles + lists + tables | F4 unit set | `tests/readers/test_docx_styles.py`, `tests/readers/test_docx_lists.py`, `tests/readers/test_docx_tables.py` |
| G5 — PDF layout-aware extraction (font-size heuristic; opt-in `docling`) | F5 unit set | `tests/readers/test_pdf_layout.py`, `tests/readers/test_pdf_docling_optin.py` |
| G6 — HTML `<figure>`/`<figcaption>`/`alt` + sitemap + canonical URL dedup | F6 unit set | `tests/fetch/test_html_figures.py`, `tests/fetch/test_sitemap.py`, `tests/fetch/test_url_canonical.py` |
| G7 — `content_sha256` over markdown body bytes; idempotent re-ingest | F1 unit set (combined with G1) | `tests/schema/test_content_sha256.py`, round-trip in frontmatter tests |
| G8 — staging metadata → `WebFrontmatter` | F7 unit set | `tests/schema/test_web_frontmatter_staging.py` |
| G9 — optional `<a id="chunk-{NNNN}"></a>` behind `assemble.emit_chunk_anchors=true` | F7 unit set | `tests/process/test_chunk_anchors.py` |
| G10 — `docs/design-docs/graphtor-docs-ingestion-contract.md` + README link | F8 docs unit | manual review during plan-review and ship's runtime verification |
| G11 — E2E integration test under `pytest -m graphtor_integration` | F8 test unit | `tests/integration/test_graphtor_ingest_contract.py` |

## Implementation Units

Each Feature (F#) decomposes into one or more atomic Tasks (Tx) that satisfy the 2-hour rule, width isolation, and atomic milestone constraints. Subtasks are noted where the per-task scope still exceeds 2 hours.

### F1 — Shared frontmatter schema + content hashing (G1 + G7)

* **F1.T1** (test-first) — Add `tests/schema/test_frontmatter_v1.py` with red-first cases:
  * required new fields (`description`, `content_sha256`, `source_path`, `chunk_strategy`, `schema_version`) accepted and rejected when missing/wrong type
  * `docline:` namespace mapping accepts arbitrary docline-only keys without leaking into top-level
  * backward-compat fixture (existing minimal frontmatter) still parses
* **F1.T2** — Extend `BaseFrontmatter` in `src/docline/schema/models.py` with the five new fields. Default `chunk_strategy = "h1-h2-h3"`, `schema_version = "1.0"`. Add `docline: dict[str, Any] | None` namespace field.
* **F1.T3** — Update `WikiFrontmatter`, `AdrFrontmatter`, `WebFrontmatter`, `TranscriptFrontmatter` in `src/docline/schema/library.py` to inherit the new base correctly; relocate docline-only fields into the `docline:` namespace.
* **F1.T4** — Add `src/docline/schema/hashing.py` with `compute_content_sha256(body_bytes: bytes) -> str`; route all assemble call sites to populate `content_sha256` after final body bytes are known. Add `tests/schema/test_content_sha256.py` (red-first).
* **F1.T5** — Add JSON Schema export at `src/docline/schema/exported/` driven by `pydantic`'s `model_json_schema()`; add CLI `docline schema export --out src/docline/schema/exported/`; add JSON Schema regression test that diffs the on-disk schema vs the live model.
* **F1.T6** — Documentation: add a short README note under `src/docline/schema/exported/README.md` describing what the exported schema is for and how to regenerate it.

### F2 — POSIX path normalization helper (G2)

* **F2.T1** (test-first) — `tests/test_posixify_path.py` with parameterized cases (Windows-style, POSIX, mixed, UNC, drive-letter, trailing-slash) — red first.
* **F2.T2** — Add `src/docline/paths.py` with `posixify_path(path: str | os.PathLike[str]) -> str`. Implementation: route through `pathlib.PurePath.as_posix()` with explicit handling for absolute Windows paths and UNC.
* **F2.T3** — Route every existing `source_path` emission through `posixify_path()`: grep + edit call sites in `process/assemble.py`, `process/output_contract.py`, `fetch/staging.py`, all reader modules. Add an `assemble.test_source_path_is_posix` test that scans a real assembled corpus.

### F3 — Heading hierarchy validation in assemble (G3)

* **F3.T1** (test-first) — `tests/process/test_heading_validation.py` with cases: valid hierarchy passes; H2 before H1 raises; H3 before H2 raises; H4-H6 do not affect validation; deeply nested doc passes.
* **F3.T2** — Add `validate_heading_hierarchy(markdown: str) -> None` and `HeadingHierarchyError(DoclineError)` to a new `src/docline/process/heading_validation.py`. Use `markdown-it-py` token stream (already an existing dependency per `pyproject.toml`).
* **F3.T3** — Integrate into `assemble_markdown` in `src/docline/process/assemble.py`; behaviour: validate after final assembly, fail-loud by default, expose `--allow-heading-disorder` CLI flag and matching MCP option (parity) for legacy corpora.

### F4 — DOCX style/list/table fidelity (G4)

* **F4.T1** (test-first, characterization) — Pin current DOCX behavior on a small fixture corpus before changing emission: snapshot existing output to `tests/readers/fixtures/docx/_baseline/`.
* **F4.T2** (test-first) — `tests/readers/test_docx_styles.py` red-first: H1-H6 from `<w:pStyle>` (Heading1..Heading6 + Title), normal paragraphs unchanged.
* **F4.T3** — Implement `<w:pStyle>` → H1-H6 mapping in `src/docline/readers/docx.py`. Behind-the-scenes: parse `word/document.xml` via `lxml`; map standardized + common-variant style names.
* **F4.T4** (test-first) — `tests/readers/test_docx_lists.py` red-first: `<w:numPr>` → GFM ordered / unordered with single level of nesting.
* **F4.T5** — Implement `<w:numPr>` → GFM list emission in `docx.py`. Multi-level nesting flattens for v1 (see Decisions §3).
* **F4.T6** (test-first) — `tests/readers/test_docx_tables.py` red-first: simple `<w:tbl>` → GFM table; cells with paragraphs concatenated; headerless tables emit no header row.
* **F4.T7** — Implement `<w:tbl>` → GFM table emission in `docx.py`.

### F5 — PDF layout-aware extraction (G5)

* **F5.T1** (test-first, characterization) — Snapshot current PDF output to `tests/readers/fixtures/pdf/_baseline/`; verify no regressions vs heuristic phase 1.
* **F5.T2** (test-first) — `tests/readers/test_pdf_layout.py` red-first: font-size histogram heuristic produces stable H1-H3 from sample PDFs (3 fixtures).
* **F5.T3** — Implement phase-1 font-size histogram in `src/docline/readers/pdf.py`. Heuristic: cluster glyph sizes into ≤3 bands; assign top band → H1, next → H2, next → H3. Conservative default; per-document threshold configurable.
* **F5.T4** (test-first) — `tests/readers/test_pdf_docling_optin.py` red-first: when `--pdf-layout-engine=docling` flag is set, opt-in path is exercised; default behavior unchanged.
* **F5.T5** — Implement phase-2 opt-in `docling` integration in `pdf.py` behind a CLI/MCP-parity flag `--pdf-layout-engine={heuristic|docling}` (default `heuristic`). If `docling` is not importable, emit a clear error.

### F6 — HTML semantic preservation + sitemap + URL canonicalization (G6)

* **F6.T1** (test-first) — `tests/fetch/test_html_figures.py` red-first: `<figure><figcaption>` preserved as a figure block; `<img alt>` preserved; missing alt yields a structured warning.
* **F6.T2** — Implement figure/caption/alt preservation in `src/docline/fetch/html_extract.py` and `src/docline/fetch/html_normalize.py`.
* **F6.T3** (test-first) — `tests/fetch/test_url_canonical.py` red-first: RFC 3986 normalization (lowercase scheme/host, remove default ports, sort query keys for dedup key only, drop fragment) — exact rules pinned by tests.
* **F6.T4** — Implement `src/docline/fetch/url_canonical.py` with `canonicalize_url(url: str) -> str` and `dedup_key_for_url(url: str) -> str` (the latter strips fragment + sorts query keys).
* **F6.T5** (test-first) — `tests/fetch/test_sitemap.py` red-first: discover URLs from `sitemap.xml`, sitemap index, gzipped sitemap; honor `robots.txt`; respect `config_dir` containment and explicit allowlists.
* **F6.T6** — Implement `src/docline/fetch/sitemap.py`: discovery from a base URL, fetch with timeout, parse with `defusedxml.ElementTree`; integrate into `src/docline/fetch/crawl.py` as an opt-in `--enable-sitemap` flag (default OFF).
* **F6.T7** — Dedup observed URLs by `dedup_key_for_url()` inside `crawl.py`; add test for round-trip dedup.

### F7 — Staging metadata propagation + optional chunk anchors (G8 + G9)

* **F7.T1** (test-first) — `tests/schema/test_web_frontmatter_staging.py` red-first: `WebFrontmatter` exposes `http_status: int`, `content_type: str`, `final_url: str`, `fetched_at: datetime` (ISO-8601).
* **F7.T2** — Extend `WebFrontmatter` in `src/docline/schema/library.py`; route fields from `src/docline/fetch/staging.py` into the frontmatter at assembly time.
* **F7.T3** (test-first) — `tests/process/test_chunk_anchors.py` red-first: when `assemble.emit_chunk_anchors=true`, `<a id="chunk-{NNNN}"></a>` anchors are inserted before each chunk boundary; default OFF emits no anchors.
* **F7.T4** — Implement chunk-anchor emission in `src/docline/process/assemble.py` gated by config flag and CLI flag `--emit-chunk-anchors`; MCP parity flag added.

### F8 — Cross-tool contract doc + E2E integration test (G10 + G11)

* **F8.T1** — Write `docs/design-docs/graphtor-docs-ingestion-contract.md` describing the contract surface: frontmatter fields, chunk-boundary rules, hashing, path normalization, schema_version policy, supported markdown features, and stability guarantees. Add link from project `README.md`.
* **F8.T2** (test-first) — Author `tests/integration/test_graphtor_ingest_contract.py` under `pytest -m graphtor_integration`: round-trip a small docline-emitted corpus through a fixture-based simulator of the graphtor-docs chunker that mirrors the documented contract.
* **F8.T3** — Register the marker in `pyproject.toml` (`tool.pytest.ini_options.markers += "graphtor_integration: end-to-end graphtor-docs ingestion contract"`); update CI test invocation to optionally run the marker on a label or schedule.
* **F8.T4** — Optional opt-in real-binary integration: skip-by-default test that exercises an installed `graphtor-docs` binary if present at a discoverable path. Skipped in default CI.

## Dependency Graph

```text
F1 ──► F3, F4, F5, F6, F7, F8
F2 ──► F1, F6, F8
F3 ──► F8
F4 ──► F8
F5 ──► F8
F6 ──► F8
F7 ──► F8
```

Concretely:

* F1 and F2 must land first (foundation).
* F3, F4, F5, F6, F7 are largely independent of each other; can be parallelized post-foundation.
* F8 sits downstream of F1-F7.

Inside features:

* F1: T1 → T2 → T3 → T4 → T5 → T6.
* F2: T1 → T2 → T3.
* F3: T1 → T2 → T3.
* F4: T1 → (T2 → T3) → (T4 → T5) → (T6 → T7).
* F5: T1 → (T2 → T3) → (T4 → T5).
* F6: T1 → T2; T3 → T4; T5 → T6; T7.
* F7: (T1 → T2); (T3 → T4).
* F8: T1; T2 → T3; T4.

## Decisions and Rationale

1. **Combine G1 (frontmatter) and G7 (content_sha256) in F1.** `content_sha256` is a frontmatter field; separating it produces a feature with no consumer. The combined feature still respects the 2-hour rule because each task (T1-T6) is independently atomic.
2. **Phase PDF layout work into heuristic + opt-in `docling`.** Phase 1 must remain default-on and deterministic with no new heavy dependency. Phase 2 is additive, behind a flag, and may be deferred if `docling` API stability proves problematic — but the integration surface lands in this shipment to avoid re-opening PDF code later.
3. **DOCX multi-level lists flatten in v1.** Multi-level numbering in `<w:numPr>` is non-trivial; v1 emits a flat ordered/unordered list and preserves indentation in the markdown source via two-space indent per nested level. A follow-up enhancement may add full nesting.
4. **Sitemap discovery is opt-in (`--enable-sitemap`, default OFF).** Default behavior must not silently widen crawl scope. Combined with `robots.txt` honor and `config_dir` containment, this preserves Constitution III workspace isolation.
5. **`schema_version: "1.0"` initial value with SemVer additive-minor policy.** Documented in F8 contract doc. Optional additive fields → MINOR bump; field removals or required-field additions → MAJOR.
6. **URL canonicalization is RFC 3986 + deterministic query-key sort for dedup key only.** The emitted `final_url` in `WebFrontmatter` is the **fetched** URL after redirects (not the canonicalized form); canonicalization is used only for dedup keying inside `crawl.py`. This preserves provenance.
7. **Heading validator fail-loud by default with `--allow-heading-disorder` escape hatch.** Default-strict behavior prevents malformed chunks at the source; the escape hatch supports legacy corpora migration.
8. **JSON Schema export lives in-repo (`src/docline/schema/exported/`) and is regenerated by an explicit CLI subcommand**, not as a build step. Avoids hidden side effects in `python -m build`.
9. **F8 default integration test uses a fixture-based simulator**, not a real `graphtor-docs` binary. Avoids CI flakiness and toolchain coupling. A skip-by-default real-binary test is provided for opt-in use.

## Risks and Caveats

| Risk | Mitigation |
|---|---|
| F1 breaks existing consumers expecting current frontmatter | All new fields optional with sensible defaults; `docline:` namespace isolates additions; backward-compat fixture pinned in tests; `schema_version: 1.0` declared. |
| F2 POSIX path change alters existing emitted `source_path` values for Windows-emitted corpora | Documented as breaking under `schema_version` 1.0; rollout requires re-ingest on graphtor side; called out in F8 contract doc. |
| F4 regresses simple DOCX documents | F4.T1 characterization snapshot pins current output; new emissions added under red tests. |
| F5 PDF heuristic degrades documents that worked before | F5.T1 characterization snapshot; heuristic conservative (≤3 bands); phase 2 strictly opt-in. |
| F6 sitemap widens crawl scope unexpectedly | Default OFF; opt-in via explicit flag; respects `robots.txt`; bounded by allowlist. |
| F8 integration test flakes | Deterministic fixture-based simulator; real-binary test opt-in only. |
| Cross-OS path test gaps | Tests parameterized on Windows + POSIX; CI matrix already runs both. |
| Long PR / review fatigue | Per-feature commits, dependency-edge ordering supports sub-PRs if needed; ship may decide to land F1+F2 first inside the same branch via stacked commits. |
| Dependency drift (`docling`, `defusedxml`, `lxml`) | All already declared in `pyproject.toml` (verified during plan-harden); no new mandatory dependency. |

## Plan Hardening Signals (REQUIRED)

| Signal | Present? | Justification |
|---|---|---|
| Public API, schema, or contract change | **YES** | F1 modifies `BaseFrontmatter` (public schema); F2 changes `source_path` representation across all outputs; F8 documents a new external contract. |
| Security, auth, permission, or compliance-sensitive behavior | NO | No auth/credential surfaces touched. |
| Migration, backfill, destructive data/config action, or irreversible step | **YES** | Existing graphtor-docs ingests of pre-`schema_version=1.0` corpora must re-ingest to pick up new `chunk_id`/`source_path` shapes. No destructive action inside docline, but downstream re-ingestion is required. |
| External integration, operator checkpoint, or external dependency | **YES** | F5b `docling` integration; F6 sitemap discovery makes external HTTP calls; F8 documents cross-tool contract with `graphtor-docs`. |
| High runtime, rollout, or rollback risk | **YES** | Cross-cutting blast radius (schema + 4 readers + fetch + process); multi-PR potential; reader regressions could silently degrade many corpora. |

**Requires plan hardening: yes**

## Runtime Verification and Closure

| Unit | Runtime surface | Runtime verification | Closure artifact |
|---|---|---|---|
| F1 (schema) | CLI (`docline fetch`, `docline process`, `docline schema export`), MCP (`fetch`, `process`, `schema/export` tools) | Emit a sample corpus via CLI; verify frontmatter shape matches JSON Schema; run MCP equivalents and verify parity. | Runtime-verification note in closure record; updated JSON Schema files committed. |
| F2 (POSIX paths) | All emission paths | Sample emit on Windows + Linux CI; confirm `source_path` is forward-slash everywhere. | Closure note: backward-incompat path representation under `schema_version: 1.0`. |
| F3 (heading validator) | CLI + MCP | Process a known-good corpus (passes); process a known-bad corpus (fails with `HeadingHierarchyError`); confirm `--allow-heading-disorder` works in both surfaces. | Closure note: list of corpora flagged by validator. |
| F4 (DOCX) | CLI + MCP `process` | Fixture corpus before/after diff; manual visual check of one representative document. | Closure: visual-check screenshots or markdown diffs in closure record. |
| F5 (PDF) | CLI + MCP `process` | Fixture corpus before/after diff; manual visual check of one representative PDF; verify `--pdf-layout-engine=docling` opt-in path. | Closure: PDF reader fidelity notes; opt-in flag documented. |
| F6 (HTML + sitemap + canonical URL) | CLI + MCP `fetch` | Crawl a small fixture site; verify figures preserved; verify dedup; verify sitemap discovery behind opt-in flag honors robots.txt. | Closure: crawl behavior diff; sitemap opt-in note. |
| F7 (staging metadata + chunk anchors) | CLI + MCP `fetch` and `process` | Fetch a sample URL; verify `WebFrontmatter` populated; process with and without `--emit-chunk-anchors`; verify anchors. | Closure: parity matrix for CLI vs MCP flags. |
| F8 (contract doc + integration test) | CI test runner | `pytest -m graphtor_integration` passes; doc reviewable. | Closure: contract doc linked from README; integration test referenced in PR description. |

## Operational Closure Expectations

* **Monitoring**: not applicable (CLI/MCP local tools; no production runtime).
* **Rollback**: revert PR; downstream graphtor-docs re-ingest of previous emissions remains valid (older `schema_version` corpora unaffected by docline rollback).
* **Validation window**: ship's runtime-verification skill exercises CLI + MCP parity matrix immediately post-merge.
* **Ownership**: docline maintainers for emission; graphtor-docs maintainers for ingestion (out of scope for this plan).

## Open Questions Carried Forward

These are surfaced for plan-harden / plan-review attention and tracked here so the harvest skill does not lose them:

1. F5b `docling` API stability at currently-pinned version — verify in F5.T5 implementation; spike if uncertain.
2. F6 canonical URL: explicit confirmation of port-removal policy (drop default 80/443 only) and trailing-slash policy (preserve, except for bare-host roots).
3. F4 multi-level list policy: flat v1 vs nested follow-up — call out explicitly in F4 task descriptions.
4. F8 real-binary integration test: agree path-discovery convention for opt-in (`GRAPHTOR_DOCS_BIN` env var?).

## Source Document Trace

* Source decision: `docs/decisions/2026-06-02-docline-graphtor-alignment-deliberation.md`
* Source gap analysis: `docs/scratch/2026-06-02-docline-graphtor-alignment-gap-analysis.md`
* Source stash entry: `C9DCDF9A` (epic, high priority)

## Plan Hardening

**Hardening required: yes.** Three hardening signals present (contract change, migration, high blast radius), plus an opt-in external dependency (`docling`). This section reinforces verification, rollback, and guardrails before plan review.

### Context Consulted

* `docs/compound/` — searched; library is currently empty (no relevant prior incidents).
* `.github/instructions/strict-safety.instructions.md` — `ProposedAction` / `ActionRisk` / `ActionResult` vocabulary applied below.
* `.github/instructions/constitution.instructions.md` — Principle II (Test-First), Principle X (context efficiency), Principle XI (merge commits).
* `docs/scratch/2026-06-02-docline-graphtor-alignment-gap-analysis.md` — gap-by-gap technical detail.
* `docs/decisions/2026-06-02-docline-graphtor-alignment-deliberation.md` — option analysis, scope-split rationale.

### Risk Triggers and Protected Invariants

| Trigger | Protected invariant |
|---|---|
| Frontmatter schema is part of the docline public contract | Existing fixtures that parse today must still parse after F1; backward-compat fixture is pinned in `tests/schema/test_backward_compat_frontmatter.py`. |
| `source_path` representation changes from native-OS to POSIX | `schema_version: "1.0"` declares the new shape; downstream consumers re-ingesting docline corpora MUST use schema_version ≥ 1.0; this is documented in F8 contract doc. |
| DOCX/PDF/HTML reader changes can silently degrade existing corpora | Characterization snapshots (F4.T1, F5.T1) pin pre-change behavior; all new emissions land under red-first tests. |
| `docling` opt-in introduces an external Python dependency at runtime | F5b strictly opt-in via `--pdf-layout-engine=docling`; default path remains pure-stdlib + `pdfminer.six`/current PDF stack; import deferred until flag is set. |
| Sitemap discovery widens crawl scope | F6 sitemap default OFF (`--enable-sitemap`); honors `robots.txt`; bounded by allowlist; tested with mock site. |
| Heading hierarchy validator may fail-loud on legacy corpora | `--allow-heading-disorder` escape hatch (and matching MCP flag) documented in F3; closure step F3 enumerates flagged corpora. |
| CLI ↔ MCP parity could drift as flags are added | Every new flag (`--allow-heading-disorder`, `--pdf-layout-engine`, `--emit-chunk-anchors`, `--enable-sitemap`, `docline schema export`) has both a CLI surface and an MCP parameter; parity matrix recorded in F7 closure. |

### Risky Actions (ProposedAction Set)

| ID | ProposedAction | Targets | Change kind | Rollback | ActionRisk | Approval required |
|---|---|---|---|---|---|---|
| PA-1 | Extend `BaseFrontmatter` with five new fields and a `docline:` namespace | `src/docline/schema/models.py`, `src/docline/schema/library.py`, all callers | Schema/contract change | Revert PR; consumers ignore unknown fields (`schema_version` = "0" tolerated) | **high** | Yes — Ship gate (plan-review + reviewers) |
| PA-2 | Switch all emitted `source_path` values to POSIX representation | `src/docline/paths.py` (new), `process/assemble.py`, `process/output_contract.py`, `fetch/staging.py`, all readers | Migration (output-shape change) | Revert PR; old corpora unaffected (only forward-incompatible for ingests on schema_version 1.0) | **high** | Yes — Ship gate |
| PA-3 | Enable heading-hierarchy validator by default (fail-loud) | `src/docline/process/assemble.py` | Behavior change | `--allow-heading-disorder` flag bypasses validator; revert PR | **moderate** | No — flag-protected |
| PA-4 | Add `docling` import path behind `--pdf-layout-engine=docling` flag | `src/docline/readers/pdf.py`, `pyproject.toml` (optional extra) | External integration | Default heuristic path always available; if `docling` import fails, error is explicit and non-fatal to default path | **moderate** | No — opt-in |
| PA-5 | Add sitemap discovery behind `--enable-sitemap` flag (default OFF) | `src/docline/fetch/sitemap.py` (new), `src/docline/fetch/crawl.py` | External integration / scope widening | Default OFF; remove flag invocation; `robots.txt` and allowlist limit blast radius | **moderate** | No — opt-in |
| PA-6 | Add JSON Schema export under `src/docline/schema/exported/` | New directory committed to repo | Repository surface addition | Delete directory; regenerable by `docline schema export` CLI | **low** | No |
| PA-7 | Add `pytest -m graphtor_integration` marker and CI invocation | `pyproject.toml`, CI workflow file (if applicable) | Test surface addition | Marker is skip-by-default unless invoked; CI invocation gated by label or schedule | **low** | No |
| PA-8 | Add `<a id="chunk-{NNNN}"></a>` chunk anchors behind `--emit-chunk-anchors` (default OFF) | `src/docline/process/assemble.py` | Behavior change behind flag | Default OFF; flag-removable | **low** | No |

### Reinforced Verification

Beyond per-unit verification in the table above, plan-harden adds these reinforcements:

* **Backward-compat fixture (F1)**: an existing pre-`schema_version` frontmatter fixture MUST round-trip through the new models without modification before F1 is considered done. Pinned in `tests/schema/test_backward_compat_frontmatter.py`.
* **Cross-OS path test (F2)**: parameterized over Windows and POSIX call-site paths; runs on both CI matrix legs.
* **Characterization snapshot before/after diff (F4, F5)**: failing diffs require explicit reviewer sign-off; document the diff in the PR description for affected readers.
* **CLI ↔ MCP parity matrix (F1, F3, F5, F6, F7)**: closure note must enumerate every new flag and confirm both surfaces accept it.
* **Sitemap behavior test (F6)**: mock-server test confirms `robots.txt` denial is honored and that the discovered URL set respects `config_dir` containment.
* **Schema export round-trip (F1)**: regression test diffs on-disk JSON Schema vs the live pydantic model on every test run; CI fails on drift.
* **Heading validator corpora sweep (F3)**: closure step runs the validator on the existing test corpus and the project's own `docs/` tree; any failures are enumerated in closure.

### Reinforced Rollback Plan

* **Per-feature commit boundaries.** Each F# lands as one or more conventional commits so individual features can be reverted without unwinding the whole shipment.
* **Schema version gate.** `schema_version: "1.0"` is the explicit contract boundary; older consumers continue to function on schema_version 0 corpora unchanged. Rolling back docline does not invalidate previously-emitted corpora.
* **Per-action rollback** (above PA-1..PA-8 table) — each risky action carries an explicit, individually-actionable rollback path; nothing requires "rollback the whole shipment".
* **No data-side rollback required.** docline does not persist state; rollback is purely a code revert. Downstream graphtor-docs may re-ingest at the operator's discretion.

### Reinforced Monitoring / Validation

* Not applicable in the traditional sense (no production runtime owned by docline).
* Substitute: Ship's `runtime-verification` skill must exercise the CLI ↔ MCP parity matrix on a representative corpus before closure.
* Substitute: F8 integration test (`pytest -m graphtor_integration`) is the contract regression signal going forward and MUST be added to either CI default or a clearly-labeled scheduled run.

### Human Checkpoints

* **Plan-review** (Step 4 below) — required before harvest.
* **PR review on the shipment branch** — Ship gate; each feature commit reviewed.
* **Post-merge closure** — Ship's `operational-closure` skill records the parity matrix and the characterization-snapshot diff results.

### Unresolved Operator Decisions (Blocking)

None. The plan is sufficiently specified for harvest.

### Unresolved Operator Decisions (Non-blocking, carried into harvest as task notes)

* F5b `docling` exact version pin (verify on first F5.T5 task; spike-out if API unstable).
* F6 canonical URL port-removal scope (default 80/443 only) and trailing-slash rule for root paths (preserve trailing slash on bare-host).
* F8 real-binary integration test env var name (`GRAPHTOR_DOCS_BIN`).

<!-- plan-review-attempt: 1 -->

## Plan Review

**Gate decision: ADVISORY.** No P0 or P1 findings. Three P2 findings recorded for harvest follow-up; the plan proceeds to harvest.

### Hardening verification

* Plan declares `Requires plan hardening: yes` and includes a `## Plan Hardening` section: **satisfied**.
* `strict-safety` capability pack is enabled; risky actions are classified via `ProposedAction` / `ActionRisk` table (PA-1..PA-8): **satisfied**.

### Personas applied

| Persona | Verdict | Findings |
|---|---|---|
| Constitution Reviewer | Pass | 0 |
| Python Reviewer | Pass | 0 |
| Scope Boundary Auditor | Pass | 0 |
| Learnings Researcher | Pass (library empty) | 0 |
| Architecture Strategist | Pass | 0 |
| Agent-Native Parity Reviewer | Pass | 0 |
| Security Lens Reviewer | Advisory | 2 P2 |
| (cross-cutting) | | 1 P2 |

Cross-model invocation not used in this session (single-agent inline review). Multi-model is preferred but not blocking per skill.

### Findings

#### P2-1 (Security Lens) — Harden DOCX XML parsing against XXE

**Where**: F4.T3 implementation (DOCX `<w:pStyle>` parsing in `src/docline/readers/docx.py`).

**Issue**: The plan calls for `lxml` parsing of `word/document.xml`. Default `lxml.etree.XMLParser` resolves external entities and can be vulnerable to XXE on adversarial DOCX inputs.

**Recommendation**: Use `defusedxml.lxml` or instantiate `lxml.etree.XMLParser(resolve_entities=False, no_network=True)` explicitly. Add a task note to F4.T3 calling this out. Add a regression test in `tests/readers/test_docx_styles.py` that asserts parser configuration rejects an XXE payload.

**Disposition**: Carry into F4.T3 as a task-level acceptance criterion at harvest.

#### P2-2 (Security Lens) — Sitemap fetcher must enforce SSRF guards

**Where**: F6.T6 implementation (`src/docline/fetch/sitemap.py`).

**Issue**: The plan correctly uses `defusedxml.ElementTree` for parsing (XXE-safe) and honors `robots.txt`, but does not explicitly restrict the HTTP fetcher from following redirects to private-IP / localhost / link-local hosts.

**Recommendation**: Reuse the SSRF guard pattern from `src/docline/fetch/crawl.py` if one exists; otherwise add explicit allow/deny lists for `localhost`, `127.0.0.0/8`, `169.254.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, IPv6 link-local. Add a task-level acceptance criterion in F6.T6 and a test in `tests/fetch/test_sitemap.py` that asserts SSRF rejection.

**Disposition**: Carry into F6.T6 as a task-level acceptance criterion at harvest.

#### P2-3 (Cross-cutting) — JSON Schema export drift across pydantic versions

**Where**: F1.T5 (`docline schema export` CLI subcommand) and the schema regression test.

**Issue**: Pydantic minor versions can change `model_json_schema()` output (key ordering, `$ref` format). A regression test that diffs on-disk JSON Schema against the live model will fail intermittently if pydantic is bumped without re-exporting.

**Recommendation**: Either (a) pin pydantic exactly in `pyproject.toml`, or (b) make the regression test tolerant by normalizing through `json.dumps(..., sort_keys=True)` and a documented schema-comparison helper, or (c) gate the test behind a make-target and document a `make schema-refresh` step. Plan-harden already addresses verification depth; this is implementation guidance, not a blocker.

**Disposition**: Carry into F1.T5 as a task note; choose option (b) by default for simplicity.

### Runtime verification and closure readiness

* Runtime surfaces are explicitly enumerated per unit: **satisfied**.
* Closure artifacts are named per unit: **satisfied**.
* CLI ↔ MCP parity matrix explicitly required in closure: **satisfied**.

### Final disposition

**ADVISORY — proceed to harvest.** All three P2 findings are tracked above and will be carried into the appropriate task acceptance criteria during harvest (Step 5). No revision of the plan body is required before harvest.
