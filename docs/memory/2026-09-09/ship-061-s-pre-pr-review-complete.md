---
date: 2026-09-09
shipment: 061-S
feature: 070-F
branch: feat/061-s-spa-api-aware-crawl-link-discovery
head_sha: 70faec9726092082a1cda8193e65a04c72b69910
phase: pre-pr-review-complete
---

# Ship session memory — 061-S SPA/API-aware crawl link discovery

## Summary

Implemented all 11 dependency-ordered tasks (070.001-T through 070.011-T) for
shipment 061-S / feature 070-F: a pluggable, browserless discovery-source seam
in `docline.fetch.crawl`, plus a concrete Terraform Registry v2 JSON:API
adapter (`docline.fetch.tf_registry_source.TfRegistrySource`), resolving the
operator's original bug report — `web_crawl` of
`https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs`
previously fetched only the one-page Ember SPA shell instead of the full
provider documentation set (1,620 docs).

## Items completed

- 070.001-T — repro harness characterizing the one-page defect (`842247f`)
- 070.002-T — `DiscoverySource` seam harness + structural stub (`17812b2`)
- 070.003-T — seam registry implementation (`81d6fad`)
- 070.004-T — TF registry adapter harness + fixtures (`8322d6e`)
- 070.005-T — recognizer + provider-version resolution (`79a035c`)
- 070.006-T — paged provider-docs enumeration (`7c06521`)
- 070.007-T — `CrawlConfig.enable_api_discovery` disable switch (`23f2502`)
- 070.008-T — crawl() composition integration harness (`950f023`)
- 070.009-T — security + degradation harness (`17317e2`)
- 070.010-T — wired the seam into `crawl()`'s composition point (`f635677`)
- 070.011-T — `docs/ARCHITECTURE.md` operator documentation (`bccdfbb`)
- Backlog archival commit for 070.011-T (`592b30b`)

All 11 tasks marked `done` in backlogit with commit SHAs recorded.

## Local adversarial review (6-persona) — completed and remediated

Launched Correctness, Security, Python, Maintainability, and Constitution
reviewers (5 subagents) plus my own direct scope-boundary check, all against
the full diff vs. `main`. Findings and disposition:

**Fixed (P1/P0-adjacent, `10bb4a1` + `70faec9`):**
1. **P1 correctness** — a recognized pinned-version start URL
   (`.../4.1.0/docs`) silently enumerated and linked to the *current latest*
   version's docs instead, since `discover_doc_urls` always read the
   `latest-version` relationship regardless of the URL's own version segment.
   Fixed: `_parse_start_url` now threads the captured version through, and
   `discover_doc_urls` fails closed with an explicit `TfRegistryAdapterError`
   for any non-`"latest"` version (degrades to static-only extraction, never
   silently substitutes wrong content). Genuine pinned-version resolution
   deferred (stash `EF8503EC`-adjacent scope, not literally captured there —
   see below).
2. **P1 constitution/hermeticity** — `test_crawl_spa_shell_repro.py`'s T1
   characterization test used the exact URL pattern the real,
   globally-registered `TfRegistrySource` recognizes, with
   `enable_api_discovery` left at its `True` default, while only
   monkeypatching `crawl.fetch_page` (not the adapter's own
   `tf_registry_source.fetch_page` binding). This would attempt live,
   unmocked network I/O against the real Terraform Registry in any
   environment with real network access — verified empirically that in
   *this* sandbox it happened to degrade safely via the fail-open path
   (confirmed via a throwaway diagnostic test + `--log-cli-level=WARNING`).
   Fixed: test now explicitly passes `enable_api_discovery=False`, matching
   its own stated intent (static-only baseline characterization).
3. **P2 correctness/maintainability** — `_seed_from_discovery_source`'s
   check-before-pull ceiling check could report `frontier_truncated=True`
   without ever asking the discovery source for an item, notably for
   `max_frontier=0`. Fixed: call site now guards `max_frontier > 0` in
   addition to `enable_api_discovery`. The remaining exact-boundary
   conservative-over-report case is left as-is and documented as an
   intentional D3-style trade-off.
4. **P2 security** — `category`/`slug`/`version_id` were charset-validated
   (I6) but a bare `.`/`..` segment passed that allowlist unnoticed and would
   produce a literal relative-path segment once percent-encoded. Fixed:
   `_is_safe_path_segment()` combines the charset check with an explicit
   reject of `.`/`..`, applied everywhere (recognizer + construction).
   `version_id` previously had zero charset validation; it now does too.
5. **P2 security** — every adapter fetch's *final* (post-redirect) response
   URL is now asserted host-confined to `registry.terraform.io`
   (`_assert_response_on_registry_host`), matching the check already applied
   to a followed `links.next` — the shared transport's redirect handler
   rejects private/reserved targets but permits redirecting to any other
   *public* host.
6. **P2 constitution** — a completed, error-free discovery-source seed now
   logs one INFO record (sanitized origin + seeded-URL count), fulfilling the
   plan's own Constitution Check commitment (the initial 070.010-T
   implementation only delivered the WARNING-on-fallback half).
7. **Docstring completion** — `DiscoverySource.discover_doc_urls`'s docstring
   now documents the required `DoclineError`-wrapping / carve-out-unwrapping
   exception contract implementations must follow for `crawl()`'s fail-open
   guarantee to actually hold.

Regression tests added for every fix; full `tests/fetch/` suite: 483 passed,
0 failed. Full project suite: 2094 passed, 6 skipped, 0 failed.

**Deferred (P-021 C2 stash captures, threadless path — no PR exists yet):**
- `D548B756` — discovery-source registry test-isolation/import-time-side
  -effect hardening (medium priority, requires deliberation)
- `DFF8E8E1` — adapter defensive-parsing hardening (aclose, broad except,
  attrs_by_id collision, continuation-page type filter, relative links.next)
  (low priority)
- `EF8503EC` — second-adapter extensibility prep (shared fetch+JSON helper,
  registrations module, split `_extract_docs_page`) (low priority, requires
  deliberation)
- `8E0B4FB5` — independent pull-count bound in `_seed_from_discovery_source`
  as defense-in-depth against a hypothetical future misbehaving adapter (low
  priority)

## Branch / commit state

- Branch: `feat/061-s-spa-api-aware-crawl-link-discovery`
- HEAD: `70faec9726092082a1cda8193e65a04c72b69910`
- 16 commits total (11 task commits + 1 backlog-archival + 1 review-fix batch
  + 1 docstring completion, atop the pre-existing merge base `f89aea0`)
- Local review readiness: **READY_WITH_FOLLOWUPS** — zero unresolved P0/P1,
  4 P2/P3 follow-ups captured as stash entries above (residual-risk notes,
  no PR-blocking work remaining)
- Full local build (`uv run python -m build`) succeeded; `dist/` artifacts
  gitignored, not committed

## Next steps

1. Push branch, create PR via `pr-lifecycle` skill with the Local Review
   Readiness block (reviewed HEAD, outcome, follow-up IDs, full-build
   evidence).
2. Cycle through Copilot review (if engaged), P-009 (merge-commit-only)/P-018
   (Copilot gate)/§1.9 readiness gates.
3. Merge with operator's pre-granted P-014 approval (per the operator's
   explicit authorization for in-scope PR merges after every mandatory gate
   passes).
4. Live runtime verification against the real Terraform Registry (bounded
   settings — low `max_pages`/`max_frontier` — proving materially more than
   one page discovered, resolving the original symptom).
5. Post-merge: shipment closure (verify 070-F qualifies for P-015 cascade —
   root feature, fully covered by exactly its 11 tasks, no extra members),
   gate-recognized `docs/closure/061-S-070-F-post-merge-closure.md`
   (`closure_status: READY`, `compaction_status: done|degraded`), compound
   refresh, mandatory P-020 `compact-context`.
