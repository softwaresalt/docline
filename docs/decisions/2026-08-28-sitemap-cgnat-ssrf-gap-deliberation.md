# Deliberation: Close the sitemap SSRF CGNAT (`100.64.0.0/10`) gap

- Date: 2026-08-28
- Stage session: PR #166 post-decomposition cycle-3 (H8 round, cycle 3) — Finding B closure
- Source: PR #166 Copilot review thread `PRRT_kwDOSsAX4c6dXgJs` (comment 3885656388),
  plan `docs/plans/2026-08-27-mcp-stdio-server-plan.md` line ~2722 (`## Risks`, the
  "Medium (tracked follow-up)" bullet)
- Status: accepted — promoted to implementation plan and backlog work item (`065-F`)

## Problem frame

The shared classifier `_is_unsafe_address` (`src/docline/fetch/sitemap.py:173-189`) rejects an
address only when one of six `ipaddress` flags is set: `is_private`, `is_loopback`,
`is_link_local`, `is_multicast`, `is_reserved`, or `is_unspecified`. Carrier-grade NAT (CGNAT)
shared address space `100.64.0.0/10` (RFC 6598) sets **none** of those six flags on any Python
3.12.x — `is_private`, `is_reserved`, and `is_global` all report `False` for that range — so
`_is_unsafe_address("100.64.0.1")` returns `False` and `validate_sitemap_url` would accept a
sitemap URL whose host resolves into CGNAT space.

The PR #166 plan tracked this as a follow-up in `## Risks` but **no backlog work item existed**,
so the fix could be lost. This deliberation creates the durable, dependency-aware work item.

## Reachability and blast-radius assessment (why this is NOT a `055-S` blocker)

1. **`validate_sitemap_url` has no live callers in `src/`.** A repository-wide search for
   `validate_sitemap_url` returns only its definition and `__all__` export — no import or call
   from `crawl.py`, `http.py`, or any other module. The sitemap module is a **dormant
   defense-in-depth** surface pinned by `tests/fetch/test_sitemap.py`; it is not on the live
   CLI or MCP fetch path today.
2. **`055-S` §H6 uses an independent, complete classifier.** The MCP/CLI fetch-path SSRF guard
   delivered by feature `064-F` (§H6, task `064.010-T`/`064.012-T`) re-implements the reserved
   class predicates in `docline.fetch.url_policy` **and adds an explicit `100.64.0.0/10`
   membership check** (plan §H6 DoD: "adds the explicit CGNAT check those six flags miss"). It
   does not delegate to `sitemap._is_unsafe_address`, so it does not inherit this gap.
3. **Conclusion.** The MCP fetch surface shipped by `055-S` is not exposed to the sitemap CGNAT
   gap. `055-S` proceeds unchanged (37 shipment members, order preserved). The sitemap fix is a
   genuinely separable follow-up and is routed to its own shipment so it is dependency-aware and
   cannot be lost. `055-S` scope is NOT expanded.

## Options considered

### Option A — Explicit `100.64.0.0/10` membership check in `_is_unsafe_address` (chosen)

Add a module-level `_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")` and, in
`_is_unsafe_address`, reject when the parsed address is contained in it — mirroring the §H6
fetch-path fix so both surfaces reject the same class. Test-pin the CGNAT class directly (as
`064.010-T` does) rather than trusting the `ipaddress` flag table, since special-purpose tables
are Python-patch-dependent (CVE-2024-4032 hardened `is_private` in 3.12.4).

- Pros: tightest correct fix; single classifier keeps parity with §H6; no new dependency;
  test-first, width-isolated (tests then code); ~1 function touched.
- Cons: none material.

### Option B — Delegate `sitemap` to `url_policy` / share one classifier

Refactor `validate_sitemap_url` to call the §H6 `url_policy` classifier so there is exactly one
SSRF predicate.

- Pros: removes the duplicate predicate long-term.
- Cons: larger blast radius; couples the dormant sitemap module to `064-F`/`055-S` timing and
  would create a cross-shipment dependency; out of scope for a focused security-gap closure.
  Deferred as a possible later consolidation, not required to close the finding.

### Option C — Do nothing / leave as tracked risk

Rejected: the finding requires a real, queued, dependency-aware work item so the fix cannot be
lost, and the classifier is a security boundary even while dormant.

## Chosen direction

Option A, delivered as a two-task (red → green) chore feature `065-F` in a dedicated shipment
`056-S`, queued high-priority, linked `related_to` `064-F` (same address class, different
surface), with **no** blocking dependency on `064-F`/`055-S`.

## SSRF classifier coverage matrix (post-`064-F`/`065-F`)

Adversarial review (Security + Architecture) flagged that SSRF address classification is spread
across independent predicates with divergent coverage. Recorded here so the divergence is visible:

| Surface | Predicate | Live? | DNS resolve | 6 class flags | metadata IPs | CGNAT `100.64.0.0/10` |
|---|---|---|---|---|---|---|
| MCP/CLI crawl (fetch path) | `url_policy` + `http` (§H6, `064-F`) | yes | yes (H6) | yes (H6) | yes (H6) | yes (H6 explicit check) |
| sitemap discovery (dormant) | `sitemap._is_unsafe_address` | no callers | yes (`validate_sitemap_url`) | yes | yes | **added by `065-F`** |

After both land, the CGNAT literal exists as two independent copies (`url_policy` vs `sitemap`) —
a known SSRF drift footgun on a security-critical predicate. The durable fix is Option B
(consolidate onto one canonical classifier), tracked as stash entry `87F2C06D` (kind=feature,
priority=medium) so it is not lost.

## Open questions

- Whether to later consolidate the sitemap and `url_policy` SSRF predicates into one shared
  classifier (Option B) — tracked as stash entry `87F2C06D`; not required to close this work item.
- Whether to also raise `requires-python` to `>=3.12.4` — an independent manifest decision noted
  in the plan `## Risks`, out of scope for this work item.
