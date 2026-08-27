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
  transfer-byte accounting**, and an **HTTP(S)-only `fetch` advertising correction**. See
  `## Plan Review Remediation` (cycle-3 subsection).
- Cross-interface blast radius: this release unit is NOT purely additive. It hardens the
  **shared** fetch code (`fetch/url_policy.py`, `fetch/http.py`, `app_models.py`) that both
  the CLI and the MCP surface call, and it changes the existing `DoclineMcpServer` adapter's
  callable surface. See `## Rollback` and `## Risks`.
<!-- plan-review-attempt: 3 -->

## Scope

In scope:

1. A dependency-free stdio JSON-RPC 2.0 dispatch loop that speaks a **dual-era** MCP method set
   and delegates to `DoclineMcpServer`:
   - **Legacy era (`2025-11-25` and earlier):** `initialize`, `notifications/initialized`,
     `tools/list`, `tools/call`, `ping`.
   - **Modern era (`2026-07-28`):** `server/discover` (MUST), plus `tools/list` / `tools/call`
     served statelessly with the protocol version read from each request's
     `_meta.io.modelcontextprotocol/protocolVersion`; unsupported versions return
     `-32022 UnsupportedProtocolVersionError`; results carry `resultType:"complete"` and
     `_meta.io.modelcontextprotocol/serverInfo`; list results carry `ttlMs`/`cacheScope`.
   - **Era routing:** a request carrying modern `_meta` is served under modern semantics; an
     `initialize` request selects legacy semantics. Authoritative basis: MCP spec
     `2026-07-28` (`server/discover.mdx`, `basic/versioning.mdx`, `basic/transports/stdio.mdx`)
     — verified against the official spec repository, see `## Protocol Era Model`.
2. A `docline-mcp` console-script entry point and `python -m docline.mcp` bootstrap.
3. Protocol + dual-interface parity tests (test-first).
4. Operator/agent documentation: README run section + `.mcp.json` example. (No separate
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
   `FetchResponse` before decoding, and the crawl sums that exact value so decode/re-encode
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
- Any change to `execute_fetch` / `execute_process` *processing* behavior (I/O parity must be
  preserved). The `fetch` advertising correction changes only the advertised description text to
  match the existing rejection behavior, not the behavior itself.
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
  explicit static allow-list `{tool_name: bound_method}`. No `getattr(server, name)` (that
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
  MUST assert every advertised MCP tool is dispatchable (no advertise-but-uncallable gap); the H4
  test (064.007-T) proves `ingest_local_dir` fails closed while excluded.
- New module `src/docline/mcp/stdio.py`:
  - `serve(stdin, stdout, server: DoclineMcpServer | None = None) -> int` — read/dispatch/write
    loop; `server` defaults to the existing module singleton `SERVER` (single construction
    path); terminates cleanly on EOF. Reserves the real stdout exclusively for JSON-RPC frames.
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
      serverInfo in `_meta`, `resultType:"complete"`) via a single adapter accessor;
      `tools/list` / `tools/call` served statelessly with the protocol version taken from
      `_meta.io.modelcontextprotocol/protocolVersion` (no prior handshake), an unsupported
      version returning `-32022`, and modern results carrying `resultType:"complete"` +
      serverInfo `_meta` (list results also `ttlMs`/`cacheScope`).
    - Common: `tools/list` → callable allow-list via `server.list_callable_tools()`;
      `tools/call` → `server.call_tool`. The version/identity/capability source of truth lives
      in exactly ONE adapter accessor (mirroring the single-source tool allow-list), so
      `initialize` and `server/discover` cannot drift.
  - Input bounds (DoS): frame reads MUST be bounded at the byte level, not size-checked after an
    unbounded `readline()`. A naive `stdin.readline()` (or `.read()` until newline) buffers an
    arbitrarily large — or never-terminated — frame into memory before any length check runs, so
    the check provides no real bound. Instead read from the raw binary stream in fixed-size chunks
    up to a hard `MAX_FRAME_BYTES` cap while scanning for the newline terminator: as soon as the
    accumulated bytes exceed the cap before a newline arrives, stop buffering, emit an
    error envelope, and **drain** the rest of that oversized frame in bounded chunks (discarding up
    to the next newline or EOF) so the loop resynchronizes without ever holding the whole frame.
    Memory stays bounded even for an unterminated or chunked-oversized input. The parse-error
    handler catches `ValueError` AND `RecursionError` (deeply nested JSON raises `RecursionError`,
    a `RuntimeError` subclass that `json.JSONDecodeError` handling would miss) so one hostile
    message degrades to an envelope rather than crashing the loop.
  - Error envelopes: `-32700` parse error (invalid JSON), `-32600` invalid request (valid JSON
    but not a valid request object — see request-shape validation above), `-32601` method not
    found, `-32602` invalid params (wrap Pydantic `ValidationError`) and unknown/unroutable tool
    name (fail closed), `-32603` internal error. Messages MUST be generic and non-reflective: no
    absolute paths, no `PathContainmentError` text, no tracebacks in `message`/`data`; log full
    detail to stderr.
  - Tool-result mapping: `execute_fetch`/`execute_process` model failure as a *successful* call
    returning `success=False` + `error`. Map a validated-but-failed tool result to a JSON-RPC
    *result* whose MCP content carries the error text with `isError=true`; reserve `-326xx`
    envelopes for framing/validation/internal faults only.
  - Fetch resource bounds (§H7): the untrusted `tools/call` `fetch` path inherits a hard
    `max_pages` upper bound (enforced in the shared `FetchRequest` model), a streamed
    per-response byte cap (`MAX_RESPONSE_BYTES`) enforced in `fetch/http.py` on the initial
    response AND every redirect hop — replacing the unbounded `response.read()` — and a
    byte-accurate aggregate crawl budget (`MAX_TOTAL_FETCH_BYTES`) that sums the **raw** body
    byte count retained on `FetchResponse` (not decoded characters). These live in shared fetch
    code (see §H7 and the shared-fetch tasks), not in the transport module.
  - `fetch` advertising (cycle-3): the shared manifest's `fetch` tool description MUST state
    HTTP(S)-only, matching `execute_fetch`'s rejection of every non-HTTP(S) source
    (`src/docline/app.py:596-603`). The prior "a URL or file path" text over-advertised an input
    mode neither interface accepts. Correct the shared description in `get_mcp_manifest`
    (`src/docline/app.py:465-468`) — it flows to both `list_tools()` and `list_callable_tools()`
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
| Open / negotiate | `initialize` handshake → capabilities + `protocolVersion` + serverInfo | per-request `_meta.io.modelcontextprotocol/protocolVersion`; no handshake |
| Discovery | `tools/list` after handshake | `server/discover` (MUST) returns supportedVersions + capabilities + serverInfo; answerable before any request |
| Version mismatch | n/a (handshake pins) | `-32022 UnsupportedProtocolVersionError` with `data.supported` + `data.requested` |
| Result shape | plain result | `resultType:"complete"` + serverInfo in result `_meta`; list results carry `ttlMs`/`cacheScope` |
| `ping` | supported | removed |

- **Era routing (server-selected):** a request carrying modern per-request `_meta` is served
  statelessly under `2026-07-28`; an `initialize` request selects legacy semantics; a
  `server/discover` call is answerable before any `initialize` (stdio probe). One request-shape
  classifier picks the era; it never depends on prior session state.
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
  AFTER the shared guarded handler returns, never as a parallel unguarded handler. The dual-era
  harnesses (064.021-T) MUST include modern-path (`_meta`, no `initialize`) H1/H3/H5 parity
  scenarios, and 064.023-T MUST carry the guard-parity enforcement as an acceptance criterion.
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
  chunks so memory never holds a whole hostile frame. `RecursionError`/`ValueError` both degrade
  to an error envelope; the loop survives hostile input. Tests: (a) oversized single line; (b)
  deeply nested array; (c) an **unterminated / chunked oversized** input (bytes exceeding the cap
  arrive with no newline) is rejected with bounded memory while waiting for the terminator, and
  the loop resynchronizes on the next valid frame.
- **H3 — Error-text non-disclosure.** No absolute paths / tracebacks in envelopes OR in
  `isError` tool-result content (the `success=False` mapping surfaces `ProcessResult.error` /
  `FetchResult.error`, which may embed absolute resolved paths via `PathContainmentError`).
  Sanitize/genericize both surfaces. Test: a containment/validation failure — as an envelope
  AND as an `isError` result — contains no absolute-path substring.
- **H4 — Closed tool allow-list.** Static `{name: method}` map; unknown names (incl.
  `ingest_local_dir` if unrouted, and dunders) fail closed with `-32602`, never `AttributeError`.
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
     link-local, or a metadata address (`169.254.169.254`). Literal-IP hosts keep their existing
     fast-path rejection. This closes the name→private gap `is_private_host` leaves open.
  2. **Redirects revalidated.** Every redirect target is re-resolved and re-validated at
     connect time, not just compared by `netloc`, so a redirect to a name that resolves to a
     private address is rejected mid-chain.
  3. **Address-pinned connect (in-scope, closes DNS-rebinding).** Validation and connection MUST
     use the **same** resolved address: the client controls both the URL and its authoritative DNS,
     so a resolve-then-let-`urllib`-re-resolve design is a *deterministic* rebinding bypass (the
     validation lookup returns a public IP; `urllib`'s own connect lookup, TTL 0, returns
     `127.0.0.1`). The connection MUST be pinned to the specific validated IP (connect to the
     resolved address while preserving the `Host` header / SNI) so no second, unvalidated
     resolution occurs. This is a blocking acceptance criterion, not a deferred follow-up.
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
    Therefore: the bounded reader MUST **retain the actual raw body byte count** (the length of the
    bytes read from the network, captured *before* decoding) on `FetchResponse` (a new
    `body_byte_count: int` field set from the bounded read in `fetch/http.py`), and the crawl MUST
    accumulate **that exact value** — never a character count or a re-encode — toward
    `MAX_TOTAL_FETCH_BYTES`. Tests MUST include a **non-ASCII multibyte** payload and an
    **invalid-byte** payload (where `errors="replace"` would otherwise under-count) proving the
    aggregate uses raw wire bytes and aborts correctly.
    **Auxiliary-fetch coverage (cycle-3 adversarial re-review).** The crawl also issues auxiliary
    `fetch_page` calls that are NOT appended to `results` — `robots.txt` fetches
    (`fetch/crawl.py` `_robots_allow`) and mdBook TOC-script fetches (`_discover_toc_links`). Each
    is individually bounded by the per-response `MAX_RESPONSE_BYTES` cap and `robots.txt` is cached
    per-origin, so the uncounted amplification is bounded (~`(origins + toc_scripts) ×
    MAX_RESPONSE_BYTES`, none staged to disk) — not an unbounded leak. Still, to make the aggregate
    a true "all transfer for this request" bound, these auxiliary responses' `body_byte_count` MUST
    also accrue to the same `MAX_TOTAL_FETCH_BYTES` running total (so a hostile server cannot amplify
    transfer via oversized-but-under-cap `robots.txt`/TOC payloads outside the budget).
  Cap tasks: the `max_pages` upper bound and the streamed per-response `MAX_RESPONSE_BYTES` cap are
  delivered by harness `064.012-T` + impl `064.013-T` (`app_models.py` / `fetch/http.py`). The
  byte-accurate **aggregate** budget — raw-byte retention on `FetchResponse`, the exact-byte crawl
  accumulator, AND auxiliary-fetch (`robots.txt`/TOC) accrual — is delivered by its own
  width-isolated pair harness `064.016-T` + impl `064.017-T` (`fetch/http.py` / `fetch/crawl.py`),
  isolating the shared-model (`FetchResponse`) blast radius and the non-ASCII/invalid-byte
  accounting tests from the per-dimension caps.
  End-to-end proof: a `tools/call` `fetch` with
  over-limit `max_pages` (rejected `-32602`), an oversized response body (aborted, including on a
  redirect), and a crawl exceeding the aggregate budget (aborted) are asserted in the MCP boundary
  harness `064.014-T`. Caps are set high enough not to break legitimate CLI crawls; the existing
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
(T-agg-h/T-agg-i) that retains the raw body byte count on `FetchResponse` and sums it in the crawl
(split out of the per-dimension cap pair so the shared-model change and the non-ASCII/invalid-byte
tests stay bounded); (ii) a **`fetch` advertising** pair (T-desc-h/T-desc-i) correcting the shared
manifest description to HTTP(S)-only with a parity test; and (iii) a **dual-era protocol** block —
two harnesses (discovery/modern-negotiation, legacy/era-routing) and two impls (modern negotiation,
dual-era routing) implementing MCP `2026-07-28` `server/discover` + per-request `_meta` negotiation +
`-32022` alongside the retained legacy `initialize` handshake (see `## Protocol Era Model`). The
chain grows from 15 to **23** tasks but stays strictly **linear and acyclic**.

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
2. T1b [064.005-T] — Dispatch parity + error-envelope + notification harness (tests domain,
   3 scenarios). `tools/call` fetch + process parity vs `execute_fetch`/`execute_process` with
   `success=False` → `isError` result; error envelopes as one parametrized scenario covering
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
   rejected mid-chain; (c) **address-pinned connect / DNS-rebinding** — when validation-time and
   connect-time resolution differ, the connection uses the validated address (no second
   resolution), and any private address in the validated record set is rejected. Verify red
   [green@T-ssrf-i]. Depends on T1d.
6. T-ssrf-i [064.011-T] — Shared-fetch SSRF connect-time resolution impl (code domain,
   ≤2 files: `fetch/url_policy.py`, `fetch/http.py`). Resolve the host and reject if ANY resolved
   address is loopback/private/link-local/metadata; revalidate every redirect target at connect
   time (not by `netloc` compare); **connect to the specific validated IP (address-pinned),
   preserving the `Host` header / SNI, so `urllib` performs no second unvalidated resolution**
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
   original raw byte length, not the replaced-character length; (c) a crawl whose cumulative
   **raw** bytes exceed the budget is aborted even though the decoded character total stays under
   budget (the undercount-bypass attack). Verify red [green@T-agg-i]. Depends on T-cap-i.
10. T-agg-i [064.017-T] — Raw-byte retention + byte-accurate aggregate accounting impl (code
    domain, ≤2 files: `fetch/http.py`, `fetch/crawl.py`). Add `FetchResponse.body_byte_count: int`
    set from the length of the bytes read by the bounded reader **before decoding** (the
    `body_bytes` already materialized at the streamed read); make the `fetch/crawl.py` aggregate
    accumulator sum that exact `body_byte_count` value and abort the crawl once
    `MAX_TOTAL_FETCH_BYTES` is exceeded. Isolated from T-cap-i so the shared-model
    (`FetchResponse`) blast radius and the non-ASCII/invalid-byte accounting land in one bounded
    task. Turns T-agg-h green. Existing fetch suite stays green. Depends on T-agg-h.
11. T-e2e [064.014-T] — MCP untrusted-fetch end-to-end boundary harness (tests domain,
    3 scenarios). Through `tools/call` fetch (stdin JSON → dispatch → `server.fetch` →
    `execute_fetch`): (a) a public hostname resolving to loopback/private is rejected end-to-end
    (§H6); (b) an over-limit `max_pages` is rejected `-32602` end-to-end (§H7); (c) an oversized
    response (per-response cap incl. redirect) OR a crawl exceeding the aggregate budget is aborted
    end-to-end (§H7). Authored red (no dispatch loop yet). The shared-fetch guards (T-ssrf-i,
    T-cap-i, T-agg-i) already enforce in `execute_fetch`, so once the dispatch loop routes
    `server.fetch` these all go green at **T2** — no separate boundary wiring is required. Depends
    on T-agg-i.
12. T-adapter [064.015-T] — Adapter callable surface + identity accessor (code domain, ≤2 files:
    `src/docline/mcp/server.py` + optionally a versions constant).
    Implement `DoclineMcpServer.call_tool(name, arguments)` (static `{name: bound_method}`
    allow-list, no `getattr`), the NEW `DoclineMcpServer.list_callable_tools()` (callable
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
    (`get_mcp_manifest().tools['fetch'].description`, reached via BOTH `list_tools()` and
    `list_callable_tools()`) states HTTP(S)-only and does **not** claim "file path" / local-file
    support; (b) manifest⇄behavior parity — the advertised input contract matches
    `execute_fetch`'s scheme rejection (`execute_fetch` fails any non-`http`/`https` source), so
    the advertisement cannot promise an input mode the executor rejects. Verify red
    [green@T-desc-i]. Depends on T-adapter.
14. T-desc-i [064.019-T] — `fetch` advertising correction impl (code domain, 1 file:
    `src/docline/app.py`). Correct the shared `fetch` description in `get_mcp_manifest`
    (`app.py:465-468`) to state HTTP(S)-only (e.g. "Fetch a document from an HTTP(S) URL and stage
    it for processing."), fixing the advertisement on BOTH the CLI `--manifest` and the MCP
    `tools/list`/`server/discover` surfaces. No processing behavior change. Turns T-desc-h green.
    Depends on T-desc-h.
15. T2 [064.002-T] — Core stdio transport loop, **legacy-era base** (code domain, ≤2 files:
    `docline/mcp/stdio.py` + entry wiring). Implement `dispatch` + `serve`, request-shape
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
    (both eras), `capabilities`, serverInfo in `_meta`, `resultType:"complete"`; (b) a modern
    request whose `_meta.io.modelcontextprotocol/protocolVersion` = `2026-07-28` is served
    statelessly (no handshake) and the result carries `resultType:"complete"` + serverInfo `_meta`
    (list results also `ttlMs`/`cacheScope`); (c) a request with an unsupported `_meta`
    protocolVersion returns **`-32022`** with `data.supported` (list) + `data.requested`. Verify
    red [green@T-era-i1]. Depends on T2s.
18. T-era-h2 [064.021-T] — Legacy-era retention + era-routing harness (tests domain, 3 scenarios).
    Author failing tests: (a) the legacy `initialize` handshake still returns capabilities +
    `2025-11-25` + serverInfo, `notifications/initialized` is silent, `ping` → `{}`, AND reports the
    **same** identity/capabilities as `server/discover` (single-source `describe_server()` — no
    drift); (b) era routing — a `tools/call` carrying modern `_meta` is served under modern
    semantics with no prior `initialize`, while the same method after `initialize` is served under
    legacy semantics; (c) **modern-path guardrail parity (parametrized)** — a modern (`_meta`, no
    `initialize`) `tools/call` `process`/`fetch` enforces §H1 (`workspace_root` reject `-32602`),
    §H3 (absolute-path sanitization in `isError`), and §H5 (clean stdout) IDENTICALLY to the legacy
    path, proving the guards apply pre-handshake and era routing cannot branch around them. Verify
    red [green@T-era-i2]. Depends on T-era-h1.
19. T-era-i1 [064.022-T] — Modern-era negotiation + modern-branch routing impl (code domain,
    ≤2 files: `docline/mcp/stdio.py` + `src/docline/mcp/server.py`).
    Implement `server/discover` dispatch backed by the `describe_server()` accessor **introduced by
    T-adapter (consume, do not re-introduce)** (supportedVersions, capabilities, serverInfo);
    per-request `_meta` protocol-version extraction + validation; the
    `-32022 UnsupportedProtocolVersionError` envelope (`data.supported` + `data.requested`); the
    modern result shape (`resultType:"complete"`, serverInfo `_meta`, list `ttlMs`/`cacheScope`);
    and **the MODERN branch of the era classifier** (detect modern `_meta` → route to modern
    handlers, served statelessly). Ownership boundary (cycle-3 arch remediation): THIS task owns the
    modern branch — so T-era-h1 scenario (b) "modern request served statelessly" greens HERE —
    while T-era-i2 owns the legacy branch + guard parity + no-drift. Turns T-era-h1 green. Depends
    on T-era-h2 (last dual-era harness authored first).
20. T-era-i2 [064.023-T] — Dual-era routing completion + legacy retention + guard parity (code
    domain, ≤2 files: `docline/mcp/stdio.py` + `src/docline/mcp/server.py`). Implement the **LEGACY
    branch** of the request-shape era classifier (`initialize` → legacy) on top of T-era-i1's modern
    branch, keep the legacy handshake/`ping` path (from T2) intact, and verify no drift — both
    `initialize` and `server/discover` read the single `describe_server()` accessor (from T-adapter),
    so no-drift holds by construction. **Guardrail
    parity (blocking):** both eras MUST funnel every `tools/call`/`process` through the SAME
    hardened dispatch path so §H1/§H3/§H4/§H5 apply before the modern result wrapper — the era
    classifier changes only negotiation + envelope shape, never which guards run (prevents a modern
    pre-handshake `workspace_root` P0 re-open). Turns T-era-h2 green (incl. the modern-path
    guard-parity scenario). Depends on T-era-i1.
21. T2b [064.008-T] — Subprocess smoke-test harness for the entry point (tests domain, 1 scenario).
    Author the failing automated subprocess test (matching `test_manifest_parity.py::`
    `test_python_m_docline_cli_runs_main`) that spawns `python -m docline.mcp` / `docline-mcp`,
    probes `server/discover` then pipes `tools/list` (modern path) — or the legacy
    `initialize`+`tools/list` — then EOF, and asserts clean exit + tool names matching the
    advertised MCP tool set (`docline --manifest` minus the excluded `ingest_local_dir`). Red until
    the entry point exists [green@T3]. Depends on T-era-i2 (the fully hardened dual-era server ships
    in the executable).
22. T3 [064.003-T] — `docline-mcp` entry point + module bootstrap (packaging surface only —
    width-isolated). Add `docline/mcp/__main__.py` (`main()` reusing `DoclineMcpServer` + `serve`)
    and the `[project.scripts]` `docline-mcp` entry (materializes `docline-mcp.exe` on Windows),
    turning the T2b subprocess harness green. No test-infra authoring in this task. Depends on T2b.
23. T4 [064.004-T] — Documentation (docs domain). README "Running the local stdio MCP server"
    section and a `.mcp.json` client example for `docline-mcp`, noting dual-era support
    (modern `server/discover` probe + legacy `initialize` fallback). Do NOT add a separate
    design-doc transport note — the deliberation already documents the transport surface (avoid
    duplication). Depends on T3.

Dependency edges: T1b→T1, T1c→T1b, T1d→T1c, T-ssrf-h→T1d, T-ssrf-i→T-ssrf-h, T-cap-h→T-ssrf-i,
T-cap-i→T-cap-h, T-agg-h→T-cap-i, T-agg-i→T-agg-h, T-e2e→T-agg-i, T-adapter→T-e2e,
T-desc-h→T-adapter, T-desc-i→T-desc-h, T2→T-desc-i, T2s→T2, T-era-h1→T2s, T-era-h2→T-era-h1,
T-era-i1→T-era-h2, T-era-i2→T-era-i1, T2b→T-era-i2, T3→T2b, T4→T3.
Execution order: 064.001 → 064.005 → 064.006 → 064.007 → 064.010 → 064.011 → 064.012 → 064.013 →
064.016 → 064.017 → 064.014 → 064.015 → 064.018 → 064.019 → 064.002 → 064.009 → 064.020 →
064.021 → 064.022 → 064.023 → 064.008 → 064.003 → 064.004.

## Verification

- `pytest tests/parity` green: the new stdio suite (incl. H1–H6/H7 gates and the `-32600`
  request-shape cases) passes. The existing adapter/transport parity suites stay green **because
  `SERVER.list_tools()` is left unchanged (full four-tool manifest)**; the MCP surface uses the
  new `list_callable_tools()`, so `test_manifest_parity.py::test_mcp_server_list_tools_exposes_shared_manifest`
  needs no edit. No existing parity test is rewritten to accommodate the callable subset.
- `pytest tests/fetch` green: the shared-fetch SSRF-by-resolution, per-dimension resource-cap, and
  **byte-accurate aggregate accounting** unit harnesses pass — including the non-ASCII multibyte
  and invalid-byte payloads proving the aggregate cap sums the raw `FetchResponse.body_byte_count`
  (not decoded characters) — and the pre-existing fetch suite remains green under the new bounds
  (caps sized above legitimate use).
- Dual-era protocol conformance (T-era-h1/h2 → T-era-i1/i2): `server/discover` returns a
  `DiscoverResult` (supportedVersions for both eras, capabilities, serverInfo, `resultType`); a
  modern request with a supported `_meta` protocolVersion is served statelessly; an unsupported
  `_meta` protocolVersion returns **`-32022`** with `data.supported`+`data.requested`; the legacy
  `initialize` handshake still works and reports the same identity/capabilities as
  `server/discover` (single-source `describe_server()`); era routing serves modern `_meta`
  requests statelessly and `initialize` requests under legacy semantics.
- **Dual-era guardrail parity (T-era-h2 → T-era-i2):** a modern (`_meta`, no `initialize`)
  `tools/call` `process` with `workspace_root` is rejected `-32602` (§H1), modern-path `isError`
  content sanitizes absolute paths (§H3), and modern-path stdout stays clean (§H5) — identically to
  the legacy path — proving both eras funnel through ONE hardened dispatch and the modern
  pre-handshake surface cannot bypass a guard.
- `fetch` advertising parity (T-desc-h → T-desc-i): the advertised `fetch` description states
  HTTP(S)-only across `tools/list`, `server/discover`, and `docline --manifest`, and matches
  `execute_fetch`'s rejection of non-HTTP(S) sources (no "file path" advertisement).
- JSON-RPC 2.0 conformance: `-32600` returned for a non-object root, a missing/invalid `jsonrpc`,
  and a missing/non-string `method` (parametrized), distinct from `-32700` and `-32601`.
- MCP boundary end-to-end (T-e2e [064.014-T]): a `tools/call` fetch to a hostname resolving to
  loopback/private is rejected (address-pinned connect closes DNS-rebinding); over-limit
  `max_pages` is rejected `-32602`; an oversized response (per-response cap incl. redirect) or a
  crawl exceeding the aggregate `MAX_TOTAL_FETCH_BYTES` budget is aborted. These green at T2 (the
  shared-fetch guards enforce via `execute_fetch`; no separate boundary wiring).
- `ruff check .`, `ruff format --check .`, `pyright src/` clean.
- Automated subprocess smoke (authored red in T2b [064.008-T], turned green by the T3 [064.003-T]
  entry point) replaces manual verification: `docline-mcp` handling a `server/discover` probe (or
  legacy `initialize`) + `tools/list` + EOF, tool names matching the advertised MCP tool set
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
  `FetchResponse` (`body_byte_count`), and the crawl to sum that exact value; the concern is
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
  budget (bounded, not unbounded). Closed by requiring their `body_byte_count` to accrue to the same
  `MAX_TOTAL_FETCH_BYTES` total (§H7 item 3, `064.017-T`).
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

## Rollback

**Not purely additive.** The release unit adds new modules (`docline/mcp/stdio.py`,
`docline/mcp/__main__.py`) and one `[project.scripts]` entry-point line, but it ALSO modifies
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
  count, and the crawl accumulates it toward `MAX_TOTAL_FETCH_BYTES` (064.016/064.017). Additive
  field + accumulator; also affects CLI crawls.
- `src/docline/app.py` — `get_mcp_manifest` `fetch` description corrected to HTTP(S)-only
  (064.019, cycle-3). Text-only advertising change; flows to both `docline --manifest` (CLI) and
  the MCP `tools/list`/`server/discover` surfaces. No processing-behavior change.
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
(064.010–064.013, 064.016–064.017) and the `fetch`-advertising correction (064.019) are
self-contained and revertible on their own.

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
