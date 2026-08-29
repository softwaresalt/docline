# Stage checkpoint — PR #166 post-decomposition cycle 3 (§H8 external-engine opt-in gate)

- **Date:** 2026-08-28
- **Agent:** Stage
- **Shipment:** 055-S (queued, unclaimed)
- **Feature:** 064-F (Local stdio MCP server and docline-mcp executable)
- **Branch:** chore/stage-055-s
- **Base HEAD reviewed:** 872989e
- **Mode:** planning/backlog/plan/memory artifacts only — no production source, no push, no PR actions, Ship not invoked
- **ActionRisk:** moderate (planning-only; the underlying MCP contract change is high blast-radius but execution is owned by Ship). **ActionResult:** applied (Stage artifacts committed).

## Finding closed

Copilot HIGH-RISK thread `PRRT_kwDOSsAX4c6dWm-8` (comment 3885302527, `.backlogit/queue/064.015-T.md:26`):
the MCP-specific `process` schema inherited `pdf_engine="mistral_ocr"`, letting an untrusted local MCP
caller consume ambient `AZURE_AI_FOUNDRY_KEY`/`MISTRAL_API_KEY` credentials and base64-upload workspace
PDFs to an external **paid** Mistral OCR endpoint — ambient-credential consumption + external egress +
uncapped paid cost driven by a request field.

## Grounding (read-only)

`request.pdf_engine` is the **sole** client-controllable selector of the external reader:
`readers/pdf.py` `_resolve_layout_engine("auto")` never returns `mistral_ocr`; `docling` is a local
model; `pdf_mode=triage` ignores `layout_engine`; `MISTRAL_OCR_MODEL` only renames an already-selected
engine. Gating `pdf_engine` at the MCP boundary is therefore complete. `ingest_local_dir` (the second
`pdf_engine`-bearing tool) is already excluded from the MCP advertise set + `call_tool` allow-list
(§H1 Design + §H4).

## Solution — plan Hardening §H8 (mirrors §H1 omit-and-reject)

- Local-engine **allow-list** `{auto, docling, heuristic}` (fail-closed for future external engines).
- Build-time **advertise omission** in `list_callable_tools()` (third sanctioned MCP-only parity divergence).
- Runtime **-32602 reject** at a single adapter `process()` chokepoint (covers `call_tool`; shared
  `ProcessRequest` stays permissive so the CLI is unchanged), dual-era via the one hardened dispatch.
- Fail-closed, instance-local **server-side startup opt-in** (`DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES=1`
  or `--allow-external-pdf-engine`), resolved once at startup, never from request data.

## Decomposition (six new width-isolated red/green tasks)

| Task | Domain | Owns |
|---|---|---|
| 064.031-T | tests | adapter-policy harness (advertise omit + dispatch deny/accept + negatives) |
| 064.032-T | code (server.py + exceptions.py) | allow-list + flag + advertise filter + chokepoint guard |
| 064.033-T | tests | transport-mapping harness (dual-era -32602) |
| 064.034-T | code (stdio.py) | typed error → -32602 mapping |
| 064.035-T | tests | startup opt-in config harness (real main() wiring) |
| 064.036-T | code (__main__.py) | fail-closed env/flag resolution → fresh opt-in server |

Execution order: `… 064.023 → 064.031 → 064.032 → 064.033 → 064.034 → 064.008 → 064.003 → 064.035 →
064.036 → 064.004`. Re-threaded edges: `064.008` dep `064.023 → 064.034`; `064.004` dep
`064.003 → 064.036`. The runnable executable (`064.003`) lands after the omit+reject gate is green.

## Adversarial review outcome

- **Security Lens Reviewer:** verdict — gate closes the `process` vector and ordering is sound; folded
  in P1 `ingest_local_dir` explicit negative assertion, P2 belt-and-suspenders adapter chokepoint,
  P2 accepted residual paid-egress-once-enabled (documented in Risks + SA-2), P3 spoofed-opt-in-field
  negative + no-secret reject/startup logging.
- **rubber-duck (design):** confirmed acyclic ordering + red-before-green; adopted the adapter-policy
  vs transport-mapping re-partition (width), allow-list over deny-list, fail-closed exact-`"1"` env,
  instance-local fresh server to `serve(server=...)` with no `SERVER` mutation, and `main()`-level tests.

## Files modified (Stage artifacts only)

- `docs/plans/2026-08-27-mcp-stdio-server-plan.md` — §H8, tasks 21–29 (renumbered), dependency edges,
  execution order, Verification, Rollback, SA-2, Risks, Cycle-14 subsection.
- `.backlogit/queue/064-F.md` — DoD H1–H7 → H1–H8 + CLI-parity qualifier.
- `.backlogit/queue/055-S.md` — shipment 37 members (added 064.031–064.036).
- `.backlogit/queue/064.031-T.md` … `064.036-T.md` — six new tasks (created).
- `.backlogit/queue/064.001-T.md`, `064.003-T.md`, `064.008-T.md`, `064.009-T.md`, `064.004-T.md`,
  `064.015-T.md`, `064.021-T.md`, `064.023-T.md` — §H8 cross-references / re-threaded deps / docs scope.
- `.backlogit/memories.json` — cycle-14 entry.

## Validation

YAML/JSON/Markdown parse OK; backlog index synced (403 artifacts); dependency graph acyclic
(132 nodes / 109 edges); §H8 execution-order chain intact; shipment parent-first order preserved
(37 members); red-before-green ordering held; task size within the 2-hour / <3-file / <5-function /
<4-scenario heuristic; `backlogit doctor` shows no new issues (168 pre-existing archived-record
warnings only).

## Next steps

- Ship claims shipment 055-S and builds the linear chain in execution order (harness-first per task).
- Do not enable the external engine by default at any build step; verify the §H8 tasks land before
  the `docline-mcp` entry point (064.003) so no runnable artifact ships the vulnerable default.
