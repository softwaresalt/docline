---
title: "canonical_url coverage on real MS Learn corpora + deferred-derivation ROI"
type: spike
date: 2026-07-04
time_box: "4h"
conclusion: "proceed"
confidence: "high"
linked_parent_work_item: "044-F"
promoted_to: ["ask"]
tags:
  - "canonical-url"
  - "graphtor"
  - "openpublishing"
  - "coverage"
---

## Goal

Measure v1 `canonical_url` (feature 044-F) coverage on real Microsoft Learn
corpora, determine the reliable URL-prefix derivation source, and rank the
deferred derivation work (monikers, redirect maps, depot mappings, base-path
fallback) by ROI.

## Success Criteria

Quantitative coverage of v1 vs a prototype on real repos, a decomposition of
the cross-product link-resolution gap, and an ROI-ranked recommendation for
what (if anything) to build next.

## Scope Constraints

Read-only analysis of the operator-provided corpus at `C:\Source\Docs`. No
changes to docline or graphtor. Prototype derivation lived in throwaway scripts
under `logs/` (not committed to `src/`).

## Corpus

`C:\Source\Docs\`: fabric-docs, powerbi-docs, query-docs (dax + m), bi-shared-docs
(analysis-services), nosql-docs (5 docsets incl. cosmos-db), azure-docs,
azure-docs-sdk-dotnet, fabric-rest-api-specs. Measurement focused on the BI graph
the operator cares about (fabric, powerbi, dax, m, analysis-services, nosql):
**8,113 docs, 12,771 absolute links.**

## Investigation Approach

1. Inspect real `.openpublishing.publish.config.json` + `docfx.json` per repo.
2. Prototype a breadcrumb_path-derived prefix and measure doc coverage vs v1.
3. Scan absolute (`/path`) cross-product links; measure resolution against the
   derived canonical_url index; bucket the unresolved.
4. Reverse-map in-corpus unresolved links to files to separate derivation bugs
   from redirects/hubs.
5. Confirm redirect-data availability. Rank deferred items by ROI.

## Findings

### 1. v1 is ~0% on real corpora — the field it needs is absent

**No repo sets `docsets_to_publish[].url_path_prefix`** (all `None`), and
`docfx.json` `globalMetadata.base_path` is also absent. v1 `derive_canonical_url`
returns `None` for every doc → **v1 coverage ≈ 0%.** The shipped 044-F is
non-functional on real MS Learn repos.

### 2. `breadcrumb_path` is the real prefix signal — 0% → 83.3% doc coverage

`docfx.json` `globalMetadata.breadcrumb_path` encodes the prefix. Deriving the
prefix as "the path before the `breadcrumb`/`bread` segment":

| Docset | breadcrumb-derived prefix |
|---|---|
| fabric-docs (`docs`) | `/fabric` |
| powerbi-docs (`powerbi-docs`) | `/power-bi` |
| query-docs (`query-languages/dax`) | `/dax` |
| query-docs (`query-languages/m`) | `/powerquery-m` |
| bi-shared-docs (`docs`) | `/analysis-services` |
| nosql-docs (all 5 docsets) | **`None`** (`~/breadcrumb/...` relative form) |

Doc coverage: fabric/powerbi/dax/m/analysis-services = **100% each**; nosql =
**0%** (1,358 docs). **Total 6,755 / 8,113 = 83.3%** (vs v1 0%).

**Derivation accuracy is exact:** of the in-corpus unresolved links, **0** map to
an existing file — the breadcrumb derivation never produced a wrong URL for a
real doc.

### 3. Cross-product link resolution (21.2%) is dominated by un-ingested products

Of 12,771 absolute links, 2,712 (21.2%) resolved. The unresolved are dominated by
**external products not in the corpus**: `/azure` (2,472), `/sql` (2,060),
`/rest` (1,184), `/dotnet` (382), `/powershell` (285), `/entra` (269),
`/cli` (220), `/microsoft-365` (190), `/javascript` (122), … This is
**corpus completeness**, not a derivation defect — those repos were simply not
ingested.

### 4. In-corpus unresolved links (856) are 100% redirects — and the data exists

Links to in-corpus products (`/power-bi` 373, `/fabric` 230, `/analysis-services`
230) that don't resolve: reverse-mapping shows **856/856 have no source file**
(0 derivation mismatches). Samples are classic renamed slugs
(`/power-bi/enterprise/service-admin-disable-self-service`, …). The
`.openpublishing.redirection.json` files carry the fix data:
**powerbi 1,563, bi-shared 996, query 26 redirect entries** (fabric 0, nosql none).
These are at repo roots, not listed in the config's `redirection_files` field
(hence the earlier `redirection_files=0`).

## Recommendation

**Conclusion**: proceed (roadmap pivot)
**Confidence**: high

The original worry list (monikers / depot / base-path) was wrong about priority.
The data says: **breadcrumb derivation + redirect maps are the levers**, and v1's
`url_path_prefix` assumption must be replaced. ROI ranking:

1. **[ADOPT — highest] Breadcrumb-path prefix derivation.** Replaces the broken
   `url_path_prefix`-only v1. 0% → 83% doc coverage, deterministic, exact. Small.
   This is not a "nice-to-have deferral" — it's making 044-F actually work.
2. **[PROTOTYPE — high in-corpus win] Redirect-map application.** Apply
   `.openpublishing.redirection.json` so links to renamed slugs resolve to the
   current canonical_url. Recovers the entire in-corpus unresolved bucket
   (856 here; scales with redirect volume — powerbi alone has 1,563 entries).
   Structured JSON; tractable.
3. **[PROTOTYPE — medium] `~/`-breadcrumb + nested-prefix fallback.** Recovers the
   nosql/cosmos-db family (16.7% of docs, 0% today; cosmos-db → nested
   `/azure/cosmos-db`). Needs a depot-mapping read or a small per-docset override
   table. Medium complexity.
4. **[DEFER — low] Monikers.** Not a dominant failure class here (the in-corpus
   gap was 100% redirects, not `?view=` mismatches). Revisit if versioned-content
   links prove significant on other corpora.
5. **[OPERATOR SCOPE — not docline] Corpus completeness.** The biggest unresolved
   buckets (`/azure`, `/sql`, `/rest`…) are un-ingested products; resolving them
   means ingesting those repos, not a derivation feature.

## Next Steps

- Plan a **canonical_url v2** feature: breadcrumb-path derivation (item 1) +
  redirect-map application (item 2), with a nested/depot fallback (item 3) for
  `~/`-breadcrumb docsets. Defer monikers.
- Note for graphtor Option B: the derived `canonical_url` is a sound cross-source
  key for the 83%+ of docs it covers; redirect application further closes the
  in-corpus link gap.

## References

- Prototype harnesses: `logs/spike_coverage.py`, `logs/spike_incorpus.py` (throwaway).
- `src/docline/process/canonical_url.py` (v1); feature 044-F (shipped 047-S).
- `docs/decisions/2026-07-03-graphtor-cross-repo-link-resolution-spike.md`.
- Corpus: `C:\Source\Docs\{fabric,powerbi,query,bi-shared,nosql}-docs`.
