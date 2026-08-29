---
title: "Deliberation: Canonical SSRF classifier + sitemap validated-IP pinning"
date: 2026-08-29
status: accepted
stage_session: "stash-to-backlog — SSRF group {0A56B201, 87F2C06D, 0A56B202}"
stash_ids: [87F2C06D, 0A56B201, 0A56B202]
informs: docs/decisions/2026-08-28-sitemap-cgnat-ssrf-gap-deliberation.md
---

## Problem frame

Three active stash entries harden the same security boundary — outbound-fetch SSRF
address classification and connection pinning — spread across
`src/docline/fetch/url_policy.py`, `src/docline/fetch/http.py`, and
`src/docline/fetch/sitemap.py`:

- **87F2C06D** (feature, medium): the unsafe-resolved-address predicate exists as two
  independent copies — `sitemap._is_unsafe_address` and
  `url_policy.is_unsafe_resolved_address` — plus duplicated `_METADATA_IPS` and
  `_CGNAT_NETWORK` constants. The copies have already diverged: `url_policy` carries an
  explicit ULA (`fc00::/7`) membership check that `sitemap` lacks. Divergent reject-lists
  on a security-critical predicate are an SSRF drift footgun.
- **0A56B201** (bug, medium): `sitemap.validate_sitemap_url` classifies resolved IPs then
  returns the original hostname URL. Any consumer that re-resolves at fetch time reopens a
  TOCTOU / DNS-rebinding window (TTL-0: public IP at validation, private/CGNAT at fetch).
- **0A56B202** (task, low): `_is_unsafe_address` runs `addr in _METADATA_IPS` against the
  raw string **before** parse+normalization, so IPv4-mapped metadata forms
  (`::ffff:169.254.169.254`) skip the explicit metadata gate. Currently non-exploitable
  (caught post-normalization by `is_link_local`/`is_private`) but defeats defense-in-depth.

This deliberation resolves the open question left by
`2026-08-28-sitemap-cgnat-ssrf-gap-deliberation.md` ("whether to later consolidate the
sitemap and url_policy SSRF predicates"): the answer is yes, and it is the correct anchor
for both hardening follow-ups because both land cleanly in the consolidated predicate.

## Grounded current state (verified against origin/main @ 16970da)

| Surface | Predicate | Live callers | ULA `fc00::/7` | CGNAT `100.64.0.0/10` | metadata gate |
|---|---|---|---|---|---|
| fetch path (crawl) | `url_policy.is_unsafe_resolved_address` (via `http._Pinned*Connection`) | yes (`crawl.py` -> `fetch_page`) | explicit | explicit | raw pre-parse |
| sitemap (dormant) | `sitemap._is_unsafe_address` (via `validate_sitemap_url`) | none in `src/` | missing | explicit | raw pre-parse |

Two facts drive the design:

1. `http.py` already implements correct pinning: `_PinnedHTTPConnection` /
   `_PinnedHTTPSConnection` resolve+validate+connect atomically via
   `url_policy.resolve_and_validate` and set `server_hostname=self.host` so TLS SNI and
   certificate verification target the DNS name, never the pinned IP. The crawl path is
   already TOCTOU-closed.
2. `validate_sitemap_url` / `_is_unsafe_address` have **zero production callers** — a
   dormant defense-in-depth surface. This bounds blast radius: the changes are additive and
   cannot regress a live path today.

## Grouping decision (contextual similarity)

**One SSRF shipment for {87F2C06D, 0A56B201, 0A56B202}; a separate shipment for the crawl
frontier bug (173238FD).** Rationale:

- The three SSRF entries mutate one coherent security surface (`url_policy` / `sitemap` /
  `http` address classification and pinning) and would land in a single pull request. They
  share a dependency spine: consolidation (87F2C06D) creates the canonical predicate that is
  the natural, one-place home for the metadata-normalization fix (0A56B202) and the shared
  classifier the sitemap pinning path (0A56B201) must consume.
- 173238FD mutates `crawl.py` frontier/queue management — an availability/resource concern,
  not an address-classification concern. It shares no files with the SSRF group and has no
  dependency edge to it. Bundling would violate width isolation and couple two unrelated
  review surfaces. It ships independently and in parallel.

## Options considered — canonical predicate home

### Option A — `url_policy` is the single canonical predicate (chosen)

`url_policy.is_unsafe_resolved_address` becomes the one classifier; `sitemap` deletes its
copy and delegates. Shared constants (`_METADATA_IPS`, `_CGNAT_NETWORK`, `_ULA_NETWORK`)
live in `url_policy`.

- Pros: `url_policy` is the live security path and already the most complete (has ULA +
  CGNAT). Smallest new surface; matches the prior deliberation's "Option B — delegate sitemap
  to url_policy." Import direction `sitemap -> url_policy` is acyclic (url_policy has no
  fetch/sitemap imports).
- Cons: names a transport-policy module as the classifier owner. Acceptable — `url_policy`
  is already the de facto SSRF policy module.

### Option B — new neutral `address_policy` module

Extract the predicate + constants into a new module both import.

- Pros: cleanest ownership; no `sitemap -> url_policy` coupling.
- Cons: more churn; a new public module for a single predicate is speculative given only two
  consumers. Rejected now; recorded as the fallback if an import cycle or a third consumer
  ever appears.

### Option C — leave duplicated, sync by hand

Rejected: divergence already occurred (ULA). Manual sync is the exact footgun 87F2C06D
targets.

## Options considered — sitemap TOCTOU close (0A56B201)

### Option A — sitemap SSRF flows through the pinned connection infra (chosen)

Refactor the sitemap SSRF guarantee to reuse `url_policy.resolve_and_validate` (returns the
validated address set) and the `http._Pinned*Connection` pinning so that resolution,
validation, and connect are atomic and the validated IP is pinned, while Host header, TLS
SNI, and cert verification keep the original hostname. Eliminates the "validate then return
a hostname for someone else to re-resolve" contract.

- Pros: reuses proven, already-shipped pinning; closes TOCTOU by construction; composable —
  one pinning implementation for both surfaces.
- Cons: touches the sitemap module's public contract. Bounded by zero live callers.

### Option B — pin inside `validate_sitemap_url` only, keep separate fetch

Rejected: re-implements pinning in a second place — reintroduces the drift 87F2C06D removes.

### Option C — defer until sitemap discovery is wired live

Rejected: the operator explicitly requested the fix now; harness-first pins the invariant so
a future live wiring inherits it (as the 056-S closure anticipated).

## Chosen direction

Deliver Feature A "SSRF canonical classifier + sitemap validated-IP pinning" (medium,
security-weighted) as a harness-first release unit:

1. Consolidate onto `url_policy.is_unsafe_resolved_address` (87F2C06D).
2. Fix metadata-IP membership to run post parse+IPv4-mapped normalization in the one
   canonical predicate (0A56B202).
3. Refactor the sitemap SSRF path to pin the validated IP via the shared
   `resolve_and_validate` + `_Pinned*Connection` infra, preserving hostname for Host/SNI/cert
   (0A56B201).

Sequenced so the canonical predicate lands first and the two hardening fixes consume it.
Linked `related_to` `064-F`/`065-F` (same address classes, prior surfaces).

## Risk / hardening signals (feeds plan-harden)

- Security boundary change on a fail-closed SSRF classifier — **requires plan hardening: yes**.
- `is_private` semantics are Python-patch-dependent (CVE-2024-4032 hardened `is_private` in
  3.12.4). Test-pin every address class directly; never trust the flag table implicitly.
- Preserve fail-closed behavior: unparseable/ambiguous addresses stay unsafe. Regression risk
  if consolidation drops a class the dormant predicate happened to catch.
- Do not weaken HTTPS: cert/SNI must verify against the hostname, never the pinned IP.

## Open questions

- Whether to raise `requires-python` to `>=3.12.4` for CVE-2024-4032. The prior deliberation
  treated this as an out-of-scope manifest decision; this shipment now treats the runtime floor as
  the **recommended** CVE mitigation (the corrected CPython tables encode the allow-list exceptions
  the predicate must not block), so the plan carries it as an in-shipment manifest bump or a tracked
  follow-up rather than hand-rolled prefix rejection.
- Broader live-crawl sitemap **discovery orchestration** (which module drives sitemap enumeration
  into the crawl frontier) remains out of scope for a future activation shipment. Note: the pinning
  mechanism is NOT deferred — this shipment routes all sitemap retrieval through the pinned
  `fetch_sitemap` -> `fetch_page` sink (see the plan's A.T6), closing the TOCTOU now.
