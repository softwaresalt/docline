---
type: session-memory
agent: stage
date: 2026-08-28
branch: chore/stage-055-s
pr: 166
cycle: 13
head_before: 75dd336
---

# Stage — PR #166 cycle-13 redirect closure broadening + card-10g wording (Copilot post-decomposition round 1)

Operator-directed Stage remediation of **three** Copilot findings on HEAD `75dd336`, run as a full
pass with **multi-persona adversarial review first**, then the smallest complete backlog/plan/memory
changes. Scope: planning / backlog / plan / memory artifacts only. No source / test / workflow /
harness / agent / `.gitignore` / `.autoharness/config.yaml` edits. The operator's uncommitted edits in
`.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`, `.github/agents/_ship.agent.md`,
and `.gitignore` were left untouched and NOT staged.

## The three Copilot findings

1. **Finding A (thread PRRT_kwDOSsAX4c6dVwOO / comment 3884952241 on `064.028-T`):** the cycle-12
   intermediate-response closure guard is too narrow. `_ValidatingRedirectHandler.redirect_request`
   (src/docline/fetch/http.py:76-89) also raises the custom redirect-cap `FetchError` and the §H6
   `CrawlUrlRejectedError` — both BEFORE stdlib `http_error_302` reaches its own `fp.read()`/`fp.close()`,
   and, unlike stdlib `HTTPError`, neither carries the `fp` — so those exits leak the intermediate 3xx
   connection identically to the cap-breach paths.
2. **Finding 2 (thread PRRT_kwDOSsAX4c6dVwOa / comment 3884952256 on cycle-12 memory line 189):** remove
   the impossible absolute no-debit-on-loop requirement. Stdlib loop detection runs AFTER
   `redirect_request`, so a loop-terminating hop has already consumed the documented conservative debit.
3. **Finding 3 (thread PRRT_kwDOSsAX4c6dVwOg / comment 3884952265 on `memories.json`, two occurrences):**
   same durable-handoff correction — "rejected redirects consume no attempt" must be scoped to
   scheme/§H6 rejects; loop rejection is a one-attempt conservative over-count.

## Adversarial review (run first)

Multi-persona parallel review (`gemini-3.5-flash` / `gpt-5.4` / `claude-opus-4.8` + source ground-truth
passes) against the CPython `urllib.request` source and the exception hierarchy. Verdict: **ADVISORY →
PASS** after one fix. All five validation axes returned PASS:

- **urllib lifecycle / double-close (PASS):** closing the real `fp` in the `http_error_302` guard is
  correct on a `redirect_request` step-c raise (stdlib never reaches its step-f `fp.read()/close()`);
  multi-hop double-close is idempotent-safe (`http.client` `close()` no-ops when `self.fp is None`);
  "rejecting hop's fp closed once" is satisfiable (only outer already-closed fps re-close).
- **exact exception ownership / no swallowing (PASS):** within the `super().http_error_302` delegation
  the ONLY `FetchError` is the redirect cap and the ONLY `CrawlUrlRejectedError` is the redirect-target
  §H6 rejection (the generic fetch-failure `FetchError` and the initial-URL `validate_crawl_url` are in
  `fetch_page`, OUTSIDE the handler); the guard re-raises each (never swallows); the guard — which holds
  the REAL `fp` (`redirect_request` gets the proxy) — is the correct owner; stdlib `HTTPError` (carries
  `fp`) is deliberately not caught.
- **width/granularity (PASS):** `064.027-T` stays at 3 scenarios (folded into scenario c, no new
  scenario, no decomposition); `064.028-T` stays ≤1 file — within the <4-scenario / single-domain / 2h
  envelope.
- **red/green + chain/shipment (PASS):** the two closure-on-reject assertions are genuinely red pre-028
  and green post-028; chain and shipment unchanged.
- **F1 (MAJOR/HIGH, the only blocker):** plan decomposition card **10g** (`064.029-T`) still carried the
  stale "after stdlib scheme/loop validation" wording and a "loop-INVALID … debits NOTHING" target — the
  impossible no-debit-on-loop claim cycle-12 reconciled everywhere else but MISSED in card 10g. Fixing
  it converts ADVISORY → PASS. (F2/F3 advisory refinements incorporated.)

## Changes applied (smallest complete set)

**Finding A — closure guard BROADENED** (guard now `except (per-response cap error,
AggregateBudgetExceededError, FetchError, CrawlUrlRejectedError): fp.close(); raise`; stdlib scheme/loop
`HTTPError` which carries `fp` remains the sole documented residual):

- `064.028-T` — broadened the except tuple + rewrote the SCOPE paragraph (removed the "§H6 pre-existing /
  MAY broaden / harness stays at two assertions" hedge; added exact-exception-ownership note) + impl-notes
  item (3) + the harness-green criterion.
- `064.027-T` — folded two fp-closure-on-reject rows (redirect-cap `FetchError`, §H6
  `CrawlUrlRejectedError`) into scenario c (reframed "redirect-request delegation preserved + rejection
  resource-ownership"); scenario budget UNCHANGED at 3; updated the red baseline + impl-notes + budget note.
- Plan §H7 item 2 (guard tuple + "every leak-prone exit" + harness-pair note); cards 10e (scenario-c rows)
  and 10f (guard tuple + closure scope); Risks bullet; feature `064-F` DoD — all reconciled to the
  broadened scope.

**F1 — card 10g reconciled** (attempt-accounting "consistent everywhere"): "after the stdlib scheme
check AND §H6 revalidation"; no-debit scoped to scheme-check / `redirect_request` `None`-return / §H6
raises; loop = documented one-attempt conservative over-count. Also corrected 10g's stale red baseline
("debit currently in `http_error_302` before `super()`" → "after 064.028-T the override debits NOTHING
per hop; debit-on-follow + attempt-breach are red-first, no-debit-on-reject are regression anchors") to
match `064.029-T`.

**Findings 2 & 3 — memory/handoff:** cycle-12 memory line 189 re-scoped to "scheme check or §H6
revalidation" with the loop over-count noted (line 187-188 left as historical to avoid contradicting the
reconciled item-3 record — F2). `memories.json` two occurrences (`orchestrator:055-S:pr166-convergence-round2`
and `stage-2026-08-27-darkfactory-stash-sweep`) re-scoped; the line-5 "after stdlib scheme/loop
validation" phrase also corrected to "scheme check" (F3 audit confirmed exactly these two forward
claims; historical old-cycle-11-flaw descriptions left as history).

**Plan cycle-13 subsection** added (supersedes the cycle-12 "two cap failures" closure scoping; records
the F1 fix), matching the plan's cycle-by-cycle supersession convention.

## Files modified

- `.backlogit/queue/064.027-T.md`, `.backlogit/queue/064.028-T.md`, `.backlogit/queue/064-F.md`
- `.backlogit/memories.json`
- `docs/plans/2026-08-27-mcp-stdio-server-plan.md`
- `docs/memory/2026-08-28/stage-055-s-pr166-cycle12-memory.md`
- `docs/memory/2026-08-28/stage-055-s-pr166-cycle13-memory.md` (this file)

## Validation

- `.backlogit/memories.json` valid JSON (4 keys).
- All edited task + feature frontmatter valid YAML; acceptance-criteria / implementation-notes markers
  balanced; `backlogit sync` reindexed with 0 parse failures.
- Dependency chain UNCHANGED and acyclic: `064.026 → 064.027 → 064.028 → 064.029 → 064.030 → 064.014`
  (`064.014-T` deps → `064.030-T`).
- Shipment `055-S` UNCHANGED: queued, 31 members (`064-F` + 30 tasks), parent-first, redirect cluster
  `027/028/029/030` before `064.014`.
- Red-before-green pairs preserved (`027 → 028`, `029 → 030`).
- Markdown well-formed across plan + tasks + both memories.

## Semantics kept consistent everywhere (task invariant)

- **Closure scope:** guard closes `fp` on {per-response cap breach, aggregate breach, subclassed attempt
  breach, redirect-cap `FetchError`, §H6 `CrawlUrlRejectedError`}. Only residual: stdlib scheme/loop
  `HTTPError` (carries `fp`).
- **Conservative loop over-count:** no-debit only for scheme-check / `redirect_request` `None`-return /
  §H6 raises; a loop-terminated hop incurs exactly one conservative over-count debit (loop detection runs
  AFTER `redirect_request`); never UNDER-counts a followed hop → DoS upper bound holds. Identical in
  `064.029-T`, `064.030-T`, plan §H7 item 4a + card 10g + Risks, `064-F` DoD, `memories.json`, and the
  cycle-12 memory Do-NOT.

## Do NOT

- Do NOT narrow the closure guard back to only the two cap breaches — it must also close on the two
  `redirect_request`-raised custom exits (`FetchError` redirect cap, §H6 `CrawlUrlRejectedError`); stdlib
  scheme/loop `HTTPError` (carries `fp`) stays out of scope.
- Do NOT swallow: the guard re-raises every caught exit; do NOT catch bare `Exception` or stdlib
  `HTTPError`.
- Do NOT reintroduce a no-debit-on-loop claim anywhere — a loop-terminated hop incurs the conservative
  one-attempt over-count.

## Next steps

- Ship (or next session): push the Stage commit; reply + resolve the three Copilot threads
  (PRRT_kwDOSsAX4c6dVwOO / PRRT_kwDOSsAX4c6dVwOa / PRRT_kwDOSsAX4c6dVwOg); re-review; if clean, merge and
  verify the manifest before Ship claims `055-S`.
- Stage did NOT push / reply / resolve / request-review / merge; Ship not invoked; `055-S` queued/unclaimed.
