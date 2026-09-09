---
title: "Stage session memory — SPA/API-aware crawl link discovery"
date: 2026-09-08
agent: stage
stash_ids: [FC174FA7]
feature: 070-F
shipment: 061-S
status: complete
---

## Session summary

Operator-reported bug: `web_crawl` of `https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs`
fetched only one page. Ran the full Stage pipeline (intake → investigate → deliberate → plan →
harden → review → harvest → shipment).

## Tool status

- `backlogit`: TOOL_OK.
- `engram`: TOOL_DEGRADED — daemon never reached Ready (30s timeout); stopped a stale locked
  daemon (pid 40300); `index --direct` non-terminating within ~8 min. Fallback: direct source
  reads + live browser/curl probing. `workspace-status` is the status equivalent (no `status` cmd).
- Playwright MCP not exposed to session initially; used operator-provided `node_modules/@playwright/mcp`
  read-only via `playwright-core` + system Edge (`channel: msedge`). Later the operator recovered an
  Edge-backed Playwright-MCP route (`copilot -p ... --additional-mcp-config` with
  `@playwright/mcp --browser msedge --headless`); used it for the deep DOM/scroll/network probe.
  MCP server Chrome-vs-Edge config fix tracked as stash **4C03AE14** (not edited during Stage).

## Investigation evidence (root cause)

- Raw curl of the docs URL = 9,218-byte Ember SPA app-shell: 1 anchor, 0 /docs sublinks, no
  toc-*.js. docline's stdlib `urllib.request`-based `fetch_page` (address-pinned, no httpx) executes no JS → discovery finds nothing → 1 page.
- Headless Edge render: 104 anchors but provider resource/data-source links do NOT render as
  static anchors even after 30s + scroll (API-driven, virtualized).
- Edge-backed Playwright-MCP deep probe (follow-up, recovered route): settled DOM exposes 0
  matching doc sublinks (categories collapsed); after expanding categories/filter = 39; after
  scrolling = still 39. DOM caps at ~39 of 1,620 → DOM scraping is structurally incomplete;
  only the v2 JSON:API is complete. Sidebar = nav.provider-docs-menu > div.provider-docs-menu-content.
- Network capture: sidebar backed by registry v2 JSON:API — `/v2/providers/{ns}/{name}?include=
  provider-versions` → version id; `/v2/provider-versions/{id}?include=provider-docs` → full list.
- Browserless proof: plain curl of the provider-versions call returned ALL 1,620 azurerm docs
  (1104 resources, 396 data-sources, 94 list-resources, 14 guides, 7 actions, 2 ephemeral, 2
  functions, 1 overview). Every human URL constructible from category+slug. No runtime browser needed.

## Decisions

- Chosen: additive discovery-source seam + Terraform Registry provider-docs API adapter feeding the
  existing bounded/SSRF-validated crawl. Rejected: headless-render (heavy, unreliable on this
  virtualized sidebar), generic API sniffing, do-nothing.
- Deliberation: docs/decisions/2026-09-08-spa-api-crawl-discovery-deliberation.md
- Plan: docs/plans/2026-09-08-spa-api-crawl-discovery-plan.md (requires_plan_hardening: yes → hardened).

## Plan-review gate

- Attempt 1: FAIL (7 P1s: httpx-vs-fetch_page transport, sync-vs-async seam, eager-vs-lazy iterator,
  fail-open swallowing budget/SSRF, host-confinement, missing Constitution Check, unit-only kill-switch test).
- Attempt 2: FAIL (1 new P1: fail-open carve-out not bound at the adapter's own except sites).
- Attempt 3: PASS (P1-H closed, no new P0/P1). Security Lens + Constitution PASS.

## Harvest → shipment

- Feature 070-F (queued). Tasks 070.001-T … 070.011-T (11), dependency-ordered, deps persisted in
  frontmatter via `--dependencies` at create time (avoids the SQLite-cache-only erase pitfall).
- Shipment 061-S (queued, high) = 070-F + 11 tasks, parent-first. **Handoff token to Ship: 061-S.**
- Stash FC174FA7 archived. D6E758F5 (credential sanitization) left active/untouched. 060-S/069-F untouched.

## Degradations flagged

- Structured `size`/`complexity` unavailable: workspace `task` WIT does not define the fields
  (despite registry `features.sizing: true`). Values preserved as prose (`Size: X | Complexity: Y`)
  in each task description per the two-axis fallback.

## Next step (Ship)

Ship claims shipment 061-S and executes T1→T2a→T2b→T3→T4a→T4b→T5c→T5→T5s→T6→T7.
