---
title: "Implementation Plan: SSRF canonical classifier + sitemap validated-IP pinning"
date: 2026-08-29
status: reviewed
feature: "Feature A (SSRF)"
source_deliberation: docs/decisions/2026-08-29-ssrf-classifier-pinning-deliberation.md
stash_ids: [87F2C06D, 0A56B201, 0A56B202]
requires_plan_hardening: yes
---

## Objective

Collapse the duplicated, already-diverged SSRF unsafe-address classification onto one
canonical predicate, fix the IPv4-mapped metadata gate in that one place, and close the
sitemap validate-then-return-hostname TOCTOU by pinning the validated IP through the existing
`http.py` pinned-connection infrastructure — without weakening HTTPS and without regressing any
address class the fail-closed classifier currently rejects.

## Grounding (origin/main @ 16970da)

- `url_policy.is_unsafe_resolved_address(addr)` — live fetch-path classifier: metadata IPs
  (raw pre-parse), six `ipaddress` flags, explicit CGNAT `100.64.0.0/10`, explicit ULA
  `fc00::/7`. Returns `bool`, fail-closed on parse failure.
- `sitemap._is_unsafe_address(addr)` — dormant copy: metadata IPs (raw pre-parse), six flags,
  explicit CGNAT. **Missing** the ULA check. Fail-closed on parse failure.
- Duplicated constants: `_METADATA_IPS`, `_CGNAT_NETWORK` in both modules; `_ULA_NETWORK` only
  in `url_policy`.
- `http._PinnedHTTPConnection` / `_PinnedHTTPSConnection` + `_connect_validated_address` +
  `url_policy.resolve_and_validate` already resolve+validate+pin atomically and set
  `server_hostname=self.host` (SNI/cert against hostname). `crawl.py -> fetch_page` is the live,
  already-TOCTOU-closed path.
- `sitemap.validate_sitemap_url` / `_is_unsafe_address` have **zero `src/` callers** (dormant).

## Constitution Check

- I. Safety-First Python: typed exceptions preserved (`SitemapError`, `CrawlUrlRejectedError`);
  full type hints; fail-closed retained. PASS.
- II. Test-First: every task is harness-first; red harness precedes green impl via explicit
  dependency edges. PASS.
- III. Workspace isolation: no path/URL trust changes beyond tightening. PASS.
- VI. Single Responsibility: consolidation *reduces* surface; no new dependency (Option A reuses
  `url_policy`). PASS.
- No dead code: the removed duplicate predicate/constants are deleted, not left dangling.

## Task decomposition (harness-first, <=2h each, width-isolated)

Each task targets a single domain (tests XOR src). Red harness tasks precede their green
consumers via explicit dependency edges.

### A.T1 — Harness: canonical unsafe-address predicate class-parity (red)

- Domain: tests. Files: `tests/fetch/` (new parity test module).
- One parametrized family pinning every rejected class **directly** (never via the flag table):
  private, loopback, link-local, multicast, reserved, unspecified, CGNAT `100.64.0.0/10`, ULA
  `fc00::/7`, and IPv6 site-local `fec0::/10`. Assert one shared predicate is consumed by both
  `sitemap` and `url_policy` (delegation identity), and that an unparseable address is
  `unsafe=True` (fail-closed).
- Over-block guard (positive tests): assert the classifier does **not** reject the
  globally-reachable exceptions inside CVE-2024-4032-affected ranges — `192.0.0.9`, `192.0.0.10`
  (PCP/NAT64 anycast) and a representative reachable `2001::/23` sub-address — so the CVE mitigation
  never blocks valid public-unicast destinations.
- AC: harness compiles; new tests fail (red) against current divergence (sitemap misses ULA and
  site-local). Depends on: none.

### A.T2 — Consolidate onto one canonical predicate + add site-local/CVE-prefix checks (green)

- Domain: src. Files: `src/docline/fetch/url_policy.py`, `src/docline/fetch/sitemap.py`.
- Make `url_policy.is_unsafe_resolved_address` the single classifier; `sitemap` deletes its
  duplicate predicate + `_METADATA_IPS`/`_CGNAT_NETWORK` copies and delegates (import direction
  `sitemap -> url_policy`, verified acyclic). Add explicit `fec0::/10` (`is_site_local`)
  membership to the canonical predicate. Do **not** hand-roll wholesale rejection of the
  CVE-2024-4032-affected prefixes — those ranges keep globally-reachable exceptions (e.g.
  `192.0.0.9`/`192.0.0.10`, six reachable `2001::/23` subranges) and a wholesale reject would block
  valid destinations. The CVE mitigation is the runtime floor (see hardening); the predicate keeps
  relying on the six flags for those ranges. Preserve fail-closed and every existing reject.
- AC: A.T1 class-parity greens (including the over-block guard for `192.0.0.9`/`192.0.0.10`);
  `ruff`/`pyright` clean; live fetch-path behavior unchanged. Depends on A.T1.

### A.T3 — Harness: metadata-IP membership as normalized-object comparison (red)

- Domain: tests. Files: `tests/fetch/` (metadata-gate module).
- Branch-isolate the metadata gate: inject a **globally routable sentinel** into the metadata set
  so only the metadata membership check (not another special-use flag) can reject it, and assert
  IPv4-mapped (`::ffff:169.254.169.254`) plus expanded/compressed IPv6 metadata spellings are
  rejected by that gate after normalization.
- AC: harness compiles; tests fail (red) because the current raw-string `addr in _METADATA_IPS`
  runs pre-parse and compares the un-normalized string. Depends on A.T2.

### A.T4 — Fix metadata-IP membership post parse+normalization (green)

- Domain: src. Files: `src/docline/fetch/url_policy.py` (canonical predicate only).
- Store `_METADATA_IPS` as parsed `ipaddress` objects and compare the **normalized** ip object
  after IPv4-mapped normalization, so mapped/alternate IPv6 metadata spellings hit the gate. One
  place, inherited by both surfaces (consumes 0A56B202).
- AC: A.T3 metadata scenarios green; no regression to raw-literal metadata rejects. Depends on A.T3.

### A.T5 — Harness: sitemap pinned-sink composition (rebinding + redirect + proxy) (red)

- Domain: tests. Files: `tests/fetch/` (extend the `test_ssrf_resolution.py` `_fake_getaddrinfo`
  pattern).
- Pin the full sink invariant, not just connect: (a) a rebinding resolver (public at validation,
  private/CGNAT at connect) is rejected; (b) a redirect target resolving to private/CGNAT is
  rejected; (c) rebinding between the redirect precheck and connect is rejected; (d) `HTTP(S)_PROXY`
  env vars are ignored (no proxy re-resolution); (e) TLS SNI and certificate verification use the
  original hostname, never the pinned IP.
- AC: harness compiles; tests fail (red) against the current validate-then-return-hostname
  contract. Depends on A.T2.

### A.T6 — Route sitemap fetch through the public pinned sink (green)

- Domain: src. Files: `src/docline/fetch/sitemap.py` (reuse the public `http.fetch_page`; no new
  `http.py` boundary required — do not export or consume private `_Pinned*` classes).
- **Concrete contract** (removes the API ambiguity): keep `validate_sitemap_url(url) -> str` as a
  synchronous SSRF **preflight** (scheme/host/literal-IP classification via the canonical
  predicate; it explicitly does NOT perform an authoritative resolve-and-return-hostname handoff).
  Add one authoritative retrieval entry point:
  `async def fetch_sitemap(url: str, *, timeout_seconds: float = 30.0, max_redirects: int = 5) ->
  FetchResponse` that calls `validate_sitemap_url(url)` then delegates to
  `http.fetch_page(url, timeout_seconds=..., max_redirects=...)`, so resolution, validation,
  connect, redirect revalidation, and proxy suppression are atomic and the validated IP is pinned
  while Host/SNI/cert keep the hostname. This is the single sitemap fetch path; the TOCTOU-prone
  hostname-return workflow is removed by making `validate_sitemap_url` preflight-only and routing
  every fetch through `fetch_sitemap`. Reuse the shipped pinning; do not re-implement it.
- AC: A.T5 harness greens against `fetch_sitemap`; full `pytest` clean; HTTPS cert/SNI verify
  against hostname; `sitemap.__all__` exports `fetch_sitemap`. Depends on A.T5 and A.T4 (the
  full-suite green gate requires the metadata fix landed too).

### A.T7 — Raise `requires-python` to `>=3.12.4` for CVE-2024-4032 (config)

- Domain: config. Files: `pyproject.toml` (and CI test-matrix floor if it pins `3.12.0`-`3.12.3`).
- Bump the project's minimum Python to `3.12.4` so the corrected CPython `ipaddress` classification
  (with its documented allow-list exceptions) applies at runtime. This is the concrete CVE-2024-4032
  mitigation — the predicate relies on `is_private`/`is_global` for the affected prefixes and must
  run on the patched tables.
- AC: `requires-python = ">=3.12.4"`; CI matrix floor consistent; build metadata valid;
  `python -m build` succeeds. Width: config only. No code dependency, but the A.T1 over-block guard
  and A.T2 consolidation only classify the CVE-affected exceptions correctly under this floor, so
  A.T2 depends on A.T7.

## Dependency graph

```text
A.T7 ---\
A.T1 --> A.T2 -> A.T3 -> A.T4 ------\
               \-> A.T5 ------------> A.T6
```

Acyclic. Red harness precedes each green consumer. A.T2 depends on A.T1 (harness) and A.T7 (runtime
floor, so the over-block guards classify correctly). A.T3/A.T4 (metadata) and A.T5 (pinning) branch
off A.T2; A.T6 joins A.T4 and A.T5 so its full-suite green gate is attainable.

## Plan review outcome

Multi-persona adversarial plan review (Security Lens, Architecture Strategist, Scope Boundary
Auditor; diverse models). Verdict: **PASS after fixes** — no P0/P1 remained unaddressed. Fixes
folded in above:

- Added IPv6 site-local `fec0::/10` explicit membership; replaced hand-rolled CVE-2024-4032-prefix
  rejection (which would block globally-reachable exceptions) with positive over-block guards plus a
  concrete runtime-floor task A.T7 (`requires-python >= 3.12.4`) (Security P1 x2; cycle-2 review).
- Redesigned the metadata gate as normalized parsed-object comparison with a routable sentinel to
  prevent a false-green harness (Security P2).
- Bound the sitemap fix to the **public** `fetch_page`/`build_fetch_opener` sink (proxy
  suppression + redirect revalidation + pinning as one unit), not private `_Pinned*` classes
  (Security P2, Architecture P2, Scope P2).
- Added the `A.T4 -> A.T6` join so A.T6's full-suite gate is attainable (Architecture P2).
- Split metadata into harness (A.T3) + impl (A.T4) to keep width isolation (tests XOR src).

**Operator override (YAGNI debt acknowledged)**: A.T5/A.T6 harden `validate_sitemap_url`, which
has zero live callers today. The Scope auditor flagged this as pre-activation work. The operator
explicitly directed end-to-end processing of 0A56B201 now, so the TOCTOU close stays in scope;
the harness pins the invariant so a future live wiring inherits it. Debt recorded here per the
auditor's corrective.

## Plan Hardening

- **Risk class: high** (security boundary, fail-closed SSRF classifier). ProposedAction:
  consolidate + repin. Rollback: single-shipment revert; live-path behavior preserved.
- **CVE-2024-4032 guard**: `is_private`/`is_global` tables changed in Python 3.12.4 and pyproject
  currently permits 3.12.0-3.12.3. The mitigation ships in this unit as task **A.T7**
  (`requires-python >= 3.12.4`), so the corrected CPython tables (which encode the allow-list
  exceptions `192.0.0.9`, `192.0.0.10`, reachable `2001::/23` subranges) apply at runtime. The
  predicate deliberately does **not** hand-roll wholesale rejection of these prefixes, which would
  block those globally-reachable exceptions; A.T1 adds positive over-block guards asserting they
  stay accepted (and those guards only classify correctly under the A.T7 floor). The
  security-critical SSRF classes (private/loopback/link-local/CGNAT/ULA/site-local/metadata) are
  pinned by explicit membership independent of the flag table.
- **Regression guard**: A.T1 enumerates every class both predicates currently reject so
  consolidation cannot drop one; the union (adds ULA + site-local to sitemap) only tightens.
- **HTTPS integrity guard**: A.T5 asserts SNI/cert target the hostname, never the pinned IP.
- **Full-sink guard**: A.T5 asserts redirect revalidation and proxy suppression, not just connect
  pinning, so the sitemap fix cannot satisfy pinning while following an unvalidated redirect or
  honoring an env proxy.
- **Fail-closed guard**: unparseable/ambiguous addresses remain unsafe; A.T1 pins that directly.
- **Import-cycle guard**: `sitemap -> url_policy` and `sitemap -> http -> url_policy` verified
  acyclic (`url_policy` imports neither `sitemap` nor `http`); if a cycle ever appears, fall back
  to a neutral `address_policy` module (deliberation Option B).

## Verification

- Gates in order: `ruff check .`, `pyright src/`, `pytest`, `ruff format --check .`.
- Targeted: `pytest tests/fetch/test_sitemap.py tests/fetch/test_ssrf_resolution.py` plus the new
  parity / metadata-gate / pinned-sink tests.
- Runtime spot-check (Ship closure): classifier parity across the pinned class table (incl.
  `fec0::/10` and a CVE prefix) and a rebinding-resolver rejection, mirroring the 056-S closure
  table.

## Rollback

Revert the shipment merge commit. Single-domain (fetch SSRF) change, no data/config migration.
Live fetch path is behavior-preserving, so revert risk is low.
