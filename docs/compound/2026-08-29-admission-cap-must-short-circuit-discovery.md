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

# An admission cap must short-circuit discovery, not just refuse admissions

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
