---
title: "Implementation Plan: Bound crawl frontier growth independently of depth/max_pages"
date: 2026-08-29
status: shipped
shipment: 058-S
pr: 175
merge_commit: b1f4549e308b25a02dbd3f30eb6d87bf8a126331
feature: "Feature B (crawl frontier)"
source_deliberation: docs/decisions/2026-08-29-crawl-frontier-bound-deliberation.md
stash_ids: [173238FD]
requires_plan_hardening: yes
---

## Objective

Add an explicit whole-crawl frontier admission cap to `crawl()` so an adversarial link fan-out
cannot grow the in-memory `frontier` deque and `visited` set without bound, independently of
`max_pages` and `max_depth`, without changing results for crawls that stay under the cap.

## Grounding (origin/main @ 16970da)

- `crawl()` in `src/docline/fetch/crawl.py`: `frontier: deque[tuple[str, int]]` seeded with the
  start URL; `visited: set[str]` seeded with the start dedup key. The `while frontier and
  page_count < max_pages` guard bounds pops (fetches), not enqueues.
- Two append sites admit discovered links after `domain_lock` + section-scope + `visited` dedup:
  the print-page discovery branch and the main discovery branch. Each does
  `visited.add(link_key); frontier.append((link, depth + 1))`.
- `visited` never shrinks and dominates the resident footprint; `frontier` shrinks as popped.
- `CrawlConfig` is a frozen dataclass of budget knobs (`max_pages`, `max_depth`, etc.); the
  natural home for a `max_frontier` knob.
- Byte/attempt budgets (`MAX_RESPONSE_BYTES`, `MAX_TOTAL_FETCH_BYTES`, `MAX_FETCH_ATTEMPTS`)
  bound bytes and outbound attempts but not the discovered-URL set size.

## Constitution Check

- I. Safety-First Python: typed exceptions; full type hints; new knob typed on `CrawlConfig`.
  PASS.
- II. Test-First: harness-first; red harness precedes green impl via dependency edge. PASS.
- VI. Single Responsibility: one bounded-growth guard; no new dependency; reuses existing config
  surface. PASS.
- No dead code; no behavior change under the cap.

## Task decomposition (harness-first, <=2h each, width-isolated)

### B.T1 — Harness: bounded frontier admission under adversarial link fan-out (red)

- Domain: tests. Files: `tests/fetch/` (extend the `test_crawl_limits.py` pattern).
- Four scenario groups:
  1. A fetched page advertising a discovered-link fan-out far larger than `max_frontier` does
     not admit more than the cap, and the crawl still honors `max_pages` and `max_depth`.
  2. Independence: a small `max_frontier` with a large `max_pages`/`max_depth` still bounds
     admissions (the cap is not derived from either budget).
  3. Under-cap regression: a crawl whose discovery stays below the cap produces identical results
     with and without the cap (uses the exact default `max_frontier`).
  4. Non-page-counting branches do not circumvent the intended bound: distinct final URLs reached
     via print-page, duplicate-final, and redirect-alias paths (which do **not** all increment
     `page_count`) are admitted to `visited` only within the absolute per-request
     `MAX_FETCH_ATTEMPTS` budget, and the discovered-link admission cap is what bounds fan-out
     growth. Exercise at least one non-page-counting branch (e.g. a redirect chain to a distinct
     final URL) so the harness pins the real envelope, not `max_pages`.
- AC: harness compiles; tests fail (red) against the current unbounded append. Depends on: none.

### B.T2 — Enforce explicit frontier admission cap in the crawl loop (green)

- Domain: src. Files: `src/docline/fetch/crawl.py` (+ `CrawlConfig` knob in the same module).
- Add `max_frontier: int` to `CrawlConfig` with an explicit module-level default constant
  `MAX_FRONTIER = 10_000` (absolute, independent of `max_pages`/`max_depth`; overridable). Track
  the count of **discovered links admitted to the frontier**; at both discovery append sites, stop
  admitting once the cap is reached, emitting a debug log at drop time (no counter field, no
  `CrawlResult` marker). Preserve breadth-first order for admitted links; never drop the start URL.
  The crawl runs to completion with the admitted set.
- AC: B.T1 greens; a crawl below the default is unchanged; the start URL is always crawled and the
  loop terminates; `ruff`/`pyright`/`pytest` clean. Depends on B.T1.

## Bound scope (precise invariant)

The cap bounds the **only unbounded growth vector**: discovered-link admissions at the two
discovery branches, where a single page can enqueue arbitrarily many links. The other `visited`
insertions — the seed key, each fetched page's final-URL key, and redirect-alias keys — are
already bounded by the absolute per-request `MAX_FETCH_ATTEMPTS` budget (every outbound attempt and
every followed redirect debits it), **not** by `max_pages` x `max_redirects` (`page_count` is not
incremented for print-page, duplicate-final, or some scope-skip branches, and `max_redirects` is
configurable). They are not the exhaustion vector and are explicitly out of scope for the new cap;
so total resident identity keys are bounded by `MAX_FETCH_ATTEMPTS + max_frontier`. B.T1 scenario 4
pins that non-page-counting branches stay within the `MAX_FETCH_ATTEMPTS` envelope.

## Dependency graph

```text
B.T1 -> B.T2
```

Acyclic. Red harness precedes green impl.

## Plan review outcome

Multi-persona adversarial plan review (Architecture Strategist, Scope Boundary Auditor). Verdict:
**PASS after fixes**. Fixes folded in above:

- Precisely scoped the cap to discovered-link admissions (the unbounded vector) and documented
  that seed/final-URL/redirect-alias `visited` growth is already bounded by `max_pages` x
  `MAX_REDIRECTS`; added B.T1 scenario 4 with distinct redirect final URLs (Architecture P1).
- Collapsed B.T1 to four scenario groups and moved observability out of the red-harness core
  (Scope P2).
- Reduced B.T2 observability to a debug log on drop; deferred any counter/`CrawlResult` marker
  (Scope P3).
- Pinned an explicit default `MAX_FRONTIER = 10_000` with a regression scenario at that value
  (Scope P3).

## Plan Hardening

- **Risk class: moderate** (core crawl loop, live fetch path). ProposedAction: add admission cap.
  Rollback: single-shipment revert; the cap is additive and inert below the ceiling.
- **Default-safety guard**: `MAX_FRONTIER = 10_000` is generous for realistic documentation-site
  crawls at the default budgets; B.T1 scenario 3 proves an under-cap crawl is byte-for-byte
  unchanged.
- **Liveness guard**: the cap refuses only *new* admissions past the ceiling; it never deadlocks,
  skips the start URL, or drops already-admitted entries. B.T1 asserts the start URL is always
  crawled and the loop terminates.
- **Ordering guard**: breadth-first discovery order for admitted links is preserved (append-time
  cap, not reorder).
- **Observability guard**: a debug log at drop time makes ceiling hits detectable (Principle V)
  without new data structures.

## Verification

- Gates in order: `ruff check .`, `pyright src/`, `pytest`, `ruff format --check .`.
- Targeted: `pytest tests/fetch/test_crawl_limits.py` plus the new frontier-bound tests.
- Runtime spot-check (Ship closure): crawl a synthetic high-fan-out fixture and confirm bounded
  `frontier`/`visited` and honored `max_pages`.

## Rollback

Revert the shipment merge commit. Single-module (`crawl.py`) change, no data/config migration.
Inert below the ceiling, so revert risk is low.
