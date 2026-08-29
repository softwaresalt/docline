---
type: session-memory
title: "Stage session — SSRF classifier+pinning and crawl-frontier shipments"
date: 2026-08-29
agent: stage
status: complete
---

## Scope

Processed all 4 remaining active stash entries end-to-end through Stage on an isolated worktree
cut from origin/main @ 16970da (branch `stage/ssrf-pinning-crawl-frontier`).

## Grouping (contextual/code similarity)

- **057-S** (SSRF, priority high): {87F2C06D consolidate, 0A56B201 TOCTOU pinning, 0A56B202
  metadata normalization} — one coherent security surface (`url_policy`/`sitemap`/`http`).
- **058-S** (crawl frontier, priority medium): {173238FD} — independent `crawl.py` availability
  concern; no shared files or deps with the SSRF group. Confirmed parallel-shippable.

## Key grounding

- `url_policy.is_unsafe_resolved_address` (live) and `sitemap._is_unsafe_address` (dormant, zero
  `src/` callers) are divergent copies; sitemap lacks the ULA `fc00::/7` check.
- `http._Pinned*Connection` + `resolve_and_validate` already pin+validate+connect atomically with
  `server_hostname=hostname` (SNI/cert). Sitemap fix must route through the public
  `fetch_page`/`build_fetch_opener` sink, not private classes.
- Import graph acyclic: `url_policy` imports only stdlib/schema; `sitemap -> http -> url_policy` DAG.

## Backlog created

- Feature A **066-F** (from 87F2C06D): tasks 066.001-T..066.006-T (harness/impl pairs; 0A56B202
  → 066.004-T, 0A56B201 → 066.006-T). Deps: .002<-.001, .003<-.002, .004<-.003, .005<-.002,
  .006<-.005, .006<-.004.
- Feature B **067-F** (from 173238FD): tasks 067.001-T (harness), 067.002-T (impl, <-067.001-T).
- Semantic links: 066-F related_to 064-F, 065-F; 067-F related_to 055-S.
- Shipments: **057-S** (066-F + 6 tasks, high), **058-S** (067-F + 2 tasks, medium), both queued.
- All 4 stash entries harvested (state=harvested) with durable stash_links.

## Plan review (multi-persona adversarial) — PASS after fixes

Reviewers: Security Lens (gpt-5.6-sol), Architecture Strategist (gpt-5.6-terra), Scope Auditor
(claude-sonnet-4.6). No P0. Fixes folded into plans:

- Added IPv6 site-local `fec0::/10` + CVE-2024-4032-prefix explicit checks to the canonical
  predicate (Security P1 x2).
- Metadata gate redesigned as normalized parsed-object comparison with a routable sentinel to
  avoid a false-green harness (Security P2).
- Sitemap fix bound to the public `fetch_page`/`build_fetch_opener` sink (proxy suppression +
  redirect revalidation + pinning as one unit) (Security/Arch/Scope P2).
- Added `066.004-T -> 066.006-T` join so the full-suite green gate is attainable (Arch P2).
- Crawl: precise invariant (cap bounds discovered-link admissions; seed/final-URL/redirect-alias
  `visited` growth bounded by the absolute `MAX_FETCH_ATTEMPTS` budget, NOT `max_pages` x
  `max_redirects` since `page_count` skips print-page/duplicate-final branches and `max_redirects`
  is configurable; total resident keys <= `MAX_FETCH_ATTEMPTS + max_frontier`); 4 scenario groups
  incl. a non-page-counting branch; debug-log-only observability; explicit default
  `MAX_FRONTIER = 10_000` (Arch P1 + Scope P2/P3).

## Artifacts

- docs/decisions/2026-08-29-ssrf-classifier-pinning-deliberation.md
- docs/decisions/2026-08-29-crawl-frontier-bound-deliberation.md
- docs/plans/2026-08-29-ssrf-classifier-pinning-plan.md
- docs/plans/2026-08-29-crawl-frontier-bound-plan.md

## Validation

Hierarchy consistent (paths `066/066.00X`, `067/067.00X`); no orphans; doctor flagged nothing on
066/067 (168 pre-existing archive warnings unrelated); 7 acyclic dependency edges, red-before-green;
frontmatter valid; index synced (419 artifacts).

## Next

Commit + push staging artifacts, open staging PR, Copilot review cycle, merge. Ship claims 057-S
then 058-S (priority order).
