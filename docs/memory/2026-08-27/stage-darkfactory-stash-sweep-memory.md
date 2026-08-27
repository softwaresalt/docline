# Stage session memory — dark-factory stash sweep (2026-08-27)

- Agent: Stage (dark-factory / AFK autonomous mode)
- Scope: full Stage pipeline (Steps 0.0–6) over all 8 active backlogit stash entries.
- Starting state: no active/queued shipments; queue empty; 8 active stash entries.

## Triage outcome

| Stash | Kind | Priority | Disposition | Durable artifact |
|---|---|---|---|---|
| 14E46B47 | feature | medium | EXECUTABLE → full pipeline + shipment | 064-F (shipment 055-S) |
| B26003B0 | task | low | BLOCKED (Foundry creds + paid calls + forms corpus) | 060.001-T under 060-F |
| E32FAF6F | task | medium | BLOCKED (Foundry creds + paid calls + cosmos) | 060.002-T under 060-F |
| F4167E69 | spike | medium | BLOCKED (Foundry creds + paid calls) | 061.001-T under 061-F |
| 4CB606D5 | task | low | BLOCKED (missing corpora) | 062.001-T under 062-F |
| A3E6D72C | task | medium | BLOCKED (missing scanned/high-mpx corpus) | 062.002-T under 062-F |
| 3048007A | task | low | DEFERRED (no GPU host) | 063.001-T under 063-F |
| 935F2694 | task | low | DEFERRED (YAGNI, no measured I/O hot path) | 063.002-T under 063-F |

All 8 stash entries archived (reason: archived) after successful harvest to durable backlog.

## Executable work — MCP stdio server (064-F, shipment 055-S)

- Deliberation: `docs/decisions/2026-08-27-mcp-stdio-server-deliberation.md` (chose Option A —
  dependency-free stdio JSON-RPC loop wrapping the existing `DoclineMcpServer`; rejected the
  `mcp` SDK / FastAPI to avoid a runtime dependency).
- Plan: `docs/plans/2026-08-27-mcp-stdio-server-plan.md`.
- Key repo finding: the MCP *adapter* (`DoclineMcpServer.list_tools/fetch/process/export_schema`),
  shared manifest, transport guard, and parity tests already exist. The gap is the runnable
  JSON-RPC stdio loop + `docline-mcp` console entry point.
- Adversarial multi-persona plan review: Architecture ADVISORY, Scope ADVISORY,
  **Security FAIL → PASS after hardening**.
  - Security P0 (real): `ProcessRequest.workspace_root` is unvalidated; exposing `process`
    over untrusted stdio lets a client set `workspace_root:"/"` and escape workspace isolation
    (Principle III). Closed via plan §H1 (pin/strip workspace_root at the MCP boundary; blocking
    test). Re-review returned Security PASS.
  - Arch/Scope P1/P2: shared manifest advertises 4 tools (incl. `ingest_local_dir`) but adapter
    routes 3 → advertise-but-uncallable gap. Closed via manifest-driven `call_tool` allow-list;
    advertised set == callable set; parity test asserts every advertised tool is dispatchable.
  - Additional hardening H2–H6: stdin DoS bounds (+RecursionError), error-text non-disclosure
    (envelope + isError), closed allow-list fail-closed, stdout hygiene, fetch SSRF re-verify.
- Tasks (test-first, width-isolated, dependency chain T1→T2→T3→T4):
  064.001-T (test harness) → 064.002-T (dispatch loop + call_tool) → 064.003-T (docline-mcp
  entry point) → 064.004-T (README/.mcp.json docs).
- Shipment 055-S = 064-F + 4 tasks (queued, priority high). Handoff token to Ship.

## Blocked/deferred backlog (durable, NOT shipped)

Covering features 060-F, 061-F, 062-F, 063-F (status blocked). Each child task carries explicit
EVIDENCE / UNBLOCK requirements and `Do NOT fabricate` guardrails. Semantic links: 061.001-T
`informs` 060.001-T and 060.002-T (a Mistral v4 win could change forms + hybrid tasks).

## Commits / working-tree notes

- Committed ONLY backlog/planning artifacts: `.backlogit/queue/*`, `.backlogit/stash.jsonl`,
  `.backlogit/archive/stash.jsonl`, `docs/decisions/...`, `docs/plans/...`, `docs/memory/...`.
- PRESERVED and did NOT stage operator's pre-existing uncommitted changes:
  `.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`,
  `.github/agents/_ship.agent.md`, `.gitignore`.
- Role boundary honored: no push, no PR, no shipment claim, no build/test, no production code.

## Next steps

- Ship claims shipment 055-S → harness-architect (T1 red) → build-feature (T2 green) →
  T3 entry point → T4 docs → review/CI/PR → merge.
- Blocked features 060–063 remain blocked until their evidence requirements are met; re-triage
  when Foundry credentials, representative corpora, a GPU host, or production I/O profiling
  become available.
