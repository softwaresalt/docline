---
type: session-memory
agent: stage
date: 2026-08-27
branch: chore/stage-055-s
pr: 166
cycle: 10
head_before: 62df1b7
---

# Stage — PR #166 cycle-10 review remediation (round 3 of 3, final)

Final review-fix cycle of the second three-cycle allowance. Two unresolved
Copilot threads on HEAD `62df1b7` reconciled. Scope: planning / backlog / plan /
memory artifacts + backlogit relationship operations only. No source / test /
workflow / harness / agent / `.gitignore` edits. Operator edits in
`.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`,
`.github/agents/_ship.agent.md`, and `.gitignore` left untouched and NOT staged.
Uncommitted orchestration-continuity changes in `.backlogit/memories.json`,
`.backlogit/queue/055-S.md`, and the round-2 orchestrator memory were integrated
(not discarded).

## Pre-edit multi-persona adversarial review

Both findings confirmed against ACTUAL behavior (empirically verified, not
assumed):

- `urllib.request.HTTPRedirectHandler.http_error_302` (aliased 301/303/307/308)
  calls an unbounded `fp.read()` on each intermediate 3xx body BEFORE
  `opener.open()` returns (read from CPython source). The per-response cap
  (064.013) and aggregate budget (064.017/064.024) only replace the TERMINAL
  `response.read()`, so both are bypassable by a hostile redirect chain. The
  plan's "applies to every redirect hop" claim was aspirational — the mechanism
  could not see intermediate bodies. **CONFIRMED P1 (Finding A).**
- `json.loads("NaN"|"Infinity"|"-Infinity")` → non-finite `float`;
  `{"id":NaN}` parses id to `float('nan')` (passes string-or-number guard);
  `json.dumps(float('nan'))` → bare `NaN` (invalid JSON, breaks JSON-RPC
  framing). `parse_constant` rejects; `allow_nan=False` on dumps also rejects.
  **CONFIRMED P1 (Finding B).**

Persona lenses (Security, Correctness, Scope/Width, Cross-interface blast-radius,
Protocol-compliance) surfaced FOUR in-cycle corrections (all folded into the
committed artifacts before commit), each verified empirically against the CPython
`urllib` source and `json` probes:

1. A subclass overriding only `http_error_302` leaves aliases 301/303/307/308 on
   the BASE unbounded handler (`Sub.http_error_301 is base http_error_302` → True).
   The impl MUST rebind all five aliases; the harness parametrizes the cap
   scenario across all five codes.
2. Two redirect handlers cannot coexist — `OpenerDirector` runs only the first
   `http_error_NNN` handler that returns a response. The drain MUST be folded into
   the EXISTING single `_ValidatingRedirectHandler` (http.py:41), not a new
   handler.
3. `max_redirects` defaults to 5, so a single under-10-MiB chain cannot reach the
   512 MiB aggregate. The aggregate harness seeds the budget low / pre-consumes it
   to prove the decrement hermetically.
4. `parse_constant` does NOT catch overflow numeric literals: `json.loads("1e400")`
   → `float('inf')` WITHOUT invoking it. A `math.isfinite()` clause in the id
   guard (`-32600`, `id:null`) is required in addition to `parse_constant`
   (`-32700` for the tokens).

Residual (noted, not a task): stdlib redirect loop-detection/disallowed-scheme
raises `HTTPError` holding an unread `fp`, bounded by `max_redirects` (5) —
monitoring, not a vector. No P0 found; no additional P1 beyond the four folded-in
corrections.

## Finding A — intermediate-redirect-body drain (new width-isolated pair)

- NEW `064.027-T` (T-redir-h, tests/fetch, red, 3 scenarios: per-response
  intermediate-body cap, aggregate intermediate-body accounting,
  redirect-still-follows). Depends on `064.026-T`.
- NEW `064.028-T` (T-redir-i, `fetch/http.py`, ≤1 file, green): EXTEND the
  existing single `_ValidatingRedirectHandler` (http.py:41) — NOT a new handler —
  with an `http_error_302` override + rebind all aliases
  (`http_error_301 = http_error_303 = http_error_307 = http_error_308 =
  http_error_302`); wrap `fp` in a bounded proxy + delegate to
  `super().http_error_302` to keep H6 revalidation + `max_redirects` count +
  stdlib Location/loop/scheme; count against a fresh per-response
  `MAX_RESPONSE_BYTES` AND the shared request-scoped `RemainingByteBudget` (passed
  into `__init__` at http.py:119). Reuses existing caps — NO new constant. Depends
  on `064.027-T`.
- `064.014-T` re-pointed `064.026-T → 064.028-T`. Chain:
  `064.026 → 064.027 → 064.028 → 064.014`. Manifest 26 → 28.
- Scope-carve corrections: `064.013-T` (was falsely implying redirect coverage —
  now scoped to initial + terminal post-redirect response only), `064.012-T`.

## Finding B — strict non-finite JSON handling (in-place)

- `064.002-T` (impl): `parse_constant` kwarg on the `serve()`/frame `json.loads`
  rejects the `NaN`/`Infinity`/`-Infinity` TOKENS → `-32700`; AND a
  `math.isfinite()` clause in the `dispatch()` id guard rejects a non-finite
  numeric id from an OVERFLOW literal (`1e400` → `inf`, which `parse_constant`
  does not catch) → `-32600` (`id:null`). Both BEFORE era routing; both eras
  inherit. Defense-in-depth `allow_nan=False` serialization degrades a `ValueError`
  to `-32603` rather than crashing the loop. No new function (≤4-function budget).
- `064.005-T` (harness): `NaN`/`Infinity`/`-Infinity` rows on the existing
  `-32700` case AND `1e400`/`-1e400` rows on the existing `-32600` invalid-id
  case. No new scenario (budget stays 3).
- No new task.

## Reconciled surfaces

- Plan `docs/plans/2026-08-27-mcp-stdio-server-plan.md`: §H7 item 2 (redirect
  drain, composite handler + alias rebind), Selected-numeric-limits
  `MAX_RESPONSE_BYTES` note, Cap-tasks, decomposition 10e/10f, dependency edges,
  execution order, Verification (fetch + JSON-RPC + boundary), design
  request-shape/error-envelope paragraphs, Rollback, SA-1, Risks, intro cycle
  list, new `### Cycle-10 review remediation` subsection (incl. the 4-correction
  re-review note) + verdict.
- Feature `064-F` DoD: H7 redirect-drain (composite handler) clause + JSON-RPC
  `-32700` (tokens) / `-32600` (overflow) non-finite clauses.
- Shipment `055-S`: added `064.027-T`, `064.028-T` (29 members: `064-F` + 28
  tasks). Commit field left at operator's `62df1b7` (continuity); `updated_at`
  bumped.
- `.backlogit/memories.json`: cycle-10 note appended to
  `stage-2026-08-27-darkfactory-stash-sweep`; `orchestrator:...round2` extended
  with cycle-10 completion; round-2 key preserved.

## Verification

- Dependency graph 064.*: acyclic, single linear chain, 27 edges / 28 nodes;
  `064.027→064.026`, `064.028→064.027`, `064.014→064.028` present; no cycle.
- Shipment membership: `064-F` + all 28 `064.*` tasks; parent-first.
- Budgets: 064.027 = 3 scenarios; 064.028 = ≤1 file; 064.002 = ≤4 functions
  (kwarg only); 064.005 = 3 scenarios (rows only). All within heuristics.
- `memories.json` valid JSON (4 keys).
- Backlog index cache (`.backlogit/backlogit.db`) NOT synced this session
  (`backlogit.exe` permission-blocked in non-interactive mode); markdown is the
  source of truth. Ship syncs on claim (established prior-cycle pattern).

## Next steps

- Ship (or next session): `backlogit sync`, push, reply + resolve the two Copilot
  threads (`064.013-T:26` redirect, `064.002-T:25` JSON), re-review; if clean,
  merge and verify manifest on `origin/main` before Ship claims `055-S`.
- Stage did NOT push / reply / resolve / request-review / merge; Ship not invoked;
  `055-S` queued/unclaimed.
