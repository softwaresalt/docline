---
type: session-memory
agent: stage
date: 2026-08-28
branch: chore/stage-055-s
pr: 166
cycle: 11
head_before: f172806
---

# Stage — PR #166 cycle-11 review remediation (third three-cycle allowance, round 2)

Recovered an interrupted Stage remediation after a devbox restart. Partial
uncommitted edits in `.backlogit/queue/064.025-T.md`, `.backlogit/queue/064.026-T.md`,
and `docs/plans/2026-08-27-mcp-stdio-server-plan.md` were **reviewed and completed**,
not discarded. Scope: planning / backlog / plan / memory artifacts only. No source /
test / workflow / harness / agent / `.gitignore` / `.autoharness/config.yaml` edits.
Operator's uncommitted edits in `.autoharness/config.yaml`,
`.github/agents/_orchestrator.agent.md`, `.github/agents/_ship.agent.md`, and
`.gitignore` were left untouched and NOT staged.

Two threads reconciled. Both are in-place strengthenings — **no new task**; the
manifest stays at 28 tasks (`064-F` + 28 in shipment `055-S` = 29 members). The
single linear acyclic test-first chain, every dependency edge, shipment membership,
and execution order are all unchanged.

## Thread A — request-amplification bound moved to the `fetch_page` boundary (064.025-T / 064.026-T)

The cycle-8 mechanism put a per-request `fetch_attempts` counter in `fetch/crawl.py`
incremented only on main-page frontier pops. That does NOT bound actual outbound
requests: robots.txt (`_robots_allow`), mdBook TOC discovery (`_discover_toc_links`),
per-pop retries (`_fetch_with_retries` issues a fresh `fetch_page` per attempt), and
redirect hops (`_ValidatingRedirectHandler`) are all real outbound requests a
main-page-pop counter never sees; the per-response/aggregate BYTE budgets bound
transfer VOLUME not request COUNT (tiny robots/TOC responses barely spend the byte
budget). REJECTED.

**Resolution (re-scope in place, granularity still compliant):** replace the
frontier-pop counter with a request-scoped fetch-attempt budget on the SAME
request-scoped budget object (`RemainingByteBudget`) already threaded through every
`fetch_page` call by `064.017-T`/`064.024-T`. Seed a per-request attempt allowance
`MAX_FETCH_ATTEMPTS = 4000` on it; debit ONE **before** each direct outbound request
at the COMMON `fetch_page` boundary (`fetch/http.py`; main pages, robots, TOC, retries
— each a distinct `fetch_page` call, pre-I/O) AND ONE per redirect hop **inside** the
shared `_ValidatingRedirectHandler` before the next hop is followed (pre-I/O), exactly
as the aggregate byte budget already decrements intermediate 3xx bodies in that same
handler. RAISE `FetchAttemptBudgetExceededError` (a `DoclineError` subclass of
`AggregateBudgetExceededError`, so the four existing `except AggregateBudgetExceededError:
raise` clauses in `crawl.py` propagate it out of `crawl()` — NO new `crawl.py` edit).
Because every direct outbound request funnels through `fetch_page` and every redirect
hop funnels through the shared handler, auxiliary/retry/redirect traffic cannot bypass
the count.

**Redirect-hop pre-I/O correction (adversarial-review BLOCKING finding, fixed in this
session):** the redirect-hop debit MUST be per-hop INSIDE the handler (before the next
hop is followed), NOT a post-`open()` `handler.redirect_count` tally — a post-hoc count
lets urllib follow up to `max_redirects` hops beyond the cap before raising, which
contradicts the pre-I/O exact boundary. `handler.redirect_count` is retained for
observability only. **Ownership split:** `064.026-T` owns the boundary debit for direct
outbound calls (harness `064.025-T`: robots/TOC/retry); the per-hop redirect-attempt
debit is owned by the redirect-drain impl `064.028-T` (harness `064.027-T`), co-located
with the intermediate-body byte decrement it already owns — the same handler already
receives the `RemainingByteBudget` in its `__init__`, so no new task and no new file.

- `064.026-T` impl file set moves `fetch/crawl.py` → `fetch/http.py`, still 2 files
  (`fetch/http.py` + `app_models.py`). `FetchRequest.depth Field(default=0, ge=0, le=64)`
  unchanged.
- `064.025-T` harness now proves the cap trips from robots/TOC/retry traffic ALONE
  while `page_count` stays low (was: drives the three non-counting crawl branches); the
  redirect-hop attempt coverage moved to `064.027-T` (folded into its aggregate scenario,
  budget stays 3). Still 2 scenarios; test-first red preserved (`064.025-T` red →
  `064.026-T` green; `064.027-T` red → `064.028-T` green).
- `064.028-T` (redirect-drain impl) gains a one-line per-hop `MAX_FETCH_ATTEMPTS` debit in
  its existing `http_error_302` override (before `super()` follows the next hop), reusing
  the `RemainingByteBudget` already threaded into the handler `__init__`. Still ≤1 file
  (`fetch/http.py`), no new constant, no new function.
- Dependency chain unchanged: `064.024 → 064.025 → 064.026 → 064.027 → 064.028 → 064.014`.
- No new dependency edge needed: the `RemainingByteBudget` threading and the crawl.py
  re-raise clauses come from `064.017-T`/`064.024-T`, both upstream in the chain.

## Thread B — server/discover requires both `_meta` members even pre-initialize (064.020-T / 064.022-T)

The Protocol Era Model, method map, and tasks required every modern `tools/*` request
to carry per-request `_meta` with BOTH `io.modelcontextprotocol/protocolVersion` AND
`io.modelcontextprotocol/clientCapabilities`, but the era-routing precedence carried a
separate `server/discover → discovery (pre-handshake)` branch and the method map/table
presented `server/discover` as "answerable before any request" — implying it was
exempt from `_meta` validation. MCP `2026-07-28` requires per-request `_meta` on every
modern request; `server/discover` is a modern-only method.

**Resolution (no new task):** `server/discover` is routed through the SAME per-request
`_meta` validator as every modern request — a valid discovery request MUST supply BOTH
`protocolVersion` AND `clientCapabilities` (unsupported version → `-32022`, then
missing/malformed `clientCapabilities` → `-32602`, version-first) — while still
requiring NO prior `initialize` (pre-handshake availability does NOT waive required
`_meta`). Reconciled across:

- Plan: Scope modern-era bullet, Design method map, Protocol Era Model table
  (Discovery row) + era-routing precedence.
- Feature `064-F` DoD dual-era clause.
- `064.020-T`: scenario (a) sends `server/discover` WITH valid `_meta`; scenario (c)
  adds `server/discover` rejection rows as an AXIS (member × modern method incl.
  server/discover). Scenario budget stays 3.
- `064.022-T`: `server/discover` dispatch (2) runs only AFTER the `_meta` dual-member
  validator (3) accepts both members — an ordering constraint, no new function,
  `<=2`-file/`<5`-function budget unaffected.
- The metadata-free `tools/*` pre-initialize reject (`064.021-T`/`064.023-T`) is
  UNCHANGED — server/discover is modern-only, so it does not interact with the legacy
  latch semantics.

## Adversarial review outcome

An independent adversarial consistency review (rubber-duck) ran against the full artifact
set. It surfaced ONE BLOCKING internal inconsistency, now FIXED:

- **BLOCKING (fixed):** redirect hops were debited post-`open()` via `handler.redirect_count`,
  which contradicts the pre-I/O exact-boundary claim (urllib already followed the hops by
  then, so the crawl could exceed 4000 by up to `max_redirects` before raising). FIX:
  redirect-hop debit moved per-hop INSIDE `_ValidatingRedirectHandler` before the next hop
  is followed (pre-I/O), owned by `064.028-T` (harness `064.027-T`) alongside the byte
  decrement; `handler.redirect_count` is now observability-only. Reconciled across plan §H7
  item 4a + coverage req + Selected-numeric-limits + Cap-tasks + decomposition 10c/10d/10e/10f
  + cycle-11 subsection, feature DoD H7, and `064.025/026/027/028-T`.
- **NON-BLOCKING (fixed):** off-by-one boundary wording ("reach"/"at the cap" vs
  "exactly 4000 allowed") standardized to "the first 4000 debits succeed; the debit that
  would cross the cap is refused before its outbound I/O".

Self-review across full plan, tasks, dependencies, shipment, feature, and active
memories for internal consistency:

- Item-4 (A) rework fully propagated: plan overview, §H7 item 4 (a) + coverage
  requirement, Selected-numeric-limits `MAX_FETCH_ATTEMPTS`, Cap-tasks paragraph,
  decomposition 10c/10d/10e/10f, Rollback bullet, feature DoD H7 clause,
  `064.025/026/027/028-T`.
  The §H7 item-4 PROBLEM statement (max_pages doesn't bound fetch work; three
  non-counting branches; unbounded depth) is retained as the attack description; only
  the SOLUTION mechanism changed. Cycle-8 subsection kept as a historical record with an
  added superseding pointer.
- Item (B) fully propagated to every named surface; 064.021-T/064.023-T deliberately
  untouched (pre-initialize reject is tools/* only).
- Dependency graph 064.*: acyclic, single linear chain, 29 nodes (`064-F` + 28 tasks);
  no edge changed.
- Shipment `055-S`: `064-F` + 28 tasks (29 members), parent-first, deps-first order
  matches plan execution order. No membership change (item 4 re-scope in place; item B
  no new task).
- Allowance-round narrative: f172806 = round 1 (unlabeled shipment-reorder/no-drift
  reconciliation commit); cycle-11 = round 2 of the third three-cycle allowance
  (consistent with the plan overview edit).
- Validation: memories.json valid JSON (4 keys); plan/feature/task frontmatter valid
  YAML; Markdown well-formed. Backlog index `.backlogit/backlogit.db` synced this session
  (`backlogit sync` → indexed 395 artifacts); markdown remains the source of truth.

## Do NOT

- Do NOT restore the `fetch/crawl.py` frontier-pop counter or claim it bounds outbound
  requests.
- Do NOT debit redirect hops post-`open()` via `handler.redirect_count` — debit per-hop
  inside `_ValidatingRedirectHandler` before the next hop (pre-I/O); redirect_count is
  observability-only.
- Do NOT treat `server/discover` as exempt from `_meta` validation.
- Do NOT add a new task for either thread (both are in-place).

## Next steps

- Ship (or next session): `backlogit sync`, push, reply + resolve the two Copilot
  threads, re-review; if clean, merge and verify manifest on `origin/main` before Ship
  claims `055-S`.
- Stage did NOT push / reply / resolve / request-review / merge; Ship not invoked;
  `055-S` queued/unclaimed.
