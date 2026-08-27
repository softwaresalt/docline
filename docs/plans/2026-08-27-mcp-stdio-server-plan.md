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
  Security, Scope, Consistency). See `## Plan Review Remediation`.
- Cross-interface blast radius: this release unit is NOT purely additive. It hardens the
  **shared** fetch code (`fetch/url_policy.py`, `fetch/http.py`, `app_models.py`) that both
  the CLI and the MCP surface call, and it changes the existing `DoclineMcpServer` adapter's
  callable surface. See `## Rollback` and `## Risks`.
<!-- plan-review-attempt: 3 -->

## Scope

In scope:

1. A dependency-free stdio JSON-RPC 2.0 dispatch loop that speaks the minimum MCP method set
   (`initialize`, `notifications/initialized`, `tools/list`, `tools/call`, `ping`) and
   delegates to `DoclineMcpServer`.
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
   as their own width-isolated tasks (see `## Tasks`).

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
  - Method map: `initialize` → capabilities + pinned `protocolVersion` + serverInfo;
    `tools/list` → callable allow-list via `server.list_callable_tools()`; `tools/call` →
    `server.call_tool`; `ping` → `{}` (optional utility, not required for discovery/use).
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
    `max_pages` upper bound (enforced in the shared `FetchRequest` model) and a streamed
    per-response byte cap (`MAX_RESPONSE_BYTES`) enforced in `fetch/http.py` on the initial
    response AND every redirect hop — replacing the unbounded `response.read()`. These live in
    shared fetch code (see §H7 and the shared-fetch tasks), not in the transport module.
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
  3. **Aggregate crawl-byte budget.** Per-response and per-page caps do not bound their product: a
     single small `tools/call` `fetch` at the `max_pages` cap against an attacker-controlled server
     returning maximum-under-cap responses drives `max_pages × MAX_RESPONSE_BYTES` of network
     transfer and disk staging (each page is written under `output_dir` by `execute_fetch`). The
     crawl loop (`fetch/crawl.py`) MUST enforce a hard **aggregate** `MAX_TOTAL_FETCH_BYTES` budget
     across all pages of a request and abort the crawl once the running total is exceeded (bound the
     product, not each dimension).
  Delivered by the shared-fetch resource-cap tasks (harness `064.012-T`, impl `064.013-T` in
  `app_models.py`/`fetch/http.py`/`fetch/crawl.py`). End-to-end proof: a `tools/call` `fetch` with
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
proofs live in a dedicated boundary harness. The chain stays strictly **linear and acyclic**.

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
7. T-cap-h [064.012-T] — Shared-fetch resource-cap harness (tests domain, 3 scenarios). Unit
   tests in `tests/fetch/`: (a) `FetchRequest.max_pages` above the hard cap is rejected at model
   validation; (b) per-response byte cap (parametrized: initial + redirect) — a body exceeding
   `MAX_RESPONSE_BYTES` is aborted without full buffering (streamed, not a single `response.read()`);
   (c) aggregate `MAX_TOTAL_FETCH_BYTES` — a crawl whose cumulative bytes exceed the budget is
   aborted. Verify red [green@T-cap-i]. Depends on T-ssrf-i.
8. T-cap-i [064.013-T] — Shared-fetch resource-cap impl (code domain, 3 files for one cohesive
   resource-cap concern — each edit minimal: `app_models.py` `max_pages` upper bound
   (`Field(le=…)`); `fetch/http.py` streamed `MAX_RESPONSE_BYTES` read (initial + redirect),
   replacing the unbounded `response.read()`; `fetch/crawl.py` aggregate `MAX_TOTAL_FETCH_BYTES`
   accumulator that aborts the crawl). Turns T-cap-h green. Existing fetch suite stays green (caps
   sized above legitimate use). Depends on T-cap-h.
9. T-e2e [064.014-T] — MCP untrusted-fetch end-to-end boundary harness (tests domain,
   3 scenarios). Through `tools/call` fetch (stdin JSON → dispatch → `server.fetch` →
   `execute_fetch`): (a) a public hostname resolving to loopback/private is rejected end-to-end
   (§H6); (b) an over-limit `max_pages` is rejected `-32602` end-to-end (§H7); (c) an oversized
   response (per-response cap incl. redirect) OR a crawl exceeding the aggregate budget is aborted
   end-to-end (§H7). Authored red (no dispatch loop yet). The shared-fetch guards (T-ssrf-i,
   T-cap-i) already enforce in `execute_fetch`, so once the dispatch loop routes `server.fetch`
   these all go green at **T2** — no separate boundary wiring is required. Depends on T-cap-i.
10. T-adapter [064.015-T] — Adapter callable surface (code domain, ≤2 files: `src/docline/mcp/server.py`).
    Implement `DoclineMcpServer.call_tool(name, arguments)` (static `{name: bound_method}`
    allow-list, no `getattr`) and the NEW `DoclineMcpServer.list_callable_tools()` (callable
    allow-list manifest; `ingest_local_dir` excluded; `process` `inputSchema` omits `workspace_root`,
    built at build time). `list_tools()` is left **unchanged**; document the adapter invariant that
    `list_tools()` is the manifest-parity accessor only and `list_callable_tools()` is the sole MCP
    advertise source. Greens the adapter-level assertions in T1 (list_callable_tools parity,
    dispatchability, list_tools-unchanged, invariant). Depends on T-e2e (last harness authored
    first). Split from T2 so the transport task stays at ≤4 functions.
11. T2 [064.002-T] — Core stdio transport loop (code domain, ≤2 files: `docline/mcp/stdio.py` +
    entry wiring). Implement `dispatch` + `serve`, request-shape validation returning **`-32600`**,
    the bounded binary frame read/drain helper AND its runtime enforcement (§H2), the method map
    (`tools/list` via `server.list_callable_tools()`; `tools/call` via `server.call_tool`), id-less
    notification, and `success=False` → `isError` mapping. Greens T1 transport assertions, T1b, the
    H2 scenario in T1c, the H6-literal scenario in T1d, and **all of T-e2e** (the shared-fetch guards
    enforce automatically once fetch is routed). Depends on T-adapter. The remaining stdio runtime
    guardrails (H1/H3/H4/H5) are delivered by T2s.
12. T2s [064.009-T] — Stdio runtime guardrails H1/H3/H4/H5 (code domain). Implement the
    `workspace_root` dispatcher-level runtime reject (`-32602`) per §H1 (the build-time `inputSchema`
    omission is delivered by T-adapter; `extra="forbid"` does not catch a real model field, so an
    explicit pre-construction reject is required); generic non-reflective error text on envelope AND
    `isError` (§H3); fail-closed unknown tools (§H4); child-stdout redirect (§H5). Greens the H1/H3
    scenarios in T1c and the H4/H5 scenarios in T1d. **No fetch-guard wiring** — the §H6/§H7 guards
    live in the shared fetch call path and enforce automatically (greened at T2). Split from T2 so
    neither task breaches the 2-hour/<5-function rule. Depends on T2.
13. T2b [064.008-T] — Subprocess smoke-test harness for the entry point (tests domain, 1 scenario).
    Author the failing automated subprocess test (matching `test_manifest_parity.py::`
    `test_python_m_docline_cli_runs_main`) that spawns `python -m docline.mcp` / `docline-mcp`,
    pipes `initialize`+`tools/list` then EOF, and asserts clean exit + tool names matching the
    advertised MCP tool set (`docline --manifest` minus the excluded `ingest_local_dir`). Red until
    the entry point exists [green@T3]. Depends on T2s (the fully hardened server ships in the executable).
14. T3 [064.003-T] — `docline-mcp` entry point + module bootstrap (packaging surface only —
    width-isolated). Add `docline/mcp/__main__.py` (`main()` reusing `DoclineMcpServer` + `serve`)
    and the `[project.scripts]` `docline-mcp` entry (materializes `docline-mcp.exe` on Windows),
    turning the T2b subprocess harness green. No test-infra authoring in this task. Depends on T2b.
15. T4 [064.004-T] — Documentation (docs domain). README "Running the local stdio MCP server"
    section and a `.mcp.json` client example for `docline-mcp`. Do NOT add a separate design-doc
    transport note — the deliberation already documents the transport surface (avoid duplication).
    Depends on T3.

Dependency edges: T1b→T1, T1c→T1b, T1d→T1c, T-ssrf-h→T1d, T-ssrf-i→T-ssrf-h, T-cap-h→T-ssrf-i,
T-cap-i→T-cap-h, T-e2e→T-cap-i, T-adapter→T-e2e, T2→T-adapter, T2s→T2, T2b→T2s, T3→T2b, T4→T3.
Execution order: 064.001 → 064.005 → 064.006 → 064.007 → 064.010 → 064.011 → 064.012 → 064.013 →
064.014 → 064.015 → 064.002 → 064.009 → 064.008 → 064.003 → 064.004.

## Verification

- `pytest tests/parity` green: the new stdio suite (incl. H1–H6/H7 gates and the `-32600`
  request-shape cases) passes. The existing adapter/transport parity suites stay green **because
  `SERVER.list_tools()` is left unchanged (full four-tool manifest)**; the MCP surface uses the
  new `list_callable_tools()`, so `test_manifest_parity.py::test_mcp_server_list_tools_exposes_shared_manifest`
  needs no edit. No existing parity test is rewritten to accommodate the callable subset.
- `pytest tests/fetch` green: the shared-fetch SSRF-by-resolution and resource-cap unit harnesses
  pass, and the pre-existing fetch suite remains green under the new bounds (caps sized above
  legitimate use).
- JSON-RPC 2.0 conformance: `-32600` returned for a non-object root, a missing/invalid `jsonrpc`,
  and a missing/non-string `method` (parametrized), distinct from `-32700` and `-32601`.
- MCP boundary end-to-end (T-e2e [064.014-T]): a `tools/call` fetch to a hostname resolving to
  loopback/private is rejected (address-pinned connect closes DNS-rebinding); over-limit
  `max_pages` is rejected `-32602`; an oversized response (per-response cap incl. redirect) or a
  crawl exceeding the aggregate `MAX_TOTAL_FETCH_BYTES` budget is aborted. These green at T2 (the
  shared-fetch guards enforce via `execute_fetch`; no separate boundary wiring).
- `ruff check .`, `ruff format --check .`, `pyright src/` clean.
- Automated subprocess smoke (authored red in T2b [064.008-T], turned green by the T3 [064.003-T]
  entry point) replaces manual verification: `docline-mcp` handling an
  `initialize`+`tools/list`+EOF, tool names matching the advertised MCP tool set (`docline
  --manifest` minus the excluded `ingest_local_dir`).

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
- `src/docline/app_models.py` + `src/docline/fetch/http.py` + `src/docline/fetch/crawl.py` —
  resource caps (§H7): `max_pages` upper bound, streamed `MAX_RESPONSE_BYTES` read, and aggregate
  `MAX_TOTAL_FETCH_BYTES` crawl budget. Also affects CLI fetch.
- `pyproject.toml` — `[project.scripts]` entry.

Rollback = revert the feature branch. There is no data migration and no persisted-schema change, but
because the shared-fetch and adapter changes touch existing runtime paths, a rollback restores the
prior (weaker) SSRF/resource behavior on BOTH interfaces — reviewers must treat this as a
cross-interface change, not an isolated new transport. The MCP-only additions (stdio loop, adapter
callable surface, entry point) can be reverted independently of the shared-fetch hardening if only
the transport needs backing out; the shared-fetch tasks (064.010–064.013) are self-contained and
revertible on their own.

## Risks

- Medium: shared-fetch hardening (§H6/§H7) changes existing CLI `docline fetch` behavior — a
  hostname that resolves to a private address, or a crawl exceeding the new `max_pages`/response-byte
  /aggregate caps, now fails where it previously succeeded. Mitigated by sizing caps above legitimate
  use and keeping the existing `tests/fetch` suite green (or deliberately updating it for the new bound).
- Low: address-pinned connect (§H6) connects to a validated IP while preserving the `Host` header /
  SNI; verify TLS certificate validation still targets the hostname (not the IP) so pinning does not
  weaken cert checks. Covered by the SSRF harness (064.010-T).
- Low: stdout contamination would corrupt the JSON-RPC stream — mitigated by routing all logs
  to stderr and asserting clean stdout framing in tests.
- Low: manifest drift between CLI and MCP — mitigated by the T1 parity assertion against the
  single shared manifest source (callable allow-list), with `list_tools()` retained for full-manifest
  parity.
