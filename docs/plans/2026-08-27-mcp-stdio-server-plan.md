# Implementation Plan: Local stdio MCP server and `docline-mcp` executable

- Date: 2026-08-27
- Source deliberation: `docs/decisions/2026-08-27-mcp-stdio-server-deliberation.md`
- Source stash: `14E46B47`
- Primary objective: Make docline usable over a local stdio MCP connection by adding a
  runnable JSON-RPC 2.0 stdio server that wraps the existing `DoclineMcpServer`, and ship a
  `docline-mcp` console executable entry point.
- Requires plan hardening: yes — a security P0 (untrusted `workspace_root` containment
  bypass) surfaced in plan review, plus cycle-2 SSRF-by-resolution and resource-exhaustion
  P0/P1s on the newly untrusted fetch surface; hardened in this revision (see `## Plan Hardening`).
- Plan-review status: revised after adversarial multi-persona reviews (Architecture,
  Security, Scope, Consistency). Cycle-3 (PR #166) adds authoritative-spec-driven **dual-era
  protocol conformance** (MCP `2026-07-28` `server/discover` + per-request `_meta` negotiation +
  `-32022`, alongside the retained legacy `initialize` handshake), **enforceable aggregate
  transfer-byte accounting**, and an **HTTP(S)-only `fetch` advertising correction**. Cycle-4
  (PR #166) reconciles twelve unresolved review threads: threaded during-read aggregate budget,
  frame carry-over buffering, proxy-disable for the SSRF pin, adapter-owned unknown-tool mapping,
  required `DiscoverResult` cache metadata + `clientCapabilities`, and scope/parity wording fixes.
  Cycle-5 (PR #166) reconciles seven further threads: the era classifier's per-process legacy latch
  + pre-initialize reject (legacy is selected only after `initialize`; the modern branch stays
  request-stateless), the feature-DoD during-read remaining-budget wording, the `get_manifest()`
  description edit-target attribution, and the regenerated continuity memory.
  Cycle-6 (PR #166, fresh review on HEAD dbadb4a) reconciles six further threads: explicit
  strict-safety high-risk action records for the shared-fetch and exposed-MCP surfaces, the
  064.017-T <5-function split into new successor 064.024-T, pinned numeric H7 limits
  (`MAX_PAGES_LIMIT`/`MAX_RESPONSE_BYTES`/`MAX_TOTAL_FETCH_BYTES`) with boundary behavior, the
  `src/`-prefixed transport paths (064.022-T/064.023-T), and a verifiable client MCP config format
  source for 064.004-T (no reliance on the git-ignored `.mcp.json`).
  Cycle-7 (PR #166, fresh review on HEAD b38d3b0) reconciles four further threads: the required
  standards-valid MCP `CallToolResult` wire shape for both eras (`content` is `ContentBlock[]`,
  modern adds `resultType`; 064.005-T/064.021-T harnesses + 064.002-T/064.022-T impl + feature DoD),
  the exact per-response and aggregate byte-cap boundaries via a `min(…, remainder + 1)` read-size
  cap so only the crossing byte is read (064.012-T/064.013-T and 064.016-T/064.017-T/064.024-T), and
  the regenerated 24-task continuity memory (`064.017 → 064.024 → 064.014`).
  Cycle-8 (PR #166, fresh review on HEAD 4271ca7) reconciles two further threads: the §H7 **item 4
  request-amplification bound** (a `MAX_FETCH_ATTEMPTS = 4000` frontier-pop cap in `fetch/crawl.py`
  counting the print-page / duplicate / out-of-scope non-counting branches + a `MAX_DEPTH_LIMIT = 64`
  `FetchRequest.depth` upper bound), split into a NEW width-isolated pair 064.025-T/064.026-T (chain
  grows 24 → 26, `064.024 → 064.025 → 064.026 → 064.014`), and the **interactive stdio-liveness**
  contract (064.008-T interactive `Popen` smoke + 064.002-T serve() non-greedy `read1`/`os.read` +
  stdout flush) that detects live deadlocks an EOF-first smoke masks.
  See `## Plan Review Remediation` (cycle-3, cycle-4, cycle-5, cycle-6, cycle-7, and cycle-8 subsections).
- Cross-interface blast radius: this release unit is NOT purely additive. It hardens the
  **shared** fetch code (`fetch/url_policy.py`, `fetch/http.py`, `app_models.py`) that both
  the CLI and the MCP surface call, and it changes the existing `DoclineMcpServer` adapter's
  callable surface. See `## Rollback`, `## Risks`, and `## Strict-Safety Action Records`.
<!-- plan-review-attempt: 3 -->

## Scope

In scope:

1. A dependency-free stdio JSON-RPC 2.0 dispatch loop that speaks a **dual-era** MCP method set
   and delegates to `DoclineMcpServer`:
   - **Legacy era (`2025-11-25` and earlier):** `initialize`, `notifications/initialized`,
     `tools/list`, `tools/call`, `ping`.
   - **Modern era (`2026-07-28`):** `server/discover` (MUST), plus `tools/list` / `tools/call`
     served statelessly with per-request `_meta` carrying BOTH
     `io.modelcontextprotocol/protocolVersion` AND `io.modelcontextprotocol/clientCapabilities`;
     unsupported versions return `-32022 UnsupportedProtocolVersionError` and missing/malformed
     `clientCapabilities` returns `-32602` (checked after version); results carry
     `resultType:"complete"` and `_meta.io.modelcontextprotocol/serverInfo`; list results AND the
     `DiscoverResult` (a `CacheableResult`) carry `ttlMs`/`cacheScope`.
   - **Era routing:** a request carrying modern `_meta` is served under modern semantics; an
     `initialize` request selects legacy semantics. Authoritative basis: MCP spec
     `2026-07-28` (`server/discover.mdx`, `basic/versioning.mdx`, `basic/transports/stdio.mdx`)
     — verified against the official spec repository, see `## Protocol Era Model`.
2. A `docline-mcp` console-script entry point and `python -m docline.mcp` bootstrap.
3. Protocol + dual-interface parity tests (test-first).
4. Operator/agent documentation: README run section + a self-contained client MCP configuration
   example in the documented GitHub Copilot / VS Code `.vscode/mcp.json` `servers` stdio format (a
   verifiable shape; NOT the repo's git-ignored `.mcp.json`). (No separate
   design-doc transport note — the transport surface is already documented in the deliberation;
   see the Scope trims in `## Plan Review Remediation`.)
5. **Shared-fetch hardening for the untrusted surface (existing-file changes).** Exposing
   `fetch` over untrusted stdio promotes previously CLI-only assumptions into a security
   boundary. Two shared-code gaps are closed here and apply to BOTH interfaces: (a) SSRF by
   DNS resolution — `fetch/url_policy.py` currently rejects only literal private hosts and does
   not resolve names, so a public hostname resolving to loopback/private space bypasses the
   guard (§H6); (b) resource exhaustion — `FetchRequest.max_pages` has no upper bound and
   `fetch/http.py` buffers each response with an unbounded `response.read()` (§H7). These land
   as their own width-isolated tasks (see `## Tasks`). **Aggregate byte accounting is made
   enforceable** (cycle-3): the bounded reader retains the *actual raw body byte count* on
   `FetchResponse` before decoding (kept as per-response observability), and the aggregate cap is
   enforced by a request-scoped during-read remaining-byte budget decremented per chunk as bytes are
   read (aborting mid-read; counting retries and ancillary fetches) — not a post-return sum — so
   decode/re-encode
   under-count cannot bypass the aggregate cap (§H7 item 3).
6. **Dual-era protocol conformance (cycle-3, existing + new transport code).** Add MCP
   `2026-07-28` `server/discover` (MUST), per-request `_meta` protocol-version negotiation with
   `-32022`, modern stateless result shape (`resultType`, serverInfo `_meta`, list
   `ttlMs`/`cacheScope`), and server-side era routing, while retaining the legacy `initialize`
   handshake. This is what makes docline reachable by a modern MCP client (the stated
   interoperability goal). See `## Protocol Era Model` and the dual-era tasks in `## Tasks`.
7. **`fetch` advertising correction (cycle-3, existing shared manifest).** The shared `fetch`
   tool description claims "a URL or file path" while `execute_fetch` rejects every non-HTTP(S)
   source. Correct the advertised description to HTTP(S)-only (matching behavior on BOTH
   interfaces) and lock it with a manifest⇄behavior parity test.

Out of scope (explicitly):

- Remote transports (HTTP/SSE/WebSocket) — only stdio is approved.
- New tool surfaces beyond the existing `fetch`, `process`, `export_schema`, and manifest
  discovery. No new business logic; this is a transport/packaging release unit.
- Modern-era MCP features beyond discovery + version negotiation + the existing tool surface:
  `subscriptions/listen`, Multi Round-Trip Requests (MRTR), the tasks/sampling/roots/logging
  features, and OpenTelemetry `_meta` conventions are all deferred (not required for a
  tools-only stdio server; adding them would be scope creep).
- Any change to `execute_process` *processing* behavior, and any change to `execute_fetch`
  behavior **beyond** the specified §H6/§H7 hardening. The in-scope shared-fetch hardening —
  DNS-resolution SSRF rejection + address-pinned connect (§H6) and the `max_pages` /
  per-response / aggregate resource caps (§H7) — **deliberately DOES change** shared
  `execute_fetch` behavior for BOTH the CLI and the MCP surface; that security work is squarely
  in scope (see `## Plan Hardening` §H6/§H7, the shared-fetch tasks in `## Tasks`, `## Rollback`,
  and `## Risks`). Only `execute_fetch` changes *outside* that specified hardening are excluded,
  so implementers must NOT treat the §H6/§H7 security work as out of scope. The `fetch`
  advertising correction changes only the advertised description text to match the existing
  rejection behavior, not processing behavior.
- Adopting the `mcp` SDK or FastAPI (see deliberation Option B rejection).

## Constitution Check

| Principle | Compliance |
|---|---|
| I. Safety-First Python | Type hints on all new public functions; typed errors via `McpTransportError` + JSON-RPC envelopes; no bare except. |
| II. Test-First Development | Protocol + parity tests authored and observed failing before the stdio loop is implemented. |
| III. Workspace Isolation | The stdio surface is untrusted. `execute_process` is NOT inherently contained: `ProcessRequest.workspace_root` is an unvalidated absolute path (no field_validator, unlike `staging_dir`/`output_dir`) and `safe_workspace_path` only contains the relative dirs *under* that root. The MCP boundary therefore **rejects** any client-supplied `workspace_root` and pins the root to the server-configured workspace (process cwd). The field is **omitted from the MCP-specific `process` input schema** so it is never advertised as accepted (see Plan Hardening §H1). With that gate, all `tools/call` FS operations resolve within the server workspace root. |
| IV. CLI Containment | Server only reads stdin / writes stdout; no out-of-cwd writes once `workspace_root` is pinned (§H1). |
| V. Observability | JSON-RPC error envelopes carry structured codes plus generic, non-reflective messages (no absolute paths, no tracebacks — §H3); full detail logs to stderr only. |
| VI. Single Responsibility | No new runtime dependency; stdlib `json`/`sys` only. |
| X. Context Efficiency | Reuses the shared manifest; no duplicated tool schema. |

No principle conflicts. The Principle III containment gate (§H1) is a blocking acceptance
criterion, not an advisory item.

## Design

- Tool identity lives in exactly ONE layer. Add a manifest-driven dispatch entry on the
  adapter — `DoclineMcpServer.call_tool(name: str, arguments: dict) -> object` — backed by an
  explicit static allow-list `{tool_name: adapter_callable}` where every entry has a **uniform
  `(arguments: dict) -> object` signature**. The underlying methods do NOT share a signature
  (`fetch`/`process` each take one request object built from `arguments`, while `export_schema()`
  takes no arguments), so `call_tool` MUST NOT invoke a raw bound method as `handler(arguments)` —
  that raises `TypeError` for `export_schema`. Each allow-list value is a small dict-taking adapter:
  the `fetch`/`process` adapters construct their request model from `arguments`; the `export_schema`
  adapter accepts **only an empty dict** and rejects any non-empty `arguments` (mapped to `-32602`).
  No `getattr(server, name)` (that
  would expose dunder/attribute dispatch injection). The transport module carries zero tool
  names; it is a pure JSON-RPC <-> adapter translator.
- Advertised set == callable set. The MCP `tools/list` is derived from the same allow-list
  `call_tool` dispatches, so nothing is advertised that cannot be invoked. **Parity-method
  contract (implementable acceptance criterion):** the existing adapter method
  `DoclineMcpServer.list_tools()` stays **unchanged** — it still returns the full shared
  manifest (four tools), so the existing suite
  `tests/parity/test_manifest_parity.py::test_mcp_server_list_tools_exposes_shared_manifest`
  (which asserts `SERVER.list_tools()` exposes every manifest tool) remains green with no edit.
  A **new** adapter method `DoclineMcpServer.list_callable_tools()` returns the callable
  allow-list manifest (the three dispatchable tools, with the `process` `inputSchema`
  `workspace_root` property removed). The stdio transport's `tools/list` calls
  `list_callable_tools()`, never `list_tools()`. **Adapter invariant (guards the footgun):**
  `list_tools()` is the manifest-parity accessor ONLY (it deliberately still advertises the
  unguarded `ingest_local_dir`); it MUST NOT be used as an MCP advertise source. The untrusted
  stdio surface's SOLE tool-list source is `list_callable_tools()`. The `call_tool` allow-list and
  `list_callable_tools()` share ONE static source of truth so the advertised == callable set holds
  at the adapter layer (no advertise-but-uncallable gap on the MCP surface). T1 (064.001-T) asserts
  this invariant — the transport advertises the callable set only, and `list_tools()` remains the
  four-tool manifest. Both adapter methods are delivered by the dedicated adapter task
  T-adapter [064.015-T] (server.py), kept separate from the transport loop. This resolves the
  earlier contradiction where
  "existing parity test unchanged" and "MCP list excludes `ingest_local_dir` / omits
  `workspace_root`" could not both hold on one method. The shared manifest advertises four tools
  (`fetch`, `process`, `export_schema`, `ingest_local_dir`); the callable MCP surface implements
  three. **Default-safe resolution: exclude `ingest_local_dir` from `list_callable_tools()`** on the untrusted stdio surface. Its `source_path` is a hand-authored
  plain-string schema (`src/docline/app.py`) with no workspace-containment validator (unlike
  `ProcessRequest.staging_dir`/`output_dir` and `FetchRequest.output_dir`, which carry
  `validate_workspace_relative_path`), so advertising/routing it unguarded would reintroduce an
  unbounded local-FS read/exfiltration surface analogous to the §H1 `workspace_root` P0. This
  omission is a **second sanctioned parity divergence** (alongside the §H1 `workspace_root`
  omission): `tools/list` stays in semantic parity with the *callable* allow-list, not with the
  raw four-tool manifest. **Blocking constraint if `ingest_local_dir` is ever routed onto the MCP
  allow-list instead (option a):** its `source_path` (and `output`/`staging_dir`) MUST be
  workspace-contained via `validate_workspace_relative_path` (or an equivalent boundary reject),
  mirroring §H1 — routing it without that gate is forbidden. Whichever option is chosen, a test
  MUST assert every advertised MCP tool is dispatchable by **actually invoking `call_tool` for each
  of the three callable tools** (`fetch`, `process`, `export_schema`) — not merely checking
  allow-list membership — so the uniform dict-taking adapter signature is exercised (no
  advertise-but-uncallable gap and no `export_schema` `TypeError`); the H4
  test (064.007-T) proves `ingest_local_dir` fails closed while excluded.
- New module `src/docline/mcp/stdio.py`:
  - `serve(stdin, stdout, server: DoclineMcpServer | None = None) -> int` — read/dispatch/write
    loop; `server` defaults to the existing module singleton `SERVER` (single construction
    path); terminates cleanly on EOF. Reserves the real stdout exclusively for JSON-RPC frames.
    **Interactive liveness (cycle-8):** frames are read with a NON-GREEDY primitive (`read1` /
    `os.read`, returning as soon as any bytes are available and never blocking to fill a whole
    `CHUNK_SIZE`) and stdout is FLUSHED after EVERY response frame, so an interactive client that
    sends one frame, awaits its response, then sends the next — with stdin still OPEN (the T2b
    [`064.008-T`] live subprocess smoke test) — never deadlocks. A greedy `read(CHUNK_SIZE)` that
    waits for the full chunk after a short frame, or a block-buffered stdout that withholds the
    response until the pipe closes, would live-lock that probe; an EOF-first test would mask it.
  - `dispatch(message: dict, server: DoclineMcpServer) -> dict | None` — pure function mapping a
    single JSON-RPC request to a response dict (or `None` for any id-less notification —
    handled generically, no per-notification special case). Unit-testable without stdio.
  - Request-shape validation (`-32600`): after a frame parses as JSON, the decoded value MUST be
    validated as a JSON-RPC 2.0 request object BEFORE method routing. A syntactically valid JSON
    payload that is not a valid request — a non-object root (array, string, number, bool, null),
    a missing or non-`"2.0"` `jsonrpc` member, or a missing/non-string `method` — returns an
    **Invalid Request** `-32600` envelope, distinct from the `-32700` parse error (invalid JSON)
    and `-32601` method-not-found (well-formed request, unknown method). Restoring `-32600` keeps
    the advertised JSON-RPC 2.0 surface spec-compliant.
  - Method map (dual-era — see `## Protocol Era Model`):
    - **Legacy era:** `initialize` → capabilities + legacy `protocolVersion` (`2025-11-25`) +
      serverInfo; `notifications/initialized` → silent; `ping` → `{}` (legacy-only utility,
      removed in the modern era).
    - **Modern era:** `server/discover` → `DiscoverResult` (supportedVersions, capabilities,
      serverInfo in `_meta`, `resultType:"complete"`, and — since `DiscoverResult` is a
      `CacheableResult` — `ttlMs`/`cacheScope`) via a single adapter accessor;
      `tools/list` / `tools/call` served statelessly with the per-request `_meta` carrying BOTH
      `io.modelcontextprotocol/protocolVersion` AND `io.modelcontextprotocol/clientCapabilities`
      (no prior handshake); an unsupported protocol version returns `-32022`, and a request with
      missing/malformed `clientCapabilities` returns `-32602` (validated only after version is
      accepted, so version negotiation takes precedence);
      modern results carry `resultType:"complete"` + serverInfo `_meta` (list results also
      `ttlMs`/`cacheScope`).
    - Common: `tools/list` → callable allow-list via `server.list_callable_tools()`;
      `tools/call` → `server.call_tool`. The version/identity/capability source of truth lives
      in exactly ONE adapter accessor (mirroring the single-source tool allow-list), so
      `initialize` and `server/discover` cannot drift.
  - Input bounds (DoS): frame reads MUST be bounded at the byte level, not size-checked after an
    unbounded `readline()`. A naive `stdin.readline()` (or `.read()` until newline) buffers an
    arbitrarily large — or never-terminated — frame into memory before any length check runs, so
    the check provides no real bound. Instead read from the raw binary stream with a NON-GREEDY
    primitive (`read1` / `os.read`, which returns available bytes without blocking to fill the
    request) in fixed-size chunks
    up to a hard `MAX_FRAME_BYTES` cap while scanning for the newline terminator: as soon as the
    accumulated bytes exceed the cap before a newline arrives, stop buffering, emit an
    error envelope, and **drain** the rest of that oversized frame in bounded chunks (discarding up
    to the next newline or EOF) so the loop resynchronizes without ever holding the whole frame.
    **Carry-over buffer (required, both paths).** A fixed-size chunk read can return a frame's
    newline terminator followed by the first bytes of the NEXT frame; the reader MUST retain those
    post-newline bytes in a carry-over buffer and seed the next frame's accumulation from them —
    never discard them — in BOTH the normal-frame path AND the oversized-drain path (when draining
    to the next newline, any bytes after that newline belong to the following frame and MUST be
    preserved). Dropping the suffix would silently lose the next JSON-RPC request. A test MUST
    cover two complete frames arriving in a single chunk (both are dispatched), including the case
    where the second frame immediately follows an oversized-drained first frame.
    Memory stays bounded even for an unterminated or chunked-oversized input. The parse-error
    handler catches `ValueError` AND `RecursionError` (deeply nested JSON raises `RecursionError`,
    a `RuntimeError` subclass that `json.JSONDecodeError` handling would miss) so one hostile
    message degrades to an envelope rather than crashing the loop.
  - Error envelopes: `-32700` parse error (invalid JSON), `-32600` invalid request (valid JSON
    but not a valid request object — see request-shape validation above), `-32601` method not
    found, `-32602` invalid params (wrap Pydantic `ValidationError`) and unknown/unroutable tool
    name (the adapter `call_tool`'s typed unknown-tool error, mapped here — the transport holds no
    allow-list of its own; fail closed), `-32603` internal error. Messages MUST be generic and non-reflective: no
    absolute paths, no `PathContainmentError` text, no tracebacks in `message`/`data`; log full
    detail to stderr.
  - Tool-result mapping (MCP `CallToolResult` wire shape, both eras): dispatch()'s tools/call
    handler shapes every successful `tools/call` return (`fetch`/`process`/`export_schema`) INLINE
    into a standards-valid `CallToolResult` whose `result.content` is a non-empty `ContentBlock[]`
    (typed text block(s)), with `result.structuredContent` mirroring the domain result when
    applicable — NOT the raw `FetchResult`/`ProcessResult`/`str` serialized directly (which real MCP
    clients reject). For `fetch`/`process`, `execute_fetch`/`execute_process` model failure as a
    *successful* call returning `success=False` + `error`; map a validated-but-failed tool result to
    a JSON-RPC *result* whose MCP `content` carries the sanitized error text with `isError=true`.
    Reserve `-326xx` envelopes for framing/validation/internal faults only (e.g. `export_schema`
    with non-empty arguments → `-32602`, NOT an `isError` result). The legacy transport (T2) shapes
    this inline; the modern branch (T-era-i1) reuses the SAME `CallToolResult` body and applies only
    the `resultType:"complete"` wrapper on top, so both eras emit an identical, standards-conformant
    tool-result body (asserted by `064.005-T` legacy and `064.021-T` scenario (c) modern).
  - Fetch resource bounds (§H7): the untrusted `tools/call` `fetch` path inherits a hard
    `max_pages` upper bound (enforced in the shared `FetchRequest` model), a streamed
    per-response byte cap (`MAX_RESPONSE_BYTES`) enforced in `fetch/http.py` on the initial
    response AND every redirect hop — replacing the unbounded `response.read()` — and a
    byte-accurate aggregate crawl budget (`MAX_TOTAL_FETCH_BYTES`) enforced by a request-scoped
    remaining-byte budget threaded into `fetch_page`/the bounded reader and decremented per chunk as
    the **raw** wire bytes are read (aborting mid-read; counting retried failures and ancillary
    robots/TOC fetches), with the raw `body_byte_count` also retained on `FetchResponse` for
    per-response accounting. These live in shared fetch code (see §H7 and the shared-fetch tasks),
    not in the transport module.
  - `fetch` advertising (cycle-3): the shared manifest's `fetch` tool description MUST state
    HTTP(S)-only, matching `execute_fetch`'s rejection of every non-HTTP(S) source
    (`src/docline/app.py:596-603`). The prior "a URL or file path" text over-advertised an input
    mode neither interface accepts. Correct the shared description literal in `get_manifest()`
    (`src/docline/app.py:465-468`) — the single shared string that `get_mcp_manifest()` re-exposes
    to the MCP surface — it flows to both `list_tools()` and `list_callable_tools()`
    and to `docline --manifest`, so both surfaces become truthful — and lock it with a
    manifest⇄behavior parity test. (Correcting the shared string is preferred over an
    MCP-specific override because the CLI advertising is equally wrong.)
  - stdout hygiene: redirect process-level `sys.stdout` (to stderr or a buffer) for the duration
    of each `tools/call` so third-party library writes (docling/crawler/httpx) cannot corrupt or
    smuggle JSON-RPC frames. The private protocol stdout handle is used only for framing.
- New module `src/docline/mcp/__main__.py`:
  - `main() -> int` → constructs/reuses `DoclineMcpServer()` (stdio guard) and calls `serve(...)`.
  - Enables both `python -m docline.mcp` and the console script.
- `pyproject.toml` `[project.scripts]`: add `docline-mcp = "docline.mcp.__main__:main"`.
  On Windows install this materializes `docline-mcp.exe`.

## Protocol Era Model

**Authoritative basis (verified, not assumed).** The PR #166 cycle-3 review claimed MCP
`2026-07-28` mandates `server/discover`, per-request `_meta` protocol version with no
`initialize` handshake, and `-32022`. This was verified against the official specification
repository `modelcontextprotocol/modelcontextprotocol`, path `docs/specification/2026-07-28`
(retrieved 2026-08-27), rather than trusting the review:

- `server/discover.mdx`: "Servers **MUST** implement it." Advertises supported versions,
  capabilities, and identity; also the stdio backward-compatibility probe.
- `changelog.mdx` major change #2: removes the `initialize`/`notifications/initialized`
  handshake; every request carries its version in `_meta`
  (`io.modelcontextprotocol/protocolVersion`, `io.modelcontextprotocol/clientCapabilities`);
  version mismatch → `UnsupportedProtocolVersionError`.
- `changelog.mdx` minor change #12: `UnsupportedProtocolVersion` renumbered to **`-32022`**
  (MCP-reserved server-error range `-32020..-32099`); `versioning.mdx` shows the envelope with
  `data.supported` + `data.requested`.
- Also: `ping` is removed in the modern era (legacy-only); results carry a required
  `resultType` (`"complete"`); list results carry `ttlMs`/`cacheScope`.

The claims are confirmed. Under the operator's priority (external stdio discovery +
interoperability outranks feature simplicity), a legacy-only server fails the
"Modern client → Legacy server" cell of the `versioning.mdx` compatibility matrix, so the
interoperability goal is **not** met without modern support.

**Decision: dual-era server** (`versioning.mdx` "Backward Compatibility with
Initialization-Based Versions" — a dual-era server "selects its behavior from how the client
opens").

| Concern | Legacy era (`2025-11-25` and earlier) | Modern era (`2026-07-28`) |
|---|---|---|
| Open / negotiate | `initialize` handshake → capabilities + `protocolVersion` + serverInfo | per-request `_meta` carries BOTH `io.modelcontextprotocol/protocolVersion` AND `io.modelcontextprotocol/clientCapabilities`; no handshake |
| Discovery | `tools/list` after handshake | `server/discover` (MUST) returns supportedVersions + capabilities + serverInfo + cache metadata (`ttlMs`/`cacheScope` — `DiscoverResult` is a `CacheableResult`); answerable before any request |
| Version mismatch | n/a (handshake pins) | `-32022 UnsupportedProtocolVersionError` with `data.supported` + `data.requested`; missing/malformed `clientCapabilities` → `-32602` (checked after version) |
| Result shape | plain result | `resultType:"complete"` + serverInfo in result `_meta`; list results AND the `DiscoverResult` carry `ttlMs`/`cacheScope` |
| `ping` | supported | removed |

- **Era routing (server-selected):** a request carrying modern per-request `_meta` is served
  statelessly under `2026-07-28` (the modern branch is **request-stateless** — it never consults
  prior session state); an `initialize` request selects **legacy semantics for the stdio process**
  by latching a per-process legacy-era selection that governs subsequent metadata-free operations; a
  `server/discover` call is answerable before any `initialize` (stdio probe). The request-shape
  classifier resolves the era in this precedence: modern `_meta` → modern (stateless);
  `server/discover` → discovery (pre-handshake); `initialize` → set the per-process legacy latch and
  serve legacy; an otherwise metadata-free operation (`tools/call`/`tools/list` with no `_meta`) is
  served legacy **only when the legacy latch is already set**, and is **rejected** (an error result,
  never dispatched) when it arrives **before** that `initialize` selection. A metadata-free
  operation is therefore never silently classified as legacy before initialization, so a malformed
  modern request (one missing its `_meta`) cannot bypass the required `_meta` validation by falling
  through to the legacy path. A dedicated **pre-initialize operation test** asserts this reject.
  The legacy handshake selects the process era; it is not the request shape that opens legacy.
- **Advertised versions:** `server/discover.supportedVersions` and `-32022 data.supported`
  enumerate both eras (`["2026-07-28", "2025-11-25"]`); the legacy `initialize` response pins
  `2025-11-25`.
- **Single source of truth:** the supported-version list, capabilities, and serverInfo live in
  ONE adapter accessor (`DoclineMcpServer.describe_server()`), **introduced by the adapter task
  T-adapter [064.015-T]** so the legacy `initialize` (T2) consumes it from first implementation and
  never hardcodes identity literals in the transport; both `initialize` and `server/discover`
  (T-era-i1) read from it so the two entry points cannot drift, and the transport stays a pure
  translator at every commit (mirrors the single-source tool allow-list invariant in Design).
- **Guardrail parity across eras (P0/P1, blocking).** Era routing changes ONLY the negotiation
  handshake and the result envelope shape — it MUST NOT change which security guardrails apply.
  Both eras MUST funnel every `tools/call` (and `process`) through the SAME single hardened
  dispatch path so the §H1 `workspace_root` reject, §H3 error-text non-disclosure, §H4 closed
  allow-list, and §H5 stdout hygiene are one enforcement point that the era classifier cannot
  branch around; §H6/§H7 already enforce inside the shared `execute_fetch`. This is a security
  invariant, not an optimization: because the modern surface is **stateless and answerable before
  any `initialize`**, a modern client can invoke `tools/call process` with no handshake, so a
  modern branch that re-wraps the result WITHOUT re-applying the §H1 reject would re-open the
  original P0 workspace-containment bypass (client sets `workspace_root:"/"`/`C:\\`), and a modern
  branch that skips the §H3 sanitizer would leak absolute paths in modern `isError` content. The
  modern result wrapper (`resultType`, serverInfo `_meta`, list `ttlMs`/`cacheScope`) is applied
  AFTER the shared guarded handler returns, never as a parallel unguarded handler. **Ownership
  (cycle-4):** the modern branch is BUILT to funnel through the shared hardened dispatch by
  **064.022-T** (guards-by-construction the moment the modern branch is reachable), which greens the
  modern-path H1/H3/H5 parity scenario (064.021-T scenario c) at 064.022 — so no 064.022→064.023
  build window exposes an unguarded modern pre-handshake path. **064.023-T** then VERIFIES parity is
  not regressed by the legacy branch (rather than wiring the guards for the first time). The
  dual-era harness 064.021-T carries the modern-path (`_meta`, no `initialize`) H1/H3/H5 parity
  scenario, and both 064.022-T (funnel) and 064.023-T (verify) carry guard-parity acceptance
  criteria.
- **Scope guardrail:** only discovery + version negotiation + the existing tool surface are
  added. `subscriptions/listen`, MRTR, and the tasks/sampling/roots/logging features are out of
  scope (see Scope).

## Plan Hardening

Security/reliability guardrails promoted to blocking design constraints after plan review.

- **H1 — Workspace-root containment (P0, blocking).** At the MCP boundary, `tools/call`
  `process` MUST **reject** a client-supplied `workspace_root` (single defined behavior — not
  "ignore"). The dispatcher pins the root to the server-configured workspace (process cwd) and,
  when a client passes `workspace_root` in the `process` arguments, returns a `-32602`
  invalid-params envelope rather than silently honoring or dropping it. The field is **omitted
  from the MCP-specific `process` input schema** advertised by `tools/list` (an explicit,
  documented parity exception — see the §H1 parity-exception note below), so a compliant client
  never sends it and a hostile one is rejected. Blocking test: a `process` call with
  `workspace_root:"/"` and a Windows drive-letter form (`C:\\`) is rejected and writes nothing
  outside the workspace.
  - **§H1 parity exception (documented).** `tools/list` is otherwise in semantic parity with
    the shared manifest (`get_manifest()` derives the `process` schema from
    `ProcessRequest.model_json_schema()`, which includes `workspace_root`; see
    `src/docline/app.py:459-479` and `src/docline/app_models.py:104`). The MCP `process`
    `inputSchema` intentionally **removes** the `workspace_root` property before advertising.
    Together with the `ingest_local_dir` exclusion (see the Design "Advertised set == callable
    set" note), these are the sanctioned field/tool-level divergences from raw manifest parity
    (on top of the `parameters`↔`inputSchema` key alias). The build-time `inputSchema`
    construction that removes `workspace_root` and excludes `ingest_local_dir` is delivered by
    the adapter task (T-adapter [064.015-T], via `list_callable_tools()`); the runtime reject of a
    client-supplied `workspace_root` is delivered by the security task (T2s). The T1 parity
    assertion normalizes these out — comparing `tools/list`
    against the *callable* allow-list rather than the raw four-tool manifest — so semantic parity
    still holds and the field is never advertised as an accepted, security-sensitive parameter.
- **H2 — Untrusted-input bounds.** Frame reading is bounded at the byte level: a fixed-chunk
  binary read scans for the newline terminator up to a hard `MAX_FRAME_BYTES` cap and, on
  overflow, emits an error envelope and drains the remainder of the oversized frame in bounded
  chunks so memory never holds a whole hostile frame. A **carry-over buffer** preserves any bytes
  read after a frame's newline (a chunk read can straddle a frame boundary) and seeds the next
  frame from them, in both the normal and oversized-drain paths, so a following request in the same
  chunk is never dropped. `RecursionError`/`ValueError` both degrade
  to an error envelope; the loop survives hostile input. Tests: (a) oversized single line; (b)
  deeply nested array; (c) an **unterminated / chunked oversized** input (bytes exceeding the cap
  arrive with no newline) is rejected with bounded memory while waiting for the terminator, and
  the loop resynchronizes on the next valid frame; (d) **two complete frames in a single chunk**
  are both dispatched (carry-over preserves the post-newline suffix), including a valid frame
  immediately following an oversized-drained frame in the same chunk.
- **H3 — Error-text non-disclosure.** No absolute paths / tracebacks in envelopes OR in
  `isError` tool-result content (the `success=False` mapping surfaces `ProcessResult.error` /
  `FetchResult.error`, which may embed absolute resolved paths via `PathContainmentError`).
  Sanitize/genericize both surfaces. Test: a containment/validation failure — as an envelope
  AND as an `isError` result — contains no absolute-path substring.
- **H4 — Closed tool allow-list.** The static `{name: adapter_callable}` map (uniform dict-taking
  adapters) lives in EXACTLY ONE place —
  the adapter (`DoclineMcpServer.call_tool`, task 064.015-T). `call_tool` raises a typed
  unknown-tool error for any name absent from that allow-list (incl. `ingest_local_dir` if
  unrouted, and dunders); the transport MAPS that typed error to a `-32602` envelope and carries
  no tool names of its own. Fail closed, never `AttributeError`, and never a second allow-list
  duplicated in `stdio.py` (which would recreate advertise/dispatch drift).
- **H5 — stdout reserved for frames.** Child-library stdout redirected during tool execution;
  test asserts stdout carries only well-formed JSON-RPC frames across a fetch/process call.
- **H6 — fetch SSRF by DNS resolution (P0, blocking).** Literal-IP rejection is NOT sufficient
  on the untrusted MCP surface. The current guard `fetch/url_policy.py` `is_private_host` does
  **not** resolve hostnames (`src/docline/fetch/url_policy.py:50-56`) and `fetch/http.py` connects
  via `urllib` (`src/docline/fetch/http.py:116-123`), so a public hostname that resolves to
  loopback/private/link-local space (`internal.example.com` → `127.0.0.1`, or a DNS-rebinding
  A-record) bypasses the guard entirely and gives the new untrusted surface SSRF access to
  local/metadata services. Required behavior (shared-code hardening, both interfaces):
  1. **Resolution/connect-time validation.** Before connecting, resolve the host and reject if
     **any** resolved address (all A/AAAA records) is loopback, private (RFC 1918 / RFC 4193),
     link-local, or a metadata address (`169.254.169.254`). Normalize IPv4-mapped IPv6
     (`::ffff:a.b.c.d`) to its IPv4 form before classification, and include ULA (`fc00::/7`),
     CGNAT (`100.64.0.0/10`), and `0.0.0.0` so alternate-encoding SSRF bypasses are covered.
     Literal-IP hosts keep their existing fast-path rejection. This closes the name→private gap
     `is_private_host` leaves open.
  2. **Redirects revalidated.** Every redirect target is re-resolved and re-validated at
     connect time, not just compared by `netloc`, so a redirect to a name that resolves to a
     private address is rejected mid-chain.
  3. **Address-pinned connect (in-scope, closes DNS-rebinding).** Validation and connection MUST
     use the **same** resolved address: the client controls both the URL and its authoritative DNS,
     so a resolve-then-let-`urllib`-re-resolve design is a *deterministic* rebinding bypass (the
     validation lookup returns a public IP; `urllib`'s own connect lookup, TTL 0, returns
     `127.0.0.1`). The connection MUST be pinned to the specific validated IP (connect to the
     resolved address while preserving the `Host` header / SNI) so no second, unvalidated
     resolution occurs. **Inherited proxies MUST be disabled for this fetcher.**
     `request.build_opener(handler)` installs urllib's default `ProxyHandler`, which honors
     `HTTP(S)_PROXY` environment variables and would hand the ORIGINAL hostname to a proxy that
     performs its own second, unvalidated DNS resolution — reopening rebinding whenever proxy vars
     are set. The fetcher MUST install an explicitly empty `ProxyHandler({})` (NOT `ProxyHandler(None)`,
     which falls back to `getproxies()` and would still honor macOS SystemConfiguration /
     Windows-registry system proxies) so no proxy re-resolves the host on any platform; alternatively
     an IP-pinned `CONNECT` path may be specified and tested. This is a blocking acceptance
     criterion, not a deferred follow-up, with a proxy-variables-set test proving no proxy-side
     resolution occurs.
  Delivered by the shared-fetch SSRF tasks (harness `064.010-T`, impl `064.011-T` in
  `url_policy.py`/`http.py`). End-to-end proof: a `tools/call` `fetch` to a hostname resolving to
  loopback/private is rejected through the full boundary (stdin JSON → dispatch → `server.fetch`
  → `execute_fetch`), asserted in the MCP boundary harness `064.014-T`. The literal-IP end-to-end
  smoke (`http://127.0.0.1`, `http://169.254.169.254`) stays in `064.007-T`.
- **H7 — fetch resource-exhaustion bounds (P1, blocking).** A small valid request can trigger
  unbounded work: `FetchRequest.max_pages` has no upper limit (`src/docline/app_models.py:25`) and
  each response is buffered with an unbounded `response.read()` (`src/docline/fetch/http.py:123`),
  so an untrusted caller can request arbitrarily many pages or a single arbitrarily large response
  and exhaust memory/network. Required behavior (shared-code hardening, both interfaces):
  1. **Page/work cap.** `FetchRequest.max_pages` gains a hard upper bound (`Field(le=…)`), so an
     over-limit value is rejected at validation and surfaces as `-32602` on the MCP boundary.
  2. **Streamed response-byte cap.** `fetch/http.py` reads the body in bounded chunks up to a
     hard `MAX_RESPONSE_BYTES` cap and aborts once exceeded — never a single unbounded
     `response.read()`. The cap applies to the initial response AND to the body of every redirect
     hop's final response.
  3. **Aggregate crawl-byte budget (byte-accurate, enforceable).** Per-response and per-page caps
    do not bound their product: a single small `tools/call` `fetch` at the `max_pages` cap
    against an attacker-controlled server returning maximum-under-cap responses drives
    `max_pages × MAX_RESPONSE_BYTES` of network transfer and disk staging (each page is written
    under `output_dir` by `execute_fetch`). The crawl loop (`fetch/crawl.py`) MUST enforce a hard
    **aggregate** `MAX_TOTAL_FETCH_BYTES` budget across all pages and abort once the running total
    is exceeded (bound the product, not each dimension).
    **Enforceability requirement (cycle-3, review-mandated).** The budget is defined in *bytes*,
    but `crawl.py` today receives only `FetchResponse.body: str` — the raw byte count is discarded
    when `fetch_page` decodes the response (`fetch/http.py:123-125`, `body_bytes.decode(charset,
    errors="replace")`). Summing `len(body)` (characters) or `len(body.encode())` (a *re-encode*,
    not the wire bytes) **under-counts** the actual transfer: non-ASCII bodies have more bytes than
    characters, and `errors="replace"` collapses each invalid byte to a single `U+FFFD`, so a
    hostile server can drive far more than `MAX_TOTAL_FETCH_BYTES` of real transfer while the
    character/re-encode total stays under budget — the bound is not enforceable as written.
    Therefore two coupled requirements: (1) the bounded reader MUST **retain the actual raw body
    byte count** (the length of the bytes read from the network, captured *before* decoding) on
    `FetchResponse` (a new `body_byte_count: int` field set from the bounded read in
    `fetch/http.py`) for accurate per-response accounting; and (2) the aggregate MUST be enforced by
    a **request-scoped remaining-byte budget threaded into `fetch_page` and its bounded reader and
    decremented WHILE CHUNKS ARE READ** — not by a post-hoc `crawl.py` accumulator that sums
    `body_byte_count` only after `fetch_page` returns a *successful* `FetchResponse`. A post-return
    accumulator cannot enforce a hard bound: the response that crosses the budget has already been
    fully read before it is summed, and bytes consumed by over-cap attempts that raise and are
    retried by `_fetch_with_retries` never return a `FetchResponse` to accrue at all. Instead,
    `crawl.py` seeds ONE request-scoped budget per crawl request and passes it through **every**
    `fetch_page` call (main pages, retries, and the ancillary fetches below); the bounded reader
    decrements that shared budget per chunk and aborts the read **mid-stream** the instant the
    remaining aggregate allowance would be exceeded (the crossing response is never fully buffered).
    The budget accumulates the exact raw wire bytes — never a character count or a re-encode. The
    budget defaults to unbounded for a standalone single fetch so existing CLI single-fetch callers
    are unaffected. Tests MUST include a **non-ASCII multibyte** payload and an **invalid-byte**
    payload (where `errors="replace"` would otherwise under-count) proving the aggregate uses raw
    wire bytes, PLUS a **repeated-failure** case (a retried over-cap attempt still decrements the
    shared budget) and a **mid-read abort** case (the crossing response aborts before full
    buffering).
    **Propagation requirement (cycle-4, review-mandated).** The mid-read abort raises a typed
    `AggregateBudgetExceededError` (a `DoclineError` subclass, per the typed-error convention). Because
    `crawl.py` catches `DoclineError` broadly at FOUR sites — the `crawl()` main loop, `_fetch_with_retries`,
    `_robots_allow`, and `_discover_toc_links` — the budget error would be silently swallowed and recorded
    as a per-page skip, letting the crawl continue over the remaining frontier with budget `0` and
    degrading a clean byte-abort into a `max_pages × backoff` time-exhaustion. Therefore the budget error
    MUST be re-raised at all four sites via `except AggregateBudgetExceededError: raise` placed immediately
    before each broad `except (DoclineError, OSError)` handler (mirroring the existing
    `except CrawlUrlRejectedError: raise` pattern; `_robots_allow` has no prior re-raise clause and needs
    one added), so `crawl()` itself RAISES the budget error rather than returning skipped results. The
    harness asserts `crawl()` propagates (raises), not that it returns skipped pages.
    **Auxiliary-fetch coverage (cycle-3 adversarial re-review).** The crawl also issues auxiliary
    `fetch_page` calls that are NOT appended to `results` — `robots.txt` fetches
    (`fetch/crawl.py` `_robots_allow`) and mdBook TOC-script fetches (`_discover_toc_links`). Each
    is individually bounded by the per-response `MAX_RESPONSE_BYTES` cap and `robots.txt` is cached
    per-origin, so the uncounted amplification is bounded (~`(origins + toc_scripts) ×
    MAX_RESPONSE_BYTES`, none staged to disk) — not an unbounded leak. Still, to make the aggregate
    a true "all transfer for this request" bound, these auxiliary `fetch_page` calls MUST receive
    the SAME request-scoped budget and decrement it while their bytes are read (identically to main
    pages), so a hostile server cannot amplify transfer via oversized-but-under-cap
    `robots.txt`/TOC payloads outside the budget.
  4. **Request-amplification bound (request COUNT, not byte VOLUME — cycle-8, review-mandated).**
    The per-response (item 2) and aggregate (item 3) caps bound total *bytes transferred*, but
    they do NOT bound the *number of requests*. `FetchRequest.max_pages` does not cap actual fetch
    work either: the crawl loop (`fetch/crawl.py`) issues a real network fetch on **every** frontier
    pop, but only increments `page_count` on *emitted* pages — three branches fetch a page yet
    `continue` WITHOUT `page_count += 1`: the print-page branch
    (`_is_print_page(final_url, response.body)`, which ALSO enqueues the page's links), the duplicate
    branch (`final_key in emitted_urls`), and the out-of-scope-section branch
    (`domain_lock and not _url_within_section_scope(final_url, section_scope)`). Only the print-page
    branch enqueues links; the duplicate and out-of-scope branches simply consume a frontier pop
    (a real fetch) and continue. Combined with `FetchRequest.depth` having **no upper bound**
    (`app_models.py:24`, `Field(default=0, ge=0)`, flowed into `CrawlConfig.max_depth` at
    `app.py:606`), an attacker-controlled server can chain tiny under-cap `/print` pages — each far
    below `MAX_RESPONSE_BYTES` and contributing almost nothing to the `MAX_TOTAL_FETCH_BYTES`
    aggregate — that each enqueue fresh in-scope links (a self-sustaining frontier), and can seed the
    duplicate/out-of-scope pops from an emitted page that enqueues many distinct alias URLs which
    each redirect to an already-emitted or out-of-section final URL — driving **far more than
    `MAX_PAGES_LIMIT`** actual fetches (connection/DNS/robots amplification, retry storms)
    while `page_count` never reaches its cap and the byte budgets stay unspent. Therefore two
    coupled, hard, measurable request-count bounds are required (shared-code hardening, both
    interfaces):
    (a) a **fetch-attempt/frontier-pop cap**: `fetch/crawl.py` maintains a per-request `fetch_attempts`
    counter incremented on EVERY frontier pop (an actual main-page fetch) — so the print-page,
    duplicate, and out-of-scope branches all count — and aborts the crawl by RAISING a typed error
    (a `DoclineError` subclass) once attempts would exceed `MAX_FETCH_ATTEMPTS`; the crawl RAISES,
    it does not silently return the accumulated skipped results. Implement as a pre-fetch increment
    plus abort, or extend the loop guard to `while frontier and page_count < max_pages and
    fetch_attempts < MAX_FETCH_ATTEMPTS`. This caps FRONTIER POPS (main-page fetch attempts), which
    is the unbounded amplification vector; the bounded per-pop multipliers — per-pop retries
    (`_fetch_with_retries`) and per-hop redirects — remain governed by their existing small
    constants, and the ancillary `robots.txt` (per-origin cached) and depth-0 TOC-script fetches
    (`_discover_toc_links`) remain governed by the per-response cap + the aggregate byte budget, so
    the total outbound-request count is a finite bounded product of the pop cap and those existing
    limits rather than an unbounded chain. (b) a **depth upper bound**: `FetchRequest.depth` gains a
    hard `Field(le=…)` upper bound (preserving `default=0`) so an over-limit value is rejected at
    validation and surfaces as `-32602` on the MCP boundary, closing the unbounded-depth
    frontier-expansion vector at the untrusted input.
    **Coverage requirement.** The red harness MUST drive each of the three non-counting branches to
    consume frontier pops without incrementing `page_count`, using a branch-accurate fake transport:
    (i) **print** — each print response naturally enqueues a fresh in-scope link (a self-sustaining
    frontier); (ii) **duplicate final URL** — an emitted page preloads many distinct alias request
    URLs, each of which redirects (via `response.url`) to an already-emitted final URL, hitting the
    `final_key in emitted_urls` branch; (iii) **out-of-scope** — an emitted page preloads many
    distinct in-scope request URLs, each of which redirects to an out-of-section final URL, hitting
    the `not _url_within_section_scope(final_url, …)` branch. Assert that consuming the frontier
    through each branch trips `MAX_FETCH_ATTEMPTS` while `page_count` stays below `max_pages`; plus an
    over-limit `depth` (`>= MAX_DEPTH_LIMIT + 1`) rejected at model validation AND a request
    OMITTING `depth` still validating (depth defaults to 0).
  **Selected numeric limits (cycle-6, review-mandated — measurable boundary before red tests).**
  These constants are pinned now so the H7 harnesses (`064.012-T`, `064.016-T`, `064.014-T`) assert
  exact boundaries rather than implementation-time judgment. They are named module constants in the
  shared fetch code, sized against the current workload baseline (`CrawlConfig.max_pages` default =
  `50`, `src/docline/fetch/crawl.py`):
  - **`MAX_PAGES_LIMIT = 1000`** (`FetchRequest.max_pages` bound: `Field(ge=1, le=1000)`).
    Rationale: 20× the current bounded-crawler default of `50` — generous headroom for large
    documentation-site / mdBook crawls (hundreds of pages) while bounding an untrusted caller from
    requesting an unbounded page count. Boundary: `max_pages` in `1..1000` inclusive is accepted;
    `>= 1001` is rejected at Pydantic validation → `-32602` on the MCP boundary. `None` still means
    "use the crawler default of `50`".
  - **`MAX_RESPONSE_BYTES = 10 * 1024 * 1024 = 10_485_760`** (10 MiB) streamed per-response cap.
    Rationale: docline stages text-centric documents (HTML/Markdown, occasionally moderate PDFs);
    10 MiB is far above a typical documentation page (KB–low-MB) yet bounds a single hostile
    response from exhausting memory via the current unbounded `response.read()`. Applies to the
    initial response body AND every redirect hop's final response. Boundary: a response up to and
    including exactly `10_485_760` raw wire bytes is allowed; the bounded reader caps each
    individual read size at `min(CHUNK_SIZE, MAX_RESPONSE_BYTES - bytes_read + 1)`, so at the
    boundary only the single crossing byte can be pulled from the socket — never a full extra
    `CHUNK_SIZE` chunk. It aborts mid-stream (typed error) the instant a read returns a byte beyond
    `10_485_760` (the over-cap response is never fully buffered; the over-cap transfer is at most
    `MAX_RESPONSE_BYTES + 1`, not `MAX_RESPONSE_BYTES + CHUNK_SIZE`).
  - **`MAX_TOTAL_FETCH_BYTES = 512 * 1024 * 1024 = 536_870_912`** (512 MiB) aggregate per-request
    crawl budget. Rationale: bounds the *product* of the page and per-response caps — the naive
    product `MAX_PAGES_LIMIT × MAX_RESPONSE_BYTES` (1000 × 10 MiB ≈ 10 GiB) is the amplification
    vector; 512 MiB caps total transfer / disk staging at ~20× below that product while still
    covering a large legitimate crawl (e.g. ~500 pages averaging ~1 MiB, or 50 pages of ~10 MiB).
    The aggregate is the effective transfer bound for the "many large pages" attack (it trips after
    at most ⌊512 MiB / 10 MiB⌋ = 51 full-size responses, well inside the 1000-page count cap).
    Boundary: the request-scoped remaining-byte budget starts at `536_870_912` and is decremented
    by the actual bytes read across **every** `fetch_page` call for the request (main pages, retried
    over-cap attempts, and ancillary `robots.txt`/TOC fetches). The bounded reader caps each read
    size at `min(CHUNK_SIZE, per_response_remainder + 1, aggregate_remainder + 1)` and counts the
    actual bytes returned, so at either boundary only the single crossing byte can be pulled from
    the socket — never a full extra `CHUNK_SIZE` chunk. A total of exactly `536_870_912` raw bytes
    is allowed; the read aborts mid-stream (raising `AggregateBudgetExceededError`, re-raised out of
    `crawl()`) the instant a read returns a byte beyond the aggregate allowance (the over-budget
    transfer is at most `budget + 1`, not `budget + CHUNK_SIZE`). Defaults to unbounded (`None`) for
    a standalone single fetch so existing CLI single-fetch callers are unaffected.
  - **`MAX_FETCH_ATTEMPTS = 4 * MAX_PAGES_LIMIT = 4000`** (per-request frontier-pop / actual
    main-page fetch-attempt cap, enforced in `fetch/crawl.py`; §H7 item 4a). Rationale: `MAX_PAGES_LIMIT`
    (1000) caps only *emitted* pages, but every frontier pop is a real fetch and the print-page /
    duplicate / out-of-scope branches pop-and-fetch without incrementing `page_count`. Even a
    skip-heavy legitimate crawl (redirects, duplicates, robots-disallowed, print variants) fetches
    at most a small multiple of its emitted-page budget, so `4×` the hard page cap gives generous
    headroom while hard-capping total main-page FETCH ATTEMPTS (frontier pops) at 4000 regardless of
    how many are uncounted by `page_count` — closing the tiny-`/print`-page amplification vector.
    Scope of the bound: this caps FRONTIER POPS, not raw HTTP transactions; the per-pop retries
    (`_fetch_with_retries`) and per-hop redirects, and the ancillary per-origin-cached `robots.txt`
    and depth-0 TOC-script fetches, remain bounded by their existing small constants and by the
    per-response + aggregate byte caps — so the total outbound-request count is a finite bounded
    product, not an unbounded chain. Boundary: exactly 4000 fetch
    attempts are allowed; the 4001st is refused (the crawl RAISES a typed error, it does not return
    the accumulated skipped results). Defaults to the same hard cap for CLI and MCP (shared code).
  - **`MAX_DEPTH_LIMIT = 64`** (`FetchRequest.depth` bound: `Field(default=0, ge=0, le=64)` — the
    existing `default=0` is PRESERVED so `depth` stays optional and a request omitting it defaults
    to 0; §H7 item 4b).
    Rationale: legitimate documentation trees are shallow (section → chapter → page, typically
    depth 0–6); 64 is an order of magnitude above any realistic doc hierarchy while preventing an
    untrusted caller from setting `depth` to a huge value to force deep frontier expansion. Combined
    with domain-lock, section-scope, dedup, and the `MAX_FETCH_ATTEMPTS` cap, depth 64 bounds the
    discovery tree. Boundary: `depth` in `0..64` inclusive is accepted; `>= 65` is rejected at
    Pydantic validation → `-32602` on the MCP boundary. `depth` flows into `CrawlConfig.max_depth`
    (`app.py:606`), so the model bound closes the untrusted-input depth vector.

  Cap tasks: the `max_pages` upper bound (`MAX_PAGES_LIMIT = 1000`) and the streamed per-response
  `MAX_RESPONSE_BYTES` (10 MiB) cap are delivered by harness `064.012-T` + impl `064.013-T`
  (`app_models.py` / `fetch/http.py`). The byte-accurate **aggregate** `MAX_TOTAL_FETCH_BYTES`
  (512 MiB) budget — raw-byte retention on `FetchResponse` (observability) and the request-scoped
  during-read remaining-byte budget (decremented per chunk, aborting mid-read) for **main pages +
  retries** — is delivered by harness `064.016-T` + impl `064.017-T` (`fetch/http.py` /
  `fetch/crawl.py`); the **ancillary-fetch** (`robots.txt`/TOC) budget decrement + its two
  `except AggregateBudgetExceededError: raise` clauses are split into successor impl `064.024-T`
  (`fetch/crawl.py`, cycle-6 split — see `## Plan Review Remediation` cycle-6), which takes over the
  `064.016-T` scenario (c)(iii) green-ownership. This isolates the shared-model (`FetchResponse`)
  blast radius and the non-ASCII/invalid-byte accounting tests from the per-dimension caps and keeps
  each impl task within the 2-hour/<5-function envelope.
  The **request-amplification bound** (§H7 item 4 — the fetch-attempt/frontier cap
  `MAX_FETCH_ATTEMPTS = 4000` in `fetch/crawl.py` covering the print-page / duplicate / out-of-scope
  non-counting branches, plus the `FetchRequest.depth` upper bound `MAX_DEPTH_LIMIT = 64` in
  `app_models.py`) is a distinct request-COUNT dimension (not byte VOLUME) delivered by harness
  `064.025-T` + impl `064.026-T` (`fetch/crawl.py` / `app_models.py`, cycle-8 split — see
  `## Plan Review Remediation` cycle-8). It is split from `064.013-T` (pinned to `app_models.py`
  `max_pages` + `fetch/http.py` byte cap = 2 files) because the fetch-attempt counter lives in
  `fetch/crawl.py`, a third file, which would breach `064.013-T`'s 2-file/function envelope.
  End-to-end proof: a `tools/call` `fetch` with
  over-limit `max_pages` (rejected `-32602`), an oversized response body (aborted, including on a
  redirect), and a crawl exceeding the aggregate budget (aborted) are asserted in the MCP boundary
  harness `064.014-T`; the request-amplification depth over-limit (`-32602`) and fetch-attempt cap
  are proven at the unit level in `064.025-T` (keeping `064.014-T` within its 3-scenario budget).
  Caps are set high enough not to break legitimate CLI crawls; the existing
  fetch suite must remain green (or be deliberately updated for the new bound).

## Tasks (decomposition)

Ordered, dependency-aware, one skill domain each (width isolation), each ≤ ~2h and each test
harness task under the repository's <4-test-scenario granularity heuristic. The original single
T1 harness (handshake + discovery/parity + dispatch + four error classes + notifications + H1–H6)
carried well over four scenarios; it is split into four dependency-linked red harness tasks. The
single make-green implementation was likewise too concentrated (all four harnesses + H1–H6 in one
code task, breaching the <5-function / <3-file rule), so it is split into an adapter task (T-adapter
— `server.py` `call_tool` + `list_callable_tools`), a core transport task (T2 — `stdio.py`
dispatch/serve), and an H1/H3/H4/H5 stdio-guardrail task (T2s). The subprocess smoke test is pulled
out of the packaging task into its own predecessor harness task so packaging stays width-isolated to
the executable surface. Cycle-2 review added the **shared-fetch hardening** (§H6 SSRF-by-resolution
and §H7 resource caps): because these change shared production code (`fetch/url_policy.py`,
`fetch/http.py`, `fetch/crawl.py`, `app_models.py`) — a different code surface than the MCP
transport — each concern is its own width-isolated harness+impl pair, and the end-to-end MCP boundary
proofs live in a dedicated boundary harness. **Cycle-3 review** adds three more width-isolated
concerns without breaking the single chain: (i) an enforceable **aggregate byte-accounting** pair
(T-agg-h/T-agg-i) that retains the raw body byte count on `FetchResponse` (observability) and enforces the aggregate via a request-scoped during-read remaining-byte budget (decremented per chunk, aborting mid-read)
(split out of the per-dimension cap pair so the shared-model change and the non-ASCII/invalid-byte
tests stay bounded); (ii) a **`fetch` advertising** pair (T-desc-h/T-desc-i) correcting the shared
manifest description to HTTP(S)-only with a parity test; and (iii) a **dual-era protocol** block —
two harnesses (discovery/modern-negotiation, legacy/era-routing) and two impls (modern negotiation,
dual-era routing) implementing MCP `2026-07-28` `server/discover` + per-request `_meta` negotiation +
`-32022` alongside the retained legacy `initialize` handshake (see `## Protocol Era Model`). The
chain grows from 15 to **23** tasks in cycle-3, then to **24** in cycle-6 (the 064.024-T
ancillary-budget split), but stays strictly **linear and acyclic**.

**Milestone model (resolves red→green atomicity).** Each *harness* task's atomic milestone is
"authored and observed **red**" — harness tasks are red-only by design. Each *impl* task's atomic
milestone is "the specific scenarios it owns go **green**". Because harnesses are grouped by theme
(protocol, security gate) while impls are grouped by implementation concern (adapter, transport,
guardrails, shared-fetch), a themed harness may be greened incrementally across more than one impl
task; the impl that greens each scenario is named explicitly below. This is intentional, not a gap.

Backlog IDs are shown in brackets. All MCP-transport harness tasks author into
`tests/parity/test_mcp_stdio.py` (the subprocess smoke test lives alongside, matching the existing
`test_manifest_parity.py` pattern); shared-fetch unit harnesses author into the fetch test suite
(`tests/fetch/`). Every harness task is verified **red** before its green implementation.

1. T1 [064.001-T] — Protocol handshake + discovery/parity harness (tests domain, 3 scenarios).
   `initialize` handshake shape [green@T2]; discovery/parity — `tools/list` == callable allow-list
   via `server.list_callable_tools()` with semantic (name + normalized-schema) parity vs the
   callable-filtered `get_manifest().tools` (normalizing the `parameters`↔`inputSchema` alias, the
   §H1 `workspace_root` omission, AND the `ingest_local_dir` exclusion — not byte-for-byte)
   [adapter-level assertions green@T-adapter; transport `tools/list` green@T2]; every advertised MCP
   tool is dispatchable via `call_tool` [green@T-adapter]; `SERVER.list_tools()` asserted
   **unchanged** (full four-tool manifest, `test_manifest_parity.py` green) [green@T-adapter]; and
   the adapter invariant — the transport advertises ONLY the callable set, never `list_tools()`.
   Verify red. No dependency (first).
2. T1b [064.005-T] — Dispatch parity + CallToolResult wire-shape + error-envelope + notification
   harness (tests domain, 3 scenarios). `tools/call` fetch/process/export_schema (success AND
   failure) each return a standards-valid MCP `CallToolResult` — `result.content` is a
   `ContentBlock[]`, `success=False` → `isError=true` with sanitized error text in `content`,
   `structuredContent` mirrored when applicable (legacy-era body; the modern `resultType` wrapper is
   asserted by T-era-h2/`064.021-T`) — with fetch/process parity vs
   `execute_fetch`/`execute_process`; error envelopes as one parametrized scenario covering
   `-32700`, **`-32600` invalid request (non-object root; missing/invalid `jsonrpc`;
   missing/non-string `method`)**, `-32601`, `-32602`, `-32603`; id-less notification is silent.
   Verify red [green@T2]. Depends on T1.
3. T1c [064.006-T] — Security gates H1–H3 harness (tests domain, 3 scenarios). H1 workspace_root
   escape (`/` and `C:\\`) rejected with `-32602`, nothing written outside workspace [green@T2s];
   H2 bounded input — oversized line, deeply nested array, AND an unterminated/chunked oversized
   frame rejected with bounded memory + loop resync [green@T2]; H3 no absolute paths in envelope OR
   `isError` content [green@T2s]. Verify red. Depends on T1b.
4. T1d [064.007-T] — Security gates H4–H6(literal) harness (tests domain, 3 scenarios). H4
   unknown/unrouted tool (incl. `ingest_local_dir` if excluded, and dunders) fails closed with
   `-32602` [green@T2s]; H5 stdout carries only well-formed JSON-RPC frames across a fetch/process
   call [green@T2s]; H6 literal-IP smoke — `tools/call` fetch to `127.0.0.1` and `169.254.169.254`
   rejected end-to-end [green@T2, via the existing literal-IP guard once fetch is routed]. The §H6
   hostname-resolution end-to-end and the §H7 cap end-to-end live in the boundary harness
   T-e2e [064.014-T]. Verify red. Depends on T1c.
5. T-ssrf-h [064.010-T] — Shared-fetch SSRF connect-time resolution harness (tests domain,
   3 scenarios). Unit tests in `tests/fetch/`: (a) initial URL whose public hostname resolves to
   loopback/private is rejected; (b) a redirect target whose hostname resolves to private is
   rejected mid-chain; (c) **address-pinned connect / DNS-rebinding (parametrized)** — when
   validation-time and connect-time resolution differ, the connection uses the validated address
   (no second resolution), and any private address in the validated record set is rejected; and,
   with `HTTP(S)_PROXY` set, the fetcher does not delegate resolution to an inherited proxy (no
   proxy-side re-resolution of the hostname). Verify red
   [green@T-ssrf-i]. Depends on T1d.
6. T-ssrf-i [064.011-T] — Shared-fetch SSRF connect-time resolution impl (code domain,
   ≤2 files: `fetch/url_policy.py`, `fetch/http.py`). Resolve the host and reject if ANY resolved
   address is loopback/private/link-local/metadata; revalidate every redirect target at connect
   time (not by `netloc` compare); **connect to the specific validated IP (address-pinned),
   preserving the `Host` header / SNI, so `urllib` performs no second unvalidated resolution**, and
   **disable inherited/environment proxies** on this fetcher's opener (install `ProxyHandler({})`
   so `build_opener` does not hand the hostname to an `HTTP(S)_PROXY` proxy that re-resolves it)
   (closes DNS-rebinding). Turns T-ssrf-h green. Existing fetch suite stays green. Depends on
   T-ssrf-h.
7. T-cap-h [064.012-T] — Shared-fetch per-dimension resource-cap harness (tests domain,
   2 scenarios). Unit tests in `tests/fetch/`: (a) `FetchRequest.max_pages` above the hard cap is
   rejected at model validation; (b) per-response byte cap (parametrized: initial + redirect) — a
   body exceeding `MAX_RESPONSE_BYTES` is aborted without full buffering (streamed, not a single
   `response.read()`). The **aggregate** byte budget is a separate byte-accurate pair
   (T-agg-h/T-agg-i) so this harness stays width-isolated to the per-dimension caps. Verify red
   [green@T-cap-i]. Depends on T-ssrf-i.
8. T-cap-i [064.013-T] — Shared-fetch per-dimension resource-cap impl (code domain, ≤2 files —
   each edit minimal: `app_models.py` `max_pages` upper bound (`Field(le=…)`); `fetch/http.py`
   streamed `MAX_RESPONSE_BYTES` read (initial + redirect), replacing the unbounded
   `response.read()`). Turns T-cap-h green. The aggregate budget + raw-byte retention are a
   separate width-isolated pair (T-agg-h/T-agg-i). Existing fetch suite stays green (caps sized
   above legitimate use). Depends on T-cap-h.
9. T-agg-h [064.016-T] — Shared-fetch aggregate byte-accounting harness (tests domain,
   3 scenarios). Unit tests in `tests/fetch/` proving the aggregate cap counts **raw wire bytes**,
   not decoded characters or a re-encode: (a) a **non-ASCII multibyte** body (byte length >
   character length) accrues its raw byte length toward `MAX_TOTAL_FETCH_BYTES`; (b) an
   **invalid-byte** body (where `errors="replace"` collapses bytes to `U+FFFD`) accrues its
   original raw byte length, not the replaced-character length; (c) **parametrized during-read
   enforcement** — a request whose cumulative **raw** bytes exceed the budget is aborted even
   though the decoded character total stays under budget (undercount-bypass), covering a main-page
   response that aborts **mid-read** before full buffering, a retried over-cap attempt whose bytes
   still decrement the shared request budget, and an ancillary robots/TOC fetch decrementing the
   same budget. Verify red [green@T-agg-i]. Depends on T-cap-i.
10. T-agg-i [064.017-T] — Raw-byte retention + byte-accurate aggregate accounting impl, **core**
   (code domain, ≤2 files: `fetch/http.py`, `fetch/crawl.py`). Add `FetchResponse.body_byte_count: int`
   set from the length of the bytes read by the bounded reader **before decoding** (the
   `body_bytes` already materialized at the streamed read) for per-response accounting; and enforce
   `MAX_TOTAL_FETCH_BYTES` (512 MiB / `536_870_912` bytes, see §H7 Selected numeric limits) via a
   **request-scoped remaining-byte budget threaded into `fetch_page`
   and its bounded reader, decremented per chunk while bytes are read** and aborting the read
   mid-stream once the remaining allowance would be exceeded — NOT a post-return `crawl.py`
   accumulator (which cannot see the crossing response before it is fully read, nor bytes from
   over-cap attempts retried by `_fetch_with_retries`). `crawl.py` seeds one budget per request and
   threads it through the **main-page and retry** `fetch_page` calls (the ancillary robots/TOC
   threading is split to successor `064.024-T`). The typed
   `AggregateBudgetExceededError` (a `DoclineError` subclass) MUST be re-raised at the **two core**
   `crawl.py` broad-handler sites (`crawl()` main loop, `_fetch_with_retries`) via
   `except AggregateBudgetExceededError: raise` before each
   `except (DoclineError, OSError)` (mirroring the existing `except CrawlUrlRejectedError: raise`), so
   `crawl()` RAISES rather than recording a per-page skip. `FetchResponse.body_byte_count` carries a
   default (`= 0`, or is placed before the defaulted `redirect_count`) so the frozen dataclass and
   existing constructors stay valid. The budget defaults to unbounded for standalone single fetch.
   Isolated from T-cap-i so the shared-model (`FetchResponse`) blast radius and the byte-accurate
   during-read accounting land in one bounded task. **Split executed (cycle-6, PR #166 review):** the
   ancillary (`_robots_allow`/`_discover_toc_links`) accrual + their two re-raise clauses are peeled
   to successor `064.024-T` (T-agg-aux) because 064.017-T already touches three functions
   (`fetch_page`, `crawl`, `_fetch_with_retries`) before any ancillary work — folding the two
   ancillary functions in would breach the <5-function envelope. This keeps 064.017-T at 3 functions
   + 2 small classes + 1 additive field. Greens `064.016-T` scenarios (a), (b), (c)(i), (c)(ii).
   Existing fetch suite stays green. Depends on T-agg-h.
10b. T-agg-aux [064.024-T] — Aggregate budget on the **ancillary** robots/TOC fetch vector (code
   domain, ≤1 file: `fetch/crawl.py`). Extends the request-scoped budget seeded by T-agg-i into the
   `_robots_allow` and `_discover_toc_links` `fetch_page` calls so ancillary `robots.txt`/mdBook-TOC
   transfer decrements the SAME budget while bytes are read, and adds the two remaining
   `except AggregateBudgetExceededError: raise` clauses (before the `_robots_allow` ~line 406 and
   `_discover_toc_links` ~line 465 broad handlers; `_robots_allow` has no prior re-raise clause).
   Takes over green-ownership of `064.016-T` scenario (c)(iii) (ancillary-fetch accrual; `crawl()`
   RAISES). 2 functions touched, single file — within the 2-hour/<5-function envelope. Turns the
   ancillary sub-vector of T-agg-h green. Existing fetch suite stays green. Depends on T-agg-i.
10c. T-amp-h [064.025-T] — Shared-fetch request-amplification harness (tests domain, 2 scenarios).
   Author the failing harness for the request-COUNT bound (§H7 item 4): (1) a branch-accurate fake
   transport drives `crawl()` to RAISE a typed error once total frontier pops reach
   `MAX_FETCH_ATTEMPTS = 4000` while `page_count` stays below `max_pages`, asserting the counter
   increments in EACH non-counting branch — **print** (each print response naturally enqueues a
   fresh in-scope link, a self-sustaining frontier), **duplicate** (an emitted page preloads many
   distinct alias request URLs that each redirect to an already-emitted final URL → `final_key in
   emitted_urls`), and **out-of-scope** (an emitted page preloads many distinct in-scope request
   URLs that each redirect to an out-of-section final URL → `not _url_within_section_scope`); only
   the print branch enqueues links, so duplicate/out-of-scope pops are seeded from the emitted
   page's preloaded frontier, not by those branches enqueuing; (2) `FetchRequest.depth >=
   MAX_DEPTH_LIMIT + 1` (`>= 65`) is rejected at model validation (`-32602`), AND a request OMITTING
   `depth` still validates (defaults to 0). This is a distinct dimension from the byte caps
   (T-cap/T-agg), so it stays
   width-isolated. Verify red [green@T-amp-i]. Depends on T-agg-aux.
10d. T-amp-i [064.026-T] — Crawl fetch-attempt + depth amplification-bound impl (code domain, ≤2
   files: `fetch/crawl.py` + `app_models.py`). (a) `fetch/crawl.py` adds a per-request
   `fetch_attempts` counter incremented on EVERY frontier pop (extend the loop guard to
   `while frontier and page_count < crawl_config.max_pages and fetch_attempts < MAX_FETCH_ATTEMPTS`,
   or pre-fetch increment + abort) so the print-page / duplicate / out-of-scope branches count, and
   RAISES a typed `DoclineError` subclass at the cap; (b) `app_models.py` bounds
   `FetchRequest.depth` with `Field(default=0, ge=0, le=64)` (`MAX_DEPTH_LIMIT`; the `default=0` is
   preserved so `depth` stays optional). Split out of T-cap-i
   (064.013-T, pinned to `app_models.py` + `fetch/http.py`) because the counter lives in
   `fetch/crawl.py`, a third file. Turns T-amp-h green. Existing fetch suite stays green (bounds
   sized 4× the page cap / 64-deep). Depends on T-amp-h.
11. T-e2e [064.014-T] — MCP untrusted-fetch end-to-end boundary harness (tests domain,
    3 scenarios). Through `tools/call` fetch (stdin JSON → dispatch → `server.fetch` →
    `execute_fetch`): (a) a public hostname resolving to loopback/private is rejected end-to-end
    (§H6); (b) an over-limit `max_pages` (`>= 1001`) is rejected `-32602` end-to-end (§H7); (c) an
    oversized response (per-response `MAX_RESPONSE_BYTES` = 10 MiB cap incl. redirect) OR a crawl
    exceeding the aggregate `MAX_TOTAL_FETCH_BYTES` = 512 MiB budget is aborted
    end-to-end (§H7). Authored red (no dispatch loop yet). The shared-fetch guards (T-ssrf-i,
    T-cap-i, T-agg-i, T-agg-aux, T-amp-i) already enforce in `execute_fetch`, so once the dispatch loop routes
    `server.fetch` these all go green at **T2** — no separate boundary wiring is required. The
    request-amplification bound (§H7 item 4) is proven at the unit level in T-amp-h, keeping this
    harness within its 3-scenario budget. Depends
    on T-amp-i (the full aggregate budget plus the request-amplification bound are in place).
12. T-adapter [064.015-T] — Adapter callable surface + identity accessor (code domain, ≤2 files:
    `src/docline/mcp/server.py` + optionally a versions constant).
    Implement `DoclineMcpServer.call_tool(name, arguments)` (static `{name: adapter_callable}`
    allow-list of uniform `(arguments: dict)` adapters — the `fetch`/`process` adapters build their
    request model from `arguments`, the `export_schema` adapter accepts only an empty dict — never a
    raw `bound_method(arguments)` call that would `TypeError` on `export_schema`, and no `getattr`),
    the NEW `DoclineMcpServer.list_callable_tools()` (callable
    allow-list manifest; `ingest_local_dir` excluded; `process` `inputSchema` omits `workspace_root`,
    built at build time), and the NEW `DoclineMcpServer.describe_server()` — the SINGLE
    identity/version/capability accessor (serverInfo, capabilities, supported protocol-version
    constant list for both eras). `list_tools()` is left **unchanged**; document the adapter
    invariants that `list_tools()` is the manifest-parity accessor only, `list_callable_tools()` is
    the sole MCP advertise source, and `describe_server()` is the sole identity/version source.
    Introducing `describe_server()` HERE (the designated adapter single-source task) means the
    legacy `initialize` (T2) consumes it from first implementation and never hardcodes identity
    literals in the transport — keeping the "identity lives in ONE adapter accessor / transport is a
    pure translator" invariant true at every commit (cycle-3 architecture remediation). `describe_server()`
    is data-only here; `server/discover` dispatch is wired later by T-era-i1. Greens the
    adapter-level assertions in T1. Depends on T-e2e (last shared-fetch harness authored first).
    Split from T2 so the transport task stays at ≤4 functions.
13. T-desc-h [064.018-T] — `fetch` advertising parity harness (tests domain, 2 scenarios). Author
    the failing parity test in `tests/parity/`: (a) the advertised `fetch` tool description
    (located by name as the existing manifest tests do —
    `next(t for t in get_mcp_manifest().tools if t.name == "fetch").description`, NOT
    `tools["fetch"]` which raises `TypeError` because `.tools` is a `list[ManifestTool]`; reached
    via BOTH `list_tools()` and `list_callable_tools()`) states HTTP(S)-only and does **not** claim
    "file path" / local-file support; (b) manifest⇄behavior parity — the advertised input contract
    matches `execute_fetch`'s scheme rejection (`execute_fetch` fails any non-`http`/`https`
    source), so the advertisement cannot promise an input mode the executor rejects. Verify red
    [green@T-desc-i]. Depends on T-adapter.
14. T-desc-i [064.019-T] — `fetch` advertising correction impl (code domain, 1 file:
    `src/docline/app.py`). Correct the shared `fetch` description literal in `get_manifest()`
    (`app.py:465-468`) — the single shared string `get_mcp_manifest()` re-exposes to the MCP surface
    (aligning with the corrected 064.019-T task) — to state HTTP(S)-only (e.g. "Fetch a document from an HTTP(S) URL and stage
    it for processing."), fixing the advertisement on BOTH the CLI `--manifest` and the MCP
    `tools/list` surfaces. (`server/discover` carries no individual tool descriptions — only
    versions/capabilities/identity/cache metadata — so it is not a description surface.) No
    processing behavior change. Turns T-desc-h green. Depends on T-desc-h.
15. T2 [064.002-T] — Core stdio transport loop, **legacy-era base** (code domain, ≤2 files:
    `src/docline/mcp/stdio.py` + entry wiring). Implement `dispatch` + `serve`, request-shape
    validation returning **`-32600`**, the bounded binary frame read/drain helper AND its runtime
    enforcement (§H2), the legacy-era method map (`initialize` → capabilities + `2025-11-25` +
    serverInfo **sourced from the adapter `describe_server()` accessor (T-adapter), not hardcoded in
    `stdio.py`**; `notifications/initialized` silent; `ping` → `{}`; `tools/list` via
    `server.list_callable_tools()`; `tools/call` via `server.call_tool`), id-less notification, and
    `success=False` → `isError` mapping. Greens the legacy T1 transport assertions, T1b, the H2
    scenario in T1c, the H6-literal scenario in T1d, and **all of T-e2e** (the shared-fetch guards
    enforce automatically once fetch is routed). The **modern** era (`server/discover`, per-request
    `_meta` negotiation, `-32022`, `resultType`) is layered by the dual-era tasks (T-era-i1/i2).
    Depends on T-desc-i. The remaining stdio runtime guardrails (H1/H3/H4/H5) are delivered by T2s.
16. T2s [064.009-T] — Stdio runtime guardrails H1/H3/H4/H5 (code domain). Implement the
    `workspace_root` dispatcher-level runtime reject (`-32602`) per §H1 (the build-time `inputSchema`
    omission is delivered by T-adapter; `extra="forbid"` does not catch a real model field, so an
    explicit pre-construction reject is required); generic non-reflective error text on envelope AND
    `isError` (§H3); fail-closed unknown tools (§H4); child-stdout redirect (§H5). Greens the H1/H3
    scenarios in T1c and the H4/H5 scenarios in T1d. **No fetch-guard wiring** — the §H6/§H7 guards
    live in the shared fetch call path and enforce automatically (greened at T2). Split from T2 so
    neither task breaches the 2-hour/<5-function rule. Depends on T2.
17. T-era-h1 [064.020-T] — Dual-era discovery + modern-negotiation harness (tests domain,
    3 scenarios). Author failing tests in `tests/parity/test_mcp_stdio.py`: (a) `server/discover`
    (answerable with no prior `initialize`) returns a `DiscoverResult` — `supportedVersions`
    (both eras), `capabilities`, serverInfo in `_meta`, `resultType:"complete"`, AND `ttlMs` +
    `cacheScope` (`DiscoverResult` is a `CacheableResult`); (b) a well-formed modern request whose
    `_meta` carries BOTH `io.modelcontextprotocol/protocolVersion` = `2026-07-28` AND
    `io.modelcontextprotocol/clientCapabilities` is served statelessly (no handshake) and the
    result carries `resultType:"complete"` + serverInfo `_meta` (list results also
    `ttlMs`/`cacheScope`); (c) **parametrized modern-metadata rejection** — an unsupported `_meta`
    protocolVersion returns **`-32022`** with `data.supported` (list) + `data.requested`, and a
    request with missing/malformed `clientCapabilities` returns **`-32602`** (checked after version
    acceptance, so version negotiation takes precedence). Verify
    red [green@T-era-i1]. Depends on T2s.
18. T-era-h2 [064.021-T] — Legacy-era retention + era-routing harness (tests domain, 3 scenarios).
    Author failing tests: (a) **legacy-only regression anchor (green at authoring** from T2 +
    T-adapter) — the legacy `initialize` handshake still returns capabilities + `2025-11-25` +
    serverInfo, `notifications/initialized` is silent, `ping` → `{}`. This anchor asserts ONLY the
    legacy handshake surface (no cross-era comparison), so it cannot be "already green" while
    depending on an unbuilt `server/discover`; the initialize-vs-discover no-drift equality is NOT
    part of it and lives in (b); (b) **era routing + no-drift (genuinely red** until T-era-i1
    discovery + T-era-i2 legacy branch) — a `tools/call` carrying modern `_meta` is served under
    modern semantics with no prior `initialize`, while the same method after `initialize` is served
    under legacy semantics, AND a metadata-free operation (`tools/call`/`tools/list` with no
    `_meta`) received **before** any `initialize` is **rejected** — never served as legacy — proving
    the process era is latched by `initialize`, not selected by an unadorned request shape (the
    **pre-initialize operation test**), AND `initialize` and `server/discover` report the **same**
    identity/capabilities/supportedVersions from the single `describe_server()` source; (c)
    **modern-path guardrail parity + CallToolResult wire shape (parametrized)** — a modern (`_meta`,
    no `initialize`) `tools/call` (`fetch`/`process`/`export_schema`) enforces §H1 (`workspace_root`
    reject `-32602`), §H3 (absolute-path sanitization in `isError`), and §H5 (clean stdout)
    IDENTICALLY to the legacy path, AND every successful modern `tools/call` wraps a standards-valid
    `CallToolResult` (`result.content` is a `ContentBlock[]`; `structuredContent` mirrored when
    applicable; `fetch`/`process` failure → `isError=true`; `export_schema` non-empty args → `-32602`,
    not `isError`) inside the `resultType:"complete"` envelope — the SAME body `064.005-T` asserts,
    differing only by the modern wrapper — proving the guards apply pre-handshake, era routing cannot
    branch around them, and the modern era emits a standards-conformant wire shape. Verify
    red [green@T-era-i2, wire-shape + guard parity green@T-era-i1]. Depends on T-era-h1.
19. T-era-i1 [064.022-T] — Modern-era negotiation + modern-branch routing impl (code domain,
    ≤2 files: `src/docline/mcp/stdio.py` + `src/docline/mcp/server.py`).
    Implement `server/discover` dispatch backed by the `describe_server()` accessor **introduced by
    T-adapter (consume, do not re-introduce)** (supportedVersions, capabilities, serverInfo);
    per-request `_meta` extraction + validation of BOTH `protocolVersion` (unsupported → `-32022`)
    AND `clientCapabilities` (missing/malformed → `-32602`, checked after version); the
    `-32022 UnsupportedProtocolVersionError` envelope (`data.supported` + `data.requested`); the
    modern result shape (`resultType:"complete"`, serverInfo `_meta`, list `ttlMs`/`cacheScope`,
    and `ttlMs`/`cacheScope` on the `DiscoverResult` itself as a `CacheableResult`);
    and **the MODERN branch of the era classifier** (detect modern `_meta` → route to modern
    handlers, served statelessly) **funnelled through the SAME hardened dispatch** as legacy so
    §H1/§H3/§H4/§H5 apply by construction, **reusing dispatch()'s inline CallToolResult shaping** and
    applying the modern envelope as a post-return wrapper only (so the modern era emits the SAME
    standards-valid `CallToolResult` body as legacy).
    Ownership boundary (cycle-3, refined cycle-4): THIS task owns the modern branch routed through
    the shared hardened dispatch — so T-era-h1 scenario (b) "modern request served statelessly"
    AND T-era-h2 scenario (c) modern-path guard parity + CallToolResult wire shape both green HERE —
    while T-era-i2 owns the
    legacy branch + no-drift VERIFICATION (it verifies parity, not first-wires it). Function/split
    guard: if the dual-member `_meta` validator + modern result-shape wrapper exceed the
    2-hour/<5-function envelope, split the result-shape wrapper to a successor before implementing.
    Turns T-era-h1 green. Depends on T-era-h2 (last dual-era harness authored first).
20. T-era-i2 [064.023-T] — Dual-era routing completion + legacy retention + guard-parity **verify**
    (code domain, ≤2 files: `src/docline/mcp/stdio.py` + `src/docline/mcp/server.py`). Implement the
    **LEGACY branch** of the request-shape era classifier — an `initialize` request **latches a
    per-process legacy-era selection** (`initialize` → legacy); metadata-free operations
    (`tools/call`/`tools/list` with no `_meta`) received **before** that selection are **rejected**,
    never served as legacy — on top of
    T-era-i1's modern branch, keep the legacy handshake/`ping` path (from T2) intact, and verify no
    drift — both `initialize` and `server/discover` read the single `describe_server()` accessor
    (from T-adapter), so no-drift holds by construction. **Guardrail parity (blocking, VERIFY not
    wire):** T-era-i1 already funnels the modern branch through the SAME hardened dispatch so
    §H1/§H3/§H4/§H5 apply by construction; this task VERIFIES both eras share that one path and does
    not regress it (the era classifier changes only negotiation + envelope shape, never which guards
    run). Greens the T-era-h2 legacy-retention + era-routing scenarios; the modern-path guard-parity
    scenario already greened at T-era-i1 and must stay green. Depends on T-era-i1.
21. T2b [064.008-T] — Subprocess smoke-test harness for the entry point (tests domain, 1 scenario).
    Author the failing automated subprocess test (matching `test_manifest_parity.py::`
    `test_python_m_docline_cli_runs_main`) that launches `python -m docline.mcp` / `docline-mcp` via
    `subprocess.Popen` with stdin AND stdout as pipes and keeps stdin OPEN across frames: it sends
    and FLUSHES one frame (the modern `server/discover` probe, or the legacy `initialize`), REQUIRES
    and reads that response BEFORE sending the next frame (`tools/list`), reads the `tools/list`
    response, and only THEN closes stdin (EOF) and awaits a clean exit. This interactive
    send→flush→require-response→send-next sequence DETECTS a live stdio deadlock (a greedy/buffered
    server read waiting for a full `CHUNK_SIZE`, or a block-buffered unflushed stdout) that an
    EOF-first "write everything then read" test masks; each response read is timeout-bounded so a
    deadlock FAILS deterministically rather than hanging the suite. Asserts clean exit + tool names
    matching the advertised MCP tool set (`docline --manifest` minus the excluded `ingest_local_dir`).
    Its PASS depends on serve() (T2) reading non-greedily (`read1`/`os.read`) and flushing stdout
    after every response (cycle-8). Red until
    the entry point exists [green@T3]. Depends on T-era-i2 (the fully hardened dual-era server ships
    in the executable).
22. T3 [064.003-T] — `docline-mcp` entry point + module bootstrap (packaging surface only —
    width-isolated). Add `src/docline/mcp/__main__.py` (`main()` reusing `DoclineMcpServer` + `serve`)
    and the `[project.scripts]` `docline-mcp` entry (materializes `docline-mcp.exe` on Windows),
    turning the T2b subprocess harness green. No test-infra authoring in this task. Depends on T2b.
23. T4 [064.004-T] — Documentation (docs domain). README "Running the local stdio MCP server"
    section and a SELF-CONTAINED client MCP configuration example for `docline-mcp` in the
    documented GitHub Copilot / VS Code `.vscode/mcp.json` `servers` stdio format (`type`/`command`/
    `args`; a verifiable shape, NOT the repo's git-ignored `.mcp.json`), noting dual-era support
    (modern `server/discover` probe + legacy `initialize` fallback). Do NOT add a separate
    design-doc transport note — the deliberation already documents the transport surface (avoid
    duplication). Depends on T3.

Dependency edges: T1b→T1, T1c→T1b, T1d→T1c, T-ssrf-h→T1d, T-ssrf-i→T-ssrf-h, T-cap-h→T-ssrf-i,
T-cap-i→T-cap-h, T-agg-h→T-cap-i, T-agg-i→T-agg-h, T-agg-aux→T-agg-i, T-amp-h→T-agg-aux,
T-amp-i→T-amp-h, T-e2e→T-amp-i, T-adapter→T-e2e,
T-desc-h→T-adapter, T-desc-i→T-desc-h, T2→T-desc-i, T2s→T2, T-era-h1→T2s, T-era-h2→T-era-h1,
T-era-i1→T-era-h2, T-era-i2→T-era-i1, T2b→T-era-i2, T3→T2b, T4→T3.
Execution order: 064.001 → 064.005 → 064.006 → 064.007 → 064.010 → 064.011 → 064.012 → 064.013 →
064.016 → 064.017 → 064.024 → 064.025 → 064.026 → 064.014 → 064.015 → 064.018 → 064.019 → 064.002 → 064.009 → 064.020 →
064.021 → 064.022 → 064.023 → 064.008 → 064.003 → 064.004.

## Verification

- `pytest tests/parity` green: the new stdio suite (incl. H1–H6/H7 gates and the `-32600`
  request-shape cases) passes. The existing adapter/transport parity suites stay green **because
  `SERVER.list_tools()` is left unchanged (full four-tool manifest)**; the MCP surface uses the
  new `list_callable_tools()`, so `test_manifest_parity.py::test_mcp_server_list_tools_exposes_shared_manifest`
  needs no edit. No existing parity test is rewritten to accommodate the callable subset.
- `pytest tests/fetch` green: the shared-fetch SSRF-by-resolution, per-dimension resource-cap, and
  **byte-accurate aggregate accounting** unit harnesses pass — including the non-ASCII multibyte
  and invalid-byte payloads proving the aggregate cap counts raw wire bytes via the request-scoped
  during-read remaining-byte budget
  (not decoded characters, and not a post-return `body_byte_count` sum) — and the pre-existing fetch suite remains green under the new bounds
  (caps sized above legitimate use).
- Dual-era protocol conformance (T-era-h1/h2 → T-era-i1/i2): `server/discover` returns a
  `DiscoverResult` (supportedVersions for both eras, capabilities, serverInfo, `resultType`, and
  `ttlMs`/`cacheScope` as a `CacheableResult`); a modern request carrying a supported `_meta`
  protocolVersion AND `clientCapabilities` is served statelessly; an unsupported `_meta`
  protocolVersion returns **`-32022`** with `data.supported`+`data.requested`, and missing/malformed
  `clientCapabilities` returns **`-32602`** (checked after version); the legacy `initialize` handshake
  still works and reports the
  same identity/capabilities as `server/discover` (single-source `describe_server()`); era routing
  serves modern `_meta` requests statelessly and `initialize` requests under legacy semantics; and a
  metadata-free operation arriving before any `initialize` is rejected rather than served as legacy
  (the pre-initialize operation test), so the process era is latched by `initialize` alone.
- **Dual-era guardrail parity (T-era-h2 → T-era-i1 funnel, verified at T-era-i2):** a modern
  (`_meta`, no `initialize`)
  `tools/call` `process` with `workspace_root` is rejected `-32602` (§H1), modern-path `isError`
  content sanitizes absolute paths (§H3), and modern-path stdout stays clean (§H5) — identically to
  the legacy path — proving both eras funnel through ONE hardened dispatch and the modern
  pre-handshake surface cannot bypass a guard.
- `fetch` advertising parity (T-desc-h → T-desc-i): the advertised `fetch` description states
  HTTP(S)-only across `tools/list` and `docline --manifest` (located by name, not by subscript),
  and matches `execute_fetch`'s rejection of non-HTTP(S) sources (no "file path" advertisement).
  `server/discover` is not a description surface (it carries versions/capabilities/identity/cache
  metadata only), so it is excluded from this assertion.
- JSON-RPC 2.0 conformance: `-32600` returned for a non-object root, a missing/invalid `jsonrpc`,
  and a missing/non-string `method` (parametrized), distinct from `-32700` and `-32601`.
- MCP boundary end-to-end (T-e2e [064.014-T]): a `tools/call` fetch to a hostname resolving to
  loopback/private is rejected (address-pinned connect closes DNS-rebinding); over-limit
  `max_pages` is rejected `-32602`; an oversized response (per-response cap incl. redirect) or a
  crawl exceeding the aggregate `MAX_TOTAL_FETCH_BYTES` budget is aborted (the crawl RAISES the
  typed budget error out of `crawl()`, not recorded as a per-page skip). These green at T2 (the
  shared-fetch guards enforce via `execute_fetch`; no separate boundary wiring).
- `ruff check .`, `ruff format --check .`, `pyright src/` clean.
- Automated subprocess smoke (authored red in T2b [064.008-T], turned green by the T3 [064.003-T]
  entry point) replaces manual verification: `docline-mcp` handling an INTERACTIVE `server/discover`
  probe (or legacy `initialize`) — one frame sent and flushed, its response required BEFORE the next
  `tools/list` frame with stdin still open, then EOF — so a live stdio deadlock is detected, tool
  names matching the advertised MCP tool set
  (`docline --manifest` minus the excluded `ingest_local_dir`).

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
  error codes originally aligned to the tested set (with `-32600` deferred) — **`-32600` was
  restored in cycle-2 for JSON-RPC 2.0 conformance; see the cycle-2 subsection below**; T4
  design-doc note removed (folded into deliberation); manual smoke automated.
- Arch P3 — `serve()` defaults `server` to the `SERVER` singleton (single construction path).

Re-review verdict (attempt 2): Architecture ADVISORY, Scope ADVISORY, **Security PASS** — P0
gated by §H1 as a blocking acceptance criterion; H2–H6 convert remaining findings into
test-first gates. Two P3 advisories from the re-review folded in: §H3 extended to cover
`isError` tool-result content; §H6 negative test drives through the `tools/call` boundary.
Plan gate cleared — ready for harvest.

### Post-harvest consistency remediation (PR #166 Copilot review)

Adversarial review of the staged artifacts surfaced four durable-consistency defects, now
corrected:

- **§H1 single behavior + schema omission** — H1 previously offered "strip/ignore OR validate",
  which both under-specified the behavior and contradicted the blocking rejection test. Resolved
  to one behavior: the MCP boundary **rejects** a client-supplied `workspace_root` (`-32602`) and
  **omits** the field from the advertised `process` `inputSchema`. The parity exception is
  documented inline (§H1 parity-exception note) so `tools/list` stays in semantic parity without
  advertising an unsupported security-sensitive parameter.
- **§H2 bounded read (not post-read check)** — a post-read size check on an unbounded `readline()`
  buffers an arbitrarily large or unterminated frame before the check runs. Resolved to a bounded
  binary chunk-read up to `MAX_FRAME_BYTES` with bounded draining of the oversized remainder; the
  H2 harness adds an unterminated/chunked oversized acceptance test proving memory stays bounded
  while awaiting the newline.
- **Deliberation semantic-parity alignment** — the source deliberation still mandated byte-for-byte
  `tools/list` parity; updated to the reviewed semantic-parity rule so both durable artifacts agree
  and T1 has one consistent acceptance criterion.
- **Task-granularity + width-isolation** — the single T1 harness exceeded the <4-scenario
  heuristic; split into four dependency-linked red harness tasks (064.001/064.005/064.006/064.007).
  The subprocess smoke test moved out of the T3 packaging task into a dedicated predecessor harness
  task (064.008) so T3 stays width-isolated to the executable packaging surface.

Attempt-3 adversarial re-review (post-remediation) surfaced three further items, now also closed:

- **Implementation-task concentration (Scope)** — the single make-green task (064.002) concentrated
  all four harnesses' green work plus H1–H6 (~3 files / >5 functions), asymmetric to the four-way
  harness split and at risk of breaching the 2-hour/<5-function rule. Split into a **core** dispatch
  task (064.002 — protocol/dispatch/error/notification) and an **H1–H6 security-hardening** task
  (064.009), preserving one skill domain and bounded scope per task. *(Cycle-2b re-scoped these
  further: adapter surface extracted to 064.015, and 064.009 narrowed to H1/H3/H4/H5 stdio
  guardrails — see the Cycle-2b subsection.)*
- **`ingest_local_dir` reconcile (Security + Consistency)** — the "advertised set == callable set"
  note left an open either/or (route vs filter). Routing it unguarded would reintroduce an
  unbounded local-FS read surface analogous to the §H1 P0, and filtering it silently contradicted
  the manifest-set parity claim. Resolved: **exclude `ingest_local_dir` from the MCP `tools/list`
  as the default-safe posture** (documented as a second sanctioned parity divergence alongside the
  `workspace_root` omission), with a **blocking constraint** that if it is ever routed instead, its
  `source_path`/`output`/`staging_dir` MUST be workspace-contained per §H1.
- **Residual scope wording** — Scope in-scope item 4 dropped the stale "design-doc note" so it
  agrees with the T4 task and the earlier scope trim.

Re-review verdict (attempt 3): consistency defects closed; implementation-task granularity and the
`ingest_local_dir` trust boundary resolved; Architecture ADVISORY, Scope ADVISORY, **Security PASS**
retained. Plan and backlog now agree on scope, granularity, parity semantics, and the H1/H2
guardrail contracts.

### Cycle-2 review remediation (PR #166 Copilot review on HEAD 6832bb9)

A second Copilot review on HEAD `6832bb9` raised six unresolved threads plus two suppressed
consistency comments. All treated as valid and closed here (planning/backlog/memory artifacts only —
no production/test code touched by Stage):

- **§H6 SSRF by DNS resolution (P0)** — the guard rejected only literal private hosts and did not
  resolve names (`fetch/url_policy.py:50-56`) before `urllib` connects (`fetch/http.py:116-123`), so
  a public hostname resolving to loopback/private bypassed it on the new untrusted surface. §H6 now
  **requires resolution/connect-time validation for the initial URL and every redirect** (reject if
  any resolved A/AAAA address is loopback/private/link-local/metadata) plus an end-to-end
  hostname-to-private MCP fetch test. Decomposed into width-isolated shared-fetch tasks
  064.010-T (harness) + 064.011-T (impl), with the boundary proof in 064.014-T.
- **§H7 fetch resource exhaustion (P1)** — `max_pages` had no upper bound (`app_models.py:25`) and
  responses were buffered with an unbounded `response.read()` (`fetch/http.py:123`). New §H7 adds an
  MCP-side page/work cap (hard `max_pages` upper bound → `-32602`) and a **streamed
  `MAX_RESPONSE_BYTES` cap on the initial response and every redirect hop**. Shared-fetch code IS
  hardened (both interfaces); represented as tasks 064.012-T (harness) + 064.013-T (impl) and in
  Rollback/Risks; boundary proof in 064.014-T.
- **`-32600` restored (JSON-RPC conformance)** — dropping `-32600` made the advertised JSON-RPC 2.0
  surface non-compliant. `dispatch` now validates request shape and returns **Invalid Request
  `-32600`** for a non-object root, a missing/invalid `jsonrpc`, or a missing/non-string `method`,
  distinct from `-32700`/`-32601`. Covered by a bounded parametrized harness in 064.005-T and
  implemented in 064.002-T.
- **Parity-method contract (suppressed #1)** — `SERVER.list_tools()` stays **unchanged** (full
  four-tool manifest; `test_manifest_parity.py:111-117` stays green) and a **new
  `list_callable_tools()`** backs the MCP `tools/list` (three callable tools, `workspace_root`
  omitted). This makes the "existing suite unchanged AND MCP list filtered" acceptance criterion
  implementable. Reflected in 064.001-T (parity) and 064.002-T (impl).
- **Memory continuity (suppressed #2 + threads on memory.md / memories.json)** — the durable
  session memory and `.backlogit/memories.json` still recorded the superseded four-task chain and
  the ambiguous `pin/strip` behavior. Both updated to the exact execution order, the
  reject-only `workspace_root` behavior, the MCP `process` schema omission, and server-root pinning.
- **Rollback/blast-radius accuracy** — the "purely additive" claim was false. Rollback and Risks now
  enumerate the existing-file changes: the `DoclineMcpServer` adapter (new `call_tool` /
  `list_callable_tools` in `src/docline/mcp/server.py`) and the shared-fetch hardening
  (`url_policy.py`, `http.py`, `app_models.py`, `crawl.py`) that affects the CLI as well.

Shipment 055-S membership and dependency edges were updated for the new tasks, preserving a
single linear, acyclic, test-first chain and 2-hour/width-isolation limits.

Re-review verdict (cycle-2, post-remediation): the SSRF-by-resolution contract, resource caps,
restored `-32600`, parity-method split, and cross-interface blast radius are consistently recorded
across plan, backlog, and memory.

### Cycle-2b multi-persona re-review remediation

A multi-persona adversarial re-review (Consistency, Security, Architecture, Scope) of the cycle-2
edits surfaced one P1 and several P2s, all now closed:

- **Feature DoD stale (Consistency P1)** — 064-F's DoD still said "H1–H6 … SSRF re-verification",
  omitting §H7 caps and the upgraded §H6 SSRF-by-resolution. Updated to H1–H7 with the caps and
  resolution behavior enumerated.
- **DNS-rebinding bypass (Security P2)** — a resolve-then-let-`urllib`-re-resolve design is a
  *deterministic* rebinding bypass on a fully untrusted surface. **Address-pinned connect** (connect
  to the validated IP, preserve `Host`/SNI) is elevated from a deferred Risk to an in-scope §H6 /
  064.011-T acceptance criterion, with a rebinding scenario in 064.010-T.
- **No aggregate resource budget (Security P2)** — per-response and per-page caps did not bound
  their product (each page staged to disk). Added a hard **aggregate `MAX_TOTAL_FETCH_BYTES`** crawl
  budget (§H7) enforced in `fetch/crawl.py`, delivered by 064.013-T and asserted in 064.012-T/064.014-T.
- **Dual-list footgun + adapter concentration (Architecture P2 / Scope P2)** — keeping
  `list_tools()` full-manifest while adding `list_callable_tools()` risked a caller sourcing the MCP
  advertise set from the unguarded `list_tools()`, and left 064.002 at ~5 functions across two
  modules. Extracted the adapter surface (`call_tool` + `list_callable_tools`) into a dedicated
  task **064.015-T** (`server.py`) with a documented invariant that `list_tools()` is the
  manifest-parity accessor ONLY and `list_callable_tools()` is the sole MCP advertise source; 064.002
  is now transport-only (≤4 functions).
- **Fuzzy 002/009 partition + non-atomic 064.014 (Architecture P2)** — the §H6/§H7 shared-fetch
  guards enforce automatically in the shared fetch call path (`execute_fetch`), so 064.009 does **no**
  fetch-guard wiring and is narrowed to H1/H3/H4/H5; 064.014's boundary scenarios green at **T2**
  (single milestone) once the dispatch loop routes `server.fetch`. Added an explicit **milestone
  model** (harness = red-only; each impl greens a named scenario set) to make incremental greening
  legible. H2 runtime enforcement moved to 064.002 to sit with its bounded-read helper.
- **Scope-label + narrative consistency (Consistency P2)** — 064.009 relabeled to "stdio runtime
  guardrails H1/H3/H4/H5" across plan/task/memory; the memory "Next steps" narrative now includes
  064.008; Rollback names `src/docline/mcp/server.py` (the actual adapter file) instead of `app.py`.

Re-review verdict (cycle-2b): P1/P2 findings remediated. Plan, backlog (15-task chain), and memory
agree on the adapter/transport/guardrail partition, the address-pinned SSRF contract, the aggregate
resource budget, and the milestone model.

### Cycle-3 review remediation (PR #166 review cycle 3)

A third Copilot review on PR #166 raised four unresolved threads. All treated as valid and closed
here (planning/backlog/memory artifacts only — Stage touches no production/test code). Each is
grounded in verified evidence, not the review assertion alone.

- **Aggregate transfer-byte accounting not enforceable (Security P1)** — the aggregate
  `MAX_TOTAL_FETCH_BYTES` budget is defined in bytes, but `crawl.py` receives only
  `FetchResponse.body: str`; the raw byte count is discarded when `fetch_page` decodes
  (`fetch/http.py:123-125`, `body_bytes.decode(charset, errors="replace")`). Summing characters or
  a re-encode under-counts non-ASCII and `errors="replace"` invalid-byte bodies, so a hostile
  server can exceed the real byte budget while the character total stays under it. **Resolution:**
  §H7 item 3 now requires the bounded reader to retain the actual raw body byte count on
  `FetchResponse` (`body_byte_count`), and (as refined in cycle-4) to enforce the aggregate via a
  request-scoped during-read remaining-byte budget rather than a post-return sum; the concern is
  isolated into a dedicated width-isolated harness+impl pair (**064.016-T** / **064.017-T**) with
  mandatory non-ASCII and invalid-byte cap tests. The per-dimension cap pair (064.012/064.013) is
  narrowed to `max_pages` + per-response, keeping each task within the 2-hour/scenario/file limits.
- **MCP `2026-07-28` protocol semantics — dual-era server required (Architecture/Spec P1)** — the
  claim that `2026-07-28` mandates `server/discover`, per-request `_meta` version negotiation, and
  `-32022` (no `initialize` handshake) was **verified against the official specification**
  (`modelcontextprotocol/modelcontextprotocol` `docs/specification/2026-07-28`: `changelog.mdx`,
  `server/discover.mdx`, `basic/versioning.mdx`, `basic/transports/stdio.mdx`, retrieved
  2026-08-27) rather than accepted on assertion. The revision exists and the claims are confirmed
  verbatim (`server/discover` MUST; per-request `_meta.io.modelcontextprotocol/protocolVersion`;
  `UnsupportedProtocolVersion` = `-32022`; `ping` removed; `resultType` required). Because the
  operator's priority is external stdio discovery + interoperability, a legacy-only server fails
  the modern-client compatibility cell. **Resolution:** added `## Protocol Era Model` and a
  **dual-era** implementation (retain legacy `initialize`; add modern `server/discover` +
  per-request `_meta` negotiation + `-32022` + modern result shape + era routing), decomposed into
  separately scoped harness/impl tasks with explicit negotiation/version tests
  (**064.020-T**/**064.021-T** harnesses, **064.022-T**/**064.023-T** impls). Deliberation updated
  with the evidence and decision.
- **Memory handoff reason inconsistent (Consistency P2)** — the durable session memory recorded
  "reason: archived" while `.backlogit/archive/stash.jsonl` records `reason: harvested` for all
  eight consumed entries. **Resolution:** memory corrected to `harvested`, matching the actual
  archive value so traceability checks resolve.
- **`fetch` tool over-advertises input mode (Consistency/Correctness P2)** — the shared `fetch`
  description advertises "a URL or file path" (`app.py:465-468`) while `execute_fetch` rejects
  every non-HTTP(S) source (`app.py:596-603`), so newly connected clients are promised an
  unsupported input mode. **Resolution:** correct the shared description to HTTP(S)-only (fixing
  both the CLI `--manifest` and the MCP surfaces, which are equally wrong) with a manifest⇄behavior
  parity test, decomposed into a harness+impl pair (**064.018-T** / **064.019-T**).

Shipment 055-S membership and dependency edges were updated for the eight new tasks, preserving a
single linear, acyclic, test-first chain (now 23 tasks) and the 2-hour/width-isolation limits.

**Cycle-3 internal multi-persona adversarial re-review (Architecture / Security / Scope /
Spec-consistency).** The cycle-3 edits were themselves put through a four-persona adversarial review
before commit; findings remediated in-place:

- **Security P1 — dual-era guardrail parity.** The modern stateless/pre-handshake path could
  re-open the §H1 `workspace_root` P0 (or drop §H3/§H5) if the modern branch re-wrapped results
  without re-applying the transport guards. Closed by the **Guardrail parity across eras** invariant
  in `## Protocol Era Model` (both eras funnel through ONE hardened dispatch), a parametrized
  modern-path H1/H3/H5 parity scenario in `064.021-T`, a guard-parity acceptance criterion in
  `064.023-T`, and a Verification bullet.
- **Architecture P2 — era-routing ownership + green attribution.** The modern/legacy classifier was
  double-owned across `064.022`/`064.023`. Made crisp: `064.022` owns the MODERN branch (so
  `064.020` scenario b greens there); `064.023` owns the LEGACY branch + guard parity + no-drift.
- **Architecture P2 — identity single-source at every commit.** `064.002` would have hardcoded
  `protocolVersion`/serverInfo literals in `stdio.py` until `describe_server()` appeared late.
  Moved `describe_server()` introduction into the adapter task `064.015` (the designated
  single-source task) so the legacy `initialize` consumes it from first implementation and the
  "identity in ONE adapter accessor / transport is a pure translator" invariant holds at every
  commit.
- **Consistency P2 — stale task title.** `064.013-T`'s title still claimed "aggregate caps";
  retitled to "page + per-response byte caps" to match its rescoped body and §H7's assignment of
  the aggregate to `064.016`/`064.017`.
- **Security P3 — auxiliary-fetch bytes.** `robots.txt`/TOC auxiliary fetches escaped the aggregate
  budget (bounded, not unbounded). Closed by requiring their reads to decrement the same
  request-scoped `MAX_TOTAL_FETCH_BYTES` during-read budget (§H7 item 3, `064.017-T`).
- **Architecture P3 — harness milestone accuracy.** `064.021-T` scenario (a) (legacy retention) is
  green-at-authoring; reframed as an explicit regression anchor, scoping the red claim to the
  genuinely-red era-routing and guard-parity scenarios.
- Accepted advisories (no change): the two-task `fetch`-description split (Scope P3) is consistent
  with the plan's uniform width-isolation rule; a suggested pre-split of the pre-existing `064.011`
  address-pinned-connect impl (Architecture P3) is out of cycle-3 scope and left for the build agent
  to split at execution if the 2-hour envelope is exceeded.

Re-review verdict (cycle-3, post-remediation): the byte-accurate aggregate accounting, the
authoritative-spec-driven dual-era protocol conformance (with cross-era guardrail parity and a
single identity source), the corrected `fetch` advertising, and the memory reason are consistently
recorded across plan, deliberation, backlog, and memory. All P0/P1/P2 findings closed.

### Cycle-4 review remediation (PR #166 review cycle 4)

A fourth Copilot review on PR #166 left twelve unresolved threads. All treated as valid and closed
here (planning/backlog/memory artifacts only — Stage touches no production/test code). Each fix
propagates through plan, backlog task acceptance criteria, dependencies, and memory so the harness
stays executable, security-first, simple, and composable. The 23-task chain and its edges are
unchanged; only acceptance-criteria text is reconciled.

- **Plan scope wording contradicted the §H6/§H7 hardening (Consistency/Scope P2)** — the "out of
  scope" line excluded "any change to `execute_fetch` … processing behavior," which reads as
  excluding the in-scope DNS-rejection + crawl-limit security work. **Resolution:** the exclusion
  is narrowed to `execute_process` processing behavior and to `execute_fetch` changes *outside* the
  specified §H6/§H7 hardening; the security work is explicitly in scope (`## Scope`).
- **Bounded frame reader dropped the next request (Correctness/Security P2)** — a fixed-chunk
  `read()` can return a newline plus the head of the next frame; draining or returning through the
  newline without retaining the suffix loses the following JSON-RPC request. **Resolution:** a
  carry-over buffer is required in BOTH the normal and oversized-drain paths, with a two-frames-in-
  one-chunk test (Design "Input bounds", §H2, 064.006-T H2 scenario, 064.002-T).
- **Aggregate byte budget not enforceable by a post-return accumulator (Security P1, two threads —
  064.013-T + 064.017-T)** — a `crawl.py` accumulator that sums `body_byte_count` only after
  `fetch_page` returns cannot bound work: the crossing response is already fully read, and bytes
  from over-cap attempts retried by `_fetch_with_retries`, plus robots.txt/TOC fetches, never
  accrue. **Resolution:** the aggregate is enforced by a request-scoped remaining-byte budget
  threaded into `fetch_page`/the bounded reader and decremented **while chunks are read** (aborting
  mid-read), across retries and ancillary fetches, with a repeated-failure/ancillary test
  (§H7 item 3, 064.016-T, 064.017-T; 064.013-T delegation note).
- **DNS-rebinding via inherited proxies (Security P1, 064.011-T)** — `request.build_opener` installs
  urllib's default `ProxyHandler`, so with `HTTP(S)_PROXY` set the original hostname is handed to a
  proxy that performs a second, unvalidated resolution, defeating the address pin. **Resolution:**
  §H6 item 3 now requires disabling inherited/environment proxies (empty `ProxyHandler({})`) or a
  specified IP-pinned `CONNECT`, with a proxy-variables-set test (064.010-T scenario c, 064.011-T).
- **Allow-list duplicated in the transport (Architecture P2, 064.009-T)** — mapping tool identity
  in `stdio.py` recreates the advertise/dispatch drift the adapter single-source is meant to
  prevent. **Resolution:** H4 is implemented by mapping the adapter `call_tool`'s typed unknown-tool
  error to `-32602`; the transport carries no allow-list (§H4, 064.009-T).
- **Memory feature ID missing its leading zero (Consistency P3)** — `64-F` should be `064-F`.
  **Resolution:** corrected in the session memory.
- **`ManifestTool` list lookup would raise `TypeError` (Correctness P2, 064.018-T)** —
  `get_mcp_manifest().tools` is a `list[ManifestTool]`, so `tools['fetch']` fails. **Resolution:**
  locate the entry by `name` (`next(t for t in … if t.name == "fetch")`) as the existing manifest
  tests do (064.018-T, plan Task 13).
- **`DiscoverResult` missing required cache metadata (Spec P2, 064.020-T)** — `DiscoverResult` is a
  `CacheableResult`, so `ttlMs`/`cacheScope` are required on the discover result. **Resolution:**
  asserted on `server/discover` (064.020-T, 064.022-T, Protocol Era Model, method map).
- **Modern request metadata validated only `protocolVersion` (Spec P2, 064.022-T)** — the
  2026-07-28 request schema requires both `protocolVersion` and `clientCapabilities`. **Resolution:**
  both are validated; missing/malformed `clientCapabilities` returns `-32602` (checked after version)
  (064.020-T, 064.022-T,
  Protocol Era Model).
- **`server/discover` claimed to advertise the fetch description (Spec/Correctness P2, 064.019-T)** —
  `server/discover` exposes versions/capabilities/identity/cache metadata, not tool descriptions.
  **Resolution:** the description correction is limited to the CLI manifest and `tools/list`
  (064.019-T, plan Task 14, Verification, Rollback).
- **Cross-era equality marked "already green" too early (Correctness P2, 064.021-T)** — the
  initialize-vs-`server/discover` no-drift equality cannot be green when 064.021-T is authored
  because `server/discover` is not implemented until successor 064.022-T. **Resolution:** scenario
  (a) is a legacy-only green anchor; the no-drift equality moves to scenario (b) and stays red until
  discovery/legacy routing exist (064.021-T, plan Task 18).
- **Aggregate enforcement during read (Security P1, 064.017-T)** — same root cause as the 064.013-T
  thread; summing after `fetch_page` returns cannot enforce a hard bound and ignores failed retried
  attempts. **Resolution:** the threaded during-read budget above; count failed attempts and
  auxiliary responses (064.017-T, §H7 item 3).

Re-review verdict (cycle-4, post-remediation): every unresolved PR #166 thread is reconciled across
plan, backlog acceptance criteria, dependencies, and memory. The chain remains a single linear,
acyclic, test-first sequence of 23 tasks within the 2-hour/width-isolation limits.

**Cycle-4 internal multi-persona adversarial re-review (Security / Architecture / Scope /
Correctness).** The cycle-4 edits were themselves put through a four-persona plan-review before
commit; findings remediated in-place:

- **Architecture P1 (blocking) — aggregate-budget abort swallowed by crawl.py.** A DoclineError-
  subclass `AggregateBudgetExceededError` would be caught by `crawl.py`'s FOUR broad
  `except (DoclineError, OSError)` handlers (`crawl()` main loop, `_fetch_with_retries`,
  `_robots_allow`, `_discover_toc_links`), recording the abort as a per-page skip and degrading the
  byte-abort into a `max_pages × backoff` time-exhaustion. Closed: §H7 item 3 and 064.017-T now
  require `except AggregateBudgetExceededError: raise` at all four sites (mirroring the existing
  `except CrawlUrlRejectedError: raise`), and 064.016-T asserts `crawl()` RAISES rather than
  returning skipped results.
- **Security/Architecture P2 — modern-branch guard funnel timing.** The stateless pre-handshake
  modern branch (064.022) was introduced one task before its guards (064.023), risking a transient
  §H1 re-open. Closed: 064.022 now funnels the modern branch through the SAME hardened dispatch
  (guards-by-construction), greening the modern-path parity scenario (064.021 c) at 064.022;
  064.023 VERIFIES parity rather than first-wiring it.
- **Correctness/Scope P2 — unpinned `clientCapabilities` rejection code.** Pinned to `-32602` with
  version-first precedence across 064.020-T, 064.022-T, and the Protocol Era Model.
- **Correctness P3 — dataclass ordering + function-name attribution.** `FetchResponse.body_byte_count`
  must carry a default (frozen dataclass ends with a defaulted field); the corrected `fetch`
  description literal lives in `get_manifest()` (not `get_mcp_manifest`, which re-exposes it). Both fixed.
- **Architecture P3 — name the unknown-tool exception.** Named `UnknownToolError` (a DoclineError
  subclass) in 064.015-T; 064.009-T catches it specifically, ordered before the generic `-32603`.
- **Scope P2/P3 — envelope + attestations.** Added function-budget + split guards to 064.017-T and
  064.022-T and scenario-budget attestations to 064.020-T/064.021-T; retitled 064.017-T off the
  superseded "sum in crawl" phrasing.
- **Security P3s (hardening) — SSRF address classification + system proxies + per-request disk.**
  §H6 now normalizes IPv4-mapped IPv6 and rejects ULA/CGNAT/`0.0.0.0`; the proxy disable pins an
  empty `ProxyHandler({})` (never `getproxies()`) to suppress system/registry proxies; a per-request
  disk/transfer residual is named in `## Risks`.

Re-review verdict (cycle-4 internal, post-remediation): the P1 abort-propagation gap is closed, the
modern-path guard funnel is intrinsic, error codes and the typed-error contract are pinned, and the
scope guards are symmetric across sibling impl tasks. All P0/P1 findings closed.

### Cycle-5 review remediation (PR #166 review cycle 5)

A fifth Copilot review on PR #166 (HEAD `b90fa77`) left seven unresolved threads. All treated as
valid and closed here (planning/backlog/memory artifacts only — Stage touches no production/test
code). The 23-task chain and its edges are unchanged; only wording is reconciled so the harness
stays executable, security-first, and consistent across plan, backlog, and memory.

- **Era classifier could classify a pre-initialize metadata-free request as legacy (Security/
  Correctness P1, Protocol Era Model + 064.021-T + 064.023-T).** As previously worded, the "one
  request-shape classifier that never depends on prior session state" implied any metadata-free
  `tools/call` was legacy even before `initialize`, so a malformed modern request (missing `_meta`)
  could fall through to the legacy path and bypass required `_meta` validation. **Resolution:** the
  process era is now **latched by `initialize`** (a per-process legacy selection); metadata-free
  operations arriving **before** that selection are **rejected**, never served as legacy; the modern
  branch remains **request-stateless**; and a dedicated **pre-initialize operation test** is added
  to the era-routing harness (064.021-T scenario b, greened by the legacy branch in 064.023-T).
- **Feature DoD still described the superseded post-return `body_byte_count` accumulator
  (Security P1, 064-F).** The H7 DoD clause read as if the aggregate `MAX_TOTAL_FETCH_BYTES` budget
  were satisfied by summing `FetchResponse.body_byte_count` after each successful response — which
  cannot count failed/retried over-cap reads or bound the crossing response. **Resolution:** the DoD
  now states the actual enforcement mechanism — a request-scoped remaining-byte budget threaded into
  `fetch_page`/the bounded reader and decremented per chunk **during** every read (counting retries
  and ancillary robots/TOC fetches, aborting mid-read), with `body_byte_count` retained only as
  per-response observability — matching 064.016-T/064.017-T so Ship cannot satisfy the feature with
  the insecure accumulator.
- **`get_manifest()` edit-target attribution (Correctness P2, Protocol Era Model design note, plan
  Task 14, Rollback, 064-F implicit).** Three plan sites (the Design "fetch advertising" note, the
  064.019-T task summary, and the Rollback inventory) named `get_mcp_manifest` as the function to
  edit, though the description literal lives in `get_manifest()` (which `get_mcp_manifest()` only
  re-exposes). **Resolution:** all three now name `get_manifest()` as the edit target / changed
  symbol, aligning with the cycle-4 resolution and the corrected 064.019-T task so implementation
  and rollback target the exact symbol.
- **Continuity memory carried the rejected implementation (Consistency P2,
  `.backlogit/memories.json`).** The structured session memory still said the crawl "sums
  `body_byte_count`" and named `get_mcp_manifest` as the edit target. **Resolution:** the
  `stage-2026-08-27-darkfactory-stash-sweep` record is regenerated from the reconciled artifacts —
  during-read remaining budget + `get_manifest()` literal + era-classifier latch — so a future
  session cannot restore the rejected approach.
- **064.015-T uniform adapter-callable signature (Correctness P2, 064.015-T).** `fetch`/`process`
  take a request object while `export_schema()` takes no arguments, so a generic `handler(arguments)`
  would raise `TypeError` for `export_schema`. **Resolution:** 064.015-T now requires uniform
  dict-taking adapter callables (with `export_schema` accepting only an empty dict), and the
  dispatchability assertion actually invokes all three tools.

Re-review verdict (cycle-5, post-remediation): the era classifier is stateful only where the spec
requires (legacy latch after `initialize`) and request-stateless for the modern era; the feature
DoD names the enforceable during-read budget; the edit-target attribution is uniform across plan,
backlog, and memory; and the adapter dispatch contract is type-safe. All P0/P1 findings closed.

### Cycle-6 review remediation (PR #166 review cycle 6, fresh Copilot review on HEAD dbadb4a)

The cycle-5 commit (dbadb4a) drew a fresh Copilot review with six unresolved threads. All six are
reconciled here (Stage's final allowed review-fix cycle for shipment 055-S), across plan, feature,
tasks, shipment, and continuity memory, preserving dependency acyclicity and execution order:

- **Strict-safety action records (thread 1, plan intro line 28 / `docs/plans/...:28`).** The plan
  named security-sensitive shared-fetch and exposed-MCP-contract changes but carried no explicit
  risk-action record or approval state. **Resolution:** added `## Strict-Safety Action Records` with
  two high-risk `ProposedAction`/`ActionRisk`/`ActionResult` entries (SA-1 shared-fetch security
  behavior, SA-2 exposed MCP contract), each with concrete targets, rollback/containment, approval
  basis (the standing dark-factory authorization for autonomous implementation + PR merge; no
  destructive action authorized), `ActionRisk: high`, and `ActionResult: approved`. Intro line 28
  cross-reference updated.
- **064.017-T exceeds its <5-function envelope (thread 2, `064.017-T:35`).** The task's acceptance
  criteria required changes to `fetch_page`, `crawl`, `_fetch_with_retries`, `_robots_allow`, and
  `_discover_toc_links` — five functions — so the conditional split guard could not make it
  compliant. **Resolution:** the split is executed now. New successor **064.024-T** (T-agg-aux) owns
  the ancillary (`_robots_allow`/`_discover_toc_links`) budget threading + their two re-raise
  clauses and takes over 064.016-T scenario (c)(iii) green-ownership; 064.017-T is narrowed to
  `fetch_page`/`crawl`/`_fetch_with_retries` (3 functions) + 2 small classes + 1 additive field.
  Chain: `064.016 → 064.017 → 064.024 → 064.014` (064.014-T re-pointed from 064.017-T to 064.024-T);
  dependency edges, execution order, feature DoD, shipment 055-S membership/order, and continuity
  memory updated. Acyclicity preserved (linear insertion).
- **Hard resource limits never assigned numeric values (thread 3, `064-F:34`).** The §H7 caps were
  symbolic. **Resolution:** pinned concrete, workload-grounded constants in a new §H7 "Selected
  numeric limits" block (source of truth) and propagated them to the feature DoD and the H7 cap
  tasks (064.012/064.013/064.014/064.016/064.017/064.024): `MAX_PAGES_LIMIT = 1000`
  (`Field(ge=1, le=1000)`, 20× the current 50-page crawl default; `>=1001` → `-32602`),
  `MAX_RESPONSE_BYTES = 10 MiB` (10 485 760 bytes; exact-cap allowed, mid-stream abort on the
  crossing byte), and `MAX_TOTAL_FETCH_BYTES = 512 MiB` (536 870 912 bytes; request-scoped
  during-read budget, exact-total allowed, mid-stream abort on the crossing byte). Rationale and
  exact boundary behavior documented in every affected artifact.
- **064.022-T / 064.023-T transport path missing `src/` (threads 4 and 6, `064.022-T:22`,
  `064.023-T:22`).** `docline/mcp/stdio.py` does not exist; the real module is
  `src/docline/mcp/stdio.py`. **Resolution:** corrected the two task file-scopes and reconciled the
  same stale path in the plan (T2, T-era-i1, T-era-i2 file scopes, Rollback module list, and the
  `__main__.py` references) to the `src/`-prefixed form.
- **064.004-T claims a nonexistent/untracked `.mcp.json` (thread 5, `064.004-T:31`).** The repo's
  `.mcp.json` is git-ignored (`.gitignore`) and not a verifiable tracked source. **Resolution:**
  replaced the "mirror the repo's `.mcp.json`" note with a concrete, verifiable format source — the
  documented GitHub Copilot / VS Code `.vscode/mcp.json` `servers` stdio entry shape
  (`type`/`command`/`args`) plus the MCP stdio transport spec — and required a SELF-CONTAINED inline
  README example; retitled the task and reconciled Scope item 4 and plan T4.

Re-review verdict (cycle-6, post-remediation): all six threads addressed consistently; the aggregate
budget is split into an envelope-compliant impl pair (064.017 core + 064.024 ancillary) with an
acyclic, order-preserving chain; the H7 caps are numeric and measurable before the red harnesses;
the transport paths and the docs-config format source are verifiable; and the plan carries explicit
strict-safety high-risk action records for the two high-blast-radius surfaces. All P0/P1 findings
closed.

### Cycle-7 review remediation (PR #166 review cycle 7, fresh Copilot review on HEAD b38d3b0)

The cycle-6 commit (b38d3b0) drew a fresh Copilot review with four unresolved threads. All four are
reconciled here (Stage resumed under a fresh operator-authorized three-cycle allowance, round 1),
across plan, feature DoD, tasks, and continuity memory, preserving dependency acyclicity, execution
order, and shipment 055-S membership (no new tasks; no edge changes):

- **`064.005-T` never requires a valid MCP `CallToolResult` wire shape (thread 1, `064.005-T:25`).**
  The harness asserted app-level parity + `isError` only, so an implementation could serialize
  `FetchResult`/`ProcessResult` directly and pass while real MCP clients reject the response.
  **Resolution:** strengthened the dispatch-parity scenario (in-place, no new scenario) to require a
  standards-valid `CallToolResult` for BOTH eras: `result.content` is a `ContentBlock[]`; the modern
  result additionally carries `resultType:"complete"`; parametrized over `fetch`/`process`/
  `export_schema` × success/failure; `structuredContent` asserted when mirrored. The LEGACY body is
  asserted by `064.005-T` (green@`064.002-T`) and the MODERN wrapper by `064.021-T` scenario (c)
  (green@`064.022-T`), preserving the milestone model. Impl tasks `064.002-T` (legacy shaping step)
  and `064.022-T` (modern wrapper around the SAME body) now require the shared, standards-conformant
  body; feature DoD and plan Design "Tool-result mapping" reconciled. Scenario counts stay at 3
  (both harnesses); width stays test-only — no split required.
- **Per-response 10 MiB cap allows a full-chunk over-read at the boundary (thread 2, `064.013-T:26`).**
  Checking after each fixed `read(CHUNK_SIZE)` lets a whole extra chunk transfer before overflow is
  detected. **Resolution:** `064.013-T` now caps each read at
  `min(CHUNK_SIZE, remaining_response_bytes + 1)` so only the single crossing byte can be consumed;
  `064.012-T` asserts (via an instrumented transport recording read sizes) that an over-cap response
  transfers AT MOST `MAX_RESPONSE_BYTES + 1` bytes, not `MAX_RESPONSE_BYTES + CHUNK_SIZE`. Plan §H7
  boundary language updated.
- **Aggregate 512 MiB budget has the same chunk-overread gap (thread 3, `064.017-T:26`).**
  **Resolution:** `064.017-T` now caps each read at
  `min(CHUNK_SIZE, per_response_remainder + 1, aggregate_remainder + 1)`, counts the actual bytes
  returned, and decrements both allowances by that count, so only the crossing byte is read;
  `064.016-T` asserts the crossing-byte-only transfer. `064.024-T` (ancillary robots/TOC) shares the
  SAME `fetch_page` bounded reader and inherits the cap, so its transfer also stops at the crossing
  byte (`064.016-T` scenario (c)(iii)). Plan §H7 aggregate boundary language updated.
- **Structured continuity memory stale after the cycle-6 split (thread 4, `.backlogit/memories.json:3`).**
  The `stage-2026-08-27-darkfactory-stash-sweep` entry still recorded 23 tasks and `064.017 → 064.014`.
  **Resolution:** regenerated that entry to 24 tasks with the `064.017 → 064.024 → 064.014` chain and
  the corrected 24-task execution order, and added the cycle-6 split + cycle-7 reconcile notes, while
  preserving the `orchestrator:055-S:pr166-review-breaker` key.

Re-review verdict (cycle-7, post-remediation): all four threads reconciled consistently across plan,
feature DoD, backlog acceptance criteria, and memory; the exact-boundary read-size cap
(`min(..., remainder + 1)`) is specified uniformly for the per-response and aggregate readers and the
shared ancillary reader; the `CallToolResult` wire shape is required for both eras from one shared
shaping step; no dependency edges or shipment membership changed (chain and 24-item manifest already
correct). All P0/P1 findings closed.

### Cycle-8 review remediation (PR #166 review cycle 8, fresh Copilot review on HEAD 4271ca7)

The cycle-7 commit (4271ca7) drew a fresh Copilot review with two unresolved threads (Stage resumed
under the fresh operator-authorized three-cycle allowance, round 2). Both are reconciled here across
plan, feature DoD, tasks, dependency chain, shipment 055-S membership, and continuity memory,
preserving dependency acyclicity and execution order. This cycle ADDS a new width-isolated
harness+impl pair (see below), so the manifest grows 24 → 26 tasks and the chain gains
`064.024 → 064.025 → 064.026 → 064.014` (064.014-T re-pointed from 064.024-T to 064.026-T).

- **`max_pages` does not bound actual fetch work; depth has no upper bound (thread 1, `064.013-T:25`).**
  `crawl.py` fetches print pages, duplicate final URLs, and out-of-scope-section final URLs and
  enqueues their links WITHOUT incrementing `page_count` (the `_is_print_page`, `final_key in
  emitted_urls`, and `not _url_within_section_scope(final_url, …)` branches each `continue` without
  `page_count += 1`), while every frontier pop is a real fetch and `FetchRequest.depth` has no
  upper bound (`app_models.py:24`). An attacker can chain tiny under-cap `/print` pages to trigger
  far more than `MAX_PAGES_LIMIT` requests while staying below the per-response and aggregate BYTE
  budgets (which bound VOLUME, not COUNT). **Resolution:** added §H7 **item 4 — request-amplification
  bound** with two hard, measurable, numeric limits in the "Selected numeric limits" block:
  `MAX_FETCH_ATTEMPTS = 4 × MAX_PAGES_LIMIT = 4000` (a per-request frontier-pop counter incremented
  on EVERY pop — so the three non-counting branches count — aborting `crawl()` with a typed error at
  the cap) and `MAX_DEPTH_LIMIT = 64` (`FetchRequest.depth` `Field(default=0, ge=0, le=64)`, default preserved, over-limit
  `-32602`). Because the fetch-attempt counter lives in `fetch/crawl.py` — a third file beyond
  `064.013-T`'s pinned 2-file envelope (`app_models.py` + `fetch/http.py`) — the work is SPLIT into a
  new width-isolated pair: harness **`064.025-T`** (T-amp-h, tests domain, 2 scenarios: drives each
  non-counting branch to prove the attempt cap trips while `page_count` stays low; depth over-limit
  rejection) and impl **`064.026-T`** (T-amp-i, code domain, 2 files: `fetch/crawl.py` counter +
  `app_models.py` depth bound). The end-to-end boundary harness `064.014-T` is re-pointed onto
  `064.026-T` (keeping its 3-scenario budget; the amplification bound is proven at the unit level in
  `064.025-T`). Plan §H7, "Selected numeric limits", "Cap tasks", decomposition list, dependency
  edges, execution order, Rollback, SA-1 record, feature DoD H7 clause, and shipment 055-S
  membership all updated.
- **EOF-driven subprocess smoke test cannot detect live stdio deadlocks (thread 2, `064.008-T:26`).**
  With the pipe left open, a buffered `read(CHUNK_SIZE)` can wait for the requested byte count after
  a short frame, and block-buffered stdout can retain a response unless explicitly flushed; closing
  stdin first masks both. **Resolution:** rewrote `064.008-T` to an INTERACTIVE `subprocess.Popen`
  harness — send and flush one frame (modern `server/discover` or legacy `initialize`), REQUIRE its
  response BEFORE sending the next (`tools/list`) frame with stdin still OPEN, read that response,
  THEN close stdin (EOF) and await clean exit; each response read is timeout-bounded so a deadlock
  FAILS deterministically. Its PASS depends on the server side, so `064.002-T` serve() now REQUIRES
  a NON-GREEDY input read (`read1`/`os.read`) and an EXPLICIT stdout flush after EVERY response
  (also propagated to the bounded frame-read helper). Plan T2 serve()/input-bounds, plan T2b
  decomposition entry, the Verification "automated subprocess smoke" bullet, `064.008-T`,
  `064.002-T`, and feature DoD line 1 (interactive-liveness clause) all reconciled. Scope preserved:
  no source/test code written; `064.002-T` and `064.008-T` retain their existing file/scenario
  envelopes (the change is a behavioral requirement, not a new function or scenario).

Re-review verdict (cycle-8, post-remediation): both threads reconciled consistently; the
request-amplification bound is numeric and measurable before its red harness, split into an
envelope-compliant width-isolated pair with an acyclic, order-preserving chain (`064.024 → 064.025 →
064.026 → 064.014`); the interactive stdio-liveness contract is specified on both the test (Popen
framing) and server (non-greedy read + flush) sides from one shared requirement. All P0/P1 findings
closed.

## Rollback

**Not purely additive.** The release unit adds new modules (`src/docline/mcp/stdio.py`,
`src/docline/mcp/__main__.py`) and one `[project.scripts]` entry-point line, but it ALSO modifies
existing files whose behavior changes for both interfaces:

- `src/docline/mcp/server.py` — adapter `DoclineMcpServer` gains `call_tool` (static allow-list
  dispatch) and the new `list_callable_tools()` method (delivered by task 064.015-T), changing the
  adapter's callable surface. `list_tools()` is unchanged.
- `src/docline/fetch/url_policy.py` + `src/docline/fetch/http.py` — SSRF-by-resolution hardening
  (§H6): host resolution + address-pinned connect-time validation on the initial URL and every
  redirect. Affects **CLI `docline fetch` too**, not just MCP.
- `src/docline/app_models.py` + `src/docline/fetch/http.py` — per-dimension resource caps (§H7):
  `max_pages` upper bound and streamed `MAX_RESPONSE_BYTES` read (064.012/064.013). Also affects
  CLI fetch.
- `src/docline/fetch/http.py` + `src/docline/fetch/crawl.py` — byte-accurate aggregate accounting
  (§H7 item 3, cycle-3): `FetchResponse` gains a `body_byte_count` field carrying the raw wire byte
  count, and the crawl enforces `MAX_TOTAL_FETCH_BYTES` via a request-scoped remaining-byte budget
  threaded into `fetch_page`/the bounded reader and decremented per chunk while bytes are read
  (main pages, retries via 064.016/064.017; ancillary robots/TOC via split successor 064.024),
  aborting mid-read. Additive field +
  threaded budget; also affects CLI crawls.
- `src/docline/fetch/crawl.py` + `src/docline/app_models.py` — request-amplification bound (§H7
  item 4, cycle-8): the crawl loop adds a per-request `fetch_attempts` counter incremented on every
  frontier pop (so the print-page / duplicate / out-of-scope non-counting branches count) and
  RAISES a typed error once attempts exceed `MAX_FETCH_ATTEMPTS = 4000`, and `FetchRequest.depth`
    gains a hard `Field(default=0, ge=0, le=64)` upper bound (`MAX_DEPTH_LIMIT`; default preserved),
    rejecting over-limit depth `-32602`
    (064.025/064.026). Tightens accepted request COUNT on the shared path; also affects CLI crawls.
- `src/docline/app.py` — `get_manifest()` `fetch` description literal corrected to HTTP(S)-only
  (re-exposed unchanged by `get_mcp_manifest()`) (064.019, cycle-3). Text-only advertising change;
  flows to both `docline --manifest` (CLI) and
  the MCP `tools/list` surface (`server/discover` carries no tool descriptions). No
  processing-behavior change.
- `src/docline/mcp/stdio.py` + `src/docline/mcp/server.py` — dual-era protocol surface (cycle-3):
  modern `server/discover`, per-request `_meta` version negotiation, `-32022`, modern result shape,
  and era routing, plus a single `describe_server()` identity/version accessor
  (064.020–064.023). Additive to the legacy transport; no behavior change for legacy clients.
- `pyproject.toml` — `[project.scripts]` entry.

Rollback = revert the feature branch. There is no data migration and no persisted-schema change, but
because the shared-fetch and adapter changes touch existing runtime paths, a rollback restores the
prior (weaker) SSRF/resource behavior on BOTH interfaces — reviewers must treat this as a
cross-interface change, not an isolated new transport. The MCP-only additions (stdio loop, dual-era
protocol surface, adapter callable surface, entry point) can be reverted independently of the
shared-fetch hardening if only the transport needs backing out; the shared-fetch tasks
(064.010–064.013, 064.016–064.017, 064.024, 064.025–064.026) and the `fetch`-advertising correction (064.019) are
self-contained and revertible on their own.

## Strict-Safety Action Records

The `strict-safety` capability pack is installed. This release unit carries two **high-blast-radius**
changes that must not stay implicit: (1) a shared-fetch **security-behavior** change on an existing
runtime path used by BOTH the CLI and the new MCP surface, and (2) a NEW **exposed MCP contract**
over an untrusted local stdio transport. Neither is a *destructive* action (no file/dir deletion,
no history rewrite, no data drop, no system-config/package change), so no destructive-action
approval gate applies. The operator's standing dark-factory instruction explicitly authorizes
autonomous implementation and autonomous PR merge for this work, but authorizes **no destructive
action**; that standing authorization is the approval basis recorded below. Execution of both
actions is owned by the Ship agent — these records are the planning-time risk surface Stage carries
forward into build, review, runtime verification, and closure.

### SA-1 — Shared-fetch security-behavior change (SSRF-by-resolution + resource caps)

- **ProposedAction.summary:** Harden the shared fetch code path — add SSRF-by-DNS-resolution
  rejection with address-pinned connect on the initial URL and every redirect (§H6), and hard
  resource caps (§H7): `MAX_PAGES_LIMIT = 1000` upper bound, streamed `MAX_RESPONSE_BYTES` = 10 MiB
  per-response cap, a request-scoped during-read aggregate `MAX_TOTAL_FETCH_BYTES` = 512 MiB
  budget, and a request-amplification bound (`MAX_FETCH_ATTEMPTS` = 4000 frontier-pop cap +
  `MAX_DEPTH_LIMIT` = 64 depth upper bound, §H7 item 4). This tightens accepted inputs on an existing runtime path shared by CLI `docline fetch`
  and the MCP `fetch` tool.
- **targets:** `src/docline/fetch/url_policy.py`, `src/docline/fetch/http.py`,
  `src/docline/fetch/crawl.py`, `src/docline/app_models.py`. Delivered by tasks 064.010–064.013,
  064.016–064.017, 064.024, 064.025–064.026.
- **change_kind:** shared-code security / behavior change (NOT purely additive) — cross-interface
  blast radius.
- **rollback / containment:** self-contained and revertible per shared-fetch task (see `## Rollback`);
  reverting restores the prior (weaker) SSRF/resource behavior on both interfaces. Blast radius is
  contained by sizing caps well above legitimate use (20× the current 50-page crawl default; 10 MiB
  per response; 512 MiB aggregate) and keeping the existing `tests/fetch` suite green (or
  deliberately updating it for the new bound). No data migration, no persisted-schema change.
- **approval_required:** covered by the standing dark-factory authorization for autonomous
  implementation + PR merge; NOT destructive, so no separate destructive-action approval is required.
- **ActionRisk:** `high` — shared-code security change with cross-interface blast radius.
- **ActionResult:** `approved` (pre-authorized by the standing dark-factory instruction; execution
  owned by Ship — `planned` for the current Stage artifact, transitions to `applied` when Ship builds
  and merges).

### SA-2 — New exposed MCP contract over untrusted stdio + adapter callable-surface change

- **ProposedAction.summary:** Expose docline over a NEW untrusted local stdio JSON-RPC 2.0 transport
  (dual-era: legacy `initialize` + modern `server/discover`/`_meta`) and change the
  `DoclineMcpServer` adapter's callable surface (`call_tool` allow-list, `list_callable_tools()`,
  `describe_server()`), promoting previously CLI-only assumptions to a security boundary guarded by
  H1–H7.
- **targets:** new `src/docline/mcp/stdio.py`, `src/docline/mcp/__main__.py`, `[project.scripts]` in
  `pyproject.toml`; modified `src/docline/mcp/server.py`. Delivered by tasks 064.001–064.009,
  064.015, 064.018–064.023, 064.002–064.004, 064.008.
- **change_kind:** new external contract + adapter callable-surface change (interface/config change);
  introduces an untrusted-input boundary.
- **rollback / containment:** the MCP-only additions (stdio loop, dual-era surface, adapter callable
  surface, entry point) revert independently of the shared-fetch hardening (see `## Rollback`).
  The boundary is contained by fail-closed guardrails: H1 `workspace_root` reject (`-32602`), H3
  error non-disclosure, H4 closed allow-list, H5 stdout hygiene, applied through ONE hardened
  dispatch across both protocol eras. Revert = drop the feature branch.
- **approval_required:** covered by the standing dark-factory authorization for autonomous
  implementation + PR merge; NOT destructive, so no separate destructive-action approval is required.
- **ActionRisk:** `high` — new untrusted attack surface / exposed contract.
- **ActionResult:** `approved` (pre-authorized by the standing dark-factory instruction; execution
  owned by Ship — `planned` for the current Stage artifact, transitions to `applied` when Ship builds
  and merges).

## Risks

- Medium: shared-fetch hardening (§H6/§H7) changes existing CLI `docline fetch` behavior — a
  hostname that resolves to a private address, or a crawl exceeding the new `max_pages`/response-byte
  /aggregate caps, now fails where it previously succeeded. Mitigated by sizing caps above legitimate
  use and keeping the existing `tests/fetch` suite green (or deliberately updating it for the new bound).
- Medium: dual-era protocol surface adds real complexity (era classification, per-request `_meta`
  negotiation, two result shapes). Mitigated by sourcing identity/versions from a single
  `describe_server()` accessor (no drift), keeping the legacy path unchanged, and gating both eras
  with explicit negotiation/version tests (064.020–064.023). Modern-era features beyond
  discovery + negotiation + tools are explicitly out of scope to bound the surface.
- Low: correcting the shared `fetch` description also changes the CLI `--manifest` output text; this
  is intentional (the CLI advertising was equally wrong) and is a text-only change with a parity
  test — no behavior change.
- Low: adding `FetchResponse.body_byte_count` touches a widely-referenced shared dataclass; the
  field is additive with a value derived from bytes the bounded reader already materializes, so
  existing `response.body` consumers are unaffected.
- Low: address-pinned connect (§H6) connects to a validated IP while preserving the `Host` header /
  SNI; verify TLS certificate validation still targets the hostname (not the IP) so pinning does not
  weaken cert checks. Covered by the SSRF harness (064.010-T).
- Low: stdout contamination would corrupt the JSON-RPC stream — mitigated by routing all logs
  to stderr and asserting clean stdout framing in tests.
- Low: manifest drift between CLI and MCP — mitigated by the T1 parity assertion against the
  single shared manifest source (callable allow-list), with `list_tools()` retained for full-manifest
  parity.
- Low (residual, cycle-4): `MAX_TOTAL_FETCH_BYTES` is a **per-request** budget. On the untrusted
  stdio surface an attacker can still issue many sequential `tools/call` `fetch` requests, each
  staging up to the aggregate budget under `output_dir`; nothing bounds cumulative cross-request
  disk/network transfer. Accepted as out of scope for this release unit (per-request bounding closes
  the single-request amplification vector); a session/global transfer or `output_dir` size quota is
  a named follow-up, not a blocker.

## Plan Review

### Cycle-4 gate (PR #166 unresolved-thread reconciliation)

- **Trigger:** Stage finalization of shipment 055-S — reconcile the twelve unresolved PR #166
  Copilot review threads, then run a fresh multi-persona adversarial plan-review before commit.
- **Personas run (4):** Security Lens Reviewer, Architecture Strategist, Scope Boundary Auditor,
  Correctness Reviewer (cross-model where available; MCP-tool-surface + shared-fetch trust boundary
  both trigger the security/parity lenses).
- **Raw persona verdicts:** Security **PASS** (1 P2, 3 P3); Correctness **PASS** (3 P3);
  Scope **ADVISORY** (2 P2, 4 P3); Architecture **FAIL** (1 P1, 2 P2, 3 P3).
- **Blocking finding (Architecture P1):** the aggregate-budget `AggregateBudgetExceededError`
  (a `DoclineError` subclass) would be swallowed by `crawl.py`'s four broad
  `except (DoclineError, OSError)` handlers, so the specified retry-handler-only fix left the cap
  unable to abort cleanly. **Remediated in-place** before commit: §H7 item 3 + 064.017-T now
  require `except AggregateBudgetExceededError: raise` at all four sites (mirroring the existing
  `except CrawlUrlRejectedError: raise`), and 064.016-T asserts `crawl()` RAISES.
- **Other findings:** all P2/P3 items (guard-funnel timing, pinned `clientCapabilities` `-32602`,
  named `UnknownToolError`, `body_byte_count` default, `get_manifest` attribution, scenario/function
  budget guards + attestations, SSRF address-normalization + system-proxy suppression, per-request
  disk residual) were remediated in-place. See the "Cycle-4 internal multi-persona adversarial
  re-review" subsection under `## Plan Review Remediation` for the item-by-item disposition.
- **Gate decision (post-remediation): PASS.** The single P1 is closed; no P0/P1 remains. Hardening
  signals are present (`## Plan Hardening` §H1–§H7) and satisfied. The chain is a single linear,
  acyclic, test-first sequence of 23 tasks within the 2-hour/width-isolation limits. Runtime
  verification and rollback/blast-radius are covered in `## Verification` and `## Rollback`. Ready
  for the harvested backlog to proceed to Ship.
