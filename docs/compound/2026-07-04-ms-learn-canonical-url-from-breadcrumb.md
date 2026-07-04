---
date: 2026-07-04
category: ms-learn-canonical-url-from-breadcrumb
keywords: [canonical-url, openpublishing, docfx, breadcrumb_path, url_path_prefix, redirection, graphtor, ms-learn, coverage, cross-product-links]
confidence: high
evidence: 045-F spike 2026-07-04 — measured on 8113 docs / 12771 links across C:\Source\Docs (fabric, powerbi, query, bi-shared, nosql)
---

# MS Learn canonical URL prefix comes from docfx `breadcrumb_path`, not openpublishing `url_path_prefix`

## Problem

docline's `canonical_url` v1 (feature 044-F) derives the URL prefix from
`.openpublishing.publish.config.json` → `docsets_to_publish[].url_path_prefix`.
Measured against real Microsoft Learn repos, **that field is never set** (all
`None`), so `derive_canonical_url` returns `None` for every doc → **~0% coverage**.
The shipped feature is non-functional on real corpora.

## Root Cause

`url_path_prefix` is essentially absent in real MS Learn OpenPublishing configs,
and `docfx.json` `globalMetadata.base_path` is absent too. The URL prefix is
actually encoded in `docfx.json` → `build.globalMetadata.breadcrumb_path`.

## Resolution / Facts

- **Derive the prefix from `breadcrumb_path`**: take the path segments *before*
  the `breadcrumb`/`bread` segment.
  - `/dax/breadcrumb/toc.json` → `/dax`; `/powerquery-m/breadcrumb/toc.json` →
    `/powerquery-m`; `/analysis-services/breadcrumb/toc.json` →
    `/analysis-services`; `/azure/bread/toc.json` → `/azure` (note `bread`, not
    `breadcrumb` — the second segment name varies).
  - This yields **83% doc coverage** and is **exact** — 0 wrong URLs for existing
    files (verified by reverse-mapping unresolved links to files).
- **`~/`-relative breadcrumb does NOT encode the prefix**: e.g. nosql cosmos-db
  is `~/breadcrumb/cosmos-db/toc.yml`, yet the doc publishes at the *nested*
  `/azure/cosmos-db/`. Those docsets (the nosql family, ~17% of docs) need a
  depot-mapping (`_op_documentIdPathDepotMapping`) or per-docset override.
- **Redirect data lives at repo roots** in `.openpublishing.redirection.json`
  (powerbi **1,563**, bi-shared **996** entries), **not** in the config's
  `redirection_files` field (which was empty). In-corpus unresolved cross-product
  links were **100% redirects** (renamed slugs with no source file), not
  derivation errors.
- Cross-product link non-resolution is otherwise dominated by **un-ingested
  products** (`/azure`, `/sql`, `/rest`, …) — a corpus-completeness matter, not a
  derivation defect.

## Prevention / Guidance

When deriving MS Learn canonical URLs in docline: use `breadcrumb_path` as the
**primary** prefix source and treat `url_path_prefix` as a rarely-present
override; read `.openpublishing.redirection.json` directly from repo roots (don't
rely on the `redirection_files` config field); expect `~/`-relative breadcrumbs +
Azure-nested prefixes (`/azure/<product>`) for the nosql/documentdb family;
monikers were not a meaningful failure class on this corpus (defer).

## Citations

- docs/decisions/2026-07-04-canonical-url-coverage-spike.md (045-F spike findings)
- docs/decisions/2026-07-03-graphtor-cross-repo-link-resolution-spike.md
- src/docline/process/canonical_url.py (v1, feature 044-F, shipped 047-S)
