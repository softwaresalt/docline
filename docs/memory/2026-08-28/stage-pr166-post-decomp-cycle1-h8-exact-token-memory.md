# Stage checkpoint — PR #166 post-decomposition cycle 1 (§H8 exact-token opt-in hardening)

- **Date:** 2026-08-28
- **Agent:** Stage
- **Shipment:** 055-S (queued, unclaimed)
- **Feature:** 064-F (Local stdio MCP server and docline-mcp executable)
- **Branch:** chore/stage-055-s
- **Base HEAD reviewed:** 36c4b1543c5b46f0c97d5c02688bcbc55104f981
- **Mode:** planning/backlog/plan/memory artifacts only — no production source, no push, no PR actions, Ship not invoked
- **ActionRisk:** moderate (planning-only; underlying MCP opt-in contract is high blast-radius but execution is owned by Ship). **ActionResult:** applied (Stage artifacts committed).

## Findings closed (2 unresolved Copilot threads)

1. **`064.036-T` — thread `PRRT_kwDOSsAX4c6dXIsf`, comment 3885516661** (`.backlogit/queue/064.036-T.md:25`).
   The impl acceptance criterion specified `os.environ.get("DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES", "").strip() == "1"`.
   `.strip()` enabled whitespace/newline-padded tokens (`" 1 "`, `"1\n"`), contradicting the §H8 exact-token
   fail-closed contract and opening ambient-credential **paid external egress** (Mistral OCR + workspace-PDF
   upload) on the untrusted MCP surface. **Fix:** raw exact-token equality
   `os.environ.get("DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES") == "1"` — no strip/trim, no case-fold, no
   truthy/int coercion; default arg dropped so unset → `None != "1"` → DISABLED.
2. **`064.035-T` — thread `PRRT_kwDOSsAX4c6dXIsc`, comment 3885516655** (`.backlogit/queue/064.035-T.md:25`).
   The RED harness scenario (a) DISABLED rows (`"0"/"false"/"true"/"yes"/""`/whitespace-only) did not
   *discriminate* raw equality from a `.strip()` impl — a strip impl passed GREEN, so the RED test failed to
   constrain the very defect it guards. **Fix:** added padded-`"1"` DISABLED discriminators (`" 1"`, `"1 "`,
   `" 1 "`, `"1\n"`) plus an explicit whitespace-only row; these green ONLY under raw `== "1"` and stay RED
   under any trim impl. The two edits land atomically (F6 coupling): strip fix without the guard leaves the
   contract untested; guard without the fix makes `064.036` self-contradictory.

## Adversarial review outcome (this cycle)

Focused adversarial review of the env-parsing contract (case/whitespace/empty/unset/non-string OS behavior,
schema/runtime parity, startup-only immutability):

- **Verdict A:** the corrected contract (raw `== "1"` + padded-`"1"` DISABLED rows) is **sufficient and
  fail-closed**. Raw `== "1"` is the tightest correct predicate; it breaks NO sanctioned opt-in path
  (`export …=1`, `.vscode/mcp.json` `"1"`, `-e VAR=1`) so zero false-negative cost.
- **Env edge cases:** DISABLED (correct) for `"0"`, `"false"`, `"true"/"True"/"TRUE"`, `"yes"`, `"on"`, `""`,
  whitespace-only, `" 1"`, `"1 "`, `" 1 "`, `"1\n"`/`"1\r\n"`, `"\t1"`, `"01"`, `"1.0"`, `"+1"`, full-width
  `"１"`. Unset → `None == "1"` → False → DISABLED (stable green anchor across raw/strip and RED→GREEN).
  Windows/POSIX `os.environ` values are always `str|None` — no non-string comparison path.
- **Parity / immutability:** CLI flag and env token remain independent OR enablers; module `SERVER` stays
  external-disabled (startup-only, instance-local, resolved EXACTLY ONCE, never re-read from request
  `arguments`/`_meta`); client-supplied `external_pdf_engines_enabled`/`allow_external` ignored+rejected
  (asserted by `064.031`/`064.033`, cross-referenced from `064.035`).
- **Verdict C — PRESERVE:** the six-task §H8 decomposition (`064.031/032` adapter policy, `064.033/034`
  transport `-32602`, `064.035/036` startup opt-in) and its strictly-linear acyclic dependency/shipment
  order are correct. The remediation is a text-level correction inside the existing RED/GREEN pair's
  existing files and existing scenario (a) — no new module, no new edge, no <4-scenario/<3-file budget
  breach. **No split justified.**

## Reconciliation scope (smallest complete)

- `.backlogit/queue/064.035-T.md` — scenario (a) padded-`"1"` DISABLED discriminators + raw-equality wording.
- `.backlogit/queue/064.036-T.md` — AC#1 `.strip()` → raw `== "1"` exact-token equality.
- `docs/plans/2026-08-27-mcp-stdio-server-plan.md` — new `### Cycle-15` changelog subsection (documented
  remediation + PRESERVE verdict). §H8 contract statements UNCHANGED (already exact-token-correct).
- Feature `064-F` DoD H8 — UNCHANGED ("fail-closed on any non-`"1"` value" already correct; not stale).
- Other H8 tasks `064.031`–`064.034` — UNCHANGED (none carried a strip/trim predicate; grep-confirmed).
- `docs/memory/2026-08-28/…` (this file) + `.backlogit/memories.json` — durable memory.

## Validation

YAML frontmatter parse OK (both tasks); plan Markdown parse OK; `memories.json` JSON parse OK; backlog
index synced; dependency graph acyclic and §H8 chain intact (`… → 064.023 → 064.031 → 064.032 → 064.033 →
064.034 → 064.008 → 064.003 → 064.035 → 064.036 → 064.004`); shipment `055-S` parent-first order preserved
(37 members, unchanged); red-before-green ordering held; scenario budget still 3 (<4 heuristic) — only
parametrized rows added.

## Constraints honored

- Did NOT stage/edit/revert/commit `.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`,
  `.github/agents/_ship.agent.md`, or `.gitignore` (these carried pre-existing unrelated working-tree
  changes and were left untouched / excluded from the commit).
- No production source edited. NOT pushed; no PR actions performed; Ship not invoked; `055-S` stays
  queued/unclaimed.

## Next steps

- Ship claims shipment `055-S` and builds the linear chain; `064.035-T` harness now discriminates the
  strip regression so `064.036-T` must implement raw `== "1"` to green scenario (a).
- On the PR, reply to both threads referencing the remediation commit and resolve them (Ship/PR lifecycle).
