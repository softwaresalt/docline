---
title: "Closure — 054-F execute_fetch web-crawl + DocBook HTML fidelity"
status: verified
feature: 054-F
merged_pr: 147
merge_sha: 6825a7d
date: 2026-07-06
---

Turned docline from a staged-file processor into a self-serve web-doc ingestion
pipeline: the previously-stubbed `execute_fetch` now fetches and crawls online
HTML end-to-end, and the HTML extractor renders DocBook structure with fidelity.
Verified against the real PostgreSQL online documentation
(`https://www.postgresql.org/docs/current/`).

## What shipped

- **T1 — `execute_fetch` orchestration** (`src/docline/app.py`): the stub is
  replaced by a thin adapter that wraps the request URL as a `WebCrawlSource`
  and delegates to the already-tested ELT staging machinery
  (`elt/execute.py::execute_source_configs`). It enforces an `http(s)` scheme
  and workspace containment, maps `FetchRequest.depth` → `CrawlConfig.max_depth`
  (page budget bounded by the `CrawlConfig` default), and produces the same
  `metadata.json` + `files/` + `crawl-manifest.json` layout `execute_process`
  consumes — so the MCP fetch tool and the CLI/ELT path stage identically.
  SSRF / robots / URL-policy guards remain enforced by the crawler.
- **T2 — verification**: live bounded fetch+process of real PostgreSQL pages
  confirmed the end-to-end path and surfaced the extractor gaps below.
- **T3 — DocBook HTML fidelity** (`src/docline/fetch/html_extract.py`):
  `<pre>` → fenced code, `<table>` → GitHub-flavored Markdown table
  (pipe-escaped, width-normalized), DocBook admonitions
  (`note`/`caution`/`warning`/`tip`/`important`) → labeled blockquotes,
  `.navheader`/`.navfooter` chrome stripped, and extraction scoped to the
  DocBook content container (`.book`/`.chapter`/`.refentry`/`.sect1`) so site
  chrome (version switcher, search) is excluded. Non-DocBook pages fall back to
  article/main/body unchanged.

## Verification (real PostgreSQL data)

| Page | code fences | table rows | admonitions | chrome leak |
|---|---|---|---|---|
| `sql-select.html` (reference) | 72 | 0* | 2 | none |
| `datatype-numeric.html` (data types) | 18 | 12 | 8 | none |

*The SQL SELECT parameters are `<dl>` lists, not `<table>` — 0 is correct.

- 14 new tests (7 `execute_fetch`, 7 `html_extract`); all offline (crawl seam
  mocked, `tmp_path` isolated). MCP/parity tests updated to the new contract and
  kept offline (unsupported-scheme sources — no live network, no `.cache`
  pollution).
- Full suite: 1560 passed, 6 skipped; ruff + pyright + format clean.
- Adversarial review focused on the remote-fetch / HTML-parse / path-containment
  surface: SSRF defense-in-depth intact, all writes contained, no code
  execution. Copilot review: no comments.

## Deferred follow-ups

`<dl>` parameter-list rendering, table colspan/rowspan, `<pre>` language hints,
`canonical_url` stamping for non-Learn hosts (`source_url`/`final_url` are
already captured — no data loss), and larger multi-page crawls via the ELT
config path. None block the shipped capability.
