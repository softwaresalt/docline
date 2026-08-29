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

## Gates per task: ruff check, ruff format --check, pyright src/, pytest (targeted then full at PR).
