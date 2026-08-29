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

