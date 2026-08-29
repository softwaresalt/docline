# Plan: Close the sitemap SSRF CGNAT (`100.64.0.0/10`) gap

- Date: 2026-08-28
- Type: chore (security hardening)
- Source deliberation: `docs/decisions/2026-08-28-sitemap-cgnat-ssrf-gap-deliberation.md`
- Origin: PR #166 Copilot thread `PRRT_kwDOSsAX4c6dXgJs` (comment 3885656388); tracked-follow-up
  bullet in `docs/plans/2026-08-27-mcp-stdio-server-plan.md` `## Risks` (line ~2722)
- Backlog: feature `065-F`, tasks `065.001-T` (red) → `065.002-T` (green), shipment `056-S`
- Requires plan hardening: no (single-function, dormant-surface, additive reject; low blast radius)

## Objective

Extend the shared sitemap SSRF classifier `_is_unsafe_address`
(`src/docline/fetch/sitemap.py:173-189`) to reject Carrier-grade NAT (CGNAT) shared address space
`100.64.0.0/10` (RFC 6598) with an **explicit network-membership check**, closing the gap where
none of the six `ipaddress` flags (`is_private`, `is_loopback`, `is_link_local`, `is_multicast`,
`is_reserved`, `is_unspecified`) catch that range on Python 3.12.x. This mirrors the §H6 fetch-path
fix (`docline.fetch.url_policy`, feature `064-F`) so both SSRF surfaces reject the same class.

## Constitution Check

- **II. Test-First (NON-NEGOTIABLE):** red harness (`065.001-T`) authored and observed failing
  before the green implementation (`065.002-T`).
- **III. Workspace Isolation / SSRF boundary:** this change strengthens a security boundary; no
  file-system or path-traversal surface touched.
- **VI. Single Responsibility:** no new dependency; uses stdlib `ipaddress` already imported by the
  module.
- **Width Isolation:** task 1 is tests-only (`tests/fetch/test_sitemap.py`); task 2 is code-only
  (`src/docline/fetch/sitemap.py`). No task crosses domains.

## Scope

**In scope**
- Add module-level `_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")` to `sitemap.py`.
- In `_is_unsafe_address`, after the six-flag classification, reject when the parsed address is
  contained in `_CGNAT_NETWORK`.
- Red tests: CGNAT IP-literal rejection (`100.64.0.1`, `100.127.255.255`, boundary
  `100.64.0.0`/`100.127.255.255`), a host that resolves into CGNAT (DNS-rebinding style), and a
  direct class-pin `_is_unsafe_address("100.64.0.1") is True` (pin the class, not the flag table,
  since special-purpose tables are Python-patch-dependent — CVE-2024-4032).
- Regression rows proving public-unicast (e.g. `93.184.216.34`) and the just-below/above boundary
  (`100.63.255.255` public, `100.128.0.0` public) stay ACCEPTED so the fix does not over-reject.

**Out of scope**
- Consolidating the `sitemap` and `url_policy` SSRF predicates into one shared classifier
  (deliberation Option B) — a possible later refactor, not required here.
- Raising `requires-python` to `>=3.12.4` — independent manifest decision noted in the `064-F`
  plan `## Risks`.
- Any change to `064-F` / shipment `055-S`. The §H6 fetch-path classifier is independent and
  already includes an explicit CGNAT check; this work item does NOT block `055-S`.

## Relationship to `064-F` / `055-S` (no blocking dependency)

`validate_sitemap_url` (the only consumer of `_is_unsafe_address`) has **no live callers** in
`src/` — the sitemap module is dormant defense-in-depth pinned by `tests/fetch/test_sitemap.py`.
The MCP/CLI fetch path shipped by `055-S` uses the independent §H6 `url_policy` classifier, which
re-implements the reserved predicates AND adds its own explicit `100.64.0.0/10` check. Therefore:

- `055-S` is NOT exposed to this gap and proceeds unchanged (37 members, order preserved).
- `065-F` is linked `related_to` `064-F` (same address class, different surface) but carries **no**
  blocking dependency on `064-F`/`055-S`; it can be built and shipped in any order relative to
  `055-S`. `065.001-T` and `065.002-T` touch only `tests/fetch/test_sitemap.py` and
  `src/docline/fetch/sitemap.py` — disjoint from the `064-F`/§H6 files
  (`url_policy.py`/`http.py`/`crawl.py`/`app_models.py`), so no merge-order conflict arises.

## Implementation units

1. **`065.001-T` (red, tests-only):** author failing CGNAT rejection rows in
   `tests/fetch/test_sitemap.py` — IP-literal, resolved-host (rebinding), boundary, class-pin, and
   public-unicast/boundary-accept regression rows. Observe RED before implementation.
2. **`065.002-T` (green, code-only):** add `_CGNAT_NETWORK` and the explicit membership check to
   `_is_unsafe_address`; greens `065.001-T`. Depends on `065.001-T`.

## Verification

- `pytest tests/fetch/test_sitemap.py` — new CGNAT rows RED at `065.001-T`, GREEN at `065.002-T`;
  all pre-existing sitemap tests stay GREEN (public-unicast still accepted; no over-rejection).
- `ruff check .`, `ruff format --check .`, `pyright src/` clean.

## Rollback

Purely additive: one module-level constant + one `if` clause in `_is_unsafe_address`, plus new
test rows. Revert the two commits (test + impl) to restore prior behavior; no data migration, no
schema or dependency change.

## Risks

- Low: over-rejection of a legitimate host that resolves into `100.64.0.0/10`. CGNAT is
  provider-internal shared space that a public sitemap should never legitimately resolve into;
  regression rows pin the just-below/above boundaries as ACCEPTED to bound the change.
