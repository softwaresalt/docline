---
type: decided-plan
source_plan: 2026-08-29-crawl-frontier-bound-plan.md
consolidated_at: 2026-08-29
status: shipped
shipment: 058-S
pr: 175
merge_commit: b1f4549e308b25a02dbd3f30eb6d87bf8a126331
---

## Decision Summary

`crawl()` grew its in-memory `frontier` deque and `visited` set from every unique in-scope
discovered link, while the loop guard bounded only pops (fetches). An adversarial link fan-out
could therefore expand resident state without bound even though per-response bytes and fetched
pages were already capped.

The shipped decision adds a whole-crawl **discovered-link admission ceiling**,
`CrawlConfig.max_frontier`, defaulting to the module constant `MAX_FRONTIER = 10_000`. The ceiling
is absolute and independent of `max_pages` and `max_depth`, and is overridable per crawl. It binds
the one genuinely unbounded vector — discovered-link admissions at the two discovery branches —
and leaves seed, final-URL, and redirect-alias keys to the existing absolute `MAX_FETCH_ATTEMPTS`
budget. Total resident identity keys are therefore bounded by `MAX_FETCH_ATTEMPTS + max_frontier`.

## Implementation Units

* Unit 1 (`067.001-T`): red harness in `tests/fetch/test_crawl_frontier_bound.py` covering
  adversarial fan-out, independence from the page and depth budgets, an under-cap regression at the
  exact default, and non-page-counting branches (redirect/duplicate-final aliases, print page)
* Unit 2 (`067.002-T`): `_admit()` gate enforced at both discovery append sites, plus discovery
  short-circuit once admissions are exhausted so no auxiliary TOC assets are fetched for links that
  would all be refused

## Constraints Preserved

* Refused links are **not** added to `visited` — adding them would reintroduce the unbounded growth
  the ceiling exists to prevent
* Breadth-first order preserved for admitted links (append-time cap, never a reorder)
* The start URL is never subject to the ceiling; the loop always terminates and the crawl runs to
  completion with the admitted set
* A crawl below the ceiling is behaviourally unchanged
* A single DEBUG record per crawl at the first drop, with the start URL passed through
  `sanitize_source()` so credentials cannot reach logs
* Negative `max_frontier` raises `CrawlLimitExceededError`; `0` means discovery disabled, verified
  to perform no discovery I/O

## Rejected Alternatives

* **Deriving the ceiling from `max_pages` or `max_depth`** — rejected: the vector is independent of
  both, so a derived bound would not hold when either budget is large or unbounded
* **A counter field or `CrawlResult` truncation marker** — deferred by plan review to keep the
  first slice minimal; carried forward as stash `7F34A0D5`
* **Logging every dropped link** — rejected: emits unbounded log volume under exactly the
  adversarial condition the ceiling defends against; a once-per-crawl record is used instead
* **Extending the ceiling to seed/final-URL/redirect-alias keys** — rejected as out of scope: those
  are already bounded by the absolute per-request `MAX_FETCH_ATTEMPTS` budget

## Verification and Rollback

Gates green in order: `ruff check .`, `pyright src/` (0 errors), `pytest` (2008 passed, 6 skipped),
`ruff format --check .`. Runtime spot-check bounded a 5,000-link fan-out to exactly
`1 + max_frontier` requests with `max_pages=1_000_000` and `max_depth=10`.

Rollback is a revert of merge commit `b1f4549` — single-module, additive, and inert below the
ceiling. Full closure record: `docs/closure/2026-08-29-058-s-crawl-frontier-bound-closure.md`.
