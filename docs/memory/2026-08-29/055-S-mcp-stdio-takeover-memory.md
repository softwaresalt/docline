---
type: session-memory
shipment: 055-S
feature: 064-F
branch: feat/055-s-mcp-stdio-server
date: 2026-08-29
---

# 055-S MCP stdio server — Ship takeover

## Recovery state
- Reversed the prior agent's premature `src/docline/app_models.py` edit manually (edit tool, no git reset). Worktree clean at origin/main 9de9f53.
- Preserve stash items 0A56B201, 87F2C06D, 0A56B202 for Stage.

## Authoritative constants (from plan §H2/§H7/§H8)
- `MAX_FRAME_BYTES = 1_048_576` (stdio.py); CHUNK_SIZE fixed-chunk reader.
- `MAX_PAGES_LIMIT = 1000` → FetchRequest.max_pages `Field(ge=1, le=1000)`.
- `MAX_DEPTH_LIMIT = 64` → FetchRequest.depth `Field(default=0, ge=0, le=64)`.
- `MAX_RESPONSE_BYTES = 10_485_760` (fetch/http.py) per-response streamed cap.
- `MAX_TOTAL_FETCH_BYTES = 536_870_912` aggregate request budget.
- `MAX_FETCH_ATTEMPTS = 4000` request-scoped attempt budget (fetch_page boundary + redirect_request per hop).
- Engines allow-list `_MCP_LOCAL_PDF_ENGINES = frozenset({"auto","docling","heuristic"})` (server.py).
- H8 opt-in: env `DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES` exact "1" OR `--allow-external-pdf-engine`.

## New symbols
- fetch/http.py: `RemainingByteBudget`, `FetchResponse.body_byte_count:int` (append AFTER redirect_count), `AggregateBudgetExceededError`, `FetchAttemptBudgetExceededError(AggregateBudgetExceededError)`.
- mcp/exceptions.py: `UnknownToolError`, `ExternalEngineNotAllowedError` (DoclineError subclasses).
- mcp/server.py: `list_callable_tools()`, `call_tool(name,args)`, `describe_server()`, `_MCP_LOCAL_PDF_ENGINES`, `DoclineMcpServer(external_pdf_engines_enabled=False)`.
- mcp/stdio.py: `dispatch(message, server)`, `serve(stdin, stdout, server=SERVER)`, bounded-read helper, MAX_FRAME_BYTES/CHUNK_SIZE.
- mcp/__main__.py: `main()`. pyproject `[project.scripts]` `docline-mcp = "docline.mcp.__main__:main"`.

## Execution order (= manifest). red=harness, green=impl.
064.001(r) 005(r) 006(r) 007(r) | 010(r ssrf) 011(g) 012(r cap) 013(g) 016(r agg) 017(g) 024(g aux)
025(r amp) 026(g) 027(r redir) 028(g) 029(r redir-attr) 030(g) 014(r e2e) 015(g adapter)
018(r desc) 019(g) 002(g T2 transport) 009(g T2s guards) 020(r era) 021(r era) 022(g) 023(g)
031(r ext) 032(g) 033(r ext-map) 034(g) 008(r smoke) 003(g entry) 035(r cfg) 036(g) 004(docs)

## Env
- venv: `.\.venv\Scripts\python.exe`. Tests: pytest. Baseline parity/transport green (30).

## Gates per task: ruff check, ruff format --check, pyright src/ (use `--pythonpath .venv\Scripts\python.exe`), pytest (targeted then full at PR).

## PROGRESS (updated)
Done (committed, each red→green, all gates green):
- Recovery: reversed premature app_models edit; clean worktree.
- 064.001,005,006,007 (red MCP transport harnesses in tests/parity/test_mcp_stdio.py).
- 064.010(r)/011(g) SSRF-by-resolution: url_policy.resolve_and_validate+is_unsafe_resolved_address; http.py address-pinned connect (_PinnedHTTP(S)Connection/Handler), build_fetch_opener (empty ProxyHandler), redirect revalidation.
- 064.012(r)/013(g) per-dimension caps: MAX_PAGES_LIMIT le on max_pages; read_body_capped + MAX_RESPONSE_BYTES + CHUNK_SIZE=65536 + ResponseByteLimitError.
- 064.016(r)/017(g)/024(g) aggregate byte budget: RemainingByteBudget, AggregateBudgetExceededError, FetchAttemptBudgetExceededError, MAX_TOTAL_FETCH_BYTES, MAX_FETCH_ATTEMPTS, FetchResponse.body_byte_count; crawl seeds+threads budget (main+robots+TOC); re-raise at 4 sites. Updated fetch_page test doubles (**_kwargs).
- 064.025(r)/026(g) amp: fetch_page debits attempt pre-I/O; crawl seeds max_attempts; FetchRequest.depth le=MAX_DEPTH_LIMIT=64.

NEXT (manifest order): 064.027(r)/028(g) redirect-body drain+fp-closure (extend _ValidatingRedirectHandler http_error_302 + alias rebind); 029(r)/030(g) redirect-hop attempt debit in redirect_request; 014(r e2e); 015(g adapter list_callable_tools/call_tool/describe_server); 018(r)/019(g) fetch desc HTTP(S)-only; 002(g transport stdio.py) — greens 001/005/006/007/014; 009(g guardrails H1/H3/H4/H5); 020/021(r era)/022/023(g); 031-036 H8; 008(r smoke)/003(g entry); 035(r)/036(g cfg); 004 docs.

## Key wire contracts already fixed by committed harnesses
- serve(stdin,stdout,server=SERVER): non-greedy read1, per-frame flush, newline-delimited JSON frames.
- dispatch(message,server)->dict|None (None only for valid no-id notification).
- CallToolResult: result.content=[{type:text,text}], structuredContent mirrors model_dump for fetch/process, isError on success=False; export_schema text=schema, -32602 on nonempty args.
- tools/list == SERVER.list_callable_tools() (3 tools, process omits workspace_root); initialize protocolVersion 2025-11-25.
- Error codes: -32700 (incl NaN/Inf tokens), -32600 (shape/id rules, id echo vs null), -32601, -32602 (unknown tool/invalid params/workspace_root/ext-engine), -32603.

## SESSION-END STATUS (2026-08-29) — 23/36 tasks complete, branch fully GREEN + PUSHED
Branch feat/055-s-mcp-stdio-server pushed to origin. Full suite: 1753 passed, 17 skipped, 0 failed.
Completed & committed (red→green, per-task): 064.001,005,006,007 (transport harnesses) + entire
shared-fetch hardening 010/011,012/013,016/017,024,025/026,027/028,029/030 (SSRF-by-resolution +
address-pinned connect + proxy disable + per-response/aggregate byte caps + attempt budget +
redirect-body drain/fp-closure + depth bound) + 014 e2e + 015 adapter + 018/019 fetch-desc +
002 legacy transport + 009 guardrails H1/H3/H4/H5. Legacy MCP stdio server is COMPLETE and green.

## REMAINING WORK (13 tasks, manifest order) — HANDOFF
- 064.020(r)/021(r)/022(g)/023(g): MODERN dual-era protocol (server/discover, per-request _meta
  negotiation keyed on io.modelcontextprotocol/protocolVersion|clientCapabilities by KEY MEMBERSHIP,
  -32022 UnsupportedProtocolVersion with data.supported+data.requested, resultType:"complete"
  wrapper + serverInfo _meta + ttlMs/cacheScope; per-process legacy latch via initialize).
  **IMPORTANT**: era routing rejects a metadata-free op before any initialize/modern-_meta. The
  committed 001/005 harness tests send BARE tools/list / tools/call WITHOUT negotiating era; when
  023's pre-init reject lands, those tests MUST be updated to negotiate first (send initialize, or
  thread a shared session-state latch through dispatch). dispatch() will need a per-connection
  session-state param (currently pure/stateless) OR the latch stored on the server instance; serve()
  owns one state per connection. Modern branch MUST funnel through the SAME hardened dispatch so
  H1/H3/H4/H5 apply (022 builds modern branch guarded-by-construction; 023 verifies parity).
  describe_server() already exposes supportedVersions [2026-07-28, 2025-11-25] + capabilities +
  serverInfo — consume it for both initialize and server/discover.
- 064.031(r)/032(g)/033(r)/034(g): §H8 external-PDF-engine opt-in gate. server.py:
  _MCP_LOCAL_PDF_ENGINES={auto,docling,heuristic}; ExternalEngineNotAllowedError(DoclineError);
  DoclineMcpServer(external_pdf_engines_enabled=False); list_callable_tools() filters process
  pdf_engine enum when not opted in (same site as workspace_root omission); guard in BOTH call_tool
  process adapter AND public process() chokepoint. stdio.py: map ExternalEngineNotAllowedError->-32602
  before generic -32603 (both eras). Extend 001 semantic-parity normalization for the engine delta (031).
- 064.008(r)/003(g): subprocess smoke (Popen interactive send→flush→require-response→send-next,
  stdin open, timeout-bounded) + entry point src/docline/mcp/__main__.py main() + pyproject
  [project.scripts] docline-mcp = "docline.mcp.__main__:main".
- 064.035(r)/036(g): §H8 startup opt-in in __main__ main(): env DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES
  exact "1" OR --allow-external-pdf-engine flag, resolved once, fresh DoclineMcpServer(...) to
  serve(server=...), never mutate module SERVER, never from request data, no-secret logging.
- 064.004: docs — README "Running the local stdio MCP server" + .vscode/mcp.json example + §H8 posture;
  docs/ARCHITECTURE.md top-level domain/dependency map (mcp/stdio transport, __main__ bootstrap,
  DoclineMcpServer adapter, shared docline.app façade, core never imports mcp/cli, §H8 MCP-only).

## Then: PR lifecycle (Copilot review + GraphQL resolve + CI + merge-commit), runtime verification,
## operational-closure, backlog archival (shipment-reconcile pre/post + backlogit_ship_shipment),
## post-merge closure PR (P-014), compound-refresh, compact-context. Preserve stash 0A56B201,
## 87F2C06D, 0A56B202 for Stage.

## Gate note: pyright MUST run as `pyright --pythonpath .venv\Scripts\python.exe src/` (venv has pydantic).
## Test hygiene: fetch e2e tests that invoke execute_fetch MUST monkeypatch.chdir(tmp_path) to avoid
## polluting the worktree with .cache/staging (breaks test_mcp_server_process_missing_staging_dir_fails).

