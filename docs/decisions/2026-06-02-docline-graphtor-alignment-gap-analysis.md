# docline ↔ graphtor-docs Ingestion Alignment — Gap Analysis

**Date:** 2026-06-02
**Author:** Orchestrator (research synthesis)
**Status:** Input artifact for Stage subagent (planning only)

## Purpose

Define the contract docline must honor so that markdown emitted by `docline process` is **directly ingestible** by [graphtor-docs](d:\Source\GitHub\graphtor-docs) — its CozoDB chunk store, HNSW vector index, and `doc_edges` graph — without re-normalization. This document is the source-of-truth gap inventory handed to Stage.

## graphtor-docs ingestion contract (what we must produce)

### Frontmatter (YAML)

- File MUST begin at byte 0 with `---\n` and close with `---\n` (or `...\n`, or `---`/`...` at EOF).
- Parser: `serde_yaml` into `FrontmatterRaw { title: Option<String>, description: Option<String> }` ([src/parse/frontmatter.rs](d:\Source\GitHub\graphtor-docs\src\parse\frontmatter.rs#L6-L11)).
- **Invalid YAML is silently dropped** — must produce well-formed YAML.
- Unknown keys are ignored (safe to extend with `docline.*` namespace).
- If `title` absent, graphtor-docs falls back to first H1.

### Chunking & headings

- Chunker (`src/parse/chunker.rs`): **H1, H2, H3 are chunk boundaries**. H4–H6 fold into the parent chunk.
- Content before the first H1/H2/H3 becomes an **intro chunk** (empty heading hierarchy).
- No skipped heading levels (e.g., H1 → H3 disallowed).
- Content is **reconstructed** by `pulldown_cmark` walker — whitespace normalized, byte offsets approximate.
- Enabled extensions: tables, footnotes, strikethrough (standard CommonMark otherwise).

### Chunk-ID determinism

- `chunk_id = lower_hex(SHA-256(reconstructed_content + "\0" + source_path))` ([src/chunk/id.rs](d:\Source\GitHub\graphtor-docs\src\chunk\id.rs#L29-L48)).
- `source_path` **MUST use forward slashes** on all platforms — backslashes break cross-platform ID stability.
- Chunk ID is also the vector ID and the `doc_chunks` graph-node primary key.

### Links & code

- Markdown `[text](url)` inline links → `doc_edges` (anchors split into separate field).
- Fenced code blocks ` ```lang\n…\n``` ` → `doc_code` with deterministic snippet ID.
- Indented code blocks treated as language=None.

### Non-markdown inputs

- graphtor-docs does **NOT** parse DOCX or PDF. docline owns the DOCX/PDF → markdown conversion. The contract above applies to the markdown docline emits.

## docline current state (what we have)

| Surface | Current | File |
|---|---|---|
| Base frontmatter | `title`, `source`, `ingested_at`, `doc_type` | [src/docline/schema/models.py](d:\Source\GitHub\docline\src\docline\schema\models.py) |
| Family frontmatter | Wiki, Web (`source_url`, `crawl_depth`), Adr (`status`), Transcript | [src/docline/schema/library.py](d:\Source\GitHub\docline\src\docline\schema\library.py) |
| Markdown assembly | `assemble_markdown(fm, body)` → `"---\n{yaml}\n---\n{body}"` | [src/docline/process/assemble.py](d:\Source\GitHub\docline\src\docline\process\assemble.py) |
| HTML extract | BeautifulSoup, drops `<nav>/<aside>/<figure>`, no image alt | [src/docline/fetch/html_extract.py](d:\Source\GitHub\docline\src\docline\fetch\html_extract.py) |
| Heading normalize | Forces H1 root, removes level skips | [src/docline/fetch/html_normalize.py](d:\Source\GitHub\docline\src\docline\fetch\html_normalize.py) |
| Web crawl | urllib BFS, robots, domain_lock, SSRF guard; no sitemap, no URL canonicalization | [src/docline/fetch/crawl.py](d:\Source\GitHub\docline\src\docline\fetch\crawl.py) |
| PDF reader | pypdf + zlib fallback; **no layout/heading recovery** | [src/docline/readers/pdf.py](d:\Source\GitHub\docline\src\docline\readers\pdf.py) |
| DOCX reader | docling optional + raw `<w:p>/<w:t>` fallback; **no `<w:pStyle>` mapping** | [src/docline/readers/docx.py](d:\Source\GitHub\docline\src\docline\readers\docx.py) |
| Output paths | `{relative}.md` or `{relative}/part-{NNNN}.md` | [src/docline/process/output_contract.py](d:\Source\GitHub\docline\src\docline\process\output_contract.py) |
| Staging metadata | HTTP status, Content-Type, depth in `.meta.json` sidecar (not in frontmatter) | `fetch/staging.py` |

## Gap inventory (the deliverables)

### G1 — Shared frontmatter contract

**Problem:** docline's `BaseFrontmatter` does not include `description`; downstream graphtor-docs may want it. Also missing: stable chunk-strategy declaration, content hash, normalized source path.

**Required changes:**
- Add `description: str | None` to `BaseFrontmatter` (Pydantic, optional, omitted from YAML when None).
- Add `content_sha256: str` (hex) — hash of the markdown body (excluding frontmatter) for idempotent re-ingestion.
- Add `source_path: str` — repository-relative path with **forward slashes** (mirror graphtor-docs's normalization).
- Add `chunk_strategy: Literal["h1-h2-h3"]` — declares the heading convention applied.
- Add `schema_version: str` (semver) for future migration.
- Namespace docline-only fields under `docline:` mapping so graphtor-docs's strict-ignore-unknown stays clean.
- Publish the JSON Schema via `BaseFrontmatter.model_json_schema()` into `src/docline/schema/exported/` and commit it (so graphtor-docs can vendor / validate against it).

### G2 — Forward-slash path normalization

**Problem:** Windows backslash paths break chunk-ID determinism in graphtor-docs.

**Required changes:**
- Add `posixify_path(path: str | Path) -> str` helper (probably under `src/docline/paths.py`).
- Apply at every site that writes `source` / `source_path` / cross-document references into frontmatter or body.
- Add unit tests covering Windows path inputs.

### G3 — Heading hierarchy compliance

**Problem:** Current `normalize_heading_hierarchy` ensures H1 root and no level skips, but no test asserts the H1/H2/H3-only chunk-boundary convention nor a max-depth invariant.

**Required changes:**
- Add a `validate_heading_hierarchy(markdown)` function that enforces: starts at H1, no skipped levels, no demotion below H6, at least one H1/H2/H3 (otherwise everything is an intro chunk — warn).
- Run validation as part of `assemble_markdown`; emit `HeadingHierarchyError` on hard failures.
- Add tests pulling sample fixtures from each reader output.

### G4 — DOCX style → heading mapping

**Problem:** `readers/docx.py` discards `<w:pStyle>` so every paragraph becomes flat text.

**Required changes:**
- Parse `<w:pPr><w:pStyle w:val="…"/>` and map known names:
  - `Heading1`, `heading 1`, `Title` → `#`
  - `Heading2`, `heading 2` → `##`
  - `Heading3`, `heading 3` → `###`
  - `Heading4`–`Heading6` → `####`–`######`
- When docling is present, use docling's heading detection (already provides structured output).
- Add list-style detection (`<w:numPr>`) to emit `-`/`1.` markers.
- Add table extraction (`<w:tbl>`) → GFM pipe tables.
- Tests: synthetic DOCX fixtures covering heading styles, lists, tables.

### G5 — PDF layout-aware extraction

**Problem:** `readers/pdf.py` emits flat text; no heading recovery.

**Required changes (phase 1 — heuristic):**
- Use `pypdf` page-text + font metadata where available; build a font-size histogram per document.
- Top 1–3 distinct font sizes → H1/H2/H3 candidates (mirror graphtor-docs's two-pass approach).
- Emit `<page-break>` HTML comment or `---` separator at page boundaries (optional).

**Required changes (phase 2 — opt-in docling):**
- When `docling` extra is installed, prefer docling's layout analyzer for heading detection and table extraction.
- Tests: real-world PDF fixtures (Office export, Azure docs) asserting heading recovery rate ≥ 60%.

### G6 — HTML semantic preservation + sitemap + URL canonicalization

**Problem:** crawl currently drops `<nav>/<aside>/<figure>` and ingests query-string variants as separate pages; no sitemap discovery.

**Required changes:**
- Extend `strip_dom_noise` to capture `<figure><figcaption>` as markdown image blocks with caption.
- Capture image `alt` text in markdown `![alt](url)`.
- Add `discover_sitemap(base_url) -> list[str]` (`/sitemap.xml`, `/sitemap_index.xml`, robots.txt `Sitemap:` directives).
- Add `canonicalize_url(url) -> str`: lowercase scheme/host, strip default ports, strip `utm_*` and fragment, sort query params, remove trailing slash on non-root paths.
- Deduplicate via canonical URL before staging.
- Tests cover canonicalization vectors, sitemap parsing, deduplication.

### G7 — Content hashing & idempotent ingestion

**Problem:** No way for graphtor-docs (or docline itself) to detect unchanged content and skip re-embedding.

**Required changes:**
- Compute `content_sha256` over the markdown body bytes (post-assembly, pre-frontmatter wrap).
- Persist into frontmatter (G1).
- Tests assert the hash is stable for identical inputs and changes when body changes by one byte.

### G8 — Staging metadata → frontmatter promotion

**Problem:** HTTP status, final URL, content-type, fetched-at, crawl depth live in sidecar `.meta.json` and are lost on final markdown.

**Required changes:**
- Add `WebFrontmatter` fields: `http_status: int`, `content_type: str | None`, `final_url: str | None`, `fetched_at: datetime`.
- Pipe staging metadata through `process/assemble.py` when assembling web docs.
- Tests update existing `WebFrontmatter` schema tests.

### G9 — Optional chunk-stable anchors

**Problem:** graphtor-docs reconstructs chunk boundaries from headings; deep links from external systems cannot reference chunks by ID without coupling to graphtor-docs internals.

**Required changes (optional / phase 2):**
- After heading validation, optionally emit per-chunk HTML anchors: `<a id="chunk-{NNNN}"></a>` directly before each H1/H2/H3.
- Behind a config flag (`assemble.emit_chunk_anchors=true`).
- graphtor-docs preserves inline HTML in chunk content, so these anchors round-trip cleanly.

### G10 — Cross-tool contract documentation

**Required artifact:**
- `docs/design-docs/graphtor-docs-ingestion-contract.md` documenting the above for downstream consumers and future docline maintainers.
- Link from `README.md`.

### G11 — End-to-end integration verification

**Required artifact:**
- New test suite `tests/integration/test_graphtor_ingest_contract.py` that:
  - Runs docline against representative fixtures (PDF, DOCX, HTML, VTT).
  - Asserts emitted markdown passes:
    - YAML frontmatter parses with graphtor-docs's serde schema (Python-side equivalent assertions).
    - Heading hierarchy validation.
    - Forward-slash path invariant.
    - Re-running yields identical `content_sha256` (idempotency).
  - Optionally: spawn graphtor-docs sync against the output dir and assert chunk count > 0 (gated behind `pytest -m graphtor_integration` and graphtor-docs CLI availability).

## Suggested shipment decomposition (Stage will finalize)

| Feature | Scope | Depends on |
|---|---|---|
| **F1 — Shared frontmatter contract + path normalization + JSON Schema export** (G1 + G2 + G7 partial) | Foundation: Pydantic model changes, `posixify_path`, `content_sha256`, schema export | — |
| **F2 — Heading hierarchy validation in process pipeline** (G3) | `validate_heading_hierarchy`, integration into `assemble_markdown` | F1 |
| **F3 — DOCX style→heading mapping** (G4) | `readers/docx.py` rework with `<w:pStyle>`, list, table support | F2 |
| **F4 — PDF layout-aware extraction** (G5) | `readers/pdf.py` font-size heuristic; optional docling layout | F2 |
| **F5 — HTML semantic zones + sitemap + URL canonicalization** (G6) | `fetch/html_extract.py`, `fetch/crawl.py`, new `fetch/sitemap.py`, new `fetch/url_canonical.py` | F1 |
| **F6 — Staging metadata promotion to WebFrontmatter** (G8) | `WebFrontmatter` schema, `process/assemble.py` glue | F1, F5 |
| **F7 — Cross-tool contract doc + optional chunk anchors** (G9 + G10) | Design doc, README link, optional anchors config | F1, F2 |
| **F8 — Integration gate** (G11) | E2E test suite proving contract conformance | F1–F7 |

**Operational constraint:** 008-S (ELT multi-source ingestion) is currently ACTIVE on `feat/elt-multi-source-ingestion`. This new shipment will queue behind 008-S and 009-S; Ship cannot route it until both merge. Stage may proceed with planning under P-001 stage-only pipelining.

## Out of scope

- Cloud sources (S3, GCS, Azure Blob).
- Scheduled / continuous ingestion.
- Embedding generation in docline (graphtor-docs owns embeddings).
- Modifications to graphtor-docs itself (this is a docline-only deliverable; the only graphtor-docs touch is potentially vendoring docline's exported JSON Schema for validation, which is a separate concern).

## References

- graphtor-docs ingestion contract research: synthesized from `src/parse/frontmatter.rs`, `src/parse/chunker.rs`, `src/chunk/id.rs`, `src/db/schema.rs`, `src/db/vectors.rs`, `src/acquire/url.rs`.
- docline current state research: synthesized from `src/docline/schema/`, `src/docline/fetch/`, `src/docline/readers/`, `src/docline/process/`, plan inventory under `docs/plans/`.
