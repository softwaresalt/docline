---
type: session-memory
shipment: 055-S
feature: 064-F
branch: feat/055-s-mcp-stdio-server
date: 2026-08-29
status: implementation-complete
---

# 055-S MCP stdio server — second slice (dual-era + H8 + packaging + docs)

Continues from `055-S-mcp-stdio-takeover-memory.md` (first slice: 23/36 tasks, HEAD 7e1a96b).
This slice completed the remaining 13 manifest tasks in exact order.

## Tasks completed (each red harness → green impl, per-task commits)

| Task | Commit | Summary |
|---|---|---|
| 064.020-T | b679d10 | RED dual-era discovery + modern _meta negotiation harness |
| 064.021-T | ab7ab2c | RED legacy-retention + era-routing harness (drivers auto-latch) |
| 064.022-T | 6d5b44a | modern server/discover + _meta validator + envelope wrapper |
| 064.023-T | 932585c | per-connection legacy latch + pre-init reject + parity |
| 064.031-T | 44f6df9 | RED H8 adapter-policy harness |
| 064.032-T | 3ed9cbe | H8 adapter gate: allow-list, ExternalEngineNotAllowedError, deny |
| 064.033-T | 11b215e | RED H8 transport-mapping dual-era -32602 harness |
| 064.034-T | 1db2cc1 | map ExternalEngineNotAllowedError → -32602 in stdio |
| 064.008-T | 6c607d7 | RED docline-mcp subprocess interactive smoke |
| 064.003-T | 5945148 | docline-mcp entry point + pyproject scripts |
| 064.035-T | c90a13e | RED H8 startup opt-in config harness |
| 064.036-T | 4ae3608 | resolve opt-in from env exact-token "1" / CLI flag |
| 064.004-T | 041d4f9 | README MCP section + docs/ARCHITECTURE.md |
| (gate) | 5d57132 | style: ruff format 055-S first-slice code files (app.py, url_policy.py) |

## Key design decisions

- **Modern envelope shape** (contract authored in tests): result carries
  `resultType:"complete"` + `_meta.{"io.modelcontextprotocol/serverInfo":{name,version}}`;
  list results + DiscoverResult additionally carry `ttlMs=60000` + `cacheScope="session"`.
- **-32022** for unsupported version with `data.supported`+`data.requested`; **-32602** for
  missing/malformed-type version member and missing/non-dict clientCapabilities (version-first).
- **Era classifier** keys on KEY MEMBERSHIP of the namespaced modern member (not truthiness);
  server/discover always modern. Per-connection `_SessionState` legacy latch set by initialize;
  `dispatch(session=None)` defaults legacy-latched for direct unit calls. serve() creates a fresh
  unlatched session per connection → pre-init reject (-32600) for legacy-candidate ops before latch.
- **Test drivers auto-latch**: `_drive_serve`/`_drive_bytes` prepend a legacy initialize frame
  (id "__latch__") and strip its response so existing bare-frame serve tests stay green; pre-init
  reject tests opt out with `latch=False`.
- **H8**: `_MCP_LOCAL_PDF_ENGINES={auto,docling,heuristic}`; instance flag
  `external_pdf_engines_enabled` (default False); guard on raw args in call_tool (before model
  validation, so spoofed extra fields cannot preempt) + on resolved engine in process(); enum
  filtered in list_callable_tools; transport maps the typed error → -32602 before generic -32603.
  Startup resolution: raw `os.environ.get(...) == "1"` OR `--allow-external-pdf-engine`, once, into
  a fresh server; module SERVER never mutated.

## Quality gates (all green)

- `ruff check .` → clean.
- `ruff format --check .` → clean under **CI's pinned ruff 0.15.15** (uv.lock). NOTE: local ruff
  0.16.4 additionally reformats ~11 pre-existing docs/*.md code fences (markdown formatting added
  post-0.15); those are pre-existing, unchanged from origin/main, and NOT flagged by CI — left
  untouched (out of scope). Only 055-S code files were formatted.
- `pyright src/` → 0 errors.
- `pytest` → 1833 passed, 17 skipped.
- MCP module (tests/parity/test_mcp_stdio.py) → 140 passed.

## Next steps

- Adversarial review (correctness/security/python) → fix valid findings.
- Push branch, open feature PR, Copilot review cycles, CI, merge (merge commit only).
- Runtime verification + post-merge closure (archival, closure PR, compound/compaction).
- Preserve stash 0A56B201, 87F2C06D, 0A56B202 for Stage.

## OUTCOME — MERGED + CLOSED (2026-08-29)

- Adversarial pre-PR review (correctness/security/python): no P0–P2; P3 hardening applied.
- **PR #169 MERGED** with merge commit **`29cf11715ed7b8d638aca6d739fb3a0177c7c20f`** (merge
  commit strategy, P-009). Copilot review converged over 5 cycles (9→3→2→1→0), all valid findings
  fixed + threads resolved; 1 pre-existing crawl-frontier item stashed (`173238FD`) for Stage.
- Runtime verified: `docline-mcp` answered modern `server/discover` (resultType:complete,
  supportedVersions both eras, cacheScope:private).
- Backlog archived: shipment 055-S `shipped`; feature 064-F + 36 tasks moved done and archived
  to `.backlogit/archive/` (P-007: 0 archive deletions). Commit `ae3f34e`.
- Operational closure: `docs/closure/2026-08-29-055-s-mcp-stdio-closure.md`.
- Compound learnings: CI-ruff-pin drift; stateful pre-init reject without breaking stateless tests.
- Post-merge closure branch: `post-merge/055-s-mcp-stdio` (closure PR to follow).
- Preserved stash `0A56B201`, `87F2C06D`, `0A56B202` untouched.
