# Operational Closure — 056-S: sitemap CGNAT (100.64.0.0/10) SSRF gap

- **Shipment:** 056-S
- **Feature:** 065-F (tasks 065.001-T, 065.002-T)
- **PR:** #167 — MERGED 2026-08-29T09:09:48Z
- **Merge commit:** `9560d48dbd44c2e0ce0c30c593a7352ea966ef88` (merge commit strategy, P-009 compliant)
- **Branch:** `chore/056-s-sitemap-cgnat-ssrf`
- **Mode:** Ship, autonomous (operator AFK, merge permission granted)

## What shipped

Extended the sitemap SSRF classifier `_is_unsafe_address`
(`src/docline/fetch/sitemap.py`) to reject Carrier-grade NAT (CGNAT)
shared address space `100.64.0.0/10` (RFC 6598) via an explicit
`ipaddress` network-membership check, plus guarded IPv4-mapped IPv6
normalization applied before classification. Mirrors the §H6 fetch-path
CGNAT fix (064-F / `url_policy`) on the pre-existing sitemap surface.

## Release readiness

- Quality gates: `ruff check` clean · `ruff format --check` clean ·
  `pyright src/` 0 errors · `pytest` 1651 passed / 6 skipped.
- CI (PR #167): all checks green (ruff lint, ruff format, pyright, pytest
  ubuntu-latest, sdist+wheel, ci gate).
- Review: multi-persona adversarial review verdict **SHIP** — zero
  consensus/majority findings; one model's CRITICAL verified as a false
  positive (`::a.b.c.d` → `::/8` → `is_reserved`, already rejected).

## Runtime verification

Classifier exercised live against merged code:

| Input | Result | Expected |
|---|---|---|
| `100.64.0.1` | unsafe=True | reject ✓ |
| `::ffff:100.64.0.1` | unsafe=True | reject ✓ |
| `100.63.255.255` | unsafe=False | accept ✓ |
| `93.184.216.34` | unsafe=False | accept ✓ |
| `validate_sitemap_url("http://100.64.0.1/sitemap.xml")` | raises SitemapError | reject ✓ |
| `validate_sitemap_url("http://[::ffff:100.64.0.1]/sitemap.xml")` | raises SitemapError | reject ✓ |

## Monitoring / rollback

- **Blast radius:** minimal. `validate_sitemap_url`/`_is_unsafe_address`
  has zero production callers today (dormant defense-in-depth). The change
  is additive — no behavior change for existing address classes or
  non-mapped inputs.
- **Rollback:** revert merge commit `9560d48`; single-module change, no
  data/config migration.
- **Monitoring:** none required — no runtime surface activated. Any future
  shipment wiring sitemap discovery into the crawl path inherits the fix.

## Source artifact cleanup / archival

- Archived `056-S`, `065-F`, `065.001-T`, `065.002-T` from
  `.backlogit/queue/` to `.backlogit/archive/` with `status: archived`,
  `commit: 9560d48…`. (Manual archival — backlogit MCP/CLI unavailable in
  this environment.)
- Commit traceability: merge SHA recorded in each archived item's
  `commit` field.

## Follow-ups stashed for Stage (advisory, non-blocking)

From adversarial review LOW/advisory findings:

1. **SSRF TOCTOU / DNS-rebinding on returned hostname** (pre-existing,
   architectural) — `validate_sitemap_url` returns the hostname URL, which
   the HTTP client re-resolves at fetch time; a TTL-0 attacker could pass
   validation then serve a private/CGNAT IP at fetch. Fix requires pinning
   the validated IP into the outbound connection. Out of scope for this
   width-isolated chore.
2. **Metadata-IP membership check runs pre-parse** — `addr in _METADATA_IPS`
   matches raw strings, so IPv4-mapped metadata forms skip the explicit
   gate. Currently non-exploitable (caught by `is_link_local`/`is_private`
   post-normalization); defense-in-depth hardening only.

Both stashed to `.backlogit/stash.jsonl` for Stage triage.
