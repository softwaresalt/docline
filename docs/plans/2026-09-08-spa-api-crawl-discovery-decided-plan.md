---
title: "Decided Plan: SPA/API-aware crawl link discovery (Terraform Registry provider-docs adapter)"
date: 2026-09-08
status: decided
source_document: docs/decisions/2026-09-08-spa-api-crawl-discovery-deliberation.md
original_plan: docs/archive/plans/2026-09-08-spa-api-crawl-discovery-plan.md
stash_ids: [FC174FA7]
shipment: 061-S
feature: 070-F
plan_review_outcome: PASS (attempt 3, after 2 rounds of P1 findings)
---

# Decided Plan — SPA/API-aware Crawl Link Discovery

## Objective

Make `web_crawl` discover and fetch the **full documentation set** of JavaScript/SPA-rendered
documentation sites — starting with the Terraform Registry provider docs — instead of stopping
after the single server-rendered app-shell page, **without a runtime browser**, via an additive
discovery-source seam + a Terraform Registry provider-docs adapter enumerating every doc URL via
the registry v2 JSON:API.

## Design constraints (as delivered)

1. **Additive / zero-regression**: unrecognized start URLs behave byte-for-byte identically to
   pre-change `main`.
2. **Bounds preserved, lazily**: seeded links admitted only through `frontier.admit()`;
   `max_frontier`/`max_pages`/section-scope/`visited` dedup/`frontier_truncated` all bind. The
   adapter is a lazy async iterator; a full frontier or page budget halts further API pagination
   before it happens, not after.
3. **Transport = the existing hardened `fetch_page`** (never a new HTTP client) — address-pinned,
   redirect-revalidated, TLS-verified, byte/attempt-budgeted.
4. **SSRF preserved** via the canonical `url_policy` classifier, in both directions.
5. **Host- (and scheme/port-) confinement to the recognized origin**: `links.next` targets, the
   final response URL, and every constructed doc URL must be same-origin with
   `registry.terraform.io` (`https`, default port) before fetch/admit — hardened beyond hostname
   alone after 3 Copilot review rounds found downgrade/port/malformed-authority gaps.
6. **Path-segment safety**: `namespace`/`name`/`version`/`category`/`slug`/the resolved
   provider-version id are charset-validated (`[A-Za-z0-9._-]`, explicitly excluding bare `.`/`..`)
   before interpolation.
7. **Fail-open, with SSRF/budget carve-out** at every `except` site around `fetch_page`, both in
   the adapter and at the crawl-composition layer.
8. **No runtime browser dependency.**
9. **Additive composition**: a recognized host seeds API-enumerated URLs AND still runs static
   extraction; `visited`/`_dedup_key` collapse any overlap.
10. **`respect_robots` applies to the discovery seed too** (added during implementation review —
    not in the original plan text): a robots.txt-disallowed start URL never triggers the
    adapter's own outbound API requests.

## Work breakdown (as implemented, 11 tasks)

070.001-T (repro harness) → 070.002-T (seam harness+stub) → 070.003-T (seam impl) →
070.004-T (adapter harness+fixtures) → 070.005-T (recognizer+version resolution) →
070.006-T (paged enumeration) → 070.007-T (`enable_api_discovery` config field) →
070.008-T (crawl() composition integration harness) → 070.009-T (security+degradation harness) →
070.010-T (wire seam into `crawl()`) → 070.011-T (operator documentation).

## Protected invariants (I1–I6, all held through every hardening round)

* **I1 — Zero-regression** for unrecognized hosts and `enable_api_discovery=False`.
* **I2 — Bounds bind lazily** via `frontier.admit()`; API I/O bounded by `RemainingByteBudget`.
* **I3 — SSRF inviolate** via `fetch_page`'s connect-time address pinning.
* **I4 — Fail-open, carve-out at every except site** (adapter AND composition layer).
* **I5 — Host/origin confinement** (hardened to scheme+host+port during implementation review).
* **I6 — Path-segment safety** (hardened to exclude bare `.`/`..` during implementation review).

## Plan review outcome

**PASS at attempt 3.** Attempts 1–2 returned `FAIL` with P1 findings since closed in the shipped
code: hardened transport (not raw httpx), async/lazy producer, fail-open carve-out at both
layers, host-confinement, a Constitution Check section, and an end-to-end kill-switch test for
`enable_api_discovery=False`.

## Rollback

Set `enable_api_discovery=False` (now reachable end-to-end via `FetchRequest`/`WebCrawlSource`/
`ManifestUrlSource`) to restore legacy static-only discovery without a code revert; verified live
against the real Terraform Registry (see `docs/closure/061-S-070-F-post-merge-closure.md`).

## Full detail

The complete deliberation, work-breakdown rationale, risky-action record, and full 2-round
plan-review transcript are preserved in the archived original:
`docs/archive/plans/2026-09-08-spa-api-crawl-discovery-plan.md`.
