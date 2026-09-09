---
title: "A third-party API's response shape must be live-verified, not merely fixture-consistent"
date: 2026-09-09
agent: ship
context: external-integration
tags:
  - external-api
  - json-api
  - live-verification
  - fixture-testing
  - runtime-verification
trigger:
  - "Implementing an adapter against an undocumented or loosely-documented third-party API"
  - "Designing test fixtures for an external JSON:API response shape from investigation notes rather than a captured live response"
  - "A plan or deliberation cites an API 'relationship' or field name that was inferred, not observed"
---

## Problem

Shipment 061-S implemented a Terraform Registry v2 JSON:API adapter to resolve a provider's
latest version. The plan and deliberation both described the response as exposing a singular
`relationships["latest-version"]` relationship, and every fixture, and all 20+ unit tests built
against those fixtures, encoded that exact assumption. Every test passed. Full quality gates
(lint, format, typecheck, the full project test suite) passed. Two full rounds of local
adversarial review (5 personas) and multiple rounds of automated PR review passed. The assumed
shape was still **completely wrong**.

## Root cause

The assumption was never actually observed against the live API — it was a plausible design
choice, self-consistent with the fixtures built from it, carried forward from an earlier
investigation phase into the plan, then into the implementation, without a single live HTTP
request ever confirming it. Every layer of verification available before live runtime testing
(unit tests, quality gates, static analysis, code review by both humans-in-the-loop-equivalent
personas and an automated reviewer) is fundamentally *fixture-consistent* verification: it proves
the code correctly implements the fixtures' assumed contract, never that the fixtures' assumed
contract matches reality. A wrong assumption, once encoded into a fixture, is invisible to every
one of those layers simultaneously — they all agree with each other and are all wrong together.

The real API response instead exposed `relationships["provider-versions"]` as a flat, unordered
list of **every** published version (405 for the provider tested), with per-version
`published-at` timestamps but no explicit "is latest" flag or singular relationship anywhere in
the payload.

## Resolution

The defect was found — and could only have been found — by a mandatory live runtime
verification step performed against the real target before presenting the work as complete,
per this shipment's own explicit operator instruction to "prove materially more than one page"
against the live Terraform Registry. That step:

1. Directly queried the real endpoint with a small standalone script (`urllib.request`, no test
   framework) to inspect the raw JSON shape.
2. Compared it against the adapter's own parsing logic, found the mismatch immediately (a
   `KeyError` on the first real call).
3. Redesigned the version-resolution logic around the *actually observed* shape (select the
   maximum `published-at` timestamp across the real `included` array).
4. Rebuilt the fixtures to match the corrected, now-observed shape.
5. Re-ran the full bounded live crawl end-to-end to confirm the fix, not just the unit tests.

## Lesson

**Passing tests against self-consistent fixtures is not evidence that the fixtures are correct.**
For any adapter to a third-party API whose shape was designed from documentation, investigation
notes, or a deliberation record rather than a captured live response, budget an explicit, bounded
live-verification step — hitting the real endpoint directly, outside the test suite — as part of
the implementation, not merely as an optional post-merge nicety. Do this **before** relying on
extensive fixture-based test coverage as confidence that the integration works: the volume of
passing tests built on a wrong assumption is not just unhelpful, it is actively misleading, since
it multiplies false confidence in exact proportion to how much work went into the (wrong) fixture
design. A single real HTTP request against the live target is worth more than a hundred green
tests against a fixture nobody has checked against reality.

When live verification is not possible during initial implementation (no network access, a
staging-only credential, a destructive/paid API), say so explicitly in the plan or deliberation's
own risk record, and treat that gap as an open, named risk to close at the earliest point live
access becomes available — never as a silently-accepted, permanent substitute for it.
