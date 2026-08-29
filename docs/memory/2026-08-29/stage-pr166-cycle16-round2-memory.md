---
type: session-memory
agent: stage
date: 2026-08-29
shipments:
    - 055-S
    - 056-S
features:
    - 064-F
    - 065-F
pr: 166
cycle: cycle-16 round cycle-2
head: 30fad9b62f3653607adcbd1b39fb4460da7d25c3
---

# Stage session — PR #166 cycle-16 round-2 (HEAD 30fad9b)

Planning/backlog/docs reconciliation only. **No production or test source touched.** Five Copilot
review findings closed after a multi-persona adversarial review (security limits / valid MCP frame
sizes / liveness testability / TDD ordering / IPv4-mapped normalization / scope accounting /
shipment isolation / PR disclosure). No new tasks. Shipment `055-S` stays at **37 members**, `056-S`
at **3 members**; order unchanged.

## Two-shipment disclosure (Finding 5 — comment 3885888283 on `056-S`)

PR #166 stages **two independently executable shipments** on branch `chore/stage-055-s`, but the PR
description discloses only `055-S`. Stage cannot perform PR actions, so the recommended amendment is
recorded here and the plan/handoff now truthfully names both shipments.

- **`055-S` — Local stdio MCP server and docline-mcp executable** (feature `064-F`, 36 tasks).
- **`056-S` — Close the sitemap SSRF CGNAT (`100.64.0.0/10`) gap** (feature `065-F`, 2 tasks).

The two shipments have **no blocking dependency** (disjoint files; the sitemap surface is dormant),
and MUST be claimed, implemented, reviewed, and shipped **independently** by Ship on separate
shipment-scoped branches/PRs (Ship records one `shipment_id` per session). This staging PR carries
both manifests because it changes **planning/backlog/decision/memory artifacts only** — it must
never become the implementation PR for both shipments.

### Recommended PR title/body amendment (exact — for the operator/Ship to apply; Stage does not push or edit PRs)

**Title**

```text
chore(docs): stage MCP stdio (055-S) and sitemap CGNAT SSRF (056-S) shipments
```

**Body**

```text
Stages reviewed planning and backlog artifacts for two independently executable shipments. No
production or test code changes.

- 055-S — Local stdio MCP server and docline-mcp executable (feature 064-F, 36 tasks): the
  adversarially reviewed dual-era MCP stdio plan, security-hardened (H1-H8) feature/task hierarchy,
  dependency chain, blocked evidence-gated research backlog, and archived stash intake.
- 056-S — Close the sitemap SSRF CGNAT (100.64.0.0/10) gap (feature 065-F, 2 tasks): a test-first
  red/green pair extending _is_unsafe_address to reject RFC 6598 CGNAT shared address space
  (including the IPv4-mapped IPv6 literal form). Dormant defense-in-depth surface; no blocking
  dependency on 055-S (disjoint files), independently shippable.

Both shipments are queued and must be claimed, implemented, reviewed, and shipped independently by
Ship on separate shipment-scoped branches/PRs. Operator-approved dark-factory pipeline.
```

## Findings closed

1. **IPv4-mapped normalization** — comment 3885888208 on `065.002-T`. The sitemap SSRF membership
   test allowed `::ffff:100.64.0.1` (an `IPv6Address` is not a member of the IPv4 `_CGNAT_NETWORK`,
   and 3.12 patch levels classify mapped special-use addresses inconsistently). `065.002-T` now
   normalizes `ip` to its embedded IPv4 BEFORE the six-flag + CGNAT checks, **guarded for
   `IPv6Address` only** (`if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
   ip = ip.ipv4_mapped`), with version-guarded membership (`ip.version == 4 and ip in
   _CGNAT_NETWORK`). `065.001-T` gained in-place mapped-literal rows. **P0 caught in adversarial
   review:** an unguarded `ip.ipv4_mapped or ip` crashes on ordinary IPv4 (`IPv4Address` has no
   `.ipv4_mapped`) — the guarded form is mandatory. Only `::ffff:0:0/96` maps; deprecated
   IPv4-compatible `::/96` is not reinterpreted. Reconciled: CGNAT plan, `065-F`, `065.001-T`,
   `065.002-T`.

2. **`MAX_FRAME_BYTES` concrete value** — comment 3885888241 on `064.006-T`. Selected
   **`MAX_FRAME_BYTES = 1 MiB` (`1_048_576` payload bytes)** as an explicit operational/compatibility
   bound (NOT protocol-derived): docline MCP request frames are control-plane only (paths/URL/enums/
   flags; no inline document bytes; batch arrays unsupported → `-32600`), so 1 MiB accommodates any
   realistic request (incl. a large `initialize`/`clientCapabilities` `_meta`) while bounding
   per-frame memory. Boundary counts payload bytes before `\n` (delimiter excluded): **exact-N
   accept** (a `1_048_576`-payload-byte frame + `\n` dispatched), **N+1 reject** → discard +
   bounded-memory drain to next `\n`/EOF + resync; each read `min(CHUNK_SIZE, MAX_FRAME_BYTES -
   buffered + 1)` so at most one crossing byte is observed. Bounded MEMORY only (total drain
   time/bytes unbounded for a client that never sends `\n`). Revisit if a future tool accepts inline
   content or batch arrays. Reconciled: plan §H2 (Selected numeric limit + design cross-ref), `064-F`
   DoD H2, `064.006-T` (red exact-N/N+1 + over-read guard), `064.002-T` (green).

3. **Liveness red predecessor** — comment 3885888257 on `064.002-T`. The non-greedy-read +
   per-frame-flush liveness properties were only observable via the downstream `064.008-T`
   subprocess smoke (red merely because the entry point is absent), never observed red before
   `064.002-T` implemented them. `064.001-T` now carries an IN-PLACE instrumented `serve()`
   interactive-liveness assertion (injected non-greedy `read1` stdin + flush-recording stdout that
   withholds the second frame until the first response is flushed; timeout-bounded, deadlock fails
   deterministically; a greedy read cannot false-green) — RED here (serve() absent), green@`064.002-T`;
   scenario count stays 3. `064.008-T` remains the live subprocess/packaging smoke. Reconciled: plan
   serve() design + §H2 liveness note, `064-F` DoD, `064.001-T`, `064.002-T`, `064.008-T`.

4. **`064.024-T` scope = 3 functions** — comment 3885888272 on `064.024-T`. The count omitted the
   `crawl()` call-site changes: the request-scoped budget is local to `crawl()`, so threading it
   into the helpers necessarily edits `crawl()` + `_robots_allow` + `_discover_toc_links` (3
   functions). Call chain corrected: `_robots_allow` → DIRECT `fetch_page`; `_discover_toc_links` →
   `_fetch_with_retries` (already budget-aware from `064.017-T`, NOT a direct `fetch_page` call).
   `064.016-T`/`064.024-T` scenario (c)(iii) now requires SEPARATE robots AND TOC variants (not
   either/or). Still <5-function / ≤1-file. Reconciled: `064.024-T`, `064.016-T`, plan entry 10b.

5. **Two-shipment PR disclosure** — comment 3885888283 on `056-S` (see the amendment section above).

## Adversarial review outcome (multi-persona)

Approaches sound after one **P0 correction** folded in: the IPv4-mapped normalization MUST be guarded
for `IPv6Address` (unguarded `ip.ipv4_mapped or ip` crashes on IPv4). Refinements folded: honest
`MAX_FRAME_BYTES` rationale (operational limit, not protocol-derived; not justified via the
`MAX_RESPONSE_BYTES` cap — different resource dimensions); explicit exact-N/N+1 boundary with
delimiter-excluded payload counting; liveness fake pins `read1` + a synchronization/timeout contract
so a greedy read cannot false-green and a deadlock cannot hang the suite; accurate
`_discover_toc_links` → `_fetch_with_retries` chain and both-variant (c)(iii) coverage; bounded-MEMORY
(not total-drain) framing. TDD ordering preserved for all pairs (`065.001` → `065.002`; liveness red
`064.001` → green `064.002`; `064.006` red → `064.002` green). Shipment isolation upheld (one staging
PR may disclose two manifests; implementation stays separate).

## Files changed (Stage/backlog/docs artifacts only)

- `.backlogit/queue/064-F.md`, `064.001-T.md`, `064.002-T.md`, `064.006-T.md`, `064.008-T.md`,
  `064.016-T.md`, `064.024-T.md`, `065-F.md`, `065.001-T.md`, `065.002-T.md`
- `docs/plans/2026-08-27-mcp-stdio-server-plan.md`, `docs/plans/2026-08-28-sitemap-cgnat-ssrf-gap-plan.md`
- `docs/memory/2026-08-29/stage-pr166-cycle16-round2-memory.md` (this file)

**NOT touched (forbidden):** `.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`,
`.github/agents/_ship.agent.md`, `.gitignore`. Production/test source unchanged. Not pushed; no PR
actions; Ship not invoked; `055-S`/`056-S` remain queued/unclaimed.

## Next steps

- Operator/Ship: apply the recommended PR title/body amendment above so PR #166 discloses both
  shipments.
- Ship: claim `055-S` and `056-S` as separate shipment-scoped sessions/branches; do not co-implement.
