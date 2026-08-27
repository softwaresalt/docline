# Implementation Plan: Local stdio MCP server and `docline-mcp` executable

- Date: 2026-08-27
- Source deliberation: `docs/decisions/2026-08-27-mcp-stdio-server-deliberation.md`
- Source stash: `14E46B47`
- Primary objective: Make docline usable over a local stdio MCP connection by adding a
  runnable JSON-RPC 2.0 stdio server that wraps the existing `DoclineMcpServer`, and ship a
  `docline-mcp` console executable entry point.
- Requires plan hardening: yes — a security P0 (untrusted `workspace_root` containment
  bypass) surfaced in plan review; hardened in this revision (see `## Plan Hardening`).
- Plan-review status: revised after an adversarial multi-persona review (Architecture,
  Security, Scope). See `## Plan Review Remediation`.
<!-- plan-review-attempt: 2 -->

## Scope

In scope:

1. A dependency-free stdio JSON-RPC 2.0 dispatch loop that speaks the minimum MCP method set
   (`initialize`, `notifications/initialized`, `tools/list`, `tools/call`, `ping`) and
   delegates to `DoclineMcpServer`.
2. A `docline-mcp` console-script entry point and `python -m docline.mcp` bootstrap.
3. Protocol + dual-interface parity tests (test-first).
4. Operator/agent documentation: README run section + `.mcp.json` example + design-doc note.

Out of scope (explicitly):

- Remote transports (HTTP/SSE/WebSocket) — only stdio is approved.
- New tool surfaces beyond the existing `fetch`, `process`, `export_schema`, and manifest
  discovery. No new business logic; this is a transport/packaging release unit.
- Any change to `execute_fetch` / `execute_process` behavior (parity must be preserved).
- Adopting the `mcp` SDK or FastAPI (see deliberation Option B rejection).

## Constitution Check

| Principle | Compliance |
|---|---|
| I. Safety-First Python | Type hints on all new public functions; typed errors via `McpTransportError` + JSON-RPC envelopes; no bare except. |
| II. Test-First Development | Protocol + parity tests authored and observed failing before the stdio loop is implemented. |
| III. Workspace Isolation | The stdio surface is untrusted. `execute_process` is NOT inherently contained: `ProcessRequest.workspace_root` is an unvalidated absolute path (no field_validator, unlike `staging_dir`/`output_dir`) and `safe_workspace_path` only contains the relative dirs *under* that root. The MCP boundary MUST pin the workspace root to a server-configured value and strip/reject any client-supplied `workspace_root` (see Plan Hardening §H1). With that gate, all `tools/call` FS operations resolve within the server workspace root. |
| IV. CLI Containment | Server only reads stdin / writes stdout; no out-of-cwd writes once `workspace_root` is pinned (§H1). |
| V. Observability | JSON-RPC error envelopes carry structured codes plus generic, non-reflective messages (no absolute paths, no tracebacks — §H3); full detail logs to stderr only. |
| VI. Single Responsibility | No new runtime dependency; stdlib `json`/`sys` only. |
| X. Context Efficiency | Reuses the shared manifest; no duplicated tool schema. |

No principle conflicts. The Principle III containment gate (§H1) is a blocking acceptance
criterion, not an advisory item.

## Design

- Tool identity lives in exactly ONE layer. Add a manifest-driven dispatch entry on the
  adapter — `DoclineMcpServer.call_tool(name: str, arguments: dict) -> object` — backed by an
  explicit static allow-list `{tool_name: bound_method}`. No `getattr(server, name)` (that
  would expose dunder/attribute dispatch injection). The transport module carries zero tool
  names; it is a pure JSON-RPC <-> adapter translator.
- Advertised set == callable set. The MCP `tools/list` is derived from the same allow-list
  `call_tool` dispatches, so nothing is advertised that cannot be invoked. The shared manifest
  advertises four tools (`fetch`, `process`, `export_schema`, `ingest_local_dir`); the callable
  MCP surface currently implements three. Reconcile before shipping by EITHER (a) adding an
  `ingest_local_dir` route to the adapter allow-list, OR (b) filtering `ingest_local_dir` out
  of the MCP `tools/list`. Whichever is chosen, a test MUST assert every advertised MCP tool is
  dispatchable (no advertise-but-uncallable gap).
- New module `src/docline/mcp/stdio.py`:
  - `serve(stdin, stdout, server: DoclineMcpServer | None = None) -> int` — read/dispatch/write
    loop; `server` defaults to the existing module singleton `SERVER` (single construction
    path); terminates cleanly on EOF. Reserves the real stdout exclusively for JSON-RPC frames.
  - `dispatch(message: dict, server: DoclineMcpServer) -> dict | None` — pure function mapping a
    single JSON-RPC request to a response dict (or `None` for any id-less notification —
    handled generically, no per-notification special case). Unit-testable without stdio.
  - Method map: `initialize` → capabilities + pinned `protocolVersion` + serverInfo;
    `tools/list` → filtered manifest (callable allow-list); `tools/call` → `server.call_tool`;
    `ping` → `{}` (optional utility, not required for discovery/use).
  - Input bounds (DoS): enforce a maximum inbound message byte size; oversized frames return an
    error envelope and the loop continues. The parse-error handler catches `ValueError` AND
    `RecursionError` (deeply nested JSON raises `RecursionError`, a `RuntimeError` subclass that
    `json.JSONDecodeError` handling would miss) so one hostile message degrades to an envelope
    rather than crashing the loop.
  - Error envelopes: `-32700` parse error, `-32601` method not found, `-32602` invalid params
    (wrap Pydantic `ValidationError`) and unknown/unroutable tool name (fail closed), `-32603`
    internal error. Messages MUST be generic and non-reflective: no absolute paths, no
    `PathContainmentError` text, no tracebacks in `message`/`data`; log full detail to stderr.
  - Tool-result mapping: `execute_fetch`/`execute_process` model failure as a *successful* call
    returning `success=False` + `error`. Map a validated-but-failed tool result to a JSON-RPC
    *result* whose MCP content carries the error text with `isError=true`; reserve `-326xx`
    envelopes for framing/validation/internal faults only.
  - stdout hygiene: redirect process-level `sys.stdout` (to stderr or a buffer) for the duration
    of each `tools/call` so third-party library writes (docling/crawler/httpx) cannot corrupt or
    smuggle JSON-RPC frames. The private protocol stdout handle is used only for framing.
- New module `src/docline/mcp/__main__.py`:
  - `main() -> int` → constructs/reuses `DoclineMcpServer()` (stdio guard) and calls `serve(...)`.
  - Enables both `python -m docline.mcp` and the console script.
- `pyproject.toml` `[project.scripts]`: add `docline-mcp = "docline.mcp.__main__:main"`.
  On Windows install this materializes `docline-mcp.exe`.

## Plan Hardening

Security/reliability guardrails promoted to blocking design constraints after plan review.

- **H1 — Workspace-root containment (P0, blocking).** At the MCP boundary, `tools/call`
  `process` MUST NOT honor a client-supplied `workspace_root`. Pin the root to the
  server-configured workspace (process cwd) and strip/ignore the field, OR validate it resolves
  within an allow-listed base. Blocking test: a `process` call with `workspace_root:"/"` and a
  Windows drive-letter form (`C:\\`) is rejected and writes nothing outside the workspace.
- **H2 — Untrusted-input bounds.** Max message size enforced; `RecursionError`/`ValueError`
  both degrade to an error envelope; loop survives hostile input. Tests: oversized line, deeply
  nested array.
- **H3 — Error-text non-disclosure.** No absolute paths / tracebacks in envelopes OR in
  `isError` tool-result content (the `success=False` mapping surfaces `ProcessResult.error` /
  `FetchResult.error`, which may embed absolute resolved paths via `PathContainmentError`).
  Sanitize/genericize both surfaces. Test: a containment/validation failure — as an envelope
  AND as an `isError` result — contains no absolute-path substring.
- **H4 — Closed tool allow-list.** Static `{name: method}` map; unknown names (incl.
  `ingest_local_dir` if unrouted, and dunders) fail closed with `-32602`, never `AttributeError`.
- **H5 — stdout reserved for frames.** Child-library stdout redirected during tool execution;
  test asserts stdout carries only well-formed JSON-RPC frames across a fetch/process call.
- **H6 — fetch SSRF re-verification.** Re-confirm the crawler's SSRF guard is active on the new
  untrusted path. Negative test drives rejection **through the `tools/call` fetch boundary**
  (stdin JSON → dispatch → `server.fetch` → `execute_fetch`), not the crawler in isolation:
  `http://127.0.0.1` and `http://169.254.169.254` are rejected end-to-end.

## Tasks (decomposition)

Ordered, dependency-aware, one skill domain each (width isolation), each ≤ ~2h.

1. T1 — Protocol + parity + security test harness (tests domain). Author failing tests in
   `tests/parity/test_mcp_stdio.py`: `initialize` handshake shape; `tools/list` == callable
   allow-list with semantic (name + normalized-schema) parity vs `get_manifest().tools`
   (acknowledging the `parameters`↔`inputSchema` alias divergence — not byte-for-byte); every
   advertised MCP tool is dispatchable; `tools/call` fetch + process parity vs
   `execute_fetch`/`execute_process`; `success=False` maps to an `isError` result; error
   envelopes (`-32601`, `-32602`, `-32700`, `-32603`); id-less notification is silent; plus the
   hardening gates H1–H6 (workspace_root escape rejected; oversized + deeply nested input;
   no absolute paths in error text; unknown/unrouted tool fails closed; stdout carries only
   frames; SSRF loopback/metadata rejected). Verify red.
2. T2 — stdio dispatch loop + adapter `call_tool` allow-list (code domain). Implement
   `DoclineMcpServer.call_tool` (static allow-list) and `docline/mcp/stdio.py`
   (`dispatch` + `serve`) to make T1 pass, including all H1–H6 guardrails. Depends on T1.
3. T3 — `docline-mcp` entry point + module bootstrap (packaging/code domain; dual-domain
   acknowledged — bootstrap module + `[project.scripts]` edit + an automated subprocess smoke
   test, inseparable for delivering the runnable binary). Add `docline/mcp/__main__.py`,
   the `[project.scripts]` entry, and an automated subprocess test (matching the existing
   `test_python_m_docline_cli_runs_main` pattern) that pipes `initialize`+`tools/list` then EOF
   and asserts clean exit + manifest tool names. Depends on T2.
4. T4 — Documentation (docs domain). README "Running the local stdio MCP server" section and a
   `.mcp.json` client example for `docline-mcp`. Do NOT add a separate design-doc transport
   note — the deliberation already documents the transport surface (avoid duplication).
   Depends on T3.

Dependency edges: T2→T1, T3→T2, T4→T3.

## Verification

- `pytest tests/parity` green (new stdio suite incl. H1–H6 gates + existing adapter/transport
  suites unchanged).
- `ruff check .`, `ruff format --check .`, `pyright src/` clean.
- Automated subprocess smoke (in T3) replaces manual verification: `docline-mcp` handling an
  `initialize`+`tools/list`+EOF, tool names matching `docline --manifest`.

## Plan Review Remediation

Adversarial multi-persona review (2026-08-27) verdicts: Architecture ADVISORY, Scope ADVISORY,
Security FAIL (one P0). Disposition:

- Security P0 — untrusted `workspace_root` containment bypass → **§H1 blocking gate**; Constitution
  Check Principle III corrected.
- Arch P1 / Scope P2 / Security P2 — manifest advertises 4 tools, only 3 callable →
  advertised-set == callable-set via `call_tool` allow-list; parity test asserts every advertised
  tool is dispatchable.
- Arch P1 — triple-layer tool-name coupling → manifest-driven `call_tool`; transport carries no
  tool names (also closes the `getattr` dispatch-injection risk).
- Arch P1 / Security P3 — stdout ownership → **§H5** child-stdout redirect + hostile-stdout test.
- Arch P2 — `success=False` vs MCP `isError` → explicit result mapping + tests.
- Arch P2 / Security P4 — parity over-specified & error-text disclosure → semantic parity
  (not byte-for-byte); **§H3** generic non-reflective error messages.
- Security P2 — stdin DoS / RecursionError → **§H2** size bound + `RecursionError` handling.
- Security P2 — open dispatch → **§H4** closed allow-list, fail-closed unknown names.
- Security P3 — fetch SSRF on untrusted surface → **§H6** SSRF re-verification negative test.
- Scope trims — `ping` demoted to optional; `notifications/initialized` handled generically;
  error codes aligned to the tested set (dropped untested `-32600`); T4 design-doc note removed
  (folded into deliberation); manual smoke automated.
- Arch P3 — `serve()` defaults `server` to the `SERVER` singleton (single construction path).

Re-review verdict (attempt 2): Architecture ADVISORY, Scope ADVISORY, **Security PASS** — P0
gated by §H1 as a blocking acceptance criterion; H2–H6 convert remaining findings into
test-first gates. Two P3 advisories from the re-review folded in: §H3 extended to cover
`isError` tool-result content; §H6 negative test drives through the `tools/call` boundary.
Plan gate cleared — ready for harvest.

## Rollback

Purely additive (new modules + one entry-point line + docs). Rollback = revert the feature
branch; no data migration, no schema change, no change to existing runtime paths.

## Risks

- Low: stdout contamination would corrupt the JSON-RPC stream — mitigated by routing all logs
  to stderr and asserting clean stdout framing in tests.
- Low: manifest drift between CLI and MCP — mitigated by the T1 parity assertion against the
  single shared manifest source.
