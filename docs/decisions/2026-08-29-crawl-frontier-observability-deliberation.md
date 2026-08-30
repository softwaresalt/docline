---
title: "Deliberation: Crawl frontier truncation observability and admission-policy composability"
date: 2026-08-29
status: accepted
stage_session: "stash-to-backlog — crawl reliability/composability group {7F34A0D5, 8A99D90C, ABBE9BCC}"
stash_ids: [7F34A0D5, 8A99D90C, ABBE9BCC]
supersedes_deferrals_from: docs/closure/2026-08-29-058-s-crawl-frontier-bound-closure.md
---

## Problem frame

Shipment 058-S added `CrawlConfig.max_frontier` (default `MAX_FRONTIER = 10_000`) as a whole-crawl
discovered-link admission ceiling in `src/docline/fetch/crawl.py`. The ceiling works, but it
shipped deliberately minimal, and its review deferred three residuals that are now stash entries.
Read together they are not three unrelated nits — they are the same defect seen from three angles:

**the admission rule is an untestable closure whose only output is a DEBUG line.**

Grounded against `origin/main @ edcaa12`:

* `crawl.py` is **660 lines**, past the 400-line module convention. It carries the crawl loop,
  the HTML link extractor, TOC discovery, robots handling, URL normalisation, print-page
  detection, and backoff arithmetic in one module.
* Admission state lives in two closures (`_admit`, `_report_ceiling` at `crawl.py:191-222`) over
  three `nonlocal` variables (`admitted`, `ceiling_reported`, plus the captured `frontier` /
  `visited`). The rule cannot be exercised without driving a full crawl through
  `_fetch_with_retries`. That is **8A99D90C** (medium, task).
* The only truncation signal is `logger.debug(...)` in `_report_ceiling`. `CrawlResult` has no
  marker, `crawl()` returns a bare `list[CrawlResult]`, and `elt/execute.py::_fetch_url`
  (`execute.py:494-580`) writes `crawl-manifest.json` with only a `"pages"` key. A silently
  truncated crawl is therefore **byte-identical in shape** to a complete one on both the CLI and
  the MCP path. `_crawl_config_from_source` (`execute.py:340-355`) never sets `max_frontier`, and
  `WebCrawlSource.max_pages` may be `None`, so a legitimate large crawl can cross the ceiling with
  no user-visible signal at default verbosity. That is **7F34A0D5** (medium, feature).
* At depth zero, `_discover_toc_links` results are **appended to the tail** of `discovered_links`
  (`crawl.py:331-341`), then the admission loop breaks on the first refusal
  (`crawl.py:344-355`). Under truncation the append-time cap therefore drops authoritative mdBook
  TOC navigation *first*, on exactly the sites where the TOC is the canonical page set. That is
  **ABBE9BCC** (low, task).

## Grouping decision

These three ship **together**, as one covering feature, in one pull request.

* **Shared mutation surface.** All three modify the same ~30 lines of admission logic in
  `crawl.py`. Landing them separately means three sequential rewrites of the same block and three
  independent review passes over the same code.
* **Ordering is forced by reliability, not convenience.** 7F34A0D5 needs a *place* to record
  truncation and ABBE9BCC needs a *place* to express ordering policy. Both places are the
  structure that 8A99D90C creates. Doing the observability feature first would mean writing the
  marker into a `nonlocal` closure and then immediately moving it — throwaway work plus a
  throwaway test surface.
* **Composability outranks feature convenience** per the operating priority for this session. The
  refactor is not a nice-to-have that follows the feature; it is the precondition that makes the
  feature testable at unit granularity rather than only through a full-crawl integration path.

**F0F13C0B ships separately** (see `2026-08-29-sitemap-preflight-dedup-deliberation.md`): it
mutates `fetch/sitemap.py` DNS/SSRF preflight semantics, shares no **source** file with this
group, and has no dependency edge in either direction. The two groups do both touch
`docs/ARCHITECTURE.md`; each is scoped to a distinct section (crawl vs sitemap) so the second
shipment to merge rebases a trivial hunk. Bundling it would couple a security-boundary review
surface to a reliability review surface and violate width isolation.

## Options considered

### Option A — Extract a `_Frontier` dataclass first, then layer observability and ordering on it (chosen)

Introduce a module-level private `@dataclass` owning the frontier queue and the admission
counters (`admitted`, `ceiling_reported`, and a refusal marker), exposing `admit()` and a
`truncated` property. Split `crawl.py` along its existing seams. Then:

> **Refined during planning.** The implementation plan is the authoritative expression of this
> option and narrows it in two ways: (1) the `visited` set stays in the crawl loop rather than
> moving into the dataclass — it is mutated at three non-admission sites and serves emitted-page
> dedup, a separate responsibility (plan decision D2); (2) the split is `crawl_models.py` +
> `crawl_links.py` rather than a link/discovery pair, because a discovery module would need
> `CrawlConfig` and the models module is what makes that acyclic (plan decision D5). See
> `docs/archive/plans/2026-08-29-crawl-frontier-observability-plan.md`.

1. promote the truncation record from DEBUG to WARNING and add a `frontier_truncated` marker that
   reaches `crawl-manifest.json`;
2. order TOC-derived links **ahead of** in-page anchors at depth zero so truncation drops
   in-page anchors first.

* **Pros:** the admission rule becomes unit-testable without network or event loop; the
  truncation marker has a natural owner (`_Frontier.truncated`) instead of a fourth `nonlocal`;
  the TOC ordering change becomes a one-line list concatenation order at a single call site
  rather than a change threaded through closure state; `crawl.py` returns under the module
  convention; each of the three stash concerns keeps its own test file and its own acceptance
  criteria.
* **Cons:** the pull request touches more files than any single stash entry would. Mitigated by
  strict width isolation per task and by keeping the extraction behaviour-preserving — the
  refactor task ships with characterization tests and **no** behaviour delta.

### Option B — Ship the three entries as three independent shipments in stash-priority order

7F34A0D5 (medium) → 8A99D90C (medium) → ABBE9BCC (low).

* **Rejected.** This is the feature-convenience ordering. It writes the truncation marker into
  closure state, then rewrites it during extraction, then rewrites the ordering logic a third
  time. Three reviews of the same 30 lines, two throwaway test surfaces, and a window in which
  `crawl.py` is both over the line ceiling *and* carrying new state.

### Option C — Observability only; decline the refactor and the ordering fix

Promote the log level and add the manifest marker; leave the closures and the TOC tail-append.

* **Rejected.** It satisfies the letter of 7F34A0D5 while leaving the admission rule
  untestable, which is the root cause the other two entries describe. It also leaves the failure
  mode ABBE9BCC identifies actively worse once truncation is *visible*: operators would now see a
  truncation warning on mdBook sites without the navigation set that would let them recover from
  it.

### Option D — Change the default `MAX_FRONTIER`, or derive it from `max_pages`

* **Rejected, out of scope.** 058-S plan review already rejected deriving the ceiling from
  `max_pages`/`max_depth`, and the ceiling value is not what any of the three entries reports as
  defective. Raising the default would mask the observability gap rather than close it.

## Decision

Adopt **Option A**. Covering feature: *"Crawl frontier truncation observability and
admission-policy composability"*.

Committed dependency ordering (reliability/composability first):

```text
Unit 1  extract _Frontier + split crawl.py      (8A99D90C)  — no behaviour change
   └─> Unit 2  surface truncation to operators  (7F34A0D5)  — needs Unit 1's marker owner
   └─> Unit 3  TOC-first ordering under cap     (ABBE9BCC)  — needs Unit 1's admit() seam
```

Unit 3 depends on Unit 1 only; it is independent of Unit 2 and may be reviewed in parallel with
it, but is sequenced after it in the shipment so that its behaviour delta lands against an
already-observable truncation signal.

## Scope decisions captured

* **In scope:** `_Frontier` dataclass with `admit()`; a behaviour-preserving module split of
  `crawl.py`; WARNING-level truncation record (still once per crawl, still `sanitize_source()`-d);
  a `frontier_truncated` boolean surfaced through `crawl()` to `_fetch_url` and into
  `crawl-manifest.json`; TOC-before-anchors ordering at depth zero.
* **Out of scope:** changing `MAX_FRONTIER`; changing the ceiling semantics; per-link drop
  logging (rejected in 058-S — unbounded log volume under the adversarial condition); a schema
  version bump for `crawl-manifest.json`; any change to `WebCrawlSource`'s public manifest fields.
* **Backward compatibility:** `crawl-manifest.json` gains a key; consumers
  (`docline.app._load_crawl_manifest`) read `"pages"` and must tolerate the addition. Any change
  to `crawl()`'s return type must keep `list[CrawlResult]` iteration working for existing callers
  and tests, or the plan must justify the break explicitly.
* **Missing-task check:** no additional task surfaced during deliberation. The
  `_crawl_config_from_source` gap (never setting `max_frontier`) is *reporting*, not a defect —
  the default applies — and is covered by Unit 2's acceptance criteria rather than a fourth unit.

## Prior art consulted

`docs/compound/` searched for crawl-, frontier-, and observability-related learnings; nothing
matching this admission-policy surface. Closest prior context is the 058-S closure record, which
is the source of all three stash entries and whose "Rejected Alternatives" section constrains
Units 2 and 3 (no per-link logging, no derived ceiling).
