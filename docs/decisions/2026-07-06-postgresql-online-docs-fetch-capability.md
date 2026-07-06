---
title: "PostgreSQL online-docs processing — capability-gap analysis and execute_fetch decomposition"
type: spike
date: 2026-07-06
time_box: "1h"
conclusion: "proceed"
confidence: "high"
linked_parent_work_item: "054-F"
promoted_to: ["054-F"]
supersedes_stash: "DF4D5C3F"
tags:
  - "fetch"
  - "crawl"
  - "web-ingestion"
  - "postgresql"
  - "html"
  - "graphtor"
---

## Problem frame

The operator asked whether docline can process the **PostgreSQL online
documentation** (`https://www.postgresql.org/docs/current/`) and, if not, to
identify the required capabilities and stage the work. Unlike every corpus
docline has ingested to date (PDF/DOCX/VTT/local HTML/OpenAPI specs), this
source is **live web content that must be fetched and crawled first**, then
processed. This spike establishes exactly which capability is missing, how big
the gap is, and how to close it.

## Capability audit (grounded in code, 2026-07-06)

docline splits ingestion into two passes: **fetch** (I/O-bound crawl → staged
files) and **process** (compute-bound staged files → Markdown). The process
pass already handles staged HTML end-to-end; the fetch pass is where the gap is.

| Capability | Status | Evidence |
|---|---|---|
| Single-page HTTP fetch (timeout, SSRF-safe redirects) | **built + tested** | `fetch/http.py::fetch_page` (stdlib urllib, `_ValidatingRedirectHandler` re-validates every redirect target) |
| Bounded BFS crawl (robots, depth/page budgets, section-scope, backoff, JS-TOC discovery) | **built + tested** | `fetch/crawl.py::crawl` (L100), `_robots_allow`, `_fetch_with_retries`, `_derive_section_scope`, `_url_within_section_scope`, `compute_backoff_seconds`, `_discover_toc_links` |
| URL policy / SSRF guard (private-host + scheme deny) | **built + tested** | `fetch/url_policy.py::validate_crawl_url`, `is_private_host` |
| Sitemap discovery/parse (urlset, index, robots `Sitemap:`) | **built + tested** | `fetch/sitemap.py` (`parse_sitemap_urlset`, `discover_sitemaps_from_robots`, `validate_sitemap_url`) |
| Staging-job model + credential-sanitized cache path | **built + tested** | `fetch/staging.py::create_staging_job`, `fetch/models.py::StagingJob` |
| HTML → Markdown main-content extraction (DOM noise strip) | **built + tested** | `fetch/html_extract.py::extract_main_content`, `strip_dom_noise`; `fetch/html_normalize.py` |
| Process pass consuming staged HTML → Markdown + graph edges | **built + tested** | `app.py::execute_process` walks `metadata.json` jobs → `files/` dir + crawl-manifest; WebFrontmatter, canonical-URL, `resolve_cross_doc_links` |
| **`execute_fetch` orchestration (crawl → persist staged `files/` + manifest + `metadata.json`)** | **STUB — the gap** | `app.py::execute_fetch` returns `success=False, error="Fetch execution is not implemented."` |

**Conclusion:** every hard primitive already exists and is covered by tests
under `tests/fetch/`. The one missing piece is the **orchestration + staging
persistence** that ties `crawl()` → on-disk staging layout → `execute_process`.
This is a *wiring* feature, not a *build-a-crawler* feature.

## The precise gap

`execute_process` discovers work by walking `staging_dir.rglob("metadata.json")`,
requiring for each job:

1. a `metadata.json` = a serialized `StagingJob` with `complete=True`;
2. a sibling `files/` directory holding the staged source (e.g. `*.html`);
3. an optional crawl-manifest (`_load_crawl_manifest`) mapping staged file →
   source URL / canonical URL / order.

`crawl()` returns `list[CrawlResult]` (URL, depth, `FetchResponse` body,
skip flags) **in memory** and `create_staging_job()` returns a `StagingJob`
**model** — neither writes the `files/`, `metadata.json`, or crawl-manifest to
disk. `execute_fetch` must supply exactly that persistence bridge and map
`FetchRequest.depth` → `CrawlConfig` (depth + a sane `max_pages` budget).

## PostgreSQL source characteristics (probed 2026-07-06)

| Property | Finding | Implication |
|---|---|---|
| `robots.txt` | Allows `/docs/current/`; disallows `/docs/devel/`, `/search/`, `/message-id/*`, `/account/` | `crawl()`'s `respect_robots=True` default is correct; `/docs/current/` is crawlable |
| Sitemap | `robots.txt` advertises `Sitemap: https://www.postgresql.org/sitemap.xml` | Sitemap-driven discovery is available as an alternative/augment to BFS |
| Rendering | Static HTML; TOC is a `<table>`; doc-link `href`s are relative (`preface.html`, `intro-whatis.html`) | No headless browser needed; `extract_links` + section-scope BFS suffices |
| Content shape | Doc pages carry `<pre>` code blocks, tables, and Note/Warning admonitions; chapter/section nav | `extract_main_content` must preserve code fences, tables, and admonition semantics; version-nav chrome should be stripped as DOM noise |
| Cross-doc links | Relative `.html` links within `/docs/current/` | Feeds `resolve_cross_doc_links` → graph edges after the `.html`→`.md` mapping, valuable for graphtor unification |

`/docs/current/` is a well-behaved, robots-permitted, static-HTML corpus with a
sitemap — an ideal first real-world verification target for the fetch pass.

## Recommended approach (v1 scope)

1. **Orchestrate + persist (`execute_fetch`)** — run `asyncio.run(crawl(start_url, config))`,
   persist each non-skipped `CrawlResult` body to `{staging}/…/files/<slug>.html`,
   write a crawl-manifest (URL + canonical URL + order) and a complete
   `metadata.json`, and return `FetchResult(staged_path=…, success=True)`.
   Map `FetchRequest.depth` → `CrawlConfig.max_depth`; apply a bounded default
   `max_pages`. Preserve CLI/MCP parity (both call `execute_fetch`).
2. **Verify on PostgreSQL** — a bounded crawl of `/docs/current/` (page + depth
   caps, section-scope), then `execute_process`, then assess fidelity: tables,
   `<pre>` code fences, Note/Warning admonitions, canonical URL, and cross-doc
   edges. Use recorded fixtures for the deterministic test; a gated manual run
   confirms the live path.
3. **Fidelity fixes (as needed)** — close any `extract_main_content` /
   `html_normalize` gaps surfaced by step 2 (e.g. code-fence language, admonition
   rendering, version-nav chrome stripping).

Out of scope for v1: JS-rendered sites (headless browser), authenticated
sources, incremental re-crawl/delta, and `/docs/devel/` (robots-disallowed).

## Value proposition

Wiring `execute_fetch` turns docline from a *staged-file processor* into a
*self-serve web-doc ingestion pipeline*. It unlocks the entire class of online
documentation corpora (PostgreSQL, and by extension any robots-permitted static
HTML doc site) for graphtor's unified knowledge graph — reusing ~1,400 lines of
already-tested fetch primitives that currently have no entry point. The marginal
cost is orchestration + verification, not new subsystem construction.

## Decomposition (staged as 054-F)

- **T1** — `execute_fetch` web-crawl orchestration + staging persistence
  (crawl → `files/` + crawl-manifest + complete `metadata.json`; depth/page
  budgets; `FetchResult`; CLI/MCP parity). TDD with mocked network.
- **T2** — End-to-end PostgreSQL `/docs/current/` verification: bounded crawl →
  process → fidelity assessment (tables, code, admonitions, canonical URL,
  cross-doc edges), with recorded fixtures for a deterministic test.
- **T3** — HTML-extraction fidelity fixes for PostgreSQL doc patterns surfaced
  by T2 (only as needed).

Dependencies: T1 ← T2 ← T3.
