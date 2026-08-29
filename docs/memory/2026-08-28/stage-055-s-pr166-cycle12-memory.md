---
type: session-memory
agent: stage
date: 2026-08-28
branch: chore/stage-055-s
pr: 166
cycle: 12
head_before: 13b14b7
---

# Stage — PR #166 cycle-12 redirect decomposition (Copilot round 3)

Operator-directed **full Stage pass with further decomposition and multi-persona
adversarial review** — explicitly NOT another ordinary fix cycle. Two unresolved Copilot
round-3 findings on HEAD `13b14b7` were routed through triage → decomposition → review →
reconciliation across the backlog, the authoritative plan, the shipment, and memory.
Scope: planning / backlog / plan / memory artifacts only. No source / test / workflow /
harness / agent / `.gitignore` / `.autoharness/config.yaml` edits. Operator's uncommitted
edits in `.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`,
`.github/agents/_ship.agent.md`, and `.gitignore` were left untouched and NOT staged.

## Decomposition decision

The redirect hardening previously entangled TWO responsibilities in the
`064.027-T`/`064.028-T` pair: (1) intermediate-body byte drain, and (2) redirect-hop
fetch-attempt accounting. Per the operator directive to DECOMPOSE rather than edit
064.027/028 in place, the redirect work is now **two width-isolated test-first pairs**:

- **body-drain + closure** — `064.027-T` (harness) / `064.028-T` (impl)
- **hop-attempt placement** — `064.029-T` (harness) / `064.030-T` (impl) — NEW

Manifest grows **28 → 30 tasks**; chain
`064.026 → 064.027 → 064.028 → 064.029 → 064.030 → 064.014` (`064.014-T` re-pointed
`064.028-T` → `064.030-T`); shipment `055-S` = `064-F` + 30 tasks (31 members), with
`064.029`/`064.030` inserted between `064.028` and `064.014`.

## Finding A — intermediate-response `fp` leak on cap-breach (064.027-T / 064.028-T, re-scoped in place)

The cycle-10 bounded redirect-body proxy wraps the intermediate `fp` and delegates to
`super().http_error_302(...)`. CPython's `HTTPRedirectHandler.http_error_302` reads the
`fp` and only calls `fp.close()` AFTER a completed `fp.read()`. When the proxy raises a
per-response OR aggregate cap error MID-READ, that `fp.close()` is never reached — the
underlying intermediate 3xx response `fp` (a live socket/connection) LEAKS. Under a
hostile redirect chain that repeatedly trips the cap this is a slow-drip
resource-exhaustion residual.

**Resolution:** the `http_error_302` override wraps the `super()` delegation in a closure
guard `except (per-response cap error, AggregateBudgetExceededError): fp.close(); raise`,
closing the REAL intermediate `fp` on BOTH breach paths before re-raising. Because
`FetchAttemptBudgetExceededError` subclasses `AggregateBudgetExceededError`, the SAME
guard also releases `fp` when the Finding-B attempt debit raises from `redirect_request`
— so closure holds across all typed budget/cap breaches without duplicate close logic
(`fp.close()` is idempotent). `064.027-T` adds fp-closure assertions on the per-response
AND aggregate breach scenarios via an instrumented `fp` recording `.close()` (scenario
budget stays 3); the redirect-hop attempt assertion is REMOVED from `064.027-T`.

## Finding B — redirect-hop attempt debit placed too early (064.029-T / 064.030-T, NEW pair)

The cycle-11 mechanism debited one `MAX_FETCH_ATTEMPTS` attempt INSIDE the
`http_error_302` override BEFORE delegating to `super()`. But `super()` performs Location
resolution, the scheme check, loop detection, and calls `redirect_request` (which also
runs the §H6 address-pinned revalidation) — ANY of which can REJECT the redirect before
`parent.open()` (the outbound I/O). Debiting before `super()` therefore charges an
attempt even for redirects that validation REJECTS (no outbound request occurs),
corrupting request-COUNT accounting and prematurely exhausting the budget on rejected
hops.

**Resolution:** the debit MOVES into `_ValidatingRedirectHandler.redirect_request`,
debited exactly once immediately BEFORE it returns a non-None `Request` — after the
stdlib `super().redirect_request` build AND the §H6 revalidation, before the hop's
outbound I/O. `redirect_request` returns a non-None `Request` iff the redirect will
actually be followed, so an attempt is charged only for a FOLLOWED hop; a redirect
rejected by stdlib (`None` return) or §H6 revalidation (raises) consumes NO attempt.
`FetchAttemptBudgetExceededError` is raised from inside `redirect_request` on breach
(pre-I/O) and propagated by the existing `crawl.py` re-raise clauses (no `crawl.py`
edit). `handler.redirect_count` stays observability-only. `064.029-T` (2 scenarios)
pins debit-on-follow placement + no-debit-on-reject and attempt-breach-before-I/O;
`064.030-T` (`fetch/http.py`, ≤1 file) moves the debit, reusing the `MAX_FETCH_ATTEMPTS`
allowance seeded by `064.026-T` and threaded into the handler by `064.028-T` — no new
constant, no new file. `064.029-T` depends on `064.028-T` (the handler already receives
the budget and the closure guard is in place).

## Supersedes cycle-11

The cycle-11 memory stated `064.028-T` gains a per-hop `MAX_FETCH_ATTEMPTS` debit in its
`http_error_302` override "before `super()` follows the next hop," and that the
redirect-hop debit is owned by `064.028-T`/`064.027-T`. **Superseded:** the debit is
removed from `http_error_302` and placed in `redirect_request` after validation; the
redirect-hop attempt debit is now owned by the NEW pair `064.030-T`/`064.029-T`.
`064.026-T` remains the owner of the direct-outbound-call boundary debit
(harness `064.025-T`).

## Adversarial review outcome

Multi-persona adversarial re-review (Python urllib lifecycle / resource ownership;
precise attempt accounting; testability; task sizing; dependency order; rollback; dual
CLI/MCP impact), run against the CPython `urllib.request` source:

- **urllib lifecycle / ownership (PASS):** `http_error_302` orders `redirect_request`
  (→ attempt debit) BEFORE `fp.read()`/`fp.close()` (→ body drain) BEFORE `parent.open()`
  (→ outbound I/O). So the Finding-B debit in `redirect_request` is correctly
  "after validation, before outbound I/O," and the Finding-A closure guard in
  `http_error_302` wraps the whole delegation and thus also covers the attempt-breach
  raise. `fp.close()` is idempotent on `http.client` responses → the guard cannot
  double-free.
- **precise attempt accounting (PASS, with a documented residual):** debit at the END of
  `redirect_request` before `return new_request` means a `None`/reject path and the
  pre-`redirect_request` scheme-check reject reach no debit → no-debit-on-reject holds for
  the common rejection cases; a followed hop debits exactly once, pre-I/O. **Residual
  surfaced by the source check:** the stdlib LOOP-detection check (`max_repeats`/
  `max_redirections`) fires in `http_error_302` AFTER `redirect_request` returns (hence
  after the debit) but before `parent.open()`, so a loop-terminated hop over-counts by
  exactly one attempt before the fetch ends via `HTTPError` — bounded (by `max_redirects`),
  harmless (fetch terminating), and unavoidable without reimplementing the stdlib method
  body (forbidden). Documented in `064.029-T`/`064.030-T`, plan §H7 item 4a, and Risks;
  the harness does NOT assert no-debit for the loop case.
- **testability (PASS):** both harnesses drive fake transports with instrumented
  `fp`/`RemainingByteBudget` recording `.close()` and debit ordering — hermetic, exact.
- **task sizing / width (PASS):** `064.029` is tests-only (2 scenarios), `064.030` is
  code-only (≤1 file, moves one debit + removes one) — both <2h, single-domain.
- **dependency order (PASS):** single linear acyclic test-first chain
  `… → 064.028 → 064.029 → 064.030 → 064.014 → …` (30 tasks); red-before-green
  (027→028, 029→030) preserved.
- **rollback (PASS):** per-task revertible on the shared `fetch/http.py` surface;
  cross-interface (CLI + MCP) blast radius unchanged; SA-1 record updated.
- **dual CLI/MCP impact (PASS):** the shared `_ValidatingRedirectHandler` is on the
  opener both interfaces use; the closure + placement changes apply to CLI `docline fetch`
  and the MCP `fetch` tool identically.

No P0/P1 residuals. No budget breached.

## Review findings reconciled (the adversarial pass did real work)

The structured multi-persona review returned an initial FAIL with concrete findings that were
ALL reconciled in this session before commit:

1. **Impossible "after loop validation" wording (blocking):** early drafts said the debit sits
   "after stdlib scheme/loop validation." Verified against the CPython source: loop detection
   runs AFTER `redirect_request` returns, so the debit cannot be "after loop validation." Fixed
   across `064.029-T`, `064.030-T`, `064-F`, plan §H7 item 4a, and Risks to read "after the scheme
   check and §H6 revalidation."
2. **Self-contradictory red baseline (blocking):** `064.029-T` said both "064.028 retains only body
   drain + closure" AND "the debit is currently in http_error_302 so rejected redirects still debit."
   Fixed: after `064.028-T` there is NO redirect-hop debit; the debit-on-follow + attempt-breach
   scenarios are the red-first ones, and the no-debit-on-reject rows are REGRESSION ANCHORS
   (green pre-impl, must stay green after `064.030-T`).
3. **Closure-scope over-claim (blocking):** the guard covers Finding A's two cap failures (+ the
   subclassed attempt breach); it does NOT claim to own fp on every exit. `064.028-T` now scopes this
   honestly — stdlib scheme/loop rejections raise `HTTPError` that CARRIES fp (documented residual);
   §H6-rejection is pre-existing. Impl MAY broaden cleanup but the harness stays at two cap-breach
   closure assertions.
4. **Over-count residual framing:** re-characterized the loop-detection AND body-drain-breach
   over-counts as CONSERVATIVE — the `redirect_request` placement never UNDER-counts a followed hop,
   so the DoS upper bound is preserved (trips earlier, never later); bounded, safe. Documented the
   deliberate choice of `redirect_request` over an exact body-proxy-`close()` placement to keep the
   attempt concern width-isolated from the body-drain proxy.
5. **Near-cap test setup (non-blocking):** `064.029-T` attempt-breach scenario now requires seeding the
   allowance to `MAX_FETCH_ATTEMPTS - 1` (urllib `max_redirects` default 5 can't reach 4000 naturally).
6. **Rollback is reverse-topological (non-blocking):** plan Rollback now states the redirect cluster
   reverts in reverse-dependency order / as an atomic unit.

Confirmed sound by the review: dependency chain acyclic (`026→027→028→029→030→014`); `029` needs `028`
for budget threading + closure; shipment `055-S` = 31 members; tests-only/code-only width holds; the
shared handler applies to both CLI and MCP. Final verdict after reconciliation: sound and internally
consistent.

## Validation

- `.backlogit/memories.json` valid JSON (4 keys).
- All edited/created task + feature + shipment frontmatter valid YAML; `backlogit sync`
  → indexed 397 artifacts, 0 parse failures.
- Markdown well-formed across plan + tasks + this memory.
- Dependency graph 064.*: acyclic, single linear chain; `064.014-T` deps → `064.030-T`;
  `064.029-T` deps → `064.028-T`; `064.030-T` deps → `064.029-T` (verified via
  `item_deps` query).
- Shipment `055-S`: `064-F` + 30 tasks (31 members), parent-first, deps-first order
  matches plan execution order; `064.029`/`064.030` between `064.028` and `064.014`.
- `backlogit doctor`: only pre-existing `archived_from_self_ref` warnings on unrelated
  archived items (031–040 series); zero issues touching 064 / cycles / shipment.

## Do NOT

- Do NOT re-entangle the redirect body-drain and the redirect-hop attempt accounting —
  they are now two width-isolated pairs.
- Do NOT debit the redirect-hop attempt in `http_error_302` before `super()` — it must be
  in `redirect_request` after validation, before outbound I/O.
- Do NOT skip closing the intermediate `fp` on a cap breach — the `http_error_302`
  closure guard must release it on both breach paths.
- Do NOT charge an attempt for a redirect rejected by the scheme check or §H6 revalidation (a
  loop-rejected hop still incurs the documented one-attempt CONSERVATIVE over-count — stdlib loop
  detection runs AFTER `redirect_request`, so the debit has already occurred).

## Next steps

- Ship (or next session): push the Stage commit, reply + resolve the two Copilot
  round-3 threads, re-review; if clean, merge and verify manifest on `origin/main`
  before Ship claims `055-S`.
- Stage did NOT push / reply / resolve / request-review / merge; Ship not invoked;
  `055-S` queued/unclaimed.
