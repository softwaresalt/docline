---
type: session-memory
agent: stage
date: 2026-08-28
branch: chore/stage-055-s
pr: 166
cycle: "cycle-2 (post-decomposition Copilot review)"
head_before: b5bd481
---

# Stage — PR #166 cycle-2 H6 SSRF rejected-address set reconciliation

Operator-directed Stage remediation of **four** linked Copilot security findings on HEAD
`b5bd481081f460555c52ab34572be9a4fd82e387`, run with **multi-persona adversarial review first**, then
the smallest complete plan / backlog / memory reconciliation. Scope: planning / backlog / docs
artifacts only — no source / test / workflow / harness / agent / `.gitignore` /
`.autoharness/config.yaml` edits. The operator's pre-existing uncommitted edits in
`.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`, `.github/agents/_ship.agent.md`,
and `.gitignore` were left untouched and NOT staged.

## The four Copilot findings (all one root issue)

- thread `PRRT_kwDOSsAX4c6dWRhQ` / comment 3885162128 → plan §H6 (`docs/plans/...`:532)
- thread `PRRT_kwDOSsAX4c6dWRhh` / comment 3885162148 → task `064.010-T` (harness AC)
- thread `PRRT_kwDOSsAX4c6dWRhn` / comment 3885162154 → task `064.011-T` (impl AC)
- thread `PRRT_kwDOSsAX4c6dWRht` / comment 3885162166 → feature `064-F` DoD

Root issue: the H6 DNS-SSRF contract enumerated its rejected set as
`loopback / private / link-local / metadata` and **omitted multicast, reserved, and unspecified**, so a
DNS answer such as `224.0.0.1` (multicast), `240.0.0.1` (reserved), or `0.0.0.0` / `::` (unspecified)
could satisfy every listed check and still be connected to. Reviewers pointed at the existing
shared-fetch classifier `_is_unsafe_address` (`src/docline/fetch/sitemap.py:173-189`) which already
rejects the full class set + fails closed.

## Decision: align to the complete non-public-unicast set (no decomposition)

Reconciled the H6 rejected-address contract to a fail-closed non-public-unicast set: reject if ANY
resolved A/AAAA address is loopback, private (RFC1918 / RFC4193 ULA `fc00::/7`), link-local, CGNAT
(`100.64.0.0/10`), multicast, reserved, unspecified (`0.0.0.0` / `::`), or a metadata address, with
IPv4-mapped IPv6 normalized to IPv4 **before** classification and any unclassifiable address treated as
unsafe. Address-pinned connect + empty `ProxyHandler({})` + per-redirect revalidation unchanged.

No decomposition: the added multicast/reserved/unspecified/CGNAT/mapped forms are additional
**parametrized address inputs** to the existing single initial-URL-resolution scenario in `064.010-T`
(scenario budget stays 3, <4), and extend the existing classifier condition in `064.011-T` with no new
function (stays ≤2 files / ≤4 functions). Test-first `064.010-T` (red) → `064.011-T` (green) dependency
preserved; shipment `055-S` parent-first order preserved (`064-F` idx 0, `064.010-T` idx 5,
`064.011-T` idx 6).

## Adversarial review outcome (multi-persona, 3 models)

Verdict: **PASS-WITH-NOTES**. Reviewers A (gemini-3.5-flash), B (claude-sonnet-4.6), C (gpt-5.6-sol).
Confirmed the multicast/reserved/unspecified additions close all four findings within budget and
without over-broadening. Two blocking wording corrections were applied:

- **M-1 (blocking, corrected):** dropped the "same as / must not be narrower than `_is_unsafe_address`"
  strict-equivalence premise. That 6-flag reject-list does **not** reject CGNAT `100.64.0.0/10`
  (`is_private` / `is_reserved` / `is_global` all `False` on every Python 3.12.x), so claiming parity
  would have logically permitted dropping the CGNAT rejection the tasks already require. Contract now
  reads: "mirrors the class predicates of `_is_unsafe_address` **and additionally rejects CGNAT via an
  explicit membership check**."
- **M-2 (minimal):** `ipaddress` special-purpose tables are Python-patch-dependent (CVE-2024-4032
  hardened `is_private` in 3.12.4). Added a harness requirement to **test-pin each security-critical
  class** rather than trust the installed flag table. Did NOT edit `pyproject.toml` (production manifest
  outside this reconciliation's scope) — the `>=3.12.4` floor is recorded as a follow-up.
- Precision notes folded in: normalize IPv4-mapped **before** class checks (rationale: mapped
  multicast/CGNAT/reserved evade IPv6-form predicates); enumerate ALL answers then pin to one validated
  member; TLS `server_hostname`/SNI = original hostname on the pinned connect.

## Tracked follow-ups (recorded in plan `## Risks`, not new backlog items to preserve scope)

1. `sitemap._is_unsafe_address` shares the CGNAT `100.64.0.0/10` gap — a separate **code** chore should
   add the same explicit membership check (production source out of scope here).
2. Evaluate raising `requires-python` to `>=3.12.4` (CVE-2024-4032) as a follow-up.

## Files modified (committed)

- `docs/plans/2026-08-27-mcp-stdio-server-plan.md` — §H6 item 1 rejected-set + item 3 TLS SNI;
  T-ssrf-i task-list entry; cycle-2 retrospective + Security-P3s lines; new `## Risks` follow-up bullet.
- `.backlogit/queue/064-F.md` — DoD H6 line; `updated_at` bump.
- `.backlogit/queue/064.010-T.md` — harness AC (parametrized forms + test-pin) + intro; `updated_at`.
- `.backlogit/queue/064.011-T.md` — impl AC + body; `updated_at`.
- `docs/memory/2026-08-28/stage-055-s-pr166-h6-ssrf-rejected-set-memory.md` — this checkpoint.

## Validation

- YAML frontmatter parses for all three backlog files; backlog index resynced clean (397 artifacts,
  `parse_failures=0`).
- Dependency edges intact: `064.007-T → 064.010-T (red) → 064.011-T (green) → 064.012-T`.
- Shipment `055-S` membership + parent-first order intact.
- `backlogit doctor` pre-existing 168 issues are workspace-wide and do NOT reference the edited items.
- Markdown blocks render (H6 numbered list + Risks bullets verified).

## Next steps

- Ship owns the PR: push, resolve the four Copilot threads referencing these commits, re-request
  Copilot review, and run the pre-merge readiness gate. Stage does not push or perform PR actions.
