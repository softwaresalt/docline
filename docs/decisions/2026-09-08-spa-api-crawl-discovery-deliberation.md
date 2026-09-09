---
title: "Deliberation: SPA/API-aware crawl link discovery for JS-rendered documentation sites"
date: 2026-09-08
status: accepted
stage_session: "stash-to-backlog — SPA-crawl-discovery {FC174FA7}"
stash_ids: [FC174FA7]
source_report: "operator, 2026-09-08 — web_crawl of registry.terraform.io provider docs fetched only one page"
---

## Problem frame

**FC174FA7** (bug -> feature-shaped, high): `web_crawl` of a JavaScript/SPA-rendered
documentation site fetches only the **start page** and discovers none of the sidebar
sub-links. The operator reproduced this against
`https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs`, whose left
"scrolling sidebar" lists the full provider documentation set (resources, data-sources,
guides, ...).

Root cause is **architectural, not a bug in the existing crawl bound logic**. docline's link
discovery is static-HTML only:

- `src/docline/fetch/crawl_links.py::extract_links` runs `html.parser.HTMLParser` over the raw
  response body and collects `<a href>` anchors.
- `extract_toc_script_urls` / `extract_toc_links` add an mdBook-specific path: fetch
  `toc-*.js` assets and regex their embedded hrefs.
- `src/docline/fetch/http.py::fetch_page` is an httpx-class fetch — **it does not execute
  JavaScript**.

The Terraform Registry is an **Ember.js single-page application**. The server returns an app
shell; the sidebar is hydrated client-side from a JSON:API. With no JS engine, docline sees an
empty navigation and the crawl terminates after one page.

### Investigation evidence (Stage spike, 2026-09-08 — Playwright/msedge + curl, read-only)

Tool note: the runtime did not expose a Playwright MCP tool to the session, but the
operator-provided `@playwright/mcp` `node_modules` were used read-only via `playwright-core`
driving the **already-installed system Edge** (`channel: "msedge"`) — no browser download, no
mutation of `package.json`/`bun.lock`/`node_modules`.

1. **Raw HTTP fetch (what docline sees)** — `curl` of the docs URL returns a **9,218-byte app
   shell**: exactly **1** `<a>` tag, **0** `/docs/*` sub-links, **no** mdBook `toc-*.js`, and
   the body carries `terraform-registry/config/environment` + `EmberENV` + Glimmer-component
   markers (Ember SPA) plus a `<noscript>` and 3 bootstrap `<script>` tags. This is the direct,
   decisive reproduction of the one-page result.
2. **Headless render (Edge)** — after JS hydration the DOM has **104** anchors, but the
   provider **resource/data-source** sidebar links still do **not** materialize as static
   anchors even after a 30 s wait + programmatic scroll of the scroll container; the sidebar is
   API-driven and virtualized. A naive "render + scrape anchors" approach is therefore both
   heavy and unreliable here.
3. **Network capture (the real source of truth)** — the sidebar is backed by the Terraform
   Registry **v2 JSON:API**:
   - `GET /v2/providers/hashicorp/azurerm?include=...,provider-versions` -> latest
     provider-version id (observed `107778`).
   - `GET /v2/provider-versions/107778?include=provider-docs` -> the **entire** sidebar doc set.
   - `GET /v2/provider-docs/{id}` -> individual doc content.
4. **Browserless enumeration proof** — a plain `curl` (stand-in for docline's httpx client) of
   `GET /v2/provider-versions/107778?include=provider-docs` returned **1,620** `provider-docs`
   entries: **1104 resources, 396 data-sources, 94 list-resources, 14 guides, 7 actions, 2
   ephemeral-resources, 2 functions, 1 overview**. Every human doc URL is deterministically
   constructible as
   `/providers/hashicorp/azurerm/latest/docs/{category}/{slug}` from each entry's
   `attributes.category` + `attributes.slug`. **No browser is required at runtime.**
5. **Edge-backed Playwright-MCP deep probe (2026-09-08, follow-up)** — a deeper live
   DOM/network/scroll inspection via the recovered Edge-backed `@playwright/mcp` route measured the
   sidebar's rendering ceiling directly. At settle: **0** matching doc sublinks of 217 total anchors
   (categories collapsed by default). After expanding the category groups / using the sidebar filter
   input: **39** matching doc sublinks. After repeatedly scrolling the sidebar container
   (`nav.provider-docs-menu > div.provider-docs-menu-content`, `overflow:auto`) to the bottom: still
   **39** — scrolling added nothing. So even fully expanded + scrolled, the DOM exposes at most ~39
   of the 1,620 documents (a virtualized/filter-driven subset). The same probe re-confirmed the v2
   API sequence, including `GET /v2/provider-versions/107778?include=provider-docs`. **This is the
   decisive measurement: DOM scraping is structurally incapable of enumerating the full set; only
   the JSON:API is complete.**

### Prior-art constraints (compound library)

- `2026-08-29-admission-cap-must-short-circuit-discovery.md`: any newly-seeded links MUST flow
  through the existing `frontier.admit()` / `max_frontier` cap and the `visited` dedup set, and
  must preserve the `frontier_truncated` observability signal. Discovery is a property of the
  whole pipeline — seeded links cannot bypass the bound.
- `2026-07-04-ms-learn-canonical-url-from-breadcrumb.md`: URL-construction features can be 0%
  functional if the derivation source is wrong; validate against a real corpus. Mitigated here
  by empirically confirming category+slug -> URL against the live 1,620-doc response and by
  pinning a recorded fixture.

## Grouping decision

Ships **on its own dedicated shipment**. Explicitly **not** bundled with:
- **060-S / 069-F** (sitemap preflight de-duplication) — different concern (hostname resolution
  / pinning), different files, no dependency edge.
- **stash D6E758F5** (credential-sanitization in `elt/execute.py`) — unrelated security fix.

This work mutates the `docline.fetch` discovery surface (new discovery seam + adapter + a
`crawl()` seed path). It builds on, and must respect, the SSRF policy (`url_policy.py`,
057-S) and the frontier bound (`crawl.py`, 058-S) but shares no files that would couple review
surfaces.

## Options considered

### Option A — Site/API-aware discovery seam + Terraform Registry provider-docs adapter (CHOSEN)

Introduce a small **discovery-source seam**: a recognizer registry that, given a start URL, can
return a provider that enumerates the full link set for that site. Ship the first provider — a
**Terraform Registry provider-docs adapter** — that:
1. recognizes `registry.terraform.io/providers/{namespace}/{name}/.../docs` start URLs,
2. resolves the provider version via the v2 API,
3. pages the `provider-docs` collection and constructs canonical human doc URLs from
   `category`+`slug`,
4. hands those URLs to the existing bounded crawl to fetch through the normal fetch/ELT path.

All enumerated URLs pass `validate_crawl_url` / `is_unsafe_resolved_address` and are admitted
through `frontier.admit()` (so `max_frontier`, section-scope, and `visited` still bind). Adapter
failure degrades gracefully to today's static-anchor extraction.

- Pros: deterministic; **no runtime browser dependency**; reuses httpx + SSRF policy + frontier
  bound; empirically proven complete (1,620/1,620 links); testable with recorded JSON fixtures;
  the seam generalizes to future SPA doc providers (Cloud provider registries, etc.).
- Cons: site-specific per provider; needs an extensibility seam and a maintained recognizer;
  depends on a third-party API shape (mitigated: fail-open to static extraction; pin fixtures;
  version-tolerant parsing).

### Option B — Headless-browser rendering fallback (Playwright)

Detect an SPA app-shell, launch a headless browser, hydrate, scroll the virtualized sidebar, and
scrape rendered anchors.

- Rejected as the primary path. The spike showed the provider resource/data-source links do
  **not** appear as static anchors even after render + scroll within 30 s (virtualized,
  interaction-gated), and the follow-up Edge-MCP deep probe **quantified** the ceiling: even with
  every category expanded and the sidebar scrolled to the bottom, the DOM exposes only **~39 of the
  1,620** documents (a virtualized/filter-driven subset). Headless scraping is therefore
  **structurally incomplete** for this site, not merely slow. It is also **heavy**: it adds a
  browser runtime + binary download to docline's security and dependency surface, is
  non-deterministic, and is far slower. May be reconsidered later as a *generic* last-resort
  fallback for sites with no discoverable API, behind an explicit opt-in — captured as a future
  option, not this shipment.

### Option C — Generic client-side API sniffing / replay

Auto-observe the XHR/fetch calls a page makes and replay them generically.

- Rejected. Observing the calls requires executing the SPA's JS (same dependency as Option B),
  and replaying arbitrary discovered endpoints is brittle and widens the SSRF/abuse surface.
  Option A's explicit, reviewed per-provider adapter is safer and simpler.

### Option D — Document the limitation, do nothing

- Rejected. This is an operator-reported functional gap on a first-class documentation source.

## Chosen direction

Deliver **Feature: "SPA/API-aware crawl link discovery (Terraform Registry provider-docs
adapter)"** as a **harness-first** release unit:

1. a characterization harness that reproduces the one-page result on a Terraform-shell fixture;
2. a discovery-source seam (recognizer protocol + registry) with unit tests;
3. a recorded-fixture harness pinning the full enumeration + canonical-URL contract;
4. the Terraform Registry adapter implementation (version resolution + paged provider-docs
   enumeration + URL construction, each URL policy-validated);
5. a crawl-integration harness + implementation that seeds the frontier via `admit()` under the
   existing bounds, with graceful fallback to static extraction on adapter failure;
6. a config knob + operator doc note.

## Risk / hardening signals (feeds plan-harden)

- **Requires plan hardening: yes.** New **outbound network path** on the live fetch surface +
  changes to the core `crawl()` loop -> both security-critical and reliability-critical.
- **SSRF**: enumerated URLs and the API endpoints themselves MUST pass `validate_crawl_url` and
  post-resolution `is_unsafe_resolved_address` pinning; no bypass of `url_policy`.
- **Resource bounds**: seeded links MUST be admitted through `frontier.admit()` so
  `max_frontier` / `visited` still bind; the API pagination itself must be byte/attempt-budgeted
  through the shared `RemainingByteBudget`; preserve the `frontier_truncated` signal semantics.
- **Graceful degradation**: adapter/API failure (non-200, schema drift, timeout) must fall back
  to existing static-anchor extraction and never crash or hang the crawl.
- **Determinism / regression**: sites without a matching recognizer must behave exactly as
  today (byte-for-byte discovery parity) — the seam is additive.
- **Third-party contract drift**: pin recorded JSON:API fixtures; parse tolerantly
  (missing/renamed fields skip an entry, they do not abort enumeration).

## Open questions (resolved during planning/harness)

- Enable-by-default vs. opt-in config knob for API discovery — settle in plan (leaning: on by
  default for recognized hosts, with a disable switch, since it is the only way these sites work
  at all).
- JSON:API pagination shape for `provider-docs` (`page[size]` / `links.next`) — the single
  observed call returned all 1,620 via `included`, but the adapter must still follow
  `links.next` defensively; pin in the fixture harness.
- Whether to also emit an observability signal distinguishing "discovered via API adapter" from
  "discovered via static extraction" — resolve in harness design.
