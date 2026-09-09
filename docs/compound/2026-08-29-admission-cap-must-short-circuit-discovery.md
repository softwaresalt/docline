---
title: "An admission cap must short-circuit discovery, not just refuse admissions"
date: 2026-08-29
agent: ship
context: resource-bounds
tags:
  - crawl
  - resource-bounds
  - dos-hardening
  - discovery-loop
  - dedup-set
trigger:
  - "Adding a queue/frontier size cap to a discovery or worklist loop"
  - "A cap knob whose zero value is documented as disabling the feature"
  - "Bounding memory growth where a dedup set gates enqueue"
---

## Problem

Bounding `crawl()`'s frontier growth looked like a one-line guard: count admissions, and refuse
new ones past the ceiling at each `frontier.append` site. That guard is correct for the memory
bound and passed a purpose-built harness covering adversarial fan-out, budget independence,
under-cap regression, and redirect-alias branches.

It was still incomplete in two ways that only surfaced under review.

## Root cause

**The refusal was too late in the pipeline.** The depth-zero discovery path fetches mdBook
`toc-*.js` assets and builds a link list *before* the first `_admit()` call. With the ceiling
already exhausted — including `max_frontier=0`, documented as "discovery disabled" — the crawl
still issued outbound network requests for links that every subsequent admission would refuse.
A cap that refuses at the enqueue site does not stop the work that produces the candidates.

**Refusal paths must stay symmetric.** Two discovery branches existed (the main branch and the
print-page branch). Adding a short-circuit to one while leaving the other to fall through its
combined `if` condition meant one branch dropped links silently and the other reported. The same
asymmetry hid the print-page site from the harness entirely: it could have been deleted with the
suite still green.

## Resolution

1. Short-circuit at the top of the discovery step, before candidate generation and any auxiliary
   asset fetch: `if admitted >= cap: report(); continue`.
2. Route every refusal — enqueue-site and short-circuit alike — through one reporting helper so
   observability cannot drift between branches.
3. Never add refused keys to the dedup set. Adding them reintroduces exactly the unbounded growth
   the cap exists to prevent, since the dedup set is usually the dominant resident structure and
   never shrinks.
4. Write one test per admission site. Counting sites in the source and then counting tests is a
   cheap way to catch a site the harness never drives.

## Lesson

A resource cap is a property of the whole discovery pipeline, not of the enqueue statement. Ask
where candidate generation begins, not where insertion happens — the gap between the two is where
the cap silently fails to bind. When a knob's extreme value is documented as "disables X", write
the test that proves X performs no I/O at that value; the docstring is not the contract, the test
is.

## Refinement (059-S, 2026-08-30)

059-S added an observability signal (`frontier_truncated`) on top of this cap, and that reversed
part of resolution point 1. The short-circuit no longer skips **all** candidate generation — it
still runs the **pure in-memory parse** (`extract_links`, and at depth zero `extract_toc_script_urls`)
to decide whether the cap actually *cost* the crawl an eligible link, while still skipping
`_discover_toc_links` (the **network** fetch). The distinction that matters is I/O versus parse: a
cap must not issue network requests for links it will refuse, but a truncation signal needs the
cheap in-memory parse to tell "cap reached, nothing lost" from "cap reached, a link was dropped."
So the sharper rule is: **short-circuit the I/O at the cap, but keep the pure parse when an
observability signal depends on knowing whether the cap bound.** The `max_frontier=0` no-network
invariant from the original lesson still holds and is still asserted.

## Refinement (061-S, 2026-09-09)

061-S applied this same lesson to a genuinely different discovery-candidate shape: a **paginated,
network-backed async generator** (a Terraform Registry API adapter), not the earlier in-memory
static-HTML candidate list. Two extensions surfaced.

**The check-before-pull ordering generalizes, but the cost model differs.** For an async
generator, "candidate generation" and "the network I/O" are the same event — pulling the next
item **is** the fetch (a paginated API call). The existing lesson's "short-circuit before
candidate generation" becomes, concretely: check the cap **before** calling `__anext__()` again,
using manual `__aiter__()`/`__anext__()` stepping rather than a plain `async for` (which always
pulls the next item before the loop body can check anything). This is strictly more expensive to
get wrong than the static case: an unnecessary "one more pull" here is a real outbound page
fetch, not a cheap in-memory list access.

**`max_frontier=0` needs an explicit call-site guard, not just a within-loop short-circuit.**
Checking the cap at the *top* of the seed loop (mirroring the original lesson's "short-circuit at
the top of the discovery step") still runs the loop's first iteration when the cap is already `0`
— and that iteration must itself record the drop for the truncation signal, without ever calling
`__anext__()`. But since the truncation signal here is `frontier_truncated`, and reporting "the
cap cost the crawl a link" without ever having asked the source for one is a category error
(there is no cheap in-memory parse to fall back on, unlike the static case's 059-S refinement),
the correct fix was to guard the **call site**: skip invoking the discovery seed at all when
`max_frontier == 0`, rather than entering the seed loop and reporting a false-positive truncation
on its very first check. A second, independent cap (`max_pages`) needed the identical
check-before-pull treatment for the same reason: with `max_frontier` large but `max_pages` small,
the seed must stop once the frontier queue already covers the page budget, not continue paginating
an API for admissions the main crawl loop can never reach.

**Restated rule**: for a network-backed async producer, "the cap" is not one property but two —
(a) an entry guard for the exactly-disabled case (avoid a false-positive signal from a loop that
was never truly attempted), and (b) a check-before-pull loop body for the genuinely-bounded case
(avoid a real network fetch for a candidate the cap will refuse). Both are required; neither
substitutes for the other.

