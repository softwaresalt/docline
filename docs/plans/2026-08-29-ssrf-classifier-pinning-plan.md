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
  `fc00::/7`, IPv6 site-local `fec0::/10`, and a CVE-2024-4032-affected prefix (e.g.
  `192.0.0.0/24`). Assert one shared predicate is consumed by both `sitemap` and `url_policy`
  (delegation identity), and that an unparseable address is `unsafe=True` (fail-closed).
- AC: harness compiles; new tests fail (red) against current divergence (sitemap misses ULA and
  site-local; neither predicate pins the CVE prefix independent of `is_private`). Depends on: none.

### A.T2 — Consolidate onto one canonical predicate + add site-local/CVE-prefix checks (green)

- Domain: src. Files: `src/docline/fetch/url_policy.py`, `src/docline/fetch/sitemap.py`.
- Make `url_policy.is_unsafe_resolved_address` the single classifier; `sitemap` deletes its
  duplicate predicate + `_METADATA_IPS`/`_CGNAT_NETWORK` copies and delegates (import direction
  `sitemap -> url_policy`, verified acyclic). Add explicit `fec0::/10` (`is_site_local`)
  membership and explicit network-membership checks for the CVE-2024-4032-affected special-use
  prefixes so classification does not depend on the runtime `ipaddress` patch level. Preserve
  fail-closed and every existing reject.
- AC: A.T1 class-parity greens; `ruff`/`pyright` clean; live fetch-path behavior unchanged.
  Depends on A.T1.

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

- Domain: src. Files: `src/docline/fetch/sitemap.py` (and, if a resolve-once pinned-target boundary
  is required, an explicit **public** `http.py` boundary — do not export or consume private
  `_Pinned*` classes).
- Make the sitemap SSRF guarantee flow through the public HTTP sink as one inseparable unit:
  `http.fetch_page` / `build_fetch_opener(ProxyHandler({}), pinned handlers,
  _ValidatingRedirectHandler)` so resolution, validation, connect, redirect revalidation, and
  proxy suppression are atomic and the validated IP is pinned while Host/SNI/cert keep the
  hostname. Eliminate the TOCTOU-prone hostname-return contract (consumes 0A56B201). Reuse the
  shipped pinning; do not re-implement it.
- AC: A.T5 harness greens; full `pytest` clean; HTTPS cert/SNI verify against hostname. Depends on
  A.T5 and A.T4 (the full-suite green gate requires the metadata fix landed too).

## Dependency graph

```text
A.T1 -> A.T2 -> A.T3 -> A.T4 ------\
              \-> A.T5 -------------> A.T6
```

Acyclic. Red harness precedes each green consumer. A.T3/A.T4 (metadata) and A.T5 (pinning) both
branch off A.T2; A.T6 joins both (A.T4 and A.T5) so its full-suite green gate is attainable.

## Plan review outcome

Multi-persona adversarial plan review (Security Lens, Architecture Strategist, Scope Boundary
Auditor; diverse models). Verdict: **PASS after fixes** — no P0/P1 remained unaddressed. Fixes
folded in above:

- Added IPv6 site-local `fec0::/10` and explicit CVE-2024-4032-affected-prefix membership to the
  canonical predicate (Security P1 x2).
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
  currently permits 3.12.0-3.12.3. The canonical predicate adds explicit network-membership checks
  for the affected prefixes so classification is patch-independent; A.T1 pins a CVE-affected prefix
  directly. Recommended complementary defense: raise `requires-python` to `>=3.12.4` (carried as an
  open question / independent manifest decision — not required because the explicit checks close the
  gap in-code).
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
