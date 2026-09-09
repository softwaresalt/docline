<!-- plan-review-attempt: 1 -->
<!-- plan-review-attempt: 2 -->
<!-- plan-review-attempt: 3 -->
---
title: "Plan: SPA/API-aware crawl link discovery (Terraform Registry provider-docs adapter)"
date: 2026-09-08
status: decided
source_document: docs/decisions/2026-09-08-spa-api-crawl-discovery-deliberation.md
stash_ids: [FC174FA7]
requires_plan_hardening: yes
---

## Objective

Make `web_crawl` discover and fetch the **full documentation set** of JavaScript/SPA-rendered
documentation sites — starting with the Terraform Registry provider docs — instead of stopping
after the single server-rendered app-shell page. Do this **without a runtime browser**, by
adding an additive **discovery-source seam** plus a **Terraform Registry provider-docs adapter**
that enumerates every doc URL via the registry v2 JSON:API and feeds them into the existing
bounded, SSRF-validated crawl pipeline.

Source of truth: the deliberation at
`docs/decisions/2026-09-08-spa-api-crawl-discovery-deliberation.md`
(investigation evidence, options, chosen direction, hardening signals).

## Design constraints (non-negotiable)

1. **Additive / zero-regression**: start URLs with no matching recognizer must behave exactly as
   today (identical discovery output).
2. **Bounds preserved**: seeded links are admitted only through `frontier.admit()`; `max_frontier`,
   section-scope, `visited` dedup, and the `frontier_truncated` signal all still bind
   (compound: admission-cap-must-short-circuit-discovery). Discovery is **lazy**: the adapter is an
   **async iterator** consumed through `frontier.admit()`, so a bound halts further API pagination.
3. **Transport = the existing hardened fetch path (NOT raw httpx)**: every v2 API request is issued
   through `docline.fetch.http.fetch_page(url, ..., budget=budget)` — the stdlib-urllib client with
   connect-time address pinning (`resolve_and_validate` / `_PinnedHTTPConnection`), per-hop redirect
   re-validation under `MAX_REDIRECTS`, TLS verification, and `RemainingByteBudget` debiting. The
   adapter parses `json.loads(response.body)`. No new third-party HTTP dependency is introduced.
   This is what makes I2 (budget) and I3 (post-resolution SSRF / DNS-rebinding) actually hold.
4. **SSRF preserved (both directions)**: every v2 API URL AND every constructed doc URL passes
   `validate_crawl_url` and — because they flow through `fetch_page` — post-resolution
   `is_unsafe_resolved_address` address pinning. Uses the canonical `url_policy` classifier (the
   CGNAT-fixed copy), never a new host allow-list or the sitemap SSRF copy.
5. **Host-confinement to the recognized origin**: `links.next` pagination targets and every
   constructed doc URL MUST have `host == registry.terraform.io` (the recognized start-URL origin)
   before being fetched or admitted; an off-host target is refused/aborted. SSRF policy alone
   permits any public host, so this is a distinct check from the SSRF gate.
6. **Path-segment safety**: `namespace`/`name` (parsed from the start URL) and `category`/`slug`
   (from third-party JSON) are percent-encoded and validated against a strict allowed-character set
   (`[A-Za-z0-9._-]`) before interpolation; a segment failing the pattern is skipped (doc URL) or
   fails recognition (start-URL ns/name). Prevents path traversal / host injection.
7. **Fail-open, with SSRF/budget carve-out**: an adapter/API failure (non-200, timeout, schema
   drift, off-host, JSON-decode) falls back to static anchor extraction and the crawl never crashes
   or hangs. BUT the fallback catches only the narrow adapter/`DoclineError`-subclass error and
   **re-raises** `AggregateBudgetExceededError` and `CrawlUrlRejectedError`, mirroring crawl.py's
   except ordering — a budget/SSRF stop is never masked as "adapter failed, fall back".
8. **No runtime browser dependency**; stdlib + existing deps only.
9. **On success, additive composition**: a recognized host seeds API-enumerated URLs AND still runs
   the normal depth-0 static extraction; `visited`/`_dedup_key` collapse any overlap (no double-fetch).

## Work breakdown (harness-first, dependency-ordered)

### Sub-epic SE-1 — Reproduction harness & discovery-source seam

- **T1 (tests, test-first)** — Characterization test reproducing the one-page result.
  Fixture: a Terraform-Registry-style Ember app-shell HTML (1 anchor, no `/docs/*` sub-links,
  no `toc-*.js`). Assert current `crawl()` yields exactly 1 `CrawlResult`. Locks the defect.
  - Size: S | Complexity: low | Posture: characterization-first
  - Files: `tests/fetch/test_crawl_spa_shell_repro.py` (+ inline fixture)
  - AC: (a) test drives `crawl()` over the shell fixture and asserts `len(results) == 1`;
    (b) test is red-meaningful — documents that discovery found 0 eligible links;
    (c) no production code changed.

- **T2a (tests, test-first)** — Discovery-source seam harness. Unit tests pinning the
  `DiscoverySource` protocol and a minimal first-match registry: `recognizes(start_url) -> bool`
  (pure/sync) and `discover_doc_urls(start_url, config, budget) -> AsyncIterator[str]` (lazy,
  async). Uses a stub source.
  - Size: S | Complexity: low | Posture: test-first (harness before code)
  - Files: `tests/fetch/test_link_sources.py`
  - AC: (a) registry returns `None` for an unrecognized URL (regression-safety);
    (b) registry returns the registered stub source for a matching URL (first-match);
    (c) the stub's `discover_doc_urls` is an async iterator consumed lazily (consumer can stop
    early and the producer stops); (d) harness is red before T2b exists.

- **T2b (code)** — Discovery-source seam implementation: `link_sources.py` exposing the
  `DiscoverySource` protocol + a minimal first-match registry (`register(source)` /
  `find_source(start_url) -> DiscoverySource | None`). Named `link_sources` (not
  `crawl_discovery*`) to avoid colliding with the existing `crawl_discovery.py` robots/backoff
  module.
  - Size: S | Complexity: low | Posture: implement-to-green
  - Files: `src/docline/fetch/link_sources.py`
  - AC: (a) passes the T2a harness; (b) module imports only leaf deps
    (`crawl_models`/`http`/`url_policy`) — **no import of any concrete provider adapter** and no
    cycle into `crawl`/`crawl_models` (crawl_models/http never import the seam back);
    (c) registry is a simple first-match (no multi-source precedence machinery — YAGNI for one
    provider).

### Sub-epic SE-2 — Terraform Registry provider-docs adapter

- **T3 (tests, test-first)** — Adapter enumeration harness with **recorded** v2 JSON:API
  fixtures (trimmed real payloads: providers lookup, provider-versions+provider-docs incl. a
  `links.next` second page) and the expected canonical-URL set. Includes adversarial fixtures.
  - Size: S | Complexity: low | Posture: test-first
  - Files: `tests/fetch/fixtures/tf_registry/*.json`, `tests/fetch/test_tf_registry_source.py`
  - AC: (a) fixtures capture a **paginated** `provider-docs` response (>=2 pages via `links.next`)
    and >=2 categories (resources + data-sources); (b) expected-URL set is asserted exactly
    (category+slug -> `/providers/{ns}/{name}/latest/docs/{category}/{slug}`); (c) fixtures include
    a **hostile-slug** entry (e.g. `../../etc`, `x/../y`) and an **off-host `links.next`** target;
    (d) harness pins the contract before adapter code exists.

- **T4a (code)** — TF registry recognizer + version resolution. `recognizes()` matches
  `registry.terraform.io/providers/{ns}/{name}/(latest|<v>)/docs`; parse, percent-encode, and
  charset-validate (`[A-Za-z0-9._-]`) `{ns}`/`{name}` (fail recognition on a bad segment); resolve
  the provider-version id via `fetch_page("/v2/providers/{ns}/{name}?include=provider-versions",
  budget=budget)` + `json.loads`. Define `TfRegistryAdapterError(DoclineError)` (wrap causes with
  `from err`).
  - Size: S | Complexity: medium | Posture: test-first (uses T3 fixtures)
  - Files: `src/docline/fetch/tf_registry_source.py` (recognizer + version resolution)
  - AC: (a) recognizes valid TF docs URLs, rejects non-TF/off-host URLs; (b) an ns/name with a
    disallowed character fails recognition (no API call); (c) version resolution issues its GET via
    `fetch_page(..., budget=budget)` (NOT raw httpx), and asserts a JSON content-type / guards the
    `json.loads` so a 200 non-JSON body is a deterministic schema-drift error; (d) non-200 /
    JSON-decode / schema-drift raises `TfRegistryAdapterError`, but the `except`/wrap **re-raises**
    `AggregateBudgetExceededError`/`CrawlUrlRejectedError` unwrapped before wrapping (carve-out I4a).

- **T4b (code)** — Paged provider-docs enumeration as a **lazy async iterator**. `async def
  discover_doc_urls(...)` pages `/v2/provider-versions/{id}?include=provider-docs` following
  `links.next` **only while the consumer keeps pulling**; for each entry, percent-encode +
  charset-validate `category`/`slug`, construct the canonical human URL, enforce
  **host-confinement** (`host == registry.terraform.io`) on both the constructed URL and every
  `links.next` target, and `validate_crawl_url` each; `yield` valid URLs; skip (not abort)
  malformed/partial entries. All fetches via `fetch_page(..., budget=budget)`.
  - Size: M | Complexity: high | Posture: test-first (de-risked by the 2026-09-08 spike + T3 fixtures)
  - Files: `src/docline/fetch/tf_registry_source.py` (enumeration; register into T2b registry is
    done at the T6 composition point, not here)
  - AC: (a) passes T3 — yields the exact expected URL set across pages; (b) every yielded URL passes
    `validate_crawl_url` and host-confinement (compared against the **normalized** hostname —
    lowercased, trailing-dot stripped — equal to the literal `registry.terraform.io`, applied to the
    **final** fetched URL after any redirect); (c) a hostile-slug entry yields no off-path/off-host
    URL (skipped); (d) an off-host `links.next` aborts pagination without fetching it; (e) all API
    fetches thread the shared byte/attempt budget via `fetch_page`, and the enumeration `except`/wrap
    **re-raises** `AggregateBudgetExceededError`/`CrawlUrlRejectedError` unwrapped before wrapping
    into `TfRegistryAdapterError` (carve-out I4a); (f) consumer stopping early stops further
    `links.next` fetches (lazy).

### Sub-epic SE-3 — Crawl integration, bounds & security hardening

- **T5 (tests, test-first)** — Integration + bounds harness: recognized start URL ->
  every fixture sidebar link is discovered and fetched; enumerated links admitted through
  `frontier.admit()`.
  - Size: M | Complexity: medium | Posture: test-first
  - Files: `tests/fetch/test_crawl_api_discovery_integration.py`
  - AC: (a) recognized-host crawl over fixtures fetches all enumerated docs (bounded by
    `max_pages`/`max_frontier`); (b) with `max_frontier` below the doc count, result is truncated
    and `frontier_truncated is True`, AND the lazy iterator stopped paginating once the cap bound;
    (c) additive composition — a recognized host whose start page also has static anchors admits
    the union with no double-fetch (`visited` dedup).

- **T5s (tests, test-first)** — Security + degradation harness.
  - Size: M | Complexity: medium | Posture: test-first
  - Files: `tests/fetch/test_crawl_api_discovery_safety.py`
  - AC: (a) an injected private/loopback enumerated URL is rejected — assert the **classifier
    result** (`is_unsafe_resolved_address`), and an API host that DNS-resolves to a private address
    is rejected at connect (rebinding) because fetches go through `fetch_page`; (b) an off-host
    `links.next` **and** an off-host redirect on an API GET are refused; (c) a hostile `category`/
    `slug` produces no off-path/off-host URL; (d) adapter failure -> static-extraction fallback,
    crawl completes, logged **once**, and a budget/SSRF error
    (`AggregateBudgetExceededError`/`CrawlUrlRejectedError`) raised **mid-enumeration** propagates
    unwrapped (not masked as fallback, not swallowed at the adapter or T6 layer); (e) **end-to-end**
    `enable_api_discovery=False` on a recognized host yields byte-identical legacy discovery (not a
    unit assertion — a real crawl).

- **T5c (config)** — Add `CrawlConfig.enable_api_discovery: bool = True` (disable switch);
  the adapter reuses existing `user_agent` / `page_timeout_seconds` threaded via `fetch_page`.
  - Size: XS | Complexity: trivial | Posture: config-only (lands before T6's guard)
  - Files: `src/docline/fetch/crawl_models.py` (field only, no logic)
  - AC: (a) field present with default `True`; (b) no behavioral logic in this task (the guard is
    in T6); (c) width-isolated (config only).

- **T6 (code)** — Wire the seam into `crawl()` and register the concrete adapter here (composition
  point, so the generic seam never imports the provider). At crawl start, when
  `config.enable_api_discovery` and `find_source(start_url)` matches, consume the source's lazy
  async iterator through the normal `_iter_eligible_links`/`frontier.admit()` admission (section-
  scope, dedup, cap all bind) **in addition to** the depth-0 static extraction; on the narrow
  adapter error, log once (via `_origin_label`/`sanitize_source`, never raw URLs) and continue with
  static extraction, while **re-raising** `AggregateBudgetExceededError`/`CrawlUrlRejectedError`.
  Unrecognized/disabled path is byte-identical to today.
  - Size: M | Complexity: high | Posture: test-first
  - Files: `src/docline/fetch/crawl.py` (seed hook + guard + adapter registration)
  - AC: (a) passes the T5 + T5s harnesses; (b) unrecognized start URLs (and `enable_api_discovery=
    False`) produce byte-identical discovery to pre-change (regression test); (c) seeded admissions
    honor `max_frontier`/`visited`; (d) adapter failure logged once and degrades, never raises out
    of `crawl()`, except budget/SSRF errors which propagate.

- **T7 (docs)** — Operator documentation only: describe SPA/API discovery behavior, the Terraform
  Registry provider-docs support, host-confinement/SSRF posture, and the `enable_api_discovery`
  disable switch.
  - Size: S | Complexity: low | Posture: docs-only (width-isolated)
  - Files: `docs/` operator note (no source changes)
  - AC: (a) doc explains behavior, supported sites, and the switch; (b) no code/config change in
    this task.

## Dependency order (execution)

```
T1  (repro, independent — land first)
T2a ─> T2b ─┬─> T3 ─> T4a ─> T4b ─┐
            ├─> T5  ───────────────┼─> T6 ─> T7
            └─> T5s ───────────────┤
T5c ────────────────────────────────┘  (config field, before T6)
```

- T2b depends on T2a. T3 depends on T2b. T4a depends on T2b + T3. T4b depends on T4a.
- T5 and T5s depend on T2b (harnesses target the seam). T5c is independent (config field).
- T6 depends on T4b + T5 + T5s + T5c. T7 (docs) depends on T6.
- T1 is independent and gates nothing but should land first to lock the defect.

Suggested serial order: **T1 -> T2a -> T2b -> T3 -> T4a -> T4b -> T5c -> T5 -> T5s -> T6 -> T7**
(11 tasks, ~2 h each, ~20 h total human-equivalent).

## Constitution Check

Mapping the plan against `.github/instructions/constitution.instructions.md`:

- **I — Safety-First Python**: new modules (`link_sources.py`, `tf_registry_source.py`) and the
  `DiscoverySource` protocol carry full type hints, Google-style docstrings, and a typed
  `TfRegistryAdapterError(DoclineError)`; all satisfy the ordered quality gates (ruff, pyright).
  No new third-party dependency (stdlib + existing `fetch_page`).
- **II — Task Granularity (2-hour rule + width isolation)**: 11 tasks, each < 3 files / < 5
  functions / <= 4 test scenarios; every task is single-width (T1/T2a/T3/T5/T5s tests; T2b/T4a/T4b/T6
  code; T5c config; T7 docs). Harness-before-code pairs: T2a->T2b, T3->T4a/T4b, T5+T5s->T6.
- **III/IV — Isolation/Containment**: all writes under `src/`, `tests/`, `docs/`; no traversal;
  path-segment charset validation prevents constructed-URL traversal.
- **V — Observability**: INFO seed log (origin + count) and single WARNING on fallback (sanitized
  status, no raw URL), reusing `_origin_label`/`sanitize_source`.
- **VI — Single Responsibility / feature-flagged optionality**: `enable_api_discovery` flag;
  additive seam; no new deps.
- **VII/VIII — Destructive-action approval / safety modes**: no destructive actions; strict-safety
  risky-action classification (A1–A3) with a kill-switch rollback; investigate-first honored (the
  2026-09-08 spike preceded planning).
- **Workflow — Backlog-driven**: this markdown breakdown is a pre-decomposition planning artifact
  only; the T-list is decomposed into backlogit as the durable task state (not persisted as the
  tracking source), with the dependency DAG written into task frontmatter (compound:
  add_dependency does not survive sync).
- **Security/bounds**: I2 (frontier bound + budget), I3/I4 (SSRF via `fetch_page` pinning), host-
  confinement — all mapped to T4b/T5/T5s ACs.

No unjustified violations. One operator decision (default-on vs. opt-in for `enable_api_discovery`)
is deferred to the review gate / T7; default-on is acceptable only once the host-confinement and
`fetch_page`-transport ACs (T4b/T5s) are in place — which this revision requires.

## Out of scope (explicit)

- Headless-browser rendering (Option B) — deferred future fallback for API-less SPA sites.
  Empirically ruled out as a *complete* solution for this site (Edge-MCP deep probe: DOM exposes
  only ~39 of 1,620 docs even fully expanded + scrolled).
- Generic API sniffing/replay (Option C).
- Additional provider registries beyond Terraform (the seam is built to accept them later).
- Any change to `060-S` / `069-F` (sitemap dedup) or stash `D6E758F5` (credential sanitization).
- **Browser tooling is investigation/verification-only, not a runtime or CI dependency**: this
  feature is browserless (API + recorded fixtures). The Playwright MCP server's Chrome-vs-Edge
  config fix is tracked separately as stash **4C03AE14** (do not bundle with this shipment; do not
  edit `.mcp.json` during Stage).

## Verification (feature-level)

- Repro test (T1) proves the pre-fix one-page result.
- Integration test (T5/T6) proves discovery + fetch of the **full** fixture sidebar set.
- Regression test (T6) proves byte-identical behavior for unrecognized hosts and for
  `enable_api_discovery=False` (end-to-end, per T5s AC-e).
- Security/bounds tests (T4b/T5s) prove SSRF (via `fetch_page` pinning), host-confinement,
  path-segment safety, lazy short-circuit, and the fail-open carve-out are enforced.

## Plan Hardening

**Hardening required: yes.** Triggers: (1) a **new outbound network path** (calls to the
Terraform Registry v2 API) on the live fetch surface — security-sensitive; (2) modification of
the **core `crawl()` discovery loop** — high blast radius / reliability-critical; (3) dependence
on a **third-party API contract** — external-integration fragility. This matches the
deliberation's `Requires plan hardening: yes`.

### Protected invariants (must survive every task)

- **I1 — Zero-regression for unrecognized hosts.** Discovery output for any start URL without a
  matching recognizer is byte-for-byte identical to pre-change `main`. Enforced by an explicit
  regression test in T6.
- **I2 — Bounds bind on seeded links (lazily).** Every API-enumerated link is admitted only
  through `frontier.admit()`; `max_frontier`, `visited` dedup, section-scope, and the
  `frontier_truncated` signal remain correct. The adapter is a **lazy async iterator** consumed
  through admission, so a full frontier **halts further API pagination** (no I/O the cap will
  refuse) — compound: `2026-08-29-admission-cap-must-short-circuit-discovery.md`. API I/O is
  bounded by the shared `RemainingByteBudget` because all fetches go through `fetch_page`.
- **I3 — SSRF policy is inviolate, via the hardened transport.** Every v2 API request AND every
  constructed doc URL is issued through `docline.fetch.http.fetch_page` — the urllib client with
  connect-time `resolve_and_validate` address pinning, per-hop redirect re-validation, and TLS
  verification. `validate_crawl_url` alone is NOT treated as the SSRF gate (it does not resolve
  DNS); the pinning inside `fetch_page` is. Uses the canonical CGNAT-fixed `url_policy` classifier.
- **I4 — Fail-open, never fail-closed-crash, with carve-out (binding at EVERY except site).** Adapter/API
  failure (non-200, timeout, TLS error, schema drift, off-host, empty) degrades to static-anchor
  extraction; `crawl()` never raises/hangs/returns-zero *because* the adapter was tried. The
  re-raise carve-out binds at **both** layers: (a) the adapter's own `except`/wrap sites around
  `fetch_page` (T4a version-resolution, T4b enumeration) must **re-raise**
  `AggregateBudgetExceededError` and `CrawlUrlRejectedError` BEFORE wrapping anything into
  `TfRegistryAdapterError` — otherwise the wrap masks a budget/SSRF stop as an adapter failure; and
  (b) the T6 fallback catches only `TfRegistryAdapterError`/narrow `DoclineError`-subclass and
  re-raises the same two. A JSON-decode / schema-drift error is a legitimate fallback trigger; a
  budget/SSRF error is never one.
- **I5 — Host-confinement.** `links.next` targets and constructed doc URLs must have
  `host == registry.terraform.io` (recognized origin) before fetch/admit; off-host aborts. Distinct
  from I3 (SSRF permits any public host).
- **I6 — Path-segment safety.** `ns`/`name`/`category`/`slug` are percent-encoded and
  charset-validated (`[A-Za-z0-9._-]`) before interpolation; failing segments skip (doc) or fail
  recognition (start-URL).

### Learnings & instructions consulted

- `docs/compound/2026-08-29-admission-cap-must-short-circuit-discovery.md` (I2 — seeded links
  through admit; preserve `frontier_truncated`).
- `docs/compound/2026-07-04-ms-learn-canonical-url-from-breadcrumb.md` (validate URL construction
  against a real corpus — mitigated by the live 1,620-doc spike + pinned T3 fixtures).
- `.github/instructions/strict-safety.instructions.md` (risky-action classification below).
- `src/docline/fetch/url_policy.py` (I3), `src/docline/fetch/crawl.py` + `crawl_models.py` (I2).

### Risky actions (strict-safety vocabulary)

- **ProposedAction A1**: Issue outbound HTTP GETs to `registry.terraform.io/v2/*` during
  discovery **through the hardened `fetch_page` path** (address-pinned, redirect-revalidated,
  TLS-verified, byte/attempt-budgeted) — NOT a bespoke httpx client. **ActionRisk: medium**
  (network egress to a public host, SSRF-pinned + host-confined + budgeted). Approval: not required
  — but "existing policy" here means the address-pinned `fetch_page` transport plus host-confinement
  (I5), not `validate_crawl_url` alone. **Expected ActionResult**: bounded JSON responses; on
  failure -> fall back (I4 carve-out).
- **ProposedAction A2**: Mutate the core `crawl()` loop to add a pre-static seed hook.
  **ActionRisk: high** (blast radius on the live crawl path). Approval: covered by plan-review
  gate + regression invariant I1. **Expected ActionResult**: additive seed path; unrecognized-URL
  path untouched (regression test green).
- **ProposedAction A3**: Add `enable_api_discovery` to `CrawlConfig`. **ActionRisk: low**
  (additive config field, default `True`, disable switch). **Expected ActionResult**: guarded
  recognizer entry; `False` fully restores legacy behavior.
- No destructive, migration, backfill, or irreversible data/config actions are proposed.

### Added verification / monitoring / rollback

- **Verification depth**: T1 red-meaningful repro; T5 exercises the four safety scenarios
  (full discovery, cap-truncation, SSRF rejection of an injected private URL, adapter-failure
  fallback); T6 regression parity for unrecognized hosts. Each admission/seed site gets a test
  (per the admission-cap learning: count sites, count tests).
- **Monitoring signal**: log once at INFO when API discovery seeds links (count + provider) and
  once at WARNING on adapter fallback (reason) — do **not** log full URLs carrying query tokens
  (coordinate with the credential-sanitization concern tracked separately in D6E758F5; the TF
  registry API URLs here carry no credentials, but keep logging origin/count, not raw URL).
- **Rollback triggers**: any discovery regression on unrecognized hosts, any SSRF/bounds test
  failure, or adapter-induced crawl instability.
- **Rollback procedure**: set `enable_api_discovery = False` (A3 kill switch) to restore legacy
  static-only discovery **without a code revert**; full revert is a single additive-diff revert.
- **Owner / validation window**: Ship claimant; validate on the first real recognized-host crawl
  post-merge (the live Terraform azurerm docs URL) plus the fixture-backed CI suite.

### Review-gate capability risk (carry into plan-review)

- Plan-review must emit literal `dispatch_mode:` and `decision:` markers.
- **P-012 note for review**: `engram` was **degraded** this session (daemon unreachable);
  investigation used direct source reads + live browser/curl probing. Plan review should proceed
  in that degraded-context posture and must **not** block on engram-backed retrieval.

### Unresolved operator decisions blocking safe execution

- None blocking. One default to confirm at review or during T7: `enable_api_discovery` defaults
  to **True** for recognized hosts (justification: these sites are otherwise un-crawlable). A
  reviewer or operator may flip the default to opt-in without changing any task's scope.

## Plan Review

dispatch_mode: multi-agent
decision: FAIL

**Gate: FAIL (attempt 1)** — P1 findings present; plan returned for revision before harvest.

Plan hardening was required and present, but review surfaced P1 security/correctness gaps the
hardening did not fully close. Reviewer subagent dispatch was available (`TOOL_OK:
reviewer-subagent-dispatch`); model-specific routing not asserted, so cross-model personas ran
same-model — recorded, non-blocking. Engram was degraded this session (P-012, carried from plan
hardening); review did not rely on engram retrieval.

### Persona coverage

| Persona | Mode | Result |
|---|---|---|
| Constitution Reviewer | subagent | 1 P1, 2 P2, 5 P3 |
| Python Reviewer | subagent | 4 P1, 3 P2, 2 P3 |
| Scope Boundary Auditor | subagent | 2 P2, 3 P3 |
| Learnings Researcher | subagent | 1 P1, 3 P2, 3 P3 |
| Architecture Strategist | subagent | 3 P2, 2 P3 |
| Security Lens Reviewer | subagent | 2 P1, 2 P2, 3 P3 |

### P1 findings (must fix before harvest)

- **P1-A (Python+Security) Transport:** adapter must route v2 API fetches through the existing
  hardened `fetch_page` (urllib + connect-time address pinning + `RemainingByteBudget`), NOT raw
  `httpx`. Raw httpx does its own DNS/connect with no `is_unsafe_resolved_address` pinning and no
  budget debit — voiding invariants I2 and I3 (DNS-rebinding exposure).
- **P1-B (Python) Async seam:** `enumerate(...) -> list[str]` is sync; it must be
  `async` and await the async fetch path, or it stalls the event loop.
- **P1-C (Python+Architecture) Lazy producer:** an eager list pages the whole 1,620-entry
  collection before admission; a full `max_frontier` cannot stop it. Use a lazy async iterator
  consumed through `frontier.admit()` so a bound halts pagination (admission-cap short-circuit).
- **P1-D (Python) Fail-open carve-out:** the fallback must catch only the narrow adapter/schema
  error and **re-raise** `AggregateBudgetExceededError` and `CrawlUrlRejectedError`, mirroring
  crawl.py's except ordering.
- **P1-E (Security) Host-confinement:** `links.next` targets and constructed doc URLs must be
  confined to the recognized origin host (`registry.terraform.io`); SSRF policy alone permits any
  public host, allowing a malicious response to pivot the crawl off-host.
- **P1-F (Constitution) Constitution Check:** add the mandatory Constitution Check section.
- **P1-G (Learnings) End-to-end kill-switch test:** validate `enable_api_discovery=False` with an
  end-to-end recognized-host crawl proving byte-identical legacy discovery, not a unit assertion
  only (opt-in-flag silent-no-op trap, PR #42 precedent).

### P2 findings (addressed in revision)

- Width isolation: split T2 (code+tests) and T7 (config+docs) by skill domain.
- 2-hour rule: split oversized T4 into recognizer/version-resolution vs. paged-enumeration.
- YAGNI: drop multi-source precedence machinery for a single provider; minimal first-match hook.
- Injection: percent-encode + charset-validate every interpolated path segment (ns/name/category/slug).
- Wiring direction: the generic seam module must not import the concrete provider; register at the
  crawl.py composition point.
- TLS verify + per-hop redirect re-validation on API fetches (inherited by using `fetch_page`).
- Config guard belongs with the seed hook (T6), not retro-edited in T7.

### Next action

Revise plan to close all P1 findings and the listed P2 findings, then re-run the plan-review
gate (attempt 2).

## Plan Review (attempt 2)

dispatch_mode: multi-agent
decision: FAIL

**Gate: FAIL (attempt 2)** — all seven attempt-1 P1 findings verified CLOSED (Security Lens: PASS;
Constitution: PASS), but the revision introduced ONE new P1 (Python Reviewer): the fail-open
carve-out was specified only at the T6 fallback, while the adapter's own `except`/wrap around
`fetch_page` (T4a/T4b) is a new masking site that would rewrap `AggregateBudgetExceededError`/
`CrawlUrlRejectedError` into `TfRegistryAdapterError`. Returned for a narrow fix.

Persona coverage: Python Reviewer (subagent), Security Lens Reviewer (subagent, PASS),
Constitution Reviewer (subagent, PASS). Architecture/Scope/Learnings P2s from attempt 1 were
addressed inline in the revision.

### New P1 (attempt 2) — now fixed

- **P1-H (Python):** extend the I4 re-raise carve-out to bind at the adapter's own `except`/wrap
  sites (T4a AC-d, T4b AC-e), and add T5s AC-d asserting a budget/SSRF error raised mid-enumeration
  propagates unwrapped. Also folded P3 advisories: content-type/JSON guard (T4a AC-c),
  host-confinement on the final post-redirect URL with normalized hostname compare (T4b AC-b),
  off-host redirect refusal (T5s AC-b).

### Next action

Re-run the gate (attempt 3) to verify P1-H closure.

## Plan Review (attempt 3)

dispatch_mode: multi-agent
decision: PASS

**Gate: PASS (attempt 3)** — the attempt-2 P1 (P1-H) is verified CLOSED with no new P0/P1
introduced. Plan hardening required and satisfied; strict-safety risky actions (A1–A3) classified;
Constitution Check present; all P1 findings across attempts 1–2 resolved.

Persona coverage (attempt 3): Python Reviewer (subagent) — P1-H CLOSED, no new P0/P1.
Carried from attempt 2: Security Lens Reviewer PASS, Constitution Reviewer PASS.

Residual advisories (P3, non-blocking — for the implementer, tracked in ACs where actionable):
- T4b remains the riskiest task (Size M / Complexity high, 6 ACs); may be split further at
  execution if the harness grows. De-risked by the 2026-09-08 spike + T3 fixtures.
- Host-confinement normalized-hostname compare and off-host-redirect refusal are now in T4b AC-b /
  T5s AC-b.

**Cumulative decision: PASS → proceed to harvest.**
