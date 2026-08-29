---
title: "Deliberation: Bound crawl frontier growth independently of depth/max_pages"
date: 2026-08-29
status: accepted
stage_session: "stash-to-backlog — crawl-resource group {173238FD}"
stash_ids: [173238FD]
---

## Problem frame

**173238FD** (bug, medium): `crawl()` in `src/docline/fetch/crawl.py` appends every unique,
in-scope discovered link to an in-memory `frontier: deque` (and records each in a `visited`
set) before the `while frontier and page_count < max_pages` guard stops *popping*. The loop
caps how many pages are **fetched** (`max_pages`) and how deep discovery goes (`max_depth`),
and per-response bytes are capped (`MAX_RESPONSE_BYTES`), aggregate bytes/attempts are capped
(`MAX_TOTAL_FETCH_BYTES` / `MAX_FETCH_ATTEMPTS`). But nothing caps the **size of the discovered
frontier itself**: a single fetched page with a large adversarial link fan-out can enqueue an
unbounded number of entries into `frontier` and `visited` even though only `max_pages` are ever
fetched. This is a memory-exhaustion (availability) gap, flagged by Copilot review on PR #169
(055-S) and deferred at the review-fix cycle-3 limit.

Grounded append sites (verified against origin/main @ 16970da): `crawl.py` frontier appends at
the print-page discovery branch and the main discovery branch; each guarded only by
`domain_lock`, section-scope, and `visited` dedup — none of which bounds total growth. `visited`
never shrinks, so it, not the popped `frontier`, dominates the resident footprint.

## Grouping decision

Ships **separately** from the SSRF group {87F2C06D, 0A56B201, 0A56B202}. This bug mutates
`crawl.py` frontier/queue management (an availability/resource concern); the SSRF group mutates
`url_policy` / `sitemap` / `http` address classification and pinning. No shared files, no
dependency edge — bundling would violate width isolation and couple unrelated review surfaces.
Parallel-shippable.

## Options considered

### Option A — Explicit total-frontier admission cap (chosen)

Add a `max_frontier` bound (config knob on `CrawlConfig`, default independent of `max_pages` /
`max_depth`, e.g. an absolute ceiling). Enforce at both append sites: once the number of URLs
admitted to the frontier for the crawl reaches the cap, drop further discovered links (the crawl
continues to completion with the links already admitted, honoring `max_pages`).

- Pros: bounds both `frontier` and `visited` growth with one counter; independent of depth /
  page budget as the bug requires; minimal, surgical; no behavior change under the cap.
- Cons: a crawl that legitimately needs a huge frontier drops late links — acceptable and
  observable (skip/debug signal), and configurable.

### Option B — Cap `frontier` deque length only

Bound `len(frontier)`; stop appending when full.

- Rejected as sole fix: `frontier` shrinks as entries are popped, so a length cap does not bound
  the monotonically growing `visited` set — the dominant footprint. Would under-protect.

### Option C — Per-page dedup/link cap

Limit links admitted per fetched page.

- Rejected as sole fix: `max_pages` pages x per-page cap still grows unboundedly with `max_pages`
  and does not give a hard whole-crawl ceiling. Weaker invariant than Option A. May be folded in
  as a secondary guard but the whole-crawl admission cap is the primary bound.

## Chosen direction

Deliver Feature B "Bound crawl frontier growth independently of depth/max_pages" (medium,
reliability) as a harness-first release unit: a harness pinning the invariant (an adversarial
link fan-out cannot grow the frontier/visited beyond the explicit cap; crawl still honors
`max_pages`/`max_depth`; the bound is independent of both), then an implementation adding the
`max_frontier` cap enforced at both append sites, with a `CrawlConfig` knob and a documented
default.

## Risk / hardening signals (feeds plan-harden)

- Moderate blast radius: changes the core crawl loop on the live fetch path. **Requires plan
  hardening: yes** — reliability-critical loop, needs explicit rollback + a default that cannot
  shrink existing legitimate crawls.
- Correctness risk: the cap must not change results for crawls below the cap (regression guard),
  and must not deadlock or skip the start URL. Preserve breadth-first order for admitted links.
- Observability: dropped links should be countable/loggable, not silent, so operators can detect
  when a crawl hit the ceiling.

## Open questions

- Exact default `max_frontier` value — settled in the plan/harness; must be generous enough to
  not affect realistic documentation-site crawls yet bound adversarial fan-out.
- Whether to also emit a `CrawlResult` skip marker for the ceiling event or only a debug log —
  resolved during harness design.
