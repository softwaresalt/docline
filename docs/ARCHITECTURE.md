# Architecture

docline is a document-to-Markdown ingestion and normalization pipeline exposed
through two interfaces — a CLI and a stdio MCP server — that both resolve through
one shared application façade. This document is the top-level domain map and the
authoritative record of dependency direction. It carries boundaries and direction
only; protocol and design rationale live in the deliberations and plans under
`docs/`.

## Interfaces and domains

```text
docline-mcp (console script)
  └─ docline.mcp.__main__            bootstrap: resolve §H8 opt-in, build server
       └─ docline.mcp.stdio          JSON-RPC 2.0 stdio transport (dual-era)
            └─ docline.mcp.server    DoclineMcpServer adapter (tool allow-list)
                 └─ docline.app      shared application façade / contracts
                      └─ fetch · process · readers · schema

docline (console script)
  └─ docline.cli                     argument parsing, console output
       ├─ docline.app                shared application façade / contracts
       └─ docline.elt.orchestrate    fetch orchestration
            └─ fetch · process · readers · schema
```

| Layer | Package(s) | Responsibility |
|---|---|---|
| MCP interface | `docline.mcp.__main__`, `docline.mcp.stdio`, `docline.mcp.server` | stdio transport, dual-era protocol, tool adapter |
| CLI interface | `docline.cli`, `docline.elt.orchestrate` | argument parsing, orchestration, console output |
| Shared façade | `docline.app`, `docline.app_models` | validated `fetch`/`process`/`export_schema` contracts |
| Core domains | `docline.fetch`, `docline.process`, `docline.readers`, `docline.schema` | I/O, extraction, normalization, schema |

## Dependency-direction invariants

* The shared and core domains (`app`, `fetch`, `process`, `readers`, `schema`) do
  **not** import the interface packages (`docline.mcp.*`, `docline.cli`).
  Dependencies flow inward: interfaces → façade → core.
* Both interfaces reach the same domains through `docline.app`
  (`docline.mcp.server` and `docline.cli` both import `docline.app`), so CLI and
  MCP behavior stay in parity by construction.
* Shared-fetch hardening (SSRF-by-resolution, per-response and aggregate byte
  budgets, redirect revalidation — §H6/§H7) lives in `docline.fetch` and applies
  to **both** the CLI and the MCP surface.
* The §H8 external-PDF-engine opt-in policy is **MCP-boundary-specific**
  (`docline.mcp.server` advertise/dispatch gate, `docline.mcp.stdio` `-32602`
  mapping, `docline.mcp.__main__` startup resolution) and does **not** change CLI
  behavior: `docline process --pdf-engine mistral_ocr` is unaffected.

## Crawl frontier truncation observability

The bounded crawl (`docline.fetch.crawl`) admits at most `MAX_FRONTIER` (10,000)
discovered links per crawl, independent of `max_pages` and `max_depth`. When that
ceiling refuses an eligible link, the crawl records the loss through one signal
that reaches **both** interfaces by construction:

* `crawl()` returns a `CrawlOutcome` carrying `results` and a `frontier_truncated`
  flag. The flag reports whether the ceiling cost the crawl an eligible link. It
  is set on a direct admission refusal and, at a depth-zero exhausted
  short-circuit, from an eligible `toc-*.js` reference that cannot be examined
  without a network fetch (the conservative case below). Reaching the cap without
  dropping an eligible link is not truncation.
* A single WARNING is logged once per crawl at default verbosity. Its payload is
  the sanitized crawl **origin** (scheme and host) plus the admission count; it
  omits the path, query, fragment, and userinfo, so a default-visible record
  cannot leak URL-carried credentials.
* `docline.elt.execute` threads the flag into `crawl-manifest.json` (written even
  when zero pages stage) and onto `StagingJob.frontier_truncated`.
* The CLI serializes `StagingJob` verbatim, so the field appears in CLI JSON with
  no CLI-specific change. The MCP path copies it onto `FetchResult.frontier_truncated`.
  Both surfaces report the same value for an equivalent request.

At depth zero, TOC-derived navigation is ordered ahead of in-page anchors, so a
truncated mdBook crawl sheds anchors and keeps the authoritative TOC set. The
signal is deliberately conservative: a depth-zero page that references a TOC
script may report truncation even when that script would have yielded no
admissible links, because confirming otherwise would require the network fetch
the exhausted short-circuit exists to avoid. A false "may be incomplete" prompts
a re-run; a false "complete" would hide data loss.

`MAX_FRONTIER` is not operator-configurable on the CLI or MCP fetch paths, and
the ELT path always uses the default. The remedy for a truncated crawl is to
narrow it with a tighter start URL, a lower `depth`, or a section-scoped entry
point.

## Sitemap preflight de-duplication: single-resolution model

`docline.fetch.sitemap.fetch_sitemap` resolves the **original hostname of a
successful, non-redirected fetch exactly once** — inside
`docline.fetch.http.fetch_page`'s authoritative resolve-validate-pin
sequence, where the resolved address is pinned for the connection — instead
of twice. This is the initial-hop invariant; a followed redirect target is
resolved twice more (a revalidation precheck, then the pinned connection —
see the lookup-count table below), so the total DNS budget for a fetch that
follows redirects is not "one" overall, only one for the initial hop.
`validate_sitemap_url` is a deterministic, resolution-free preflight: it
checks scheme, host presence, cloud-metadata hostnames, and (for IP-literal
hosts only) reserved-address classification via the shared
`docline.fetch.url_policy.is_unsafe_resolved_address` predicate, and never
performs DNS resolution for a hostname. `fetch_page` remains the sole
authoritative hostname resolver, and the sole gate for any address obtained
through that resolution; an IP-literal host is instead gated directly by
the preflight, through the same shared classifier — a resolution-free path
that never involves `fetch_page`.

The two exception types are never interchangeable: `SitemapError` from the
preflight means a **static** disqualification (bad scheme, missing host,
metadata hostname, or an unsafe IP literal). `CrawlUrlRejectedError` is
raised only from `fetch_page`, never the preflight, for any crawl-policy or
address-gate rejection it enforces — not resolved-address rejection alone:
a malformed port or other `validate_crawl_url` policy failure, DNS
resolution failure or an empty resolver answer, or a resolved address (for
the hostname or any redirect target) the canonical predicate rejects.

Hostname-lookup counts (one `getaddrinfo` call whose host argument is the
original hostname — not a raw count of every `getaddrinfo` call, since
`socket.create_connection` also resolves an already-validated numeric
address):

| Scenario | Hostname lookups |
|---|---|
| Successful initial hop | 1 (`fetch_page`'s connect) |
| Each followed redirect target | 2 (redirect precheck + pinned connection) |
| Redirect target rejected at precheck | 1, and no connection attempted |
| Preflight (`validate_sitemap_url`) | 0 |

`timeout_seconds` continues to bound the preflight call plus the fetch
combined: the preflight is still offloaded to the default executor under
`asyncio.wait_for` and its elapsed time is still deducted from the deadline
handed to `fetch_page`, even though the preflight itself no longer performs
any resolution — `fetch_sitemap`'s executor-offload and deadline-arithmetic
contract is unchanged by this de-duplication.

## SPA/API-aware crawl link discovery

Some documentation sites (for example the Terraform Registry's provider-docs
pages) render as a JavaScript single-page-application shell: the raw HTML
response carries no static anchors to the rest of the site's documents, so a
pure static-extraction crawl (`docline.fetch.crawl_links.extract_links`)
discovers only the one start page. `docline.fetch.crawl` addresses this with a
**pluggable, browserless discovery-source seam** rather than a headless
browser: a recognized start URL can be enumerated through the site's own API,
while every other host is completely unaffected.

* `docline.fetch.link_sources` defines the generic seam: a `DiscoverySource`
  protocol (`recognizes(start_url) -> bool`,
  `discover_doc_urls(start_url, config, budget) -> AsyncIterator[str]`) plus a
  first-match `register()`/`find_source()` registry. This module never imports
  a concrete provider adapter — it stays genuinely site-agnostic.
* `docline.fetch.tf_registry_source.TfRegistrySource` is the first concrete
  adapter: it recognizes `registry.terraform.io/providers/{namespace}/{name}/
  (latest|<version>)/docs` start URLs and lazily enumerates every document URL
  for that provider via the registry's `v2` JSON:API (paginated
  `provider-docs` relationship), constructing human-readable doc URLs
  (`/providers/{namespace}/{name}/latest/docs/{category}/{slug}`) without ever
  loading a browser. Only the `"latest"` version segment is actually resolved
  and enumerated: a pinned, non-`"latest"` version URL is recognized (so it is
  never treated as an ordinary static-only host) but fails closed with an
  explicit adapter error rather than silently substituting the current latest
  version's docs — degrading to static-only extraction like any other adapter
  failure. Genuine pinned-version resolution is tracked as follow-up work.
* `docline.fetch.crawl` is the **composition point**: it registers
  `TfRegistrySource` into the seam at import time (so the generic seam module
  still never imports it), and at the start of every crawl — when
  `CrawlConfig.enable_api_discovery` is `True`, `CrawlConfig.max_frontier > 0`,
  and a registered source recognizes the start URL — lazily drains that source
  and admits each URL through the *same* frontier ceiling, domain-lock/section
  -scope filter, and visited-dedup rules static anchor links already go
  through. Discovery is strictly **additive**: the start page's own static
  anchors are still extracted and admitted normally, and a URL surfaced by
  both paths is fetched exactly once.

Safety and degradation posture, uniformly enforced at the composition layer
(not merely trusted from the adapter):

* **Host confinement.** Every adapter fetch — the version lookup and every
  paged `provider-docs` request — forbids redirects outright
  (`max_redirects=0`, never the crawl's own `max_redirects`): the shared
  transport's redirect handler rejects private/reserved targets (SSRF) but
  permits redirecting to any other *public* host, and only validates the
  *final* URL after the outbound hop already happened, so forbidding
  redirects entirely closes the gap instead of merely detecting it post-hoc.
  A paginated `links.next` target pointing off-host stops pagination
  silently (no further fetch, no error) rather than being followed, and a
  `links.next` that cycles back to an already-fetched pagination URL also
  stops pagination immediately rather than looping until the global
  attempt budget exhausts. Every fetch's final response URL is additionally
  asserted host-confined as defense-in-depth. Every outbound fetch continues
  to route exclusively through `docline.fetch.http.fetch_page` — the same
  connect-time address-pinned, budget-aware transport every other crawl path
  uses, so DNS-rebinding protections apply identically here.
* **Path-segment safety.** Namespace, name, version, category, slug, and the
  resolved provider-version id are all charset-validated (an allowlist, plus
  an explicit reject of the bare reserved segments `"."`/`".."`, which the
  charset allowlist alone would not catch) before being percent-encoded into a
  constructed URL; a hostile or malformed entry (for example a path-traversal
  slug) is skipped, never aborts the rest of the enumeration.
* **`respect_robots` applies to discovery too.** A start URL disallowed by
  `robots.txt` never triggers the discovery seed's own outbound API requests
  — discovery is additional traffic made on the start URL's behalf, so it is
  gated on the same cached robots check the crawl's main loop performs for
  every page, not exempt from `CrawlConfig.respect_robots`. This check covers
  the start URL's own path; the adapter's internal API endpoints (the
  version-lookup and provider-docs-page requests) are not individually
  re-checked against `robots.txt`, matching the existing precedent for other
  auxiliary discovery fetches (mdBook `toc-*.js` script requests are not
  individually robots-checked either) — every *user-facing* discovered
  document URL still receives its own per-URL robots check via the main
  crawl loop, unchanged.
* **Seed stops once the page budget is covered.** The seed also stops pulling
  once the frontier queue already holds `max_pages` items — at seed time
  (always before the main loop's first iteration) that many admissions are
  already guaranteed to exhaust the crawl's own page-fetch budget, so
  continuing to paginate a large provider's API past that point would
  perform additional network fetches purely to enqueue URLs the main loop
  will never reach. Distinct from the `max_frontier` ceiling above: this is
  not a frontier-ceiling refusal and never affects `frontier_truncated`.
* **Frontier-ceiling efficiency.** The composition point checks the
  `max_frontier` ceiling *before* pulling each item from a discovery source's
  async generator (not after, unlike the existing admit-then-check pattern used
  for already-parsed in-memory anchor links), so a paginated, network-backed
  source is never driven to fetch one further page just to have it refused.
  This is what bounds a large provider's enumeration (for example the Terraform
  Registry's ~1,600 `azurerm` documents) by `max_frontier` rather than by the
  provider's own document count. `max_frontier == 0` ("disable link discovery
  entirely") skips the discovery seed outright rather than reporting a
  false-positive truncation before ever asking the source for an item; for any
  other cap, an exact-boundary case (the source's remaining items happen to
  equal the remaining capacity) is a deliberately conservative over-report,
  mirroring the existing depth-zero TOC-script truncation signal.
* **Independent of `max_depth`/`depth`.** `max_depth`/`depth` bounds *static
  HTML link traversal* hops only. A recognized discovery source's
  API-enumerated documents are seeded once at crawl start regardless of this
  value — they are siblings of the start page (all part of one logical
  provider's document set), not deeper-hop targets reached by following
  links, so `depth=0` (the default, meaning "single page only" for static
  traversal) does not suppress discovery. Set
  `enable_api_discovery=False` for a host where pure depth-bounded static
  traversal is required instead.
* **Fail-open degradation.** A generic adapter failure is logged once (the
  sanitized crawl origin only, never a raw URL or credential-bearing data) and
  the crawl falls back to static-only extraction for the rest of the run — it
  never aborts the crawl. A completed, error-free seed also logs a single INFO
  record (sanitized origin plus the count of URLs seeded) for observability. A
  budget or SSRF rejection (`AggregateBudgetExceededError` /
  `CrawlUrlRejectedError`) raised mid-enumeration is never masked as a generic
  adapter failure: it propagates uncaught out of `crawl()`, identical to any
  other budget/SSRF rejection during a crawl.
* **Disable switch, operator-reachable.** `CrawlConfig.enable_api_discovery`
  (default `True`) disables discovery-seam consultation entirely when set to
  `False`: the crawl falls back to byte-identical legacy
  static-extraction-only behavior for a recognized host, with no other
  behavioral change. Reachable end-to-end from every public fetch surface —
  `FetchRequest.enable_api_discovery` (MCP `fetch` tool and
  `docline.app.execute_fetch`), `WebCrawlSource.enable_api_discovery` (flat
  ELT `type: web_crawl` config), and `ManifestUrlSource.enable_api_discovery`
  (graphtor-docs manifest `type: url` entries) — not merely a Python-level
  `CrawlConfig` construction, so an operator can flip it without a code
  change or revert.
* **Page/frontier budget still applies.** Discovery only changes what a crawl
  *can discover* (bounded by `max_frontier`); it does not change how many
  pages a crawl *fetches* (bounded by `max_pages`, default `50`). Reaching a
  large provider's full document set (for example all ~1,600 `azurerm`
  documents) requires an explicit `max_pages` override sized for that
  provider — the same pre-existing, intentional safety bound every crawl
  already has, unrelated to this feature.

This design is deliberately browser-free: an investigation into headless
browser crawling found that the Terraform Registry's sidebar is virtualized
and API-driven, exposing only a small fraction of a provider's documents to
DOM inspection even after fully expanding every category — so a runtime
browser dependency would still be structurally incomplete. The API-backed
adapter, by contrast, discovers the provider's complete, authoritative
document set.

