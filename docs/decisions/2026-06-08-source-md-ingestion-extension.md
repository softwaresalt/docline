---
title: Source-markdown ingestion — strategic extension to extraction study
date: 2026-06-08
status: decided
related_decisions:
  - docs/decisions/2026-06-08-extraction-strategy-study.md
related_closures:
  - docs/closure/021-S-triage-then-repair.md
  - docs/closure/022-S-pa4-closure.md
study_artifacts:
  - .elt/output/source-md-spike/postgresql-source-md-metrics.json
---

## Question

If we could **download source markdown from a GitHub repo** for a
corpus (rather than extracting from the published PDF), would that
change docline's strategic direction?

## Answer

**Yes — fundamentally.** It changes docline from "primarily an
extraction pipeline" to "primarily a source-routing + normalization
pipeline, with extraction as fallback."

## Empirical spike (2026-06-08 ~22:00 PT)

Cosmos DB source MD has been moved to a private repo (Microsoft has
been making service docs progressively private). But **Azure
PostgreSQL** docs remain public in
`MicrosoftDocs/azure-databases-docs/articles/postgresql/` — same
structural family as cosmos (technical reference, includes code,
tables, headings, cross-doc links). Used as proxy.

Sampled **10 files** spanning sizes (5 KB → 34 KB) across 6 subdirs
(security, monitoring, configure-maintain, high-availability, migrate,
postgresql root). Fetched via raw GitHub URL, parsed with
markdown-it-py, ran the same AST metrics as the 2026-06-08 study.

### Per-1000-char structural density (normalized for fair comparison)

| Engine | Density | Heading / 1k | Table cells / 1k | Sections / 1k |
|---|---|---|---|---|
| markitdown | 2.62 | 0.018 | 0.771 | 0.036 |
| docling | 6.80 | 1.601 | 1.567 | 1.615 |
| **source-md** | **9.14** | 1.331 | **3.770** | 1.407 |

### Cost per page (rough orders of magnitude)

| Engine | Per-page wall-clock |
|---|---|
| markitdown | 1-2 sec |
| docling (rt_detr layout) | 15-30 sec |
| **source-md fetch + parse** | **0.1-0.5 sec** |

For the 3,426-page cosmos PDF:
- Docling all-pages: 4-9 hours
- Triage (53% flagged): 4 hours (verified)
- **Source-MD equivalent (if accessible)**: probably **< 5 minutes**
  total wall-clock, plus one-time repo clone / sparse-fetch

## Why source MD beats docling on quality

1. **Source IS ground truth.** Author wrote markdown directly. No
   inference needed — docling's whole 15-30 sec/page cost is spent
   recovering structure the author already encoded.
2. **Tables are dramatically richer**: 3.77 cells/1k chars vs
   docling's 1.57 — author tables are perfectly structured;
   PDF-rendered tables lose cell alignment data that docling has
   to re-infer (lossy).
3. **YAML frontmatter for free**: titles, ms.topic, ms.date, author,
   tags — all structured metadata that PDFs strip and that docling
   cannot recover.
4. **Cross-doc links are first-class graph edges**: source MD uses
   relative paths `[Provisioned throughput](provision-throughput.md)`
   that map directly to graph relationships. Docling output (and
   markitdown output) has these as raw URL text without semantic
   structure.

## Why source MD wins for the stated use cases

| Use case | Why source MD is the right primary engine |
|---|---|
| **Vector embeddings** | YAML frontmatter feeds doc-level metadata; heading-anchored sections at median 542 chars are near-optimal direct embedding chunks |
| **Graph DB** | Cross-doc relative links → graph edges by construction; `ms.topic`, `ms.author` → node attributes for free; doc hierarchy from TOC.yml → graph parent/child |
| **LLM context** | Token-efficient by definition (the author's canonical form); structured frontmatter lets the LLM see metadata without consuming context |

## What this means for docline's architecture

The current design treats **extraction** (PDF/DOCX/HTML → markdown)
as the primary value proposition. The roadmap from
`docs/plans/2026-06-08-extraction-strategy-roadmap.md` focuses on
making extraction better (scoring inversion, docling speedup, etc.).

The new framing: **docline becomes a source-aware ingestion router**:

1. **First**: detect whether source MD is available for the input
   (e.g., is the input URL a Microsoft Learn / AWS Docs / Kubernetes
   docs / React docs page? Is there a known mapping to a source repo?)
2. **If yes**: fetch source MD, normalize via a small adapter, emit
   docline's standard output
3. **If no**: fall back to the existing extraction pipeline
   (docling primary per the 2026-06-08 study)

The existing extraction work (021-S, 022-S, the planned 024-S scoring
inversion) is **NOT wasted** — it remains essential for the long tail:
- Vendor PDFs without published source
- Scanned/OCR'd documents
- Legal contracts and proprietary docs
- Books, papers, articles without authorial markdown
- Internal corporate docs in Office formats

But the **showcase case** (Cosmos DB docs, Azure docs, AWS docs, K8s
docs, anything in a public docs repo) flows through the new source
pathway and gets dramatically faster + better output.

## Capabilities needed for the new path

1. **URL-to-source-repo mapping**: published doc URL ↔ source repo
   path. Microsoft Learn, AWS Docs, K8s, React, Python — each has
   a discoverable mapping (often via the `<meta name="github_url">`
   on the published HTML page).
2. **Repo discovery / caching**: shallow clone or sparse-checkout
   the source repo on first use; refresh on demand.
3. **DocFx adapter**: handle Microsoft-flavored markdown extensions
   (`:::` containers, `[!INCLUDE]` directives, code references).
4. **Generic markdown normalization**: convert flavors (MkDocs,
   Sphinx-RST, DocFx, GFM, CommonMark) to a canonical AST.
5. **Asset handling**: bundle or rewrite image references.
6. **Link resolution**: rewrite relative `.md` links to canonical URLs.
7. **Manifest synthesis**: emit docline's standard output format
   from the source MD, preserving the source provenance.

## Comparable open-source corpora (validates broad applicability)

| Corpus | Source repo | Visibility |
|---|---|---|
| Azure docs (many services) | `MicrosoftDocs/azure-*-docs` | partly public |
| PowerShell docs | `MicrosoftDocs/PowerShell-Docs` | public |
| SQL Server docs | `MicrosoftDocs/sql-docs` | public |
| Kubernetes | `kubernetes/website` | public |
| React | `reactjs/react.dev` | public |
| Python | `python/cpython/Doc/` (RST, similar principle) | public |
| Node.js | `nodejs/node/doc/api/` | public |
| Rust book | `rust-lang/book` | public |
| Most OSS libraries | their own `docs/` + `README.md` trees | public |

Any of these would benefit from the same source-MD pathway. The
pattern generalizes.

## Risks / costs

1. **License compliance**: respect each repo's LICENSE for cached
   content. Most docs repos are CC-BY or similar — attribution
   needed in downstream outputs.
2. **DocFx extension complexity**: not all custom syntax is trivial.
   `[!INCLUDE]` is straightforward; `:::moniker-end` zone-pivots
   need careful handling.
3. **URL-mapping fragility**: published URLs change; mapping needs
   to be robust to redirects.
4. **Source ≠ rendered**: the published version may include zone-
   pivots, conditional content, or includes that aren't visible
   in any one source file alone. May need partial assembly.
5. **Source-private corpora**: Cosmos DB specifically is now in a
   private repo. The source-MD pathway can't help when there's no
   public source. Extraction remains the only option there.
6. **Versioning**: which branch/tag for stable extraction? Most
   repos have `main`/`live` but some have versioned docs.

## Updated roadmap (extends `docs/plans/2026-06-08-extraction-strategy-roadmap.md`)

The new direction adds a **026-S shipment** to the roadmap, **before**
the existing 024-S scoring inversion work:

| Shipment | Theme | Stash(es) |
|---|---|---|
| **023-S** | Strategy alignment (existing roadmap) | `13F608BA` `378C8BC0` `A39C3704` `5A622B72` |
| **NEW: 026-S** | Source-MD ingestion pathway (NEW) | `<TBD>` (this decision) |
| **024-S** | Scoring inversion (downgraded — fewer pages will need scoring once 026-S routes around extraction) | `EFC6C84E` |
| **025-S** | Docling speedup (downgraded — fewer pages need docling once 026-S handles source-available corpora) | `51332802` |
| **research** | Generalization study | `4CB606D5` |

026-S sequence:
1. Spike: build minimal URL-to-source-repo mapper for Microsoft Learn
   (publicly documented via `<meta name="github_url">`); validate
   round-trip on 5-10 cosmos / azure-sql / postgresql pages
2. Implement source-MD adapter for DocFx flavor
3. Add `--source mode=auto|extract|source-md` CLI flag
4. Add manifest provenance: emit `docline:source_type` (extract /
   source-md) and `docline:source_repo` (when applicable)
5. Verify on a small Azure docs slice: source-MD path produces
   equivalent or better AST quality than docling at 100× lower cost

## Verdict

**Yes, this changes the game.** Source MD ingestion should become
docline's primary path for any corpus with public source. The
extraction pipeline remains essential for the (still very large) long
tail of docs without source — and the prior 022-S / extraction study
work continues to matter for that tail.

Capture as new high-priority stash, restructure roadmap to insert
026-S before 024-S.
