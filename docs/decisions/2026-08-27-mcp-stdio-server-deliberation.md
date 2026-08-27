# Deliberation: Local stdio MCP server and `docline-mcp` executable

- Date: 2026-08-27
- Stage session: dark-factory stash sweep
- Source stash entry: `14E46B47` (feature, medium priority)
- Status: accepted — promoted to implementation plan

## Problem frame

The stash entry asks that docline "be discovered and used through a local stdio MCP
connection" and that MCP tools be exposed "via a `docline-mcp.exe` executable."

docline already ships a substantial MCP *adapter* layer:

- `docline.mcp.server.DoclineMcpServer` exposes `list_tools()`, `fetch()`, `process()`,
  and `export_schema()` over a stdio-only transport guard (`TransportMode.STDIO`).
- `docline.app.get_mcp_manifest()` returns the shared tool manifest, and the CLI already
  prints the same manifest via `docline --manifest`.
- Parity tests (`tests/parity/test_mcp_adapters.py`, `tests/parity/test_mcp_transport.py`)
  lock the adapter contracts to the shared app layer.

What is missing is the **runnable protocol surface**: there is no JSON-RPC stdio loop that
an external MCP client can speak to, and there is no `docline-mcp` console-script entry
point that produces the `docline-mcp(.exe)` binary. Today an agent cannot actually connect
to docline over stdio; it can only import the adapter in-process.

This is an interoperability/composability gap, not a feature-novelty request. Under the
operator's priority ordering (interoperability/composability over feature expansion), it
ranks as high product outcome even though it is scored `medium` in the stash.

## Options considered

### Option A — Hand-rolled JSON-RPC 2.0 stdio loop over the existing adapter (chosen)

Add a thin, dependency-free stdio dispatcher (`docline.mcp.stdio`) that reads line-delimited
JSON-RPC 2.0 messages from stdin, dispatches the MCP methods (`initialize`, `tools/list`,
`tools/call`, `ping`), delegates to the existing `DoclineMcpServer`, and writes JSON-RPC
responses to stdout. Add a `docline-mcp` console entry point plus `python -m docline.mcp`.

- Pros: no new runtime dependency (Single Responsibility principle VI); reuses the proven
  adapter + manifest + transport guard; keeps CLI/MCP parity trivial because both surfaces
  call the same `execute_fetch`/`execute_process`; smallest blast radius.
- Cons: we own the JSON-RPC framing and must test the protocol envelopes ourselves.

### Option B — Adopt the official `mcp` Python SDK / FastAPI-based server

Pull in the `mcp` SDK (or FastAPI, mentioned in the stack notes) and register tools through
its decorators.

- Pros: spec-tracking handshake maintained upstream.
- Cons: adds a heavyweight runtime dependency and a second server framework for a stdio-only
  surface; violates principle VI (dependencies justified by concrete need) when the adapter
  already exists; larger supply-chain/attack surface; more churn to reconcile with the
  existing manifest/transport-guard contracts. Rejected for this release unit; can be
  revisited if remote transports are ever approved (currently only stdio is approved).

### Option C — Defer / do nothing

Rejected: the stash entry is the highest product-outcome item in the sweep and has no
external blockers (no credentials, no paid calls, no corpora). It is safe executable work.

## Chosen direction

Option A. Implement a dependency-free stdio JSON-RPC 2.0 server that wraps the existing
`DoclineMcpServer`, expose it as `docline-mcp` (and `python -m docline.mcp`), and lock the
behavior with protocol + dual-interface parity tests before implementation (test-first).

Scope guardrails:

- Only stdio transport (reuse the existing `TransportMode` guard; reject anything else).
- No new production dependency; standard library `json`/`sys` only.
- `tools/list` must remain in **semantic parity** with the docline **callable allow-list** —
  same tool names and same normalized parameter schema — but NOT byte-for-byte identical to the
  raw `docline --manifest` four-tool set. Two sanctioned divergences apply: (1) MCP advertises
  tool schemas under `inputSchema` whereas the shared manifest uses `parameters` (a key alias);
  and (2) the security-sensitive `process.workspace_root` field is omitted, and
  `ingest_local_dir` is excluded from the MCP surface, on the untrusted stdio transport (see the
  plan §H1 parity exception and the Design "Advertised set == callable set" note). Parity is
  asserted on tool name + normalized schema content of the *advertised == callable* set, not raw
  byte equality against the full manifest.
- `tools/call` must route to the same shared app functions the CLI uses, preserving parity.
- Map Pydantic `ValidationError` to a JSON-RPC invalid-params (`-32602`) error envelope;
  unknown methods to `-32601`; malformed JSON to parse error (`-32700`).

## Open questions (resolved for this unit)

- Protocol version string to advertise in `initialize`: pin a single constant and assert it
  in tests; bump deliberately. Not a blocker.
- Notification handling (`notifications/initialized`): accept and ignore (no response), per
  JSON-RPC notification semantics. Covered by a test.

## References

- `src/docline/mcp/server.py`, `src/docline/mcp/exceptions.py`
- `src/docline/app.py` (`get_mcp_manifest`, `execute_fetch`, `execute_process`)
- `src/docline/app_models.py` (`ManifestTool`, `McpManifestResponse`)
- `tests/parity/test_mcp_adapters.py`, `tests/parity/test_mcp_transport.py`
- `docs/compound/2026-07-03-backlogit-mcp-down-fall-back-to-cli.md` (stdio MCP degraded-mode prior art)
