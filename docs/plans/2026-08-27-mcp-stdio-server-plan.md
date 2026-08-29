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
  request-amplification bound** (a `MAX_FETCH_ATTEMPTS = 4000` request-count bound + a `MAX_DEPTH_LIMIT = 64`
  `FetchRequest.depth` upper bound — the count-bound mechanism was later reworked in cycle-11, see below),
  split into a NEW width-isolated pair 064.025-T/064.026-T (chain
  grows 24 → 26, `064.024 → 064.025 → 064.026 → 064.014`), and the **interactive stdio-liveness**
  contract (064.008-T interactive `Popen` smoke + 064.002-T serve() non-greedy `read1`/`os.read` +
  stdout flush) that detects live deadlocks an EOF-first smoke masks.
  Cycle-9 (PR #166, fresh review on HEAD 546a256, round 3 of the second three-cycle allowance)
  reconciles two further threads: the JSON-RPC request-shape contract now validates the `id` type per
  MCP 2026-07-28 `RequestId` (a present `id` that is an object/array/bool/null → `-32600`, never
  echoed, `id:null` frame; an absent id on an OTHERWISE-VALID request stays a notification, but an
  absent id on a MALFORMED payload — non-object root, bad/missing `jsonrpc`, or missing/non-string
  `method` — is a `-32600`/`id:null` error, NOT suppression), specified once in the shared
  pre-routing `dispatch()` guard and inherited by both eras (asserted for the legacy/shared path in
  064.005-T and for the modern path in 064.021-T scenario (c), implemented in 064.002-T with a
  shape-before-`_meta`/era ordering criterion in 064.022-T, + feature DoD),   and the two intended `informs`
    relationships on `061.001-T` are kept durable in a tracked `links:` frontmatter block (the
    git-ignored `item_links` DB cache is reconstructed from it on sync, not the reverse). No new task (manifest stays 26).
  Cycle-10 (PR #166, fresh review on HEAD 62df1b7, round 3 of the second three-cycle allowance)
  reconciles two further threads confirmed against actual `urllib` redirect + Python JSON behavior:
  (A) the existing single `_ValidatingRedirectHandler` is extended (all `http_error_301/302/303/307/308`
  aliases rebound; ONE composite handler) to bounded-read/count every INTERMEDIATE 3xx redirect body
  (urllib's in-handler unbounded `fp.read()` bypassed both the
  per-response `MAX_RESPONSE_BYTES` cap and the aggregate `MAX_TOTAL_FETCH_BYTES` budget), split into
  a NEW width-isolated pair 064.027-T/064.028-T (chain grows 26 → 28,
  `064.026 → 064.027 → 064.028 → 064.014`); and (B) strict `parse_constant` rejection of the non-finite
  JSON constant TOKENS `NaN`/`Infinity`/`-Infinity` → `-32700`, plus a `math.isfinite()` id guard
  rejecting overflow literals (`1e400` → `inf`) → `-32600`, both before era routing, so
  no non-finite number can enter `RequestId` or response serialization (in-place strengthening of
  064.002-T impl + 064.005-T harness, no new task).
  Cycle-11 (PR #166, fresh review on HEAD f172806, round 2 of the third three-cycle allowance)
  reconciles two further threads: (A) the §H7 **item 4** request-count bound is REWORKED — the cycle-8
  `fetch/crawl.py` frontier-pop counter did NOT bound actual outbound requests (robots, TOC, retries,
  and redirect hops bypass a main-page-pop counter, and the byte budgets bound VOLUME not COUNT), so it
  is REPLACED by a request-scoped fetch-attempt budget enforced at the common `fetch_page` boundary
  (`fetch/http.py`) that debits every outbound attempt AND redirect hop (main pages, robots, TOC,
  retries, redirects), riding the existing `RemainingByteBudget` threading and raising
  `FetchAttemptBudgetExceededError` (a subclass of `AggregateBudgetExceededError`) so the existing
  `crawl.py` re-raise clauses propagate it — 064.025-T/064.026-T re-scoped in place (impl file set
  `fetch/crawl.py` → `fetch/http.py`, still 2 files; chain, membership, and order unchanged); and (B)
  `server/discover` is routed through the SAME modern `_meta` validator as every modern request —
  a valid discovery request MUST supply BOTH `io.modelcontextprotocol/protocolVersion` AND
  `io.modelcontextprotocol/clientCapabilities`, missing/malformed → `-32602` (unsupported version →
  `-32022`, version-first), while still requiring NO prior `initialize` (pre-handshake availability
  does not waive required `_meta`) — reconciled across 064.020-T/064.022-T, the Protocol Era Model,
  method map, feature DoD, and memory (no new task).
  Cycle-12 (PR #166, fresh Copilot review on HEAD `13b14b7`, Copilot round 3) routes two redirect
  residuals through a full Stage decomposition rather than an in-place fix: (A) the cycle-10 bounded
  redirect-body proxy delegated to `super().http_error_302` can LEAK the intermediate 3xx response
  `fp` when a per-response or aggregate cap error interrupts the drain before stdlib reaches its own
  `fp.close()` — the override MUST now CLOSE the intermediate `fp` on BOTH cap-breach paths (delivered
  by re-scoped 064.027-T/064.028-T); and (B) the cycle-11 redirect-hop `MAX_FETCH_ATTEMPTS` debit was
  placed in `http_error_302` BEFORE `super()`, charging an attempt even for redirects that
  scheme/loop/§H6 validation REJECTS before `parent.open()` — the debit MOVES into `redirect_request`
  on the successful non-None-return path (after validation, before outbound I/O), decomposed into a
  NEW width-isolated pair 064.029-T (harness) / 064.030-T (impl). The redirect responsibilities are now
  two width-isolated test-first pairs: body-drain + closure (064.027/028) and hop-attempt placement
  (064.029/030). The chain grows 28 → 30 tasks (`064.026 → 064.027 → 064.028 → 064.029 → 064.030 →
  064.014`, with `064.014-T` re-pointed from `064.028-T` to `064.030-T`); shipment `055-S` = 064-F + 30
  tasks (31 members).
  See `## Plan Review Remediation` (cycle-3, cycle-4, cycle-5, cycle-6, cycle-7, cycle-8, cycle-9, cycle-10, cycle-11, and cycle-12 subsections), and the later `### Cycle-13`–`### Cycle-16` sections (post-decomposition cycles: §H8 gate, exact-token hardening, and the cycle-16 id-less-notification reconciliation + sitemap-CGNAT work item).
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
   - **Modern era (`2026-07-28`):** `server/discover` (MUST), `tools/list`, and `tools/call` — all
     served statelessly with per-request `_meta` carrying BOTH
     `io.modelcontextprotocol/protocolVersion` AND `io.modelcontextprotocol/clientCapabilities`
     (`server/discover` itself is routed through the same `_meta` validator even though it needs no
     prior `initialize`; cycle-11);
     unsupported versions return `-32022 UnsupportedProtocolVersionError` and missing/malformed
     `clientCapabilities` returns `-32602` (checked after version); results carry
     `resultType:"complete"` and `_meta.io.modelcontextprotocol/serverInfo`; list results AND the
     `DiscoverResult` (a `CacheableResult`) carry `ttlMs`/`cacheScope`.
   - **Era routing:** a request whose `_meta` carries a namespaced modern negotiation member
     (`io.modelcontextprotocol/protocolVersion`, equivalently `io.modelcontextprotocol/clientCapabilities`),
     or a `server/discover` (modern-only), is served under modern semantics; an
     `initialize` request latches legacy semantics, and a subsequent request lacking a modern
     negotiation member (including one carrying only ancillary `_meta`) stays legacy. Authoritative basis: MCP spec
     `2026-07-28` (`server/discover.mdx`, `basic/versioning.mdx`, `basic/transports/stdio.mdx`)
     — verified against the official spec repository, see `## Protocol Era Model`.
2. A `docline-mcp` console-script entry point and `python -m docline.mcp` bootstrap.
3. Protocol + dual-interface parity tests (test-first).
4. Operator/agent documentation: README run section + a self-contained client MCP configuration
   example in the documented GitHub Copilot / VS Code `.vscode/mcp.json` `servers` stdio format (a
   verifiable shape; NOT the repo's git-ignored `.mcp.json`), PLUS a concise top-level
   `docs/ARCHITECTURE.md` domain/dependency map for the new stdio transport, the `docline-mcp`
   executable bootstrap, and the adapter boundary (boundaries + direction only, no duplicated
   rationale; per `.github/instructions/architecture-doc.instructions.md`). (No separate
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
    **Interactive liveness (cycle-8; in-process red predecessor added cycle-16 round-2):** frames
    are read with a NON-GREEDY primitive (`read1` on the injected stdin stream / `os.read`,
    returning as soon as any bytes are available and never blocking to fill a whole
    `CHUNK_SIZE`) and stdout is FLUSHED after EVERY response frame, so an interactive client that
    sends one frame, awaits its response, then sends the next — with stdin still OPEN (the T2b
    [`064.008-T`] live subprocess smoke test) — never deadlocks. A greedy `read(CHUNK_SIZE)` that
    waits for the full chunk after a short frame, or a block-buffered stdout that withholds the
    response until the pipe closes, would live-lock that probe; an EOF-first test would mask it.
    Because `serve()` takes injected `stdin`/`stdout` streams and uses their `read1`/`flush`, the
    liveness property has an IN-PROCESS red predecessor in T1 [`064.001-T`] — an instrumented
    non-greedy stdin + flush-recording stdout that withholds the second frame until the first
    response is flushed — so the property is observed RED before it is implemented here (T2), not
    only via the downstream `064.008-T` subprocess smoke.
  - `dispatch(message: dict, server: DoclineMcpServer) -> dict | None` — pure function mapping a
    single JSON-RPC request to a response dict (or `None` ONLY for a well-formed request that lacks
    an `id` — a genuine JSON-RPC notification; handled generically, no per-notification special case).
    A malformed id-less payload — a non-object root, a bad/missing `jsonrpc`, or a missing/non-string/empty
    `method` (e.g. `{"jsonrpc":"2.0"}` with no `method` and no `id`) — is NOT a notification: it
    returns a `-32600` (`id:null`) envelope, never `None`. Unit-testable without stdio.
  - Request-shape validation (`-32600`): after a frame parses as JSON, the decoded value MUST be
    validated as a JSON-RPC 2.0 request object BEFORE method routing. A syntactically valid JSON
    payload that is not a valid request — a non-object root (array, string, number, bool, null),
    a missing or non-`"2.0"` `jsonrpc` member, a `method` that is not a present, non-empty string
    (absent, non-string, or empty-string `""` — the SINGLE `method` predicate applied identically
    by both the shape guard and the notification precondition below; a whitespace-only string is a
    valid `method` and routes to `-32601`, not `-32600`), or a present `id`
    whose JSON type is not a string or number — returns an
    **Invalid Request** `-32600` envelope, distinct from the `-32700` parse error (invalid JSON)
    and `-32601` method-not-found (well-formed request, unknown method). Restoring `-32600` keeps
    the advertised JSON-RPC 2.0 surface spec-compliant. The pre-suppression shape guard inspects ONLY
    `{root, jsonrpc, method, id-type}`; `params` structural validation is POST-suppression and applies
    only to id-bearing requests (mapped to `-32602`), so a no-id notification with malformed `params`
    stays silent (JSON-RPC 2.0: "the Server MUST NOT reply to a Notification, including errors"), never
    a spurious `-32600`. An ARRAY root is `-32600` (not a batch): MCP 2026-07-28 does NOT support
    JSON-RPC batching (removed in the 2025-06-18 revision), so the transport reads one frame → one
    Request object and a non-object array is an invalid single request → a single `-32600` (`id:null`),
    never a per-element batch response.
    Per the MCP 2026-07-28 `RequestId` definition, a request `id`, when present, MUST be a JSON
    string or number; an `id` that is an object, array, boolean, or `null` is an invalid request
    (`-32600`) and MUST NOT be echoed back into the response — the error frame carries `id: null`.
    Response-`id` rule (JSON-RPC 2.0): a `-32600` carries `id: null` ONLY when the id is undetectable —
    absent, or itself malformed/non-finite; when a VALID present `id` (string or finite number)
    accompanies a NON-id defect (missing/empty `method`, bad/missing `jsonrpc`), that valid id is
    ECHOED in the `-32600` frame so strict clients can still correlate the response (a non-object root
    cannot carry an id, so it remains `id: null`).
    Notification suppression is evaluated ONLY AFTER request-shape validation passes: an ABSENT `id`
    makes an OTHERWISE-VALID request (object root, `jsonrpc` `"2.0"`, non-empty string `method`) an
    id-less notification (silent, handled generically). Id-absence is decided by KEY MEMBERSHIP
    (`"id" not in message`), NOT truthiness — a present `id: 0` or `id: ""` is a valid RequestId and
    gets a normal echoed response, never silent suppression. An absent `id` on a MALFORMED payload — a
    non-object root (`[]`/`42`/`"s"`/`true`/`null`), a bad/missing `jsonrpc`, or a missing/non-string/empty
    `method` (e.g. `{"jsonrpc":"2.0"}`) — does NOT suppress the response: it returns `-32600` with
    `id:null`. This is distinct from a
    present `null` id (which is a `-32600` invalid request, never a notification). A present *numeric*
    `id` that is not finite (an overflow literal such as `1e400`, which `json.loads` parses to
    `float('inf')` WITHOUT invoking `parse_constant`) is likewise an invalid `RequestId` → `-32600`
    with `id:null`, via a `math.isfinite()` clause in the same request-shape guard. Because this
    request-shape validation runs in the single shared `dispatch()` BEFORE `_meta` extraction, era
    classification, method routing, AND the id-absent notification-suppression branch, both the
    legacy and modern eras inherit the id-type guard
    identically and cannot echo a malformed id: a malformed id short-circuits to `-32600` (`id:null`)
    and never surfaces as `-32022`/`-32602`/`-32601` or a wrapped modern result (this pre-routing
    ordering is test-bound for the modern path in `064.021-T` scenario (c) and made an explicit
    acceptance criterion in `064.022-T`).
  - Method map (dual-era — see `## Protocol Era Model`):
    - **Legacy era:** `initialize` → capabilities + legacy `protocolVersion` (`2025-11-25`) +
      serverInfo; `notifications/initialized` → silent; `ping` → `{}` (legacy-only utility,
      removed in the modern era).
    - **Modern era:** `server/discover`, `tools/list`, and `tools/call` are all served statelessly
      with the per-request `_meta` carrying BOTH `io.modelcontextprotocol/protocolVersion` AND
      `io.modelcontextprotocol/clientCapabilities` (no prior handshake) and are validated by the SAME
      `_meta` validator: an unsupported protocol version returns `-32022`, and a request with
      missing/malformed `clientCapabilities` returns `-32602` (validated only after version is
      accepted, so version negotiation takes precedence). `server/discover` is **not** exempt — it is
      a modern method that requires both `_meta` members even though it needs no prior `initialize`
      (pre-handshake availability does not waive required `_meta`; cycle-11) — and returns a
      `DiscoverResult` (supportedVersions, capabilities, serverInfo in `_meta`, `resultType:"complete"`,
      and — since `DiscoverResult` is a `CacheableResult` — `ttlMs`/`cacheScope`) via a single adapter
      accessor. Modern results carry `resultType:"complete"` + serverInfo `_meta` (list results also
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
    up to a hard `MAX_FRAME_BYTES` cap (pinned to `1 MiB` = `1_048_576` payload bytes; see the §H2
    Selected numeric limit) while scanning for the newline terminator: as soon as the
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
    Memory stays bounded even for an unterminated or chunked-oversized input. The frame parse
    (`json.loads`) passes a `parse_constant` callback that rejects Python's permissive non-finite
    JSON tokens (`NaN`/`Infinity`/`-Infinity`) as a `-32700` parse error, and the parse-error
    handler catches `ValueError` AND `RecursionError` (deeply nested JSON raises `RecursionError`,
    a `RuntimeError` subclass that `json.JSONDecodeError` handling would miss) so one hostile
    message degrades to an envelope rather than crashing the loop. Response serialization uses
    `json.dumps(..., allow_nan=False)` and degrades a serialization `ValueError` to a `-32603`
    envelope rather than emitting a non-JSON token or crashing the loop.
  - Error envelopes: `-32700` parse error (invalid JSON, including the non-finite `NaN`/`Infinity`/
    `-Infinity` tokens rejected via `parse_constant`), `-32600` invalid request (valid JSON
    but not a valid request object — see request-shape validation above, including a non-finite
    numeric `id` from an overflow literal), `-32601` method not
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
    the **entity-body** bytes are read (aborting mid-read; counting retried failures and ancillary
    robots/TOC fetches), with the `body_byte_count` (undecoded entity-body bytes) also retained on
    `FetchResponse` for completed-terminal-response accounting. These live in shared fetch code (see §H7 and the shared-fetch tasks),
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
| Discovery | `tools/list` after handshake | `server/discover` (MUST) returns supportedVersions + capabilities + serverInfo + cache metadata (`ttlMs`/`cacheScope` — `DiscoverResult` is a `CacheableResult`); answerable before any `initialize` but still routed through the modern `_meta` validator — MUST carry BOTH `protocolVersion` AND `clientCapabilities` (cycle-11) |
| Version mismatch | n/a (handshake pins) | `-32022 UnsupportedProtocolVersionError` with `data.supported` + `data.requested`; missing/malformed `clientCapabilities` → `-32602` (checked after version) |
| Result shape | plain result | `resultType:"complete"` + serverInfo in result `_meta`; list results AND the `DiscoverResult` carry `ttlMs`/`cacheScope` |
| `ping` | supported | removed |

- **Era routing (server-selected — discriminator: namespaced modern negotiation member, cycle-16
  round-1).** The era is NOT selected by the mere presence of per-request `_meta`: a retained
  `2025-11-25` legacy client legitimately carries **ancillary** `_meta` (e.g. `_meta.progressToken`)
  that has nothing to do with 2026 negotiation, so keying on any `_meta` would misroute it to the
  modern validator and reject it. A request is **modern** when its `_meta` carries a namespaced modern
  negotiation member — canonically `io.modelcontextprotocol/protocolVersion` (equivalently
  `io.modelcontextprotocol/clientCapabilities`), detected by **key membership, not truthiness** so a
  present-but-malformed member still routes to the modern validator (→ `-32602`/`-32022`), never
  falls through to legacy — or when it is a `server/discover` (a **modern-only** method). The modern
  branch is **request-stateless** (it never consults prior session state). An `initialize` request
  selects **legacy semantics for the stdio process** by latching a per-process legacy-era selection
  that governs subsequent requests lacking a modern negotiation member. A
  `server/discover` call is answerable before any `initialize` (stdio probe), but — as a **modern,
  modern-only method** — it is routed through the SAME per-request `_meta` validator as every modern
  request and MUST carry BOTH `io.modelcontextprotocol/protocolVersion` AND
  `io.modelcontextprotocol/clientCapabilities` (unsupported version → `-32022`; then missing/malformed
  `clientCapabilities` → `-32602`); pre-handshake availability does **not** waive required `_meta`
  (cycle-11). The request-shape classifier resolves the era in this precedence: (1) a namespaced
  modern negotiation member present (`io.modelcontextprotocol/protocolVersion` or
  `io.modelcontextprotocol/clientCapabilities`), or a `server/discover` (modern-only) → **modern**
  (stateless, `_meta`-validated — a modern method arriving without valid `_meta` is rejected
  `-32602`/`-32022`, never dispatched) — this precedence holds **even after** a legacy latch is set, so
  a `protocolVersion`-bearing request following an `initialize` is still served modern; (2) otherwise,
  `initialize` → set the per-process legacy latch and serve legacy; (3) any other operation lacking a
  modern negotiation member (whether it carries only ancillary `_meta` such as `_meta.progressToken`,
  or no `_meta` at all) is served **legacy only when the legacy latch is already set** — a retained
  legacy client's ancillary `_meta` stays on the legacy path, never routed to modern validation — and
  is **rejected** (an error result, never dispatched) when it arrives **before** that `initialize`
  selection. An operation lacking a modern negotiation member is therefore never silently classified as
  legacy before initialization, and a malformed modern request cannot bypass the required `_meta`
  validation by falling through to the legacy path. Dedicated **pre-initialize operation tests** assert
  the reject for both a metadata-free operation AND an ancillary-`_meta`-only operation. The legacy
  handshake selects the process era; ancillary `_meta` presence never opens either era.
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
  to an error envelope; the loop survives hostile input.
  **Selected numeric limit (H2 transport, cycle-16 round-2 — review-mandated concrete value,
  comment 3885888241): `MAX_FRAME_BYTES = 1 * 1024 * 1024 = 1_048_576`** (1 MiB). This is an
  explicit OPERATIONAL / COMPATIBILITY bound for the untrusted stdio request channel, NOT a
  protocol-derived maximum: docline MCP request frames carry control-plane data only — a URL +
  crawl options (`fetch`), `staging_dir`/`output_dir`/`workspace_root` paths + `pdf_engine`/
  `pdf_mode` enums + boolean flags (`process`), no arguments (`export_schema`), and the
  `initialize`/`server/discover`/`tools/list`/`ping` handshakes — and NO tool accepts inline
  document bytes (`ProcessRequest`/`FetchRequest` carry paths/URL, never content); JSON-RPC batch
  arrays are unsupported (a non-object root is rejected `-32600`). 1 MiB therefore accommodates any
  realistic docline request (including a large `initialize`/`clientCapabilities` `_meta` block)
  while bounding per-frame memory on the untrusted boundary. **Boundary (exact — mirrors the
  `MAX_RESPONSE_BYTES` crossing-byte pattern):** `MAX_FRAME_BYTES` counts the frame's payload bytes
  BEFORE the `\n` terminator (the delimiter is excluded). A frame of up to and including exactly
  `1_048_576` payload bytes followed by `\n` is accepted and dispatched (**exact-N acceptance**);
  each boundary read requests at most `min(CHUNK_SIZE, MAX_FRAME_BYTES - buffered_payload + 1)` so
  the reader observes at most the single crossing byte. The first non-`\n` byte beyond `1_048_576`
  (payload byte **N+1**) trips overflow: the oversized accumulation is DISCARDED (not decoded), an
  error envelope is emitted, and the remainder of the oversized frame is drained in bounded
  `CHUNK_SIZE` chunks to the next `\n`/EOF, after which the loop **resynchronizes** on the next
  valid frame (carry-over preserved). Bounded-**memory** only: per-read allocation and buffered
  bytes are bounded (at most `MAX_FRAME_BYTES + 1` for an accepted-then-crossing frame; the
  oversized remainder is never retained), but total drain bytes/time are NOT bounded for a client
  that never sends `\n` (the same exposure as a client that opens stdin and never completes a
  frame); resynchronization is guaranteed only once `\n`/EOF arrives. Revisit trigger: if a future
  MCP tool accepts inline content or JSON-RPC batch arrays, re-evaluate this bound. Tests: (a)
  oversized single line; (b)
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
  1. **Resolution/connect-time validation (fail-closed public-unicast allow policy).** Before
     connecting, resolve the host and reject if **any** resolved address (all A/AAAA records) is
     **not** a global public-unicast address — i.e. loopback, private (RFC 1918 / RFC 4193),
     link-local, **multicast**, **reserved**, **unspecified** (`0.0.0.0` / `::`), or a metadata
     address (`169.254.169.254`) — **failing closed** on any address that cannot be classified.
     **Normalize IPv4-mapped IPv6 (`::ffff:a.b.c.d`) to its embedded IPv4 form BEFORE applying any
     class predicate** — mapped multicast/CGNAT/reserved forms (`::ffff:224.0.0.1`,
     `::ffff:100.64.0.1`) do not trigger the IPv6-form predicates. Enumerate **all** `getaddrinfo`
     answers, reject the whole target if **any** is unsafe, then pin the connection to one member of
     the fully validated set (see item 3). This rejected set is **normative and self-contained** —
     it mirrors the class predicates of the shared classifier `_is_unsafe_address`
     (`src/docline/fetch/sitemap.py:173-189`: metadata IPs, then `is_private` / `is_loopback` /
     `is_link_local` / `is_multicast` / `is_reserved` / `is_unspecified`, unclassifiable → unsafe)
     **and additionally rejects CGNAT (`100.64.0.0/10`) via an explicit network-membership check
     and ULA (`fc00::/7`)**, because CGNAT is caught by none of those six flags on any Python
     3.12.x (`is_private` / `is_reserved` / `is_global` all `False`). H6 therefore MUST be at least
     as strict as — and is deliberately broader than — `_is_unsafe_address` (whose own CGNAT gap is
     a separate tracked code follow-up in `## Risks`, out of scope for this planning
     reconciliation). Because `ipaddress` flag tables are Python-patch-dependent (CVE-2024-4032
     hardened `is_private` in 3.12.4), the `064.010-T` harness MUST **test-pin each security-critical
     class** rather than trust the installed flag table. Literal-IP hosts keep their existing
     fast-path rejection. This closes the name→private gap `is_private_host` leaves open.
  2. **Redirects revalidated.** Every redirect target is re-resolved and re-validated at
     connect time, not just compared by `netloc`, so a redirect to a name that resolves to a
     private address is rejected mid-chain.
  3. **Address-pinned connect (in-scope, closes DNS-rebinding).** Validation and connection MUST
     use the **same** resolved address: the client controls both the URL and its authoritative DNS,
     so a resolve-then-let-`urllib`-re-resolve design is a *deterministic* rebinding bypass (the
     validation lookup returns a public IP; `urllib`'s own connect lookup, TTL 0, returns
     `127.0.0.1`). The connection MUST be pinned to the specific validated IP (connect to the
     resolved address while sending the ORIGINAL hostname as the `Host` header and the TLS
     `server_hostname`/SNI, so the certificate chain + hostname verification still target the DNS
     name — never the pinned IP) so no second, unvalidated resolution occurs. **Inherited proxies MUST be disabled for this fetcher.**
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
     `response.read()`. The cap applies to the initial response, the terminal response
     `opener.open()` returns after following redirects, **AND every intermediate 3xx redirect body**.
     **Intermediate-redirect-body drain (cycle-10, review-mandated).** The bounded reader above
     replaces only the *terminal* `response.read()` (the response `opener.open()` returns); it does
     NOT see the intermediate 3xx bodies that `urllib.request.HTTPRedirectHandler.http_error_302`
     (aliased to 301/303/307/308) drains with its OWN unbounded `fp.read()` *before* `opener.open()`
     returns. A hostile server can therefore return a chain of 3xx responses whose intermediate
     bodies are arbitrarily large (or many under-cap bodies) and exhaust memory/network while
     bypassing BOTH the per-response `MAX_RESPONSE_BYTES` cap and the request-scoped aggregate
     `MAX_TOTAL_FETCH_BYTES` budget. Required: **extend the EXISTING single redirect handler**
     `_ValidatingRedirectHandler` (`fetch/http.py:41`, already installed on the opener and already
     overriding `redirect_request` for §H6 per-redirect revalidation + the `max_redirects` count) with
     an `http_error_302` override whose bounded-reading proxy drains each intermediate body through the
     SAME bounded reader — counting the actual bytes and decrementing BOTH a fresh per-response
     allowance AND the request-scoped aggregate budget (bytes are counted **even while redirecting**)
     — and raises the typed cap error mid-drain on breach, while **preserving the redirect** (the
     recommended minimal technique wraps the intermediate `fp` in a bounded proxy and delegates to
     `super().http_error_302(...)` so the existing `redirect_request` §H6 revalidation + count and the
     stdlib Location/loop/scheme logic are unchanged). Two urllib specifics MUST be honored: (1) the
     subclass MUST rebind ALL redirect aliases (`http_error_301 = http_error_303 = http_error_307 =
     http_error_308 = http_error_302`) — a subclass overriding only `http_error_302` leaves the other
     four codes bound to the BASE unbounded handler; (2) do NOT install a SECOND redirect handler —
     `OpenerDirector` dispatches a given `http_error_NNN` to handlers in order and stops at the first
     returning a response, so two      redirect handlers cannot both run; the drain MUST be folded into the existing handler as ONE
     composite handler. **Intermediate-response closure (cycle-12, Copilot round-3 Finding A).** The
     bounded proxy delegates to `super().http_error_302(...)`, which reads the wrapped `fp` and only
     calls `fp.close()` AFTER a completed read; when the proxy raises a per-response OR aggregate cap
     error MID-STREAM, that `fp.close()` is never reached, so the underlying intermediate 3xx response
     `fp` (a live socket/connection) LEAKS. The override MUST therefore CLOSE the real intermediate `fp`
     before the typed error propagates, on every leak-prone exit — e.g. wrap the `super()` delegation in
     a guard `except (per-response cap error, AggregateBudgetExceededError, FetchError, CrawlUrlRejectedError): fp.close(); raise` — closing the real `fp` not only on the per-response and aggregate body-drain breaches but also on the two `redirect_request`-raised custom exits (the redirect-cap `FetchError` and the §H6 `CrawlUrlRejectedError`, which unlike stdlib `HTTPError` do not carry the `fp`)
     (since `FetchAttemptBudgetExceededError` subclasses `AggregateBudgetExceededError`, this same guard
     also releases `fp` on the redirect-hop attempt breach raised from `redirect_request` per §H7 item
     4a). `fp.close()` is idempotent, so a redundant close is a no-op. Delivered by the width-isolated
     pair `064.027-T` (harness — per-response + aggregate cap, redirect-still-follows, AND fp-closure on
     both breach paths + the two `redirect_request`-raised custom exits) / `064.028-T` (`fetch/http.py` — bounded drain + broadened closure guard), split out
     because the drain must also decrement the request-scoped aggregate budget that only exists after
     `064.017-T`/`064.024-T`. The redirect-HOP attempt debit (§H7 item 4a) is a SEPARATE width-isolated
     concern, decomposed into `064.029-T`/`064.030-T` (cycle-12).
  3. **Aggregate crawl-byte budget (byte-accurate, enforceable).** Per-response and per-page caps
    do not bound their product: a single small `tools/call` `fetch` at the `max_pages` cap
    against an attacker-controlled server returning maximum-under-cap responses drives
    `max_pages × MAX_RESPONSE_BYTES` of entity-body buffering and disk staging (each page is written
    under `output_dir` by `execute_fetch`). The crawl loop (`fetch/crawl.py`) MUST enforce a hard
    **aggregate** `MAX_TOTAL_FETCH_BYTES` budget across all pages and abort once the running total
    is exceeded (bound the product, not each dimension).
    **Enforceability requirement (cycle-3, review-mandated).** The budget is defined in *bytes*,
    but `crawl.py` today receives only `FetchResponse.body: str` — the raw byte count is discarded
    when `fetch_page` decodes the response (`fetch/http.py:123-125`, `body_bytes.decode(charset,
    errors="replace")`). Summing `len(body)` (characters) or `len(body.encode())` (a *re-encode*,
    not the undecoded body bytes) **under-counts** the entity-body bytes actually buffered: non-ASCII
    bodies have more bytes than characters, and `errors="replace"` collapses each invalid byte to a
    single `U+FFFD`, so a hostile server can buffer and stage far more than `MAX_TOTAL_FETCH_BYTES` of
    entity-body content while the character/re-encode total stays under budget — the bound is not
    enforceable as written. **Scope of the bound (cycle-16 round-1, review-mandated).** `len(body_bytes)`
    is NOT a raw-wire count: `urllib`/`http.client` strips HTTP transfer framing (chunk-size lines,
    trailers) and response headers before `HTTPResponse.read()` returns, and it does not content-decode
    (a `gzip` body stays compressed). The budget therefore bounds the **entity-body bytes** — the
    undecoded response-content bytes returned by `HTTPResponse.read()` that docline buffers, decodes,
    and stages under `output_dir` (the memory + disk blast radius) — NOT raw socket bytes.
    Therefore two coupled requirements: (1) the bounded reader MUST **retain the actual entity-body
    byte count** (the length of the undecoded response-content bytes returned by `HTTPResponse.read()`,
    transfer framing and headers already removed, captured *before* charset decoding) on
    `FetchResponse` (a new `body_byte_count: int` field set from the bounded read in
    `fetch/http.py`) for completed-terminal-response accounting/observability ONLY — it is NOT the
    aggregate enforcement source and does NOT record failed, retried, or intermediate-redirect
    responses; and (2) the aggregate MUST be enforced by
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
    The budget accumulates the exact **entity-body bytes** — the undecoded response-content bytes
    returned by `HTTPResponse.read()` (transfer framing and headers excluded; still content-encoded,
    e.g. `gzip` stays compressed), never a character count or a re-encode. This bounds the buffered
    and `output_dir`-staged content (the memory + disk blast radius); it does **not** bound response
    headers, transfer framing, raw socket bandwidth, or parser CPU (accepted residual — see
    `## Risks`). The budget defaults to unbounded for a standalone single fetch so existing CLI
    single-fetch callers are unaffected. Tests MUST include a **non-ASCII multibyte** payload and an
    **invalid-byte** payload (where `errors="replace"` would otherwise under-count) proving the
    aggregate counts undecoded entity-body bytes (guarding against the decode/re-encode **undercount**),
    NOT that it accounts for transfer framing or header overhead, PLUS a **repeated-failure** case (a
    retried over-cap attempt still decrements the shared budget) and a **mid-read abort** case (the
    crossing response aborts before full buffering).
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
    (a) a **request-scoped fetch-attempt budget at the common outbound-fetch boundary**: `fetch_page`
    in `fetch/http.py` — the single choke point through which every DIRECT outbound request flows
    (main-page fetches, `robots.txt` via `_robots_allow`, mdBook TOC-script fetches via
    `_discover_toc_links`, per-pop retries via `_fetch_with_retries` — each a distinct `fetch_page`
    call) — debits a per-request attempt allowance seeded at `MAX_FETCH_ATTEMPTS`, one debit **before**
    each such outbound request (pre-I/O), and aborts the crawl by RAISING a typed
    `FetchAttemptBudgetExceededError` (a `DoclineError` subclass of `AggregateBudgetExceededError`) the
    instant a debit would exceed the cap; the crawl RAISES, it does not silently return the accumulated
    skipped results. **Redirect hops** — which urllib follows INSIDE a single `fetch_page`'s
    `opener.open()`, not at the boundary — are debited one attempt per FOLLOWED hop INSIDE the shared
    `_ValidatingRedirectHandler`, placed in **`redirect_request`** immediately before it returns a
    non-None `Request` — i.e. AFTER the stdlib scheme check (raised in `http_error_302` before
    `redirect_request`) and the §H6 address-pinned per-redirect revalidation, and BEFORE the hop's
    outbound I/O (`parent.open()`) — from the same
    request-scoped budget object, raising `FetchAttemptBudgetExceededError` on breach. Placing the
    debit here (not in `http_error_302` before `super()`, the REJECTED cycle-11 placement) means an
    attempt is charged if-and-only-if the redirect will actually be FOLLOWED: a redirect the SCHEME
    check rejects (before `redirect_request`) or that §H6/stdlib `redirect_request` rejects (`None`
    return or raise) consumes NO attempt (cycle-12 Copilot round-3 Finding B). **Bounded conservative
    residual** (verified against the CPython `http_error_302` source): two paths debit before their
    `parent.open()` runs — the stdlib LOOP-detection check (`max_repeats`/`max_redirections`) fires AFTER
    `redirect_request` returns (hence after the debit) but before `parent.open()`, and a
    per-response/aggregate body-drain breach fires after `redirect_request` but before `parent.open()`;
    each over-counts by exactly one attempt on a terminating (or retried) hop. This is CONSERVATIVE: the
    `redirect_request` placement NEVER UNDER-counts a followed hop, so the over-count can only make
    `MAX_FETCH_ATTEMPTS` trip earlier, never allow more outbound work than the cap — the DoS upper-bound
    invariant holds. It is bounded (at most one per such hop; retries add at most one phantom debit per
    retried pop) and unavoidable without reimplementing the stdlib method body (forbidden); same residual
    class as the loop-detection/disallowed-scheme unread-`fp` note in `## Risks`. `redirect_request` is
    chosen over a body-proxy-`close()` placement (which would be exact/residual-free) to keep the attempt
    concern WIDTH-ISOLATED from the `064.028-T` body-drain proxy per the cycle-12 decomposition. A post-`open()`
    `handler.redirect_count` tally (which would let urllib follow up to `max_redirects` hops beyond the
    cap before raising) is NOT used for enforcement (`handler.redirect_count` is retained for
    observability only). This per-hop redirect-attempt debit is delivered by the NEW width-isolated
    pair `064.030-T` (impl — moves the debit into `redirect_request`) / `064.029-T` (harness — proves
    debit-on-follow placement, no-debit-on-reject, and attempt-breach-before-I/O); the boundary debit
    for direct outbound calls is delivered by `064.026-T` (harness `064.025-T`). The allowance rides the SAME request-scoped
    budget object (`RemainingByteBudget`) that `064.017-T`/`064.024-T` already thread through every
    `fetch_page` call, and because the abort subclasses `AggregateBudgetExceededError` the four existing
    `except AggregateBudgetExceededError: raise` clauses in `crawl.py` propagate it out of `crawl()` —
    so no new `crawl.py` re-raise is needed. **Enforcing at the boundary — not with a `fetch/crawl.py`
    frontier-pop counter (the cycle-8 mechanism, REJECTED by cycle-11) — is required**: a frontier-pop
    counter counts only main-page pops and leaves robots, TOC, retries, and redirect hops (all real
    outbound requests) uncounted, and the per-response/aggregate byte budgets bound transfer VOLUME not
    request COUNT (empty/tiny robots/TOC responses barely spend the byte budget). Debiting at the
    single `fetch_page` choke point for direct outbound calls, and inside the shared redirect handler
    for redirect hops, makes auxiliary, retry, and redirect traffic decrement the same request-scoped
    bound, so none of them can exceed `MAX_FETCH_ATTEMPTS`. (b) a **depth upper bound**:
    `FetchRequest.depth` gains a hard `Field(le=…)` upper bound (preserving `default=0`) so an
    over-limit value is rejected at validation and surfaces as `-32602` on the MCP boundary, closing
    the unbounded-depth frontier-expansion vector at the untrusted input.
    **Coverage requirement.** The red harness MUST prove that AUXILIARY and RETRY/REDIRECT traffic
    alone cannot bypass the cap, using a fake transport that keeps emitted `page_count` low while
    driving high outbound traffic: (i) **robots** — enabling `robots.txt` fetching issues
    `_robots_allow` `fetch_page` calls that each debit the budget; (ii) **TOC** — mdBook TOC-script
    discovery issues `_discover_toc_links` `fetch_page` calls that each debit the budget; (iii)
    **retries** — transient failures make `_fetch_with_retries` issue multiple `fetch_page` calls per
    pop, each debiting at the boundary (robots/TOC/retries proven by `064.025-T`); (iv) **redirects** —
    responses that redirect make the shared `_ValidatingRedirectHandler` debit one attempt per FOLLOWED
    hop in `redirect_request` (after validation, before outbound I/O), from the same request-scoped
    budget, while a rejected redirect consumes no attempt (proven by the redirect-hop attempt-debit
    placement harness `064.029-T`). Assert that a crawl whose
    emitted `page_count` stays below `max_pages` but whose robots/TOC/retry/redirect outbound traffic
    is high still trips `MAX_FETCH_ATTEMPTS` and RAISES; plus an over-limit `depth` (`>= MAX_DEPTH_LIMIT + 1`) rejected at
    model validation AND a request OMITTING `depth` still validating (depth defaults to 0).
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
    initial response body, the terminal post-redirect response body, AND every intermediate 3xx
    redirect body (the last bounded-drained by the extended `_ValidatingRedirectHandler` of
    `064.028-T`, using this SAME cap — no new constant). Boundary: a response up to and
    including exactly `10_485_760` entity-body bytes (the undecoded response-content bytes returned by
    `HTTPResponse.read()`, transfer framing and headers excluded) is allowed; the bounded reader caps each
    individual read size at `min(CHUNK_SIZE, MAX_RESPONSE_BYTES - bytes_read + 1)`, so at the
    boundary `HTTPResponse.read()` returns at most the single crossing entity-body byte beyond the
    allowance — never a full extra
    `CHUNK_SIZE` chunk of body. It aborts mid-stream (typed error) the instant a read returns a byte beyond
    `10_485_760` (the over-cap response is never fully buffered; the over-cap buffered content is at most
    `MAX_RESPONSE_BYTES + 1`, not `MAX_RESPONSE_BYTES + CHUNK_SIZE`).
  - **`MAX_TOTAL_FETCH_BYTES = 512 * 1024 * 1024 = 536_870_912`** (512 MiB) aggregate per-request
    crawl budget. Rationale: bounds the *product* of the page and per-response caps — the naive
    product `MAX_PAGES_LIMIT × MAX_RESPONSE_BYTES` (1000 × 10 MiB ≈ 10 GiB) is the amplification
    vector; 512 MiB caps total entity-body buffering / disk staging at ~20× below that product while still
    covering a large legitimate crawl (e.g. ~500 pages averaging ~1 MiB, or 50 pages of ~10 MiB).
    The aggregate is the effective entity-body-staging bound for the "many large pages" attack (it trips after
    at most ⌊512 MiB / 10 MiB⌋ = 51 full-size responses, well inside the 1000-page count cap).
    Boundary: the request-scoped remaining-byte budget starts at `536_870_912` and is decremented
    by the actual bytes read across **every** `fetch_page` call for the request (main pages, retried
    over-cap attempts, and ancillary `robots.txt`/TOC fetches). The bounded reader caps each read
    size at `min(CHUNK_SIZE, per_response_remainder + 1, aggregate_remainder + 1)` and counts the
    actual bytes returned, so at either boundary `HTTPResponse.read()` returns at most the single
    crossing entity-body byte beyond the allowance — never a full extra `CHUNK_SIZE` chunk of body.
    A total of exactly `536_870_912` entity-body bytes
    is allowed; the read aborts mid-stream (raising `AggregateBudgetExceededError`, re-raised out of
    `crawl()`) the instant a read returns a byte beyond the aggregate allowance (the over-budget
    buffered content is at most `budget + 1`, not `budget + CHUNK_SIZE`). Defaults to unbounded (`None`) for
    a standalone single fetch so existing CLI single-fetch callers are unaffected.
  - **`MAX_FETCH_ATTEMPTS = 4 * MAX_PAGES_LIMIT = 4000`** (per-request outbound-fetch-attempt budget,
    enforced at the common `fetch_page` boundary in `fetch/http.py`; §H7 item 4a). Rationale: `MAX_PAGES_LIMIT`
    (1000) caps only *emitted* pages, but every outbound request is real — main-page fetches, the
    print-page / duplicate / out-of-scope pops that fetch without incrementing `page_count`, per-pop
    retries, redirect hops, and the ancillary `robots.txt`/TOC fetches. Even a skip-heavy legitimate
    crawl (redirects, duplicates, robots-disallowed, print variants, retries) issues at most a small
    multiple of its emitted-page budget of outbound requests, so `4×` the hard page cap gives generous
    headroom while hard-capping TOTAL OUTBOUND ATTEMPTS at 4000 regardless of how many are uncounted by
    `page_count` — closing the tiny-`/print`-page AND auxiliary/retry/redirect amplification vectors.
    Scope of the bound: `fetch_page` debits ONE attempt per DIRECT outbound request (pre-I/O), and
    the shared `_ValidatingRedirectHandler` debits ONE attempt per redirect hop before following it
    (pre-I/O; `handler.redirect_count` is observability-only, not post-hoc enforcement), so main-page
    fetches, per-pop retries
    (`_fetch_with_retries`, each a distinct `fetch_page` call), per-hop redirects, and the
    per-origin-cached `robots.txt` and depth-0 TOC-script fetches (`_discover_toc_links`) ALL decrement
    the same request-scoped budget — auxiliary, retry, and redirect traffic cannot exceed the cap. This
    REPLACES the cycle-8 `fetch/crawl.py` frontier-pop counter, which counted only main-page pops and
    left robots/TOC/retries/redirects uncounted (see cycle-11 remediation). Boundary: exactly 4000
    outbound attempts are allowed; the attempt that would cross the cap is refused (the crawl RAISES
    `FetchAttemptBudgetExceededError`, a `DoclineError` subclass of `AggregateBudgetExceededError`, so
    the existing four `crawl.py` re-raise clauses propagate it; it does not return the accumulated
    skipped results). The attempt allowance defaults to the shared hard cap for a crawl request and to
    unbounded/None for a standalone single fetch (shared code, CLI + MCP).
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
  The **request-amplification bound** (§H7 item 4 — the request-scoped fetch-attempt budget
  `MAX_FETCH_ATTEMPTS = 4000` on the shared `RemainingByteBudget`, debited pre-I/O at the common
  `fetch_page` boundary in `fetch/http.py` for every DIRECT outbound request (main pages, robots, TOC,
  retries) and per redirect hop inside the shared `_ValidatingRedirectHandler` in `redirect_request`
  after validation (before each hop is followed), plus the `FetchRequest.depth` upper bound
  `MAX_DEPTH_LIMIT = 64` in `app_models.py`) is a
  distinct request-COUNT dimension (not byte VOLUME): the boundary debit is delivered by harness
  `064.025-T` + impl `064.026-T`, and the redirect-hop debit is delivered by harness `064.029-T` +
  impl `064.030-T` (`fetch/http.py`, cycle-8 split, mechanism reworked cycle-11, redirect-hop
  placement decomposed cycle-12 — see
  `## Plan Review Remediation` cycle-8, cycle-11, and cycle-12). The attempt allowance rides the SAME
  request-scoped budget object (`RemainingByteBudget`) that `064.017-T`/`064.024-T` already thread
  through every `fetch_page` call, and the abort (`FetchAttemptBudgetExceededError`) subclasses
  `AggregateBudgetExceededError`, so the four existing `crawl.py` re-raise clauses propagate it with
  NO new `fetch/crawl.py` edit — keeping `064.026-T` at 2 files (`fetch/http.py` + `app_models.py`).
  The **intermediate-redirect-body drain + closure** (§H7 item 2, cycle-10 + cycle-12 — extend the EXISTING single
  `_ValidatingRedirectHandler` (with all `http_error_301/302/303/307/308` aliases rebound) so its
  bounded proxy reads/counts each intermediate 3xx body against the SAME per-response
  `MAX_RESPONSE_BYTES` cap AND the request-scoped `MAX_TOTAL_FETCH_BYTES` budget, closing urllib's
  in-handler unbounded `fp.read()` bypass, AND closes the intermediate `fp` on both cap-breach paths —
  ONE composite handler, not a second) is
  delivered by harness `064.027-T` + impl `064.028-T` (`fetch/http.py`, cycle-10 split, closure added
  cycle-12 — see `## Plan Review Remediation` cycle-10 and cycle-12). It reuses the existing `MAX_RESPONSE_BYTES` cap
  (`064.013-T`) and the request-scoped budget (`064.017-T`/`064.024-T`) — no new numeric constant —
  and is split from `064.013-T`/`064.017-T` because a custom redirect handler + opener wiring is
  additional width and the intermediate drain must decrement the aggregate budget that only exists
  after `064.017-T`/`064.024-T`.
  End-to-end proof: a `tools/call` `fetch` with
  over-limit `max_pages` (rejected `-32602`), an oversized response body (aborted, including on the
  terminal post-redirect response AND every intermediate 3xx redirect body via `064.028-T`), and a
  crawl exceeding the aggregate budget (aborted) are asserted in the MCP boundary
  harness `064.014-T`; the request-amplification depth over-limit (`-32602`) and outbound-attempt
  budget (direct-request debits at the `fetch_page` boundary proven in `064.025-T`; the redirect-hop
  per-hop debit placement proven in `064.029-T`) are proven at the unit level (keeping `064.014-T` within its 3-scenario budget).
  Caps are set high enough not to break legitimate CLI crawls; the existing
  fetch suite must remain green (or be deliberately updated for the new bound).
- **H8 — External PDF-engine opt-in gate on the untrusted MCP surface (P0-class, blocking).**
  The MCP-specific `process` schema is derived from `ProcessRequest.model_json_schema()`, whose
  `pdf_engine` field is `Literal["auto","docling","mistral_ocr","heuristic"]`
  (`src/docline/app_models.py:106`). `"mistral_ocr"` selects the Mistral OCR reader
  (`src/docline/readers/mistral.py`), which reads AMBIENT server credentials
  (`AZURE_AI_FOUNDRY_KEY`/`AZURE_AI_FOUNDRY_ENDPOINT`, else `MISTRAL_API_KEY`) and base64-uploads the
  workspace PDF to an external PAID OCR endpoint (Foundry MaaS or `api.mistral.ai`). On the untrusted
  stdio surface an unauthenticated local client passing `pdf_engine:"mistral_ocr"` in a `tools/call`
  `process` therefore consumes the operator's ambient credentials, egresses workspace bytes to a
  third party, and incurs uncapped paid-call cost — purely from a request field. `request.pdf_engine`
  is the **sole** client-controllable selector of that reader: `_resolve_layout_engine("auto")` never
  resolves to `mistral_ocr` (`readers/pdf.py:106-108`), `docling` is a local model, `pdf_mode=triage`
  ignores `layout_engine` (`process/output_contract.py`), and `MISTRAL_OCR_MODEL` only renames an
  already-selected engine. Required behavior (MCP-surface-only, mirroring §H1's omit-and-reject):
  1. **Local-engine ALLOW-LIST (fail-closed).** Define
     `_MCP_LOCAL_PDF_ENGINES = frozenset({"auto","docling","heuristic"})` in `src/docline/mcp/server.py`
     — the engines permitted on the untrusted MCP surface WITHOUT opt-in. An allow-list (not a
     `mistral_ocr` deny-list) is used so any FUTURE external engine added to the shared enum is denied
     by default.
  2. **Advertise omission (build time).** `DoclineMcpServer.list_callable_tools()` filters the
     advertised `process` `inputSchema` `pdf_engine` enum to `_MCP_LOCAL_PDF_ENGINES` when the server
     is NOT opted in — the SAME schema-construction site that already removes `workspace_root` (§H1).
     This is the **third sanctioned MCP-only parity divergence** (after the §H1 `workspace_root`
     omission and the `ingest_local_dir` exclusion); the T1 semantic-parity normalization
     (`064.001-T`, extended by `064.031-T`) strips exactly this delta so `tools/list` stays in
     semantic parity with the callable-filtered manifest. `list_tools()`, `get_manifest()`, and
     `docline --manifest` are UNCHANGED (CLI retains all four engines).
  3. **Dispatch reject (runtime, both eras).** A guard consulted by BOTH the `call_tool` `process`
     adapter AND the public `DoclineMcpServer.process()` method (the last hop before `execute_process`,
     so no adapter path bypasses it — the shared `ProcessRequest` stays permissive for CLI parity, so
     the guard, not the model, enforces the gate) raises a typed `ExternalEngineNotAllowedError`
     (`DoclineError` subclass) when the resolved `pdf_engine` is not in `_MCP_LOCAL_PDF_ENGINES` and the
     server is not opted in. The stdio transport maps that typed error to a `-32602` invalid-params
     envelope, ordered BEFORE the generic `-32603` (mirroring the §H4 `UnknownToolError`→`-32602`
     mapping), engine name only (no arguments/credential disclosure — §H3). Because both protocol eras
     funnel through the ONE hardened dispatch (§H1/§H3-parity invariant), the modern (`_meta`,
     pre-handshake) path rejects identically to legacy. `ingest_local_dir` (the second
     `pdf_engine`-bearing tool) is already excluded from `list_callable_tools()` and the `call_tool`
     allow-list (§H4), so it presents no egress bypass; §H8 adds an explicit negative assertion.
  4. **Server-side startup opt-in (only enabler).** External engines become available ONLY when the
     operator starts `docline-mcp` with `DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES=1` (fail-closed: only
     the exact token `"1"` enables; any other value stays disabled) OR the
     `--allow-external-pdf-engine` flag. `main()` resolves this EXACTLY ONCE at startup into a FRESH
     `DoclineMcpServer(external_pdf_engines_enabled=<resolved>)` passed to `serve(server=...)`; it does
     NOT mutate the import-time module `SERVER` default, and the flag is INSTANCE-local — never derived
     from request `arguments` or `_meta` (a client cannot spoof it; a client-supplied
     `external_pdf_engines_enabled`/`allow_external` field is ignored and still rejected). No ambient
     credential value is logged on the reject or startup paths.
  Blocking tests: default server omits `mistral_ocr` from the advertised `process` enum and rejects
  `pdf_engine:"mistral_ocr"` with `-32602` in BOTH eras (egress sentinel never called); an opt-in
  server advertises and accepts it (egress stubbed); env/flag resolution is fail-closed and
  instance-local. Delivered by the width-isolated pairs `064.031-T`/`064.032-T` (adapter policy),
  `064.033-T`/`064.034-T` (transport `-32602` mapping), and `064.035-T`/`064.036-T` (startup opt-in).
  - **§H8 residual (documented, accepted).** Once the operator opts in, the still-untrusted client can
    drive paid Mistral OCR calls and workspace-PDF upload bounded only by the reader's 120 s
    per-request timeout (no page/byte/call budget). Enabling the flag is an explicit operator
    delegation of paid external egress to the connected client; operators SHOULD enable it only for
    trusted local clients. A per-surface cost/egress budget for the enabled state is a potential
    follow-up, out of scope for closing this default-enabled finding (see `## Risks`).

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
   missing/non-string `method`; present `id` whose type is not string or number — object/array/
   bool/null, never echoed, error frame carries `id:null`)**, `-32601`, `-32602`, `-32603`; id-less
   notification is silent.
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
   address is non-public-unicast (loopback/private/link-local/multicast/reserved/unspecified/metadata,
   fail-closed on unclassifiable — the class predicates of `_is_unsafe_address` in
   `sitemap.py:173-189` **plus an explicit CGNAT `100.64.0.0/10` membership check and ULA**, which
   the six flags miss); revalidate every redirect target at connect
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
   3 scenarios). Unit tests in `tests/fetch/` proving the aggregate cap counts **entity-body bytes**
   (the undecoded response-content bytes returned by `HTTPResponse.read()`, transfer framing and
   headers excluded), not decoded characters or a re-encode: (a) a **non-ASCII multibyte** body (byte length >
   character length) accrues its undecoded entity-body byte length toward `MAX_TOTAL_FETCH_BYTES`; (b) an
   **invalid-byte** body (where `errors="replace"` collapses bytes to `U+FFFD`) accrues its
   original undecoded entity-body byte length, not the replaced-character length; (c) **parametrized during-read
   enforcement** — a request whose cumulative **entity-body** bytes exceed the budget is aborted even
   though the decoded character total stays under budget (undercount-bypass), covering a main-page
   response that aborts **mid-read** before full buffering, a retried over-cap attempt whose bytes
   still decrement the shared request budget, and an ancillary robots/TOC fetch decrementing the
   same budget. These prove enforcement is below charset decoding (resisting a decode/re-encode
   undercount), NOT wire-framing/header coverage. Verify red [green@T-agg-i]. Depends on T-cap-i.
10. T-agg-i [064.017-T] — Entity-body-count retention + byte-accurate aggregate accounting impl, **core**
   (code domain, ≤2 files: `fetch/http.py`, `fetch/crawl.py`). Add `FetchResponse.body_byte_count: int`
   set from the length of the bytes read by the bounded reader **before decoding** (the
   `body_bytes` already materialized at the streamed read) for completed-terminal-response accounting; and enforce
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
   default (`= 0`) and is **appended after** the existing defaulted `redirect_count` field (never
   inserted before it — inserting before `redirect_count` would shift its positional-argument slot
   and silently break `FetchResponse`'s public positional constructor) so the frozen dataclass and
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
   domain, ≤1 file: `fetch/crawl.py`). Extends the request-scoped budget seeded by T-agg-i by
   threading it from `crawl()`'s two ancillary call sites into `_robots_allow` (which forwards it to
   its DIRECT `fetch_page` call) and `_discover_toc_links` (which forwards it to its
   `_fetch_with_retries` call — already budget-aware from T-agg-i, NOT a direct `fetch_page` call)
   so ancillary `robots.txt`/mdBook-TOC transfer decrements the SAME budget while bytes are read,
   and adds the two remaining `except AggregateBudgetExceededError: raise` clauses (before the
   `_robots_allow` ~line 406 and `_discover_toc_links` ~line 465 broad handlers; `_robots_allow` has
   no prior re-raise clause). Takes over green-ownership of `064.016-T` scenario (c)(iii) (ancillary
   accrual with SEPARATE robots AND TOC variants; `crawl()` RAISES). **3 functions touched** —
   `crawl` (the two ancillary call-site edits; the request-scoped budget is local to `crawl()`, so
   threading it into the helpers necessarily changes `crawl()`), `_robots_allow`, and
   `_discover_toc_links` — single file, within the 2-hour/<5-function envelope. Turns the
   ancillary sub-vector of T-agg-h green. Existing fetch suite stays green. Depends on T-agg-i.
10c. T-amp-h [064.025-T] — Shared-fetch request-amplification harness (tests domain, 2 scenarios).
   Author the failing harness for the request-COUNT bound (§H7 item 4): (1) a fake transport drives
   `crawl()` to RAISE a typed error once TOTAL outbound attempts — the first 4000 debits succeed and
   the debit that would cross `MAX_FETCH_ATTEMPTS = 4000` is refused BEFORE its outbound I/O — while
   `page_count` stays below `max_pages`, proving AUXILIARY and RETRY traffic alone cannot bypass the
   cap: **robots** (`_robots_allow` `fetch_page` calls debit the budget at the boundary), **TOC**
   (`_discover_toc_links` `fetch_page` calls debit the budget at the boundary), and **retries**
   (`_fetch_with_retries` issues multiple `fetch_page` calls per pop, each debiting one at the
   boundary) — a crawl whose emitted `page_count` stays low but whose robots/TOC/retry traffic is high
   still trips the cap and RAISES (the **redirect-hop** attempt debit — one per followed hop inside the
   shared redirect handler's `redirect_request`, after validation — is proven by `064.029-T`, not
   here); (2)
   `FetchRequest.depth >= MAX_DEPTH_LIMIT + 1` (`>= 65`) is rejected at model validation (`-32602`),
   AND a request OMITTING `depth` still validates (defaults to 0). This is a distinct dimension from
   the byte caps (T-cap/T-agg), so it stays
   width-isolated. Verify red [green@T-amp-i]. Depends on T-agg-aux.
10d. T-amp-i [064.026-T] — Request-scoped fetch-attempt budget + depth amplification-bound impl
   (code domain, ≤2 files: `fetch/http.py` + `app_models.py`). (a) `fetch/http.py` seeds a per-request
   fetch-attempt allowance `MAX_FETCH_ATTEMPTS = 4000` on the SAME request-scoped budget object
   (`RemainingByteBudget`, threaded through every `fetch_page` call by 064.017-T/064.024-T); `fetch_page`
   debits one attempt BEFORE each direct outbound request (main-page/robots/TOC/retries — each a
   distinct `fetch_page` call; pre-I/O) and RAISES `FetchAttemptBudgetExceededError` (a `DoclineError`
   subclass of `AggregateBudgetExceededError`, so the four existing `crawl.py` re-raise clauses
   propagate it — no `fetch/crawl.py` edit) when a debit would cross the cap (the first 4000 debits
   succeed; the crossing debit is refused before its outbound I/O). Redirect-hop attempt debits are NOT owned here:
   they live inside the shared `_ValidatingRedirectHandler.redirect_request` (one per followed hop, after
   validation, before outbound I/O) and are delivered by `064.030-T` (harness `064.029-T`), which reuses the
   same budget `064.028-T` threads into that handler for its byte decrement; (b) `app_models.py` bounds `FetchRequest.depth` with
   `Field(default=0, ge=0, le=64)` (`MAX_DEPTH_LIMIT`; the `default=0` is preserved so `depth` stays
   optional). The mechanism moved from a `fetch/crawl.py` frontier-pop counter (cycle-8, REJECTED) to
   the `fetch_page` boundary (cycle-11) so robots/TOC/retries/redirects — all real outbound requests —
   are counted; the file set changes from `fetch/crawl.py` + `app_models.py` to `fetch/http.py` +
   `app_models.py` while staying at 2 files (threading + abort-propagation reused from 064.017-T/064.024-T).
   Turns T-amp-h green. Existing fetch suite stays green (bounds sized 4× the page cap / 64-deep;
   attempt allowance unbounded for a standalone single fetch). Depends on T-amp-h.
10e. T-redir-h [064.027-T] — Intermediate-redirect-body drain + closure harness (tests domain, 3 scenarios).
   Author the failing harness for the redirect-body vector (§H7 item 2, cycle-10 + cycle-12 closure):
   via a fake transport returning a controllable chain of 3xx responses with intermediate bodies of
   known raw byte lengths (and an instrumented `fp` recording read sizes AND `.close()` calls), assert
   (a) an intermediate 3xx body exceeding `MAX_RESPONSE_BYTES` (10 MiB) is
   aborted without full buffering (over-read ≤ `MAX_RESPONSE_BYTES + 1`, each read
   `min(CHUNK_SIZE, remaining + 1)`), **parametrized over all five redirect codes
   301/302/303/307/308** (rows, not new scenarios — proving the alias rebind), AND the intermediate
   `fp` is CLOSED when the per-response cap error propagates (cycle-12 Finding A: the mid-read raise
   must not leak the intermediate connection); (b) with the
   request-scoped budget seeded low / pre-consumed (urllib's default `max_redirects = 5` makes a
   single under-cap chain unable to reach 512 MiB, so the harness proves the decrement/cross-remaining
   behavior hermetically), an intermediate 3xx body crossing the remaining `MAX_TOTAL_FETCH_BYTES`
   allowance is aborted mid-drain (each intermediate body decrements the SAME budget while
   redirecting; `crawl()` RAISES `AggregateBudgetExceededError`), AND the intermediate `fp` is CLOSED
   when the aggregate cap error propagates (cycle-12 Finding A — the aggregate-breach path must not
   leak either); (c) a redirect chain within both
   allowances still follows to its final response AND the §H6 revalidation + count still run; AND
   (cycle-12 Finding A rows, folded into scenario c — not a new scenario) a chain EXCEEDING
   `max_redirects` (redirect-cap `FetchError`) and a hop whose newurl FAILS `validate_crawl_url` (§H6
   `CrawlUrlRejectedError`) each abort the redirect with the rejecting hop's instrumented intermediate
   `fp` CLOSED once before the typed error propagates (these `redirect_request`-raised exits, unlike
   stdlib `HTTPError`, do not carry the `fp`). The
   redirect-HOP `MAX_FETCH_ATTEMPTS` debit is NO LONGER asserted here — it is decomposed into T-redir-attr-h
   [064.029-T]. Verify red (urllib currently drains intermediate bodies with an unbounded `fp.read()`
   and never closes on a mid-read raise) [green@T-redir-i].
   Depends on T-amp-i.
10f. T-redir-i [064.028-T] — Bounded-draining + closing redirect handler impl (code domain, ≤1 file:
   `fetch/http.py`). EXTEND the EXISTING single `_ValidatingRedirectHandler` (not a second handler —
   `OpenerDirector` would run only the first redirect handler that returns a response) with an
   `http_error_302` override, and rebind all aliases
   (`http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302`). The
   override bounded-reads/drains each intermediate 3xx body through the SAME bounded reader (per-read
   `min(CHUNK_SIZE, per_response_remainder + 1, aggregate_remainder + 1)`), counting actual bytes and
   decrementing BOTH a fresh per-response `MAX_RESPONSE_BYTES` allowance (reset per hop) AND the
   request-scoped `RemainingByteBudget` (passed into `_ValidatingRedirectHandler.__init__` at
   `http.py:119`; when threaded), raising the typed cap error mid-drain on breach, AND — cycle-12
   Finding A — CLOSING the real intermediate `fp` before that error propagates on the two body-drain
   cap-breach paths AND on the two `redirect_request`-raised custom exits (redirect-cap `FetchError` +
   §H6 `CrawlUrlRejectedError`, which unlike stdlib `HTTPError` do not carry the `fp`)
   (wrap the `super()` delegation in `except (per-response cap error, AggregateBudgetExceededError, FetchError, CrawlUrlRejectedError): fp.close(); raise`;
   because `FetchAttemptBudgetExceededError` subclasses `AggregateBudgetExceededError`, this same guard
   also releases `fp` when T-redir-attr-i's `redirect_request` attempt debit raises), while preserving
   the redirect (wrap the intermediate `fp` in a bounded proxy and delegate to
   `super().http_error_302(...)` so the existing `redirect_request` §H6 revalidation + `max_redirects`
   count and the stdlib Location/loop/scheme logic are unchanged). The redirect-HOP attempt debit is
   NO LONGER placed here — it moves to T-redir-attr-i [064.030-T]'s `redirect_request`.
   Reuses `MAX_RESPONSE_BYTES` (T-cap-i) + `RemainingByteBudget`/`AggregateBudgetExceededError`
   (T-agg-i/T-agg-aux) — no new constant, no `app_models.py`/`crawl.py` change. Because the single
   validating handler is on the shared opener, main + retry + ancillary fetches are all covered. Turns
   T-redir-h green. Existing fetch suite stays green (small/empty legitimate 3xx bodies drain and
   follow normally). Depends on T-redir-h.
10g. T-redir-attr-h [064.029-T] — Redirect-hop fetch-attempt-debit placement harness (tests domain, 2 scenarios).
   Author the failing harness for the redirect-hop attempt-accounting PLACEMENT (§H7 item 4a, cycle-12
   Finding B): via a fake transport driving a controllable redirect chain whose newurl targets can be
   selectively made policy/scheme-INVALID or VALID (a loop-INVALID target, if driven, exercises the
   loop path only — a loop-terminated hop incurs the documented one-attempt CONSERVATIVE over-count and
   is NOT asserted no-debit, since stdlib loop detection runs AFTER `redirect_request`), and an instrumented `RemainingByteBudget`
   recording each attempt debit with ordering, assert (1) each FOLLOWED hop debits EXACTLY ONE
   `MAX_FETCH_ATTEMPTS` attempt INSIDE `redirect_request` on the non-None-return path — after the stdlib
   scheme check AND §H6 revalidation, before the hop's outbound I/O (`parent.open()`) — AND
   a redirect REJECTED by validation (`redirect_request` returns `None` or raises) debits NOTHING (the
   core Finding-B assertion: the correct `redirect_request` placement vs the rejected
   `http_error_302`-before-`super()` placement under which a rejected redirect would wrongly consume an
   attempt); (2) a chain whose followed hops would cross `MAX_FETCH_ATTEMPTS` is refused with
   `FetchAttemptBudgetExceededError` (subclass of `AggregateBudgetExceededError`, propagated out of
   `crawl()` by the existing re-raise clauses) BEFORE the crossing hop's outbound I/O, and the
   intermediate `fp` is closed (via T-redir-i's closure guard); `handler.redirect_count` stays
   observability-only. Verify red (after T-redir-i the `http_error_302` override debits NOTHING per hop, so
   followed hops are un-counted and the debit-on-follow placement/ordering and attempt-breach scenarios
   fail; the no-debit-on-reject rows are regression anchors — trivially green pre-impl, they must stay green
   after T-redir-attr-i places the debit in `redirect_request`) [green@T-redir-attr-i].
   Depends on T-redir-i.
10h. T-redir-attr-i [064.030-T] — Redirect-hop fetch-attempt debit in `redirect_request` impl (code domain, ≤1 file:
   `fetch/http.py`). MOVE the per-hop `MAX_FETCH_ATTEMPTS` attempt debit OUT of the `http_error_302`
   override (the rejected cycle-11 placement, which debited before `super()` and charged an attempt
   even for redirects that scheme/loop/§H6 validation REJECTS before `parent.open()`) and INTO
   `_ValidatingRedirectHandler.redirect_request`, debiting exactly ONCE immediately before returning a
   non-None `Request` — after the stdlib `super().redirect_request` build AND the §H6 address-pinned
   revalidation, before the hop's outbound I/O. A redirect that `redirect_request` rejects (`None`
   return) or that §H6 revalidation rejects (raises) consumes NO attempt. Raises
   `FetchAttemptBudgetExceededError` from inside `redirect_request` on breach (before returning the
   `Request`); the existing `crawl.py` re-raise clauses propagate it (no `crawl.py` edit). The
   intermediate-`fp` closure on this attempt-breach path is provided by T-redir-i's `http_error_302`
   closure guard (no duplicate close logic). Reuses the `MAX_FETCH_ATTEMPTS` allowance seeded by
   `064.026-T` and threaded into the handler by `064.028-T` — no new constant, no new file, no
   `app_models.py`/`crawl.py` change. `handler.redirect_count` observability-only. Turns T-redir-attr-h
   green. Existing fetch suite stays green (attempt allowance unbounded for a standalone single fetch).
   Depends on T-redir-attr-h.
11. T-e2e [064.014-T] — MCP untrusted-fetch end-to-end boundary harness (tests domain,
    3 scenarios). Through `tools/call` fetch (stdin JSON → dispatch → `server.fetch` →
    `execute_fetch`): (a) a public hostname resolving to loopback/private is rejected end-to-end
    (§H6); (b) an over-limit `max_pages` (`>= 1001`) is rejected `-32602` end-to-end (§H7); (c) an
    oversized response (per-response `MAX_RESPONSE_BYTES` = 10 MiB cap incl. the terminal
    post-redirect response AND every intermediate 3xx redirect body) OR a crawl
    exceeding the aggregate `MAX_TOTAL_FETCH_BYTES` = 512 MiB budget is aborted
    end-to-end (§H7). Authored red (no dispatch loop yet). The shared-fetch guards (T-ssrf-i,
    T-cap-i, T-agg-i, T-agg-aux, T-amp-i, T-redir-i, T-redir-attr-i) already enforce in `execute_fetch`, so once the dispatch loop routes
    `server.fetch` these all go green at **T2** — no separate boundary wiring is required. The
    request-amplification bound (§H7 item 4) is proven at the unit level in T-amp-h and T-redir-attr-h, keeping this
    harness within its 3-scenario budget. Depends
    on T-redir-attr-i (the full aggregate budget, the request-amplification bound across direct calls AND
    redirect hops, the intermediate-redirect-body drain, and intermediate-response closure are all in place).
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
    depending on an unbuilt `server/discover`; the initialize-vs-discover no-drift check is NOT
    part of it and lives in (b); (b) **era routing + no-drift (genuinely red** until T-era-i1
    discovery + T-era-i2 legacy branch) — a `tools/call` whose `_meta` carries the namespaced
    `io.modelcontextprotocol/protocolVersion` member is served under
    modern semantics with no prior `initialize`, while the same method with no modern negotiation
    member after `initialize` is served under legacy semantics; a **retained-legacy compatibility**
    row asserts that a post-`initialize` request carrying only ancillary `_meta` (e.g.
    `_meta.progressToken`) with NO `protocolVersion` member stays on the **legacy** path (never
    routed to modern validation and rejected), and a **modern-wins-after-latch** row asserts that a
    `protocolVersion`-bearing request following an `initialize` latch is still served **modern**,
    AND a metadata-free operation (`tools/call`/`tools/list` with no
    `_meta`) received **before** any `initialize` is **rejected** — never served as legacy — as is a
    pre-`initialize` operation carrying only ancillary `_meta` (no `protocolVersion` member) —
    proving
    the process era is latched by `initialize` and keyed on the namespaced modern negotiation member,
    not selected by an unadorned request shape or by ancillary `_meta` presence (the
    **pre-initialize operation tests**), AND `initialize` and `server/discover` report the **same**
    identity/capabilities from the single `describe_server()` source, with `initialize.protocolVersion`
    (legacy singular) **contained in** `server/discover.supportedVersions` (modern plural) — a
    containment check, not singular-vs-plural field equality; (c)
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
21. T-ext-h [064.031-T] — §H8 external-engine adapter-policy harness (tests domain, 3 scenarios).
    Author failing tests in `tests/parity/test_mcp_stdio.py` proving the adapter enforces the
    external-PDF-engine gate at the INSTANCE level (no transport): (a) a DEFAULT server's
    `list_callable_tools()` `process` `pdf_engine` enum == the local allow-list
    `{auto,docling,heuristic}` (`mistral_ocr` omitted), an opt-in server advertises the full enum;
    (b) DEFAULT-server `call_tool("process",{pdf_engine:"mistral_ocr"})` AND `process(...)` RAISE the
    typed `ExternalEngineNotAllowedError` before egress (sentinel never called), a client-supplied
    `external_pdf_engines_enabled`/`allow_external` field is ignored (still denied), and
    `ingest_local_dir` stays unrouted (§H4); (c) opt-in server dispatches (egress STUBBED) + the exact
    sanctioned CLI/MCP parity delta (manifest/`--manifest`/`list_tools()` keep all four engines).
    Verify red [green@T-ext-i]. Depends on T-era-i2.
22. T-ext-i [064.032-T] — §H8 adapter external-engine gate impl (code domain, ≤2 files:
    `src/docline/mcp/server.py` + `src/docline/mcp/exceptions.py`). Define
    `_MCP_LOCAL_PDF_ENGINES = frozenset({"auto","docling","heuristic"})` (allow-list),
    `ExternalEngineNotAllowedError` (`DoclineError` subclass, engine-name-only message), and
    `DoclineMcpServer(external_pdf_engines_enabled: bool = False)`; filter the advertised `process`
    enum in `list_callable_tools()` (same site as the §H1 `workspace_root` omission) and add a guard
    consulted by BOTH the `call_tool` `process` adapter and the public `process()` chokepoint that
    raises the typed error for a non-allow-list engine without opt-in. No change to `app.py`,
    `app_models.py`, `readers/pdf.py`, or `list_tools()` (CLI unchanged). Turns T-ext-h green.
    Depends on T-ext-h.
23. T-ext-map-h [064.033-T] — §H8 transport-mapping harness (tests domain, 3 scenarios). Author
    failing tests proving the stdio transport maps `ExternalEngineNotAllowedError` to `-32602` in
    BOTH eras: (a) legacy `tools/call` `process {pdf_engine:"mistral_ocr"}` on a default server →
    `-32602`, engine-name-only, no credential/arguments disclosure (§H3), egress sentinel un-called;
    (b) modern (`_meta`, no `initialize`) → `-32602` IDENTICALLY (one hardened dispatch, no
    pre-handshake bypass); (c) opt-in server → not `-32602` (dispatches, egress stubbed; green anchor
    once T-ext-i lands). Verify red on (a)/(b) [green@T-ext-map-i]. Depends on T-ext-i.
24. T-ext-map-i [064.034-T] — §H8 transport `-32602` mapping impl (code domain, ≤1 file:
    `src/docline/mcp/stdio.py`). Add an `except ExternalEngineNotAllowedError` branch mapping to a
    `-32602` invalid-params envelope, ordered BEFORE the generic `-32603` (mirroring the §H4
    `UnknownToolError`→`-32602` mapping), engine-name-only, no second allow-list in the transport.
    Both eras inherit via the shared dispatch. Turns T-ext-map-h green. Depends on T-ext-map-h.
25. T2b [064.008-T] — Subprocess smoke-test harness for the entry point (tests domain, 1 scenario).
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
    the entry point exists [green@T3]. Depends on T-ext-map-i (the fully hardened dual-era server,
    with the §H8 gate green, ships in the executable).
26. T3 [064.003-T] — `docline-mcp` entry point + module bootstrap (packaging surface only —
    width-isolated). Add `src/docline/mcp/__main__.py` (`main()` reusing `DoclineMcpServer` + `serve`)
    and the `[project.scripts]` `docline-mcp` entry (materializes `docline-mcp.exe` on Windows),
    turning the T2b subprocess harness green. Constructs the server at its secure default
    (`external_pdf_engines_enabled=False`); the §H8 opt-in wiring is layered by T-ext-cfg-i. No
    test-infra authoring in this task. Depends on T2b.
27. T-ext-cfg-h [064.035-T] — §H8 startup opt-in config harness (tests domain, 3 scenarios). Author
    failing tests on the REAL `main()` wiring: (a) fail-closed env resolution —
    `DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES` enables ONLY for exact `"1"`, every other value / unset
    disables (unset row is a green anchor); (b) `--allow-external-pdf-engine` flag enables; (c) `main()`
    builds a FRESH `DoclineMcpServer(external_pdf_engines_enabled=<resolved>)` passed to
    `serve(server=...)` without mutating the module `SERVER`, and no opt-in/credential value is logged.
    Verify red [green@T-ext-cfg-i]. Depends on T3.
28. T-ext-cfg-i [064.036-T] — §H8 startup opt-in config impl (code domain, ≤1 file:
    `src/docline/mcp/__main__.py`). Resolve the opt-in once at startup (exact-`"1"` env token OR the
    `--allow-external-pdf-engine` flag, fail-closed), construct a fresh opt-in server instance passed
    to `serve(server=...)`, never mutate `SERVER`, never read the flag from request data, no-secret
    logging. Turns T-ext-cfg-h green. Depends on T-ext-cfg-h.
29. T4 [064.004-T] — Documentation (docs domain). README "Running the local stdio MCP server"
    section and a SELF-CONTAINED client MCP configuration example for `docline-mcp` in the
    documented GitHub Copilot / VS Code `.vscode/mcp.json` `servers` stdio format (`type`/`command`/
    `args`; a verifiable shape, NOT the repo's git-ignored `.mcp.json`), noting dual-era support
    (modern `server/discover` probe + legacy `initialize` fallback) AND the §H8 external-engine
    default-deny + server-side opt-in (env/flag) with a paid-call + workspace-PDF-upload warning
    (enable only for trusted clients). PLUS a net-new `docs/ARCHITECTURE.md` top-level
    domain/dependency map (two files total, still single docs domain, <3 files) covering the new
    `src/docline/mcp/stdio.py` transport, the `__main__.py` + `docline-mcp` console-script
    bootstrap, and the `DoclineMcpServer` adapter — showing BOTH the MCP and CLI interfaces
    resolving through the shared `docline.app` façade to fetch/process/readers/schema, with the
    dependency-direction invariant (core packages never import the `mcp`/`cli` interface packages),
    cross-interface shared-fetch hardening, and MCP-only §H8 scope; boundaries + direction only, no
    duplicated rationale (per `.github/instructions/architecture-doc.instructions.md`). Do NOT add a
    separate design-doc transport note — the deliberation already documents the transport surface
    (avoid duplication). Depends on T-ext-cfg-i.

Dependency edges: T1b→T1, T1c→T1b, T1d→T1c, T-ssrf-h→T1d, T-ssrf-i→T-ssrf-h, T-cap-h→T-ssrf-i,
T-cap-i→T-cap-h, T-agg-h→T-cap-i, T-agg-i→T-agg-h, T-agg-aux→T-agg-i, T-amp-h→T-agg-aux,
T-amp-i→T-amp-h, T-redir-h→T-amp-i, T-redir-i→T-redir-h, T-redir-attr-h→T-redir-i,
T-redir-attr-i→T-redir-attr-h, T-e2e→T-redir-attr-i, T-adapter→T-e2e,
T-desc-h→T-adapter, T-desc-i→T-desc-h, T2→T-desc-i, T2s→T2, T-era-h1→T2s, T-era-h2→T-era-h1,
T-era-i1→T-era-h2, T-era-i2→T-era-i1, T-ext-h→T-era-i2, T-ext-i→T-ext-h, T-ext-map-h→T-ext-i,
T-ext-map-i→T-ext-map-h, T2b→T-ext-map-i, T3→T2b, T-ext-cfg-h→T3, T-ext-cfg-i→T-ext-cfg-h,
T4→T-ext-cfg-i.
Execution order: 064.001 → 064.005 → 064.006 → 064.007 → 064.010 → 064.011 → 064.012 → 064.013 →
064.016 → 064.017 → 064.024 → 064.025 → 064.026 → 064.027 → 064.028 → 064.029 → 064.030 → 064.014 → 064.015 → 064.018 → 064.019 → 064.002 → 064.009 → 064.020 →
064.021 → 064.022 → 064.023 → 064.031 → 064.032 → 064.033 → 064.034 → 064.008 → 064.003 → 064.035 → 064.036 → 064.004.

## Verification

- `pytest tests/parity` green: the new stdio suite (incl. H1–H6/H7 gates and the `-32600`
  request-shape cases) passes. The existing adapter/transport parity suites stay green **because
  `SERVER.list_tools()` is left unchanged (full four-tool manifest)**; the MCP surface uses the
  new `list_callable_tools()`, so `test_manifest_parity.py::test_mcp_server_list_tools_exposes_shared_manifest`
  needs no edit. No existing parity test is rewritten to accommodate the callable subset.
- `pytest tests/fetch` green: the shared-fetch SSRF-by-resolution, per-dimension resource-cap,
  **byte-accurate aggregate accounting**, and **intermediate-redirect-body drain** unit harnesses
  pass — including the non-ASCII multibyte
  and invalid-byte payloads proving the aggregate cap counts undecoded entity-body bytes (guarding
  against the decode/re-encode undercount) via the request-scoped
  during-read remaining-byte budget
  (not decoded characters, and not a post-return `body_byte_count` sum), and the redirect-body
  harness proving each intermediate 3xx body is bounded-read/counted against the same per-response
  and aggregate allowances (the extended `_ValidatingRedirectHandler`, with all redirect-code aliases
  rebound, replaces urllib's unbounded in-handler `fp.read()`) while legitimate redirects still
  follow and §H6 revalidation still runs — and the pre-existing fetch suite remains green under the new bounds
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
- **§H8 external-engine opt-in gate (T-ext-h/T-ext-i → T-ext-map-h/T-ext-map-i → T-ext-cfg-h/T-ext-cfg-i):**
  on a DEFAULT server the advertised `process` `pdf_engine` enum omits `mistral_ocr` (allow-list
  `{auto,docling,heuristic}`) and a `tools/call` `process {pdf_engine:"mistral_ocr"}` is rejected
  `-32602` in BOTH eras with the egress sentinel never called and no credential/arguments disclosure;
  `ingest_local_dir` stays unrouted (no second egress tool); a client-supplied opt-in field cannot
  flip the gate. On an OPT-IN server (`DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES=1` or
  `--allow-external-pdf-engine`, resolved fail-closed once at startup into a fresh instance) the engine
  is advertised and accepted (egress stubbed in tests). `docline process --pdf-engine mistral_ocr` and
  `docline --manifest` are UNCHANGED (CLI parity retained on all other axes).
- `fetch` advertising parity (T-desc-h → T-desc-i): the advertised `fetch` description states
  HTTP(S)-only across `tools/list` and `docline --manifest` (located by name, not by subscript),
  and matches `execute_fetch`'s rejection of non-HTTP(S) sources (no "file path" advertisement).
  `server/discover` is not a description surface (it carries versions/capabilities/identity/cache
  metadata only), so it is excluded from this assertion.
- JSON-RPC 2.0 conformance: `-32600` returned for a non-object root, a missing/invalid `jsonrpc`,
  a missing/non-string `method`, and a present `id` whose type is not a JSON string or number
  (object/array/bool/null — MCP 2026-07-28 `RequestId`; the malformed id is never echoed, the
  `-32600` frame carries `id:null`) (parametrized), distinct from `-32700` and `-32601`. `-32700`
  is also returned for the non-finite JSON constant TOKENS `NaN`/`Infinity`/`-Infinity` (rejected by
  the strict `parse_constant` callback before the id-type guard and era routing); and a present
  numeric `id` that is not finite (an overflow literal such as `1e400` → `float('inf')`, which
  `parse_constant` does not catch) is rejected `-32600` with `id:null` by the id guard's
  `math.isfinite()` clause — so no non-finite float, in token or overflow form, can enter `RequestId`
  or response serialization.
- MCP boundary end-to-end (T-e2e [064.014-T]): a `tools/call` fetch to a hostname resolving to
  loopback/private is rejected (address-pinned connect closes DNS-rebinding); over-limit
  `max_pages` is rejected `-32602`; an oversized response (per-response cap incl. the terminal
  post-redirect response AND every intermediate 3xx redirect body) or a
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
- Documentation (T4 [064.004-T]): the README gains the "Running the local stdio MCP server"
  section + self-contained `.vscode/mcp.json` `servers` stdio example + §H8 opt-in posture, and
  `docs/ARCHITECTURE.md` carries a top-level domain/dependency map covering the new stdio transport,
  the `docline-mcp`/`__main__` bootstrap, and the adapter boundary — both interfaces resolving
  through the shared `docline.app` façade, core packages never importing `mcp`/`cli`, shared-fetch
  hardening cross-interface, and §H8 scoped to the MCP boundary. Both files satisfy the repo
  markdown heading rules (README one H1; `ARCHITECTURE.md` one H1 or YAML frontmatter `title:`), and
  the architecture doc carries boundaries + direction only (no duplicated protocol/design rationale).

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
  any resolved A/AAAA address is non-public-unicast — loopback/private/link-local/multicast/reserved/unspecified/metadata,
  fail-closed on unclassifiable, mirroring the class predicates of `_is_unsafe_address` in `sitemap.py:173-189`
  plus an explicit CGNAT `100.64.0.0/10` check) plus an end-to-end
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
  initialize-vs-`server/discover` no-drift check cannot be green when 064.021-T is authored
  because `server/discover` is not implemented until successor 064.022-T. **Resolution:** scenario
  (a) is a legacy-only green anchor; the no-drift check moves to scenario (b) and stays red until
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
  §H6 now normalizes IPv4-mapped IPv6 and rejects the complete non-public-unicast set — multicast,
  reserved, and unspecified in addition to loopback/private/link-local/metadata and ULA/CGNAT/`0.0.0.0`,
  fail-closed on unclassifiable — mirroring the class predicates of the shared classifier
  `_is_unsafe_address` (`sitemap.py:173-189`) and adding an explicit CGNAT `100.64.0.0/10` check the
  six flags miss (sitemap's own CGNAT gap tracked in `## Risks`); the proxy disable pins an
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
  membership all updated. **[Superseded by cycle-11: the fetch-attempt bound moved from this
  `fetch/crawl.py` frontier-pop counter to the common `fetch_page` outbound-fetch boundary in
  `fetch/http.py` so robots/TOC/retry/redirect requests are also counted; `064.026-T`'s impl file set
  is now `fetch/http.py` + `app_models.py` (still 2 files). See the Cycle-11 subsection below.]**
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

### Cycle-9 review remediation (PR #166 review cycle 9, fresh Copilot review on HEAD 546a256)

The cycle-8 commit (546a256) drew a fresh Copilot review with two unresolved threads (Stage resumed
under the second operator-authorized three-cycle allowance, round 3 — the final cycle before
convergence evaluation). Both are reconciled here across plan, feature DoD, tasks, the dual-era
parity records, and continuity memory, preserving dependency acyclicity, execution order, and every
2-hour/width/scenario/function budget. This cycle adds NO new task (the fixes are in-place
strengthenings of an existing request-shape contract and a stray-frontmatter cleanup), so the
manifest stays at 26 tasks.

- **Request-shape contract never validates the JSON-RPC `id` type (thread 1, `064.002-T:25`).**
  MCP 2026-07-28 defines `RequestId` as ONLY a JSON string or number, so an `id` that is an object,
  array, boolean, or `null` could be echoed into a structurally invalid response while the task
  still passed its stated `-32600` checks (which covered only root / `jsonrpc` / `method`).
  **Resolution:** the shared `dispatch()` request-shape guard now ALSO rejects a present `id` whose
  JSON type is not string or number (object/array/bool/null → `-32600`), and the malformed id is
  NEVER echoed — the `-32600` frame carries `id: null`. An ABSENT `id` on an OTHERWISE-VALID request
  (object root, `jsonrpc` `"2.0"`, non-empty string `method`) remains an id-less notification
  (silent); an absent `id` on a MALFORMED payload (non-object root, bad/missing `jsonrpc`, or
  missing/non-string `method` — e.g. `{"jsonrpc":"2.0"}` with no `method` and no `id`) is NOT
  suppressed but returns `-32600` with `id:null`. Both are distinct from a present `null` id (a
  `-32600` invalid request, not a
  notification). Because request-shape validation (root/`jsonrpc`/`method`/id-type) runs BEFORE the
  id-absent notification-suppression branch AND before era classification in the single
  hardened `dispatch()`, both the legacy and modern eras inherit the id-type guard identically and
  cannot echo a malformed id. The new cases are added as extra parametrized rows to the EXISTING
  `-32600` request-shape case set in `064.005-T` (no new scenario — the parametrization widens
  in-place; scenario budget stays 3), and implemented as additional inline guard clauses in
  `dispatch()` in `064.002-T` (no new function — the ≤4-function transport budget holds). To make
  the pre-routing ordering test-bound on the MODERN path (not merely structural), `064.021-T`
  scenario (c) gains a parametrized modern (`_meta`-bearing) malformed-id row — asserting `-32600` +
  `id:null` with NO modern wrapper even when `_meta` carries an unsupported version or an unknown
  method — and `064.022-T` gains an explicit acceptance criterion that request-shape validation
  precedes `_meta` extraction / version negotiation / era routing / method dispatch. Both remain
  parametrized rows / ordering constraints, so the 3-scenario, ≤4/≤5-function, and ≤2-file budgets
  are unchanged. Plan request-shape validation paragraph, T1b harness summary, feature DoD JSON-RPC
  conformance clause, `064.005-T`, `064.002-T`, and the dual-era parity records
  `064.021-T`/`064.022-T` (guard-parity + ordering) all reconciled.
- **Semantic-link durability for a blocked spike (thread 2, `061.001-T:16`; durability
  corrected in the current cycle).** `061.001-T`'s two intended `informs` relationships
  (`061.001-T → 060.001-T`, `061.001-T → 060.002-T`) live in the `item_links` relationship store,
  created via the supported `link add` path and verified present via `link list` and an `item_links`
  SQL query. **Resolution:** because `.backlogit/backlogit.db` is a disposable, git-ignored query
  cache (`.gitignore:227`) rather than a tracked source, the durable tracked representation of these
  links is the tool-managed `links:` frontmatter block that `backlogit sync` materializes onto
  `061.001-T` from `item_links` and re-reads on a fresh index rebuild. That block is RETAINED (not
  stripped) so the relationships survive a fresh checkout / index rebuild — an earlier attempt to
  remove it left the links represented only in the git-ignored cache, which would not survive the
  handoff. Relationship traceability is preserved with no duplicate links introduced. This thread
  touches backlog metadata only — no plan contract change.

Re-review verdict (cycle-9, post-remediation): the request-id-type gap is closed at both the harness
(`064.005-T`, legacy/shared path) and impl (`064.002-T`) contracts with the never-echo `id:null` rule
specified once in the shared pre-routing guard; the pre-routing ordering is now test-bound on the
MODERN path too (`064.021-T` scenario (c) malformed-id row + `064.022-T` request-shape-precedence
criterion), so a malformed id cannot surface as `-32022`/`-32602`/`-32601` or a wrapped result; the
intended `informs` relationships on `061.001-T` are kept durable in a tracked `links:` frontmatter
block (the git-ignored `item_links` DB cache is reconstructed from it on sync). All P0/P1 findings closed; no budgets breached; no new task added.

### Cycle-10 review remediation

Cycle-10 (PR #166, fresh Copilot review on HEAD `62df1b7`, round 3 of the second three-cycle
allowance — final convergence cycle) reconciles two further threads, both confirmed against actual
`urllib` redirect behavior and Python JSON parsing behavior by an internal multi-persona adversarial
re-review (Security, Correctness, Scope/Width, Cross-interface blast-radius, Protocol-compliance).
Reconciled across plan, feature DoD, tasks, Rollback, SA-1, Risks, execution order, dependency edges,
shipment `055-S`, and continuity memory, preserving dependency acyclicity and every
2-hour/width/scenario/function budget. Finding A adds ONE new width-isolated harness+impl pair (the
manifest grows 26 → 28 tasks; the chain gains `064.026 → 064.027 → 064.028 → 064.014`, with `064.014-T`
re-pointed from `064.026-T` to `064.028-T`); Finding B is an in-place strengthening (no new task).

- **Redirect handler drains intermediate 3xx bodies with an unbounded `fp.read()` (thread A,
  `064.013-T:26`).** The per-response streamed cap (`064.013-T`) and the aggregate during-read budget
  (`064.017-T`/`064.024-T`) only replace the *terminal* `response.read()` the opener returns.
  `urllib.request.HTTPRedirectHandler.http_error_302` (aliased to 301/303/307/308) drains each
  intermediate 3xx body with its OWN unbounded `fp.read()` *before* `opener.open()` returns (verified
  by reading the CPython source), so a hostile redirect chain bypasses BOTH the per-response
  `MAX_RESPONSE_BYTES` cap and the request-scoped aggregate `MAX_TOTAL_FETCH_BYTES` budget — and the
  plan's "applies to every redirect hop" claim was aspirational (the specified mechanism could not see
  intermediate bodies). **Resolution:** §H7 item 2 now requires **extending the EXISTING single
  redirect handler** `_ValidatingRedirectHandler` (`fetch/http.py:41`, already installed and already
  overriding `redirect_request` for §H6 revalidation + the `max_redirects` count) with an
  `http_error_302` override — plus rebinding ALL aliases
  (`http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302`, since a
  subclass overriding only `http_error_302` leaves the other four codes on the BASE unbounded handler,
  verified) — whose bounded proxy reads/counts each intermediate 3xx body
  through the SAME bounded reader against a fresh per-response cap AND the request-scoped aggregate
  budget (bytes counted even while redirecting), raising the typed cap error mid-drain on breach while
  preserving the redirect (wrap the intermediate `fp` + delegate to `super().http_error_302(...)` so
  the existing `redirect_request` §H6 revalidation + count and the stdlib Location/loop/scheme logic
  are unchanged). It is ONE composite handler, NOT a second handler — `OpenerDirector` dispatches a
  given `http_error_NNN` to handlers in order and stops at the first returning a response, so two
  redirect handlers could not both run (one would bypass either H6 validation or the bounded drain).
  Delivered by a NEW width-isolated pair — harness **`064.027-T`** (T-redir-h, tests
  domain, 3 scenarios: per-response intermediate-body cap [parametrized over 301/302/303/307/308 to
  prove the alias rebind], aggregate intermediate-body accounting [budget seeded low / pre-consumed,
  since `max_redirects` default 5 makes a single under-cap chain unable to reach 512 MiB],
  redirect-still-follows + §H6-preserved) and impl **`064.028-T`** (T-redir-i, code domain, ≤1 file
  `fetch/http.py`, reusing existing caps — no new constant). Split from `064.013-T`/`064.017-T`
  because the redirect-handler override is additional width and the drain must decrement the aggregate
  budget that only exists after `064.017-T`/`064.024-T`. `064.014-T` is re-pointed onto `064.028-T`
  (its per-response "incl. redirect" scenario becomes truly redirect-enforced; 3-scenario budget
  unchanged). Plan §H7 item 2, "Selected numeric limits" `MAX_RESPONSE_BYTES` note, "Cap tasks",
  decomposition (10e/10f), dependency edges, execution order, Verification, Rollback, SA-1 record,
  Risks, feature DoD H7 clause, `064.012-T`/`064.013-T` scope-carve notes, and shipment `055-S`
  membership/order all reconciled.
- **`json.loads` accepts `NaN`/`Infinity`/`-Infinity` (thread B, `064.002-T:25`).** Python's
  `json.loads` parses the non-finite JSON extensions to `float` values (verified: `json.loads("NaN")`
  → `nan`); such an `id` passes the string-or-number RequestId guard and, when echoed via
  `json.dumps` (default `allow_nan=True`), is re-emitted as the bare non-JSON token `NaN`/`Infinity`/
  `-Infinity`, corrupting the JSON-RPC frame. **Resolution:** the frame parse (`json.loads` in
  `serve()`/the frame reader, before `dispatch()`) MUST pass a strict `parse_constant` callback that
  REJECTS the `NaN`/`Infinity`/`-Infinity` TOKENS, mapping them to `-32700` (invalid JSON per RFC 8259 /
  JSON-RPC 2.0). Critically, `parse_constant` does NOT fire for numeric OVERFLOW literals: `json.loads("1e400")`
  returns `float('inf')` WITHOUT invoking it (verified), so the request-shape guard ALSO gains a
  `math.isfinite()` clause that rejects a non-finite numeric `id` as `-32600` (`id:null`). Because both
  guards run BEFORE era routing, no non-finite float — token OR overflow form — can enter `RequestId`
  or any response serialization, and both eras inherit them.
  Defense-in-depth: the response serializer emits with `allow_nan=False` and degrades a serialization
  `ValueError` to a `-32603` envelope rather than crashing the serve loop. Implemented as a `kwarg` on
  the EXISTING single `json.loads` call plus an inline clause in the EXISTING `dispatch()` id guard in
  `064.002-T` (no new function — the ≤4-function transport
  budget holds); asserted as extra parametrized rows on the EXISTING `-32700` parse-error case (tokens)
  AND the EXISTING `-32600` invalid-id case (overflow literals) in the
  `064.005-T` error-envelope scenario (no new scenario — budget stays 3). Plan request-shape /
  error-envelope paragraph, Verification JSON-RPC conformance bullet, feature DoD JSON-RPC conformance
  clause, `064.002-T`, and `064.005-T` all reconciled.

Internal multi-persona adversarial re-review (Security / Correctness / Scope-Width / Cross-interface /
Protocol-compliance), run against the CPython `urllib` source and empirical `json`/`urllib` probes
BEFORE this commit, caught four in-cycle corrections now folded into the resolutions above: (1) a
subclass overriding only `http_error_302` leaves 301/303/307/308 on the base unbounded handler → all
five aliases MUST be rebound (and `064.027-T` parametrizes the cap scenario across them); (2) two
redirect handlers cannot coexist (`OpenerDirector` runs only the first that returns a response) → the
drain is folded into the EXISTING `_ValidatingRedirectHandler`, not a new handler; (3) with
`max_redirects` default 5 a single under-cap chain cannot reach 512 MiB → the aggregate scenario seeds
the budget low / pre-consumed to prove the decrement hermetically; (4) `parse_constant` does not catch
overflow literals (`1e400` → `inf`) → a `math.isfinite()` id guard (`-32600`) closes that path.

Re-review verdict (cycle-10, post-remediation): the redirect-drain bypass is closed by extending the
existing single `_ValidatingRedirectHandler` (all redirect-code aliases rebound; ONE composite
handler) to bounded-read/count intermediate 3xx bodies against the same per-response and aggregate
allowances while preserving redirect function and §H6 revalidation; the non-finite framing bug is
closed by a strict `parse_constant` rejection (`-32700`, tokens) plus a `math.isfinite()` id guard
(`-32600`, overflow literals) before era routing, guaranteeing no non-finite number reaches
`RequestId` or response serialization. Both fixes stay width-isolated (Finding A: 1 new harness+impl
pair, single file each; Finding B: in-place kwarg + inline clause + parametrized rows), the chain stays a single
linear acyclic test-first chain (`… → 064.026 → 064.027 → 064.028 → 064.014 → …`, 28 tasks), and no
2-hour/width/scenario/function budget is breached. All P0/P1 findings closed.

### Cycle-11 review remediation (PR #166, fresh Copilot review on HEAD f172806, third three-cycle allowance round 2)

Cycle-11 reconciles two threads on HEAD `f172806`. Both are in-place strengthenings — **no new
task** is created and the manifest stays at 28 tasks; the single linear acyclic test-first chain,
every dependency edge, shipment `055-S` membership, and execution order are all unchanged. Reconciled
across plan, feature DoD, tasks, and continuity memory.

- **The cycle-8 `MAX_FETCH_ATTEMPTS` frontier-pop counter does not bound actual outbound requests
  (thread A, `064.025-T`/`064.026-T`).** The cycle-8 mechanism placed a per-request `fetch_attempts`
  counter in `fetch/crawl.py` that incremented only on main-page frontier pops. But robots.txt
  (`_robots_allow`), mdBook TOC-script discovery (`_discover_toc_links`), per-pop retries
  (`_fetch_with_retries` issues a fresh `fetch_page` per attempt), and redirect hops
  (`_ValidatingRedirectHandler`) are all real outbound requests a main-page-pop counter never sees,
  and the per-response/aggregate BYTE budgets bound transfer VOLUME not request COUNT (empty or tiny
  robots/TOC responses barely spend the byte budget) — so the frontier-pop counter is bypassable.
  **Resolution:** the frontier-pop counter is REPLACED by a request-scoped fetch-attempt budget on
  the SAME request-scoped budget object (`RemainingByteBudget`) that `064.017-T`/`064.024-T` already
  thread through every `fetch_page` call: a per-request attempt allowance seeded at
  `MAX_FETCH_ATTEMPTS = 4000`, debited ONE **before** each direct outbound request at the common
  `fetch_page` boundary (`fetch/http.py`; main pages, robots, TOC, retries — each a distinct
  `fetch_page` call, pre-I/O) AND ONE per redirect hop **inside** the shared `_ValidatingRedirectHandler`
  before the next hop is followed (pre-I/O), exactly as the aggregate byte budget already decrements
  intermediate 3xx bodies in that same handler — NOT a post-`open()` `handler.redirect_count` tally
  (which would let urllib follow up to `max_redirects` hops beyond the cap before raising;
  `handler.redirect_count` is retained for observability only),
  RAISING a typed `FetchAttemptBudgetExceededError` — a `DoclineError` subclass of
  `AggregateBudgetExceededError`, so the four existing `except AggregateBudgetExceededError: raise`
  clauses in `crawl.py` propagate it out of `crawl()` with NO new `crawl.py` edit — the instant a
  debit would cross the cap. Because every direct outbound request funnels through `fetch_page` and
  every redirect hop funnels through the shared handler, auxiliary/retry/redirect traffic cannot bypass
  the count. Ownership: the boundary debit is delivered by `064.026-T` (harness `064.025-T`, proving
  robots/TOC/retry debits); the per-hop redirect-attempt debit is delivered by the redirect-drain impl
  `064.028-T` (harness `064.027-T`), co-located with the intermediate-body byte decrement it already
  owns — no new task and no new file for either. `064.025-T`/`064.026-T` are **re-scoped in place**:
  the harness now proves the cap trips from robots/TOC/retry traffic while `page_count` stays low, and
  the impl file set moves `fetch/crawl.py` → `fetch/http.py` (still 2 files with `app_models.py`); the
  `FetchRequest.depth` `Field(default=0, ge=0, le=64)` upper bound is unchanged. Dependency chain
  (`064.024 → 064.025 → 064.026 → 064.027 → 064.028 → 064.014`), shipment `055-S` membership, and
  execution order are unchanged. Plan §H7 item 4, "Selected numeric limits" `MAX_FETCH_ATTEMPTS` note,
  "Cap tasks", decomposition 10c/10d/10e/10f, Rollback, feature DoD H7 clause, and
  `064.025-T`/`064.026-T`/`064.027-T`/`064.028-T` all reconciled; the cycle-8 subsection above carries a
  superseding pointer to this mechanism.
- **`server/discover` was treated as a bare pre-handshake call exempt from `_meta` validation
  (thread B, `064.020-T`/`064.022-T`).** The Protocol Era Model, method map, and tasks described every
  modern `tools/*` request as requiring per-request `_meta` with BOTH
  `io.modelcontextprotocol/protocolVersion` AND `io.modelcontextprotocol/clientCapabilities`, but the
  era-routing precedence carried a separate `server/discover → discovery (pre-handshake)` branch and
  the method map/table presented `server/discover` as "answerable before any request" — implying it
  could be served WITHOUT `_meta`. MCP `2026-07-28` requires per-request `_meta` on every modern
  request, and `server/discover` is a modern-only method. **Resolution:** `server/discover` is routed
  through the SAME per-request `_meta` validator as every modern request — a valid discovery request
  MUST supply BOTH `protocolVersion` AND `clientCapabilities` (unsupported version → `-32022`, then
  missing/malformed `clientCapabilities` → `-32602`, version-first) — while still requiring NO prior
  `initialize` (pre-handshake availability does NOT waive required `_meta`). Reconciled across the
  Scope modern-era bullet, the Design method map, the Protocol Era Model table (Discovery row) and
  era-routing precedence, the feature DoD dual-era clause, `064.020-T` (scenario (a) sends
  `server/discover` WITH valid `_meta`; scenario (c) adds `server/discover` rejection rows as an axis —
  scenario budget stays 3), and `064.022-T` (`server/discover` dispatch runs through the `_meta`
  dual-member validator before returning the `DiscoverResult` — an ordering constraint on the existing
  validator, no new function, `<=2`-file/`<5`-function budget unaffected). No new task; the
  metadata-free `tools/*` pre-initialize reject (`064.021-T`/`064.023-T`) is unchanged.

Re-review verdict (cycle-11, post-remediation): the request-COUNT bound now debits pre-I/O at the
`fetch_page` choke point for direct outbound calls (`064.026-T`/`064.025-T`) AND per redirect hop
inside the shared `_ValidatingRedirectHandler` before the next hop is followed (`064.028-T`/`064.027-T`),
so robots/TOC/retry/redirect outbound traffic cannot bypass
`MAX_FETCH_ATTEMPTS`, reusing the existing request-scoped budget threading and `crawl.py` re-raise
clauses (`064.025-T`/`064.026-T` re-scoped in place, still 2 files, chain/membership/order unchanged);
`server/discover` is no longer exempt from `_meta` validation and is validated identically to every
modern request while remaining answerable pre-`initialize`. Both fixes are in-place (no new task,
manifest stays 28), the chain stays a single linear acyclic test-first chain, and no
2-hour/width/scenario/function budget is breached. All P1 findings closed. (Superseded in part by
cycle-12: the cycle-11 redirect-hop debit placement "inside `http_error_302` before `super()`" is
corrected below to `redirect_request` after validation; the ownership moves from `064.028-T`/`064.027-T`
to the new pair `064.030-T`/`064.029-T`.)

### Cycle-12 review remediation (PR #166, fresh Copilot review on HEAD `13b14b7`, Copilot round 3)

Cycle-12 routes two redirect residuals from the Copilot round-3 review through a **full Stage
decomposition** — not an in-place fix — per operator directive. The redirect hardening previously
entangled TWO responsibilities in the `064.027-T`/`064.028-T` pair (intermediate-body byte drain AND
redirect-hop attempt accounting); cycle-12 splits them into TWO width-isolated test-first pairs and
adds the missing resource-closure guarantee. The manifest grows **28 → 30 tasks** (a NEW pair
`064.029-T`/`064.030-T`); the chain gains `064.026 → 064.027 → 064.028 → 064.029 → 064.030 → 064.014`,
with `064.014-T` re-pointed from `064.028-T` to `064.030-T`; shipment `055-S` = 064-F + 30 tasks (31
members). Reconciled across plan (intro cycle list, §H7 item 2, §H7 item 4a, "Cap tasks",
decomposition 10e/10f/10g/10h, dependency edges, execution order, Verification, Rollback, SA-1, Risks),
feature DoD, tasks `064.014-T`/`064.025-T`/`064.026-T`/`064.027-T`/`064.028-T`/`064.029-T`/`064.030-T`,
shipment `055-S`, and continuity memory, preserving dependency acyclicity and every
2-hour/width/scenario/function budget.

- **Bounded redirect-body proxy leaks the intermediate response `fp` on a cap-breach mid-read
  (Finding A, `064.028-T`).** _(SUPERSEDED by Cycle-13 below: the closure guard scope is broadened to
  also close the real `fp` on the `redirect_request`-raised `FetchError` (redirect cap) and
  `CrawlUrlRejectedError` (§H6), not only the two cap breaches.)_ The cycle-10 override wraps the intermediate `fp` in a bounded proxy and
  delegates to `super().http_error_302(...)`. CPython's `HTTPRedirectHandler.http_error_302` reads the
  `fp` and only calls `fp.close()` AFTER a completed `fp.read()`; when the proxy raises a per-response
  OR aggregate cap error MID-STREAM, that `fp.close()` is never reached, so the underlying intermediate
  3xx response `fp` — a live socket/connection — LEAKS (a slow-drip resource-exhaustion residual under
  a hostile redirect chain that repeatedly trips the cap). **Resolution:** the override MUST CLOSE the
  real intermediate `fp` before the typed cap error propagates, on BOTH breach paths — wrap the
  `super()` delegation in `except (per-response cap error, AggregateBudgetExceededError): fp.close(); raise`.
  Because `FetchAttemptBudgetExceededError` subclasses `AggregateBudgetExceededError`, this SAME guard
  also releases `fp` when the redirect-hop attempt debit (Finding B) raises from `redirect_request`, so
  closure holds across all typed budget/cap breaches without duplicate close logic (`fp.close()` is
  idempotent). Delivered by re-scoped `064.027-T` (harness — adds fp-closure assertions on the
  per-response and aggregate breach scenarios via an instrumented `fp` recording `.close()`) /
  `064.028-T` (impl — adds the closure guard; the attempt debit is removed from `http_error_302`).
  Scenario budgets unchanged (closure folded as assertions on the existing two cap scenarios).
- **Redirect-hop attempt debit is placed too early — in `http_error_302` before `super()` (Finding B,
  plan §H7 item 4a redirect-hop clause).** The cycle-11 mechanism debited one `MAX_FETCH_ATTEMPTS`
  attempt inside the `http_error_302` override BEFORE delegating to `super()`. But `super()` performs
  Location resolution, the scheme check, loop detection, and calls `redirect_request` (which also runs
  the §H6 address-pinned revalidation) — ANY of which can REJECT the redirect before `parent.open()`
  (the outbound I/O). Debiting before `super()` therefore charges a fetch-attempt even for redirects
  that policy/scheme/loop validation REJECTS (no outbound request occurs), corrupting the request-COUNT
  accounting and prematurely exhausting the budget on rejected hops. **Resolution:** the debit MOVES
  into `_ValidatingRedirectHandler.redirect_request`, debiting exactly once immediately BEFORE it
  returns a non-None `Request` — after the stdlib `super().redirect_request` build AND the §H6
  revalidation, before the hop's outbound I/O. Because `redirect_request` returns a non-None `Request`
  if-and-only-if the redirect will actually be followed, an attempt is charged only for a FOLLOWED hop;
  a redirect rejected by stdlib (`None` return) or §H6 revalidation (raises) consumes NO attempt.
  `FetchAttemptBudgetExceededError` is raised from inside `redirect_request` on breach (before
  returning the `Request`, so pre-I/O) and propagated by the existing `crawl.py` re-raise clauses (no
  `crawl.py` edit); `handler.redirect_count` stays observability-only. Delivered by a NEW
  width-isolated pair — harness **`064.029-T`** (T-redir-attr-h, tests domain, 2 scenarios:
  debit-on-follow placement incl. no-debit-on-reject; attempt-breach-refused-before-outbound-I/O) and
  impl **`064.030-T`** (T-redir-attr-i, code domain, ≤1 file `fetch/http.py` — moves the debit, reuses
  the `MAX_FETCH_ATTEMPTS` allowance seeded by `064.026-T` and threaded into the handler by
  `064.028-T`, no new constant). Depends on `064.028-T` (the handler already receives the budget and
  the closure guard is in place); `064.014-T` is re-pointed onto `064.030-T`.

Internal multi-persona adversarial re-review (Python urllib lifecycle / resource ownership; precise
attempt accounting; testability; task sizing; dependency order; rollback; dual CLI/MCP impact), run
against the CPython `urllib.request` source, returned an initial FAIL that surfaced six corrections,
ALL folded into the artifacts above before commit: (i) the debit cannot be "after loop validation"
(loop detection runs AFTER `redirect_request`) — reworded to "after the scheme check and §H6
revalidation" everywhere; (ii) the `064.029-T` red baseline was self-contradictory — after `064.028-T`
there is NO redirect-hop debit, so debit-on-follow + attempt-breach are the red-first scenarios and
no-debit-on-reject rows are regression anchors; (iii) the closure guard is scoped to Finding A's two
cap failures (+ the subclassed attempt breach), not over-claimed for every exit (stdlib scheme/loop
`HTTPError` carries its own `fp` per contract — the documented residual); (iv) the loop-detection AND
body-drain-breach over-counts are re-characterized as CONSERVATIVE (never UNDER-count a followed hop,
so the DoS upper bound holds), with the deliberate `redirect_request`-over-proxy-`close()` choice made
explicit for width-isolation; (v) the `064.029-T` attempt-breach scenario now seeds the allowance near
`MAX_FETCH_ATTEMPTS - 1`; (vi) rollback within the redirect cluster is reverse-topological / atomic.
Post-reconciliation the review confirmed: (1) stdlib `http_error_302` orders `redirect_request`
(→ attempt debit) BEFORE `fp.read()`/`fp.close()` (→ body drain) BEFORE `parent.open()` (→ outbound
I/O), so the Finding-B debit is correctly "after validation, before outbound I/O", and the Finding-A
closure guard in `http_error_302` wraps the whole delegation and thus also covers the attempt-breach
raise; (2) `fp.close()` is idempotent on `http.client` responses, so the guard cannot double-free; (3)
a redirect rejected by the scheme check or by §H6/stdlib `redirect_request` reaches no debit
(debit at the end, before `return new_request`), satisfying no-debit-on-reject; (4) both new tasks are
single-domain (tests `064.029`, code `064.030`), <2h, and the chain stays a single linear acyclic
test-first chain (`… → 064.028 → 064.029 → 064.030 → 064.014 → …`, 30 tasks); (5) rollback is
reverse-topological within the shared `fetch/http.py` cluster with cross-interface (CLI + MCP) blast
radius unchanged. All P1 findings closed; no budget breached.

### Cycle-13 — PR #166 Copilot post-decomposition cycle 1 (Finding-A closure broadening + card-10g wording)

Operator-directed Stage remediation of three Copilot findings on HEAD `75dd336` (planning/backlog/plan/memory
artifacts only). Multi-persona adversarial review run first (verdict ADVISORY → PASS after the card-10g fix).

- **Finding A closure scope BROADENED (supersedes the cycle-12 "two cap failures" scoping above).** Copilot
  observed that the cycle-12 closure guard is too narrow: `redirect_request` also raises the custom redirect-cap
  `FetchError` and the §H6 `CrawlUrlRejectedError`, both BEFORE stdlib `http_error_302` reaches its own
  `fp.read()`/`fp.close()`, and — unlike stdlib `HTTPError` — neither carries the `fp`, so those exits leak the
  intermediate 3xx connection identically. **Resolution:** the `http_error_302` closure guard is broadened to
  `except (per-response cap error, AggregateBudgetExceededError, FetchError, CrawlUrlRejectedError): fp.close(); raise`,
  closing the real `fp` on the two body-drain cap breaches AND the two `redirect_request`-raised custom exits
  (and, via the `AggregateBudgetExceededError` subclass, the `064.030-T` attempt breach). EXACT exception
  ownership, no broad swallowing: within the `super().http_error_302` delegation the ONLY `FetchError` is the
  redirect cap and the ONLY `CrawlUrlRejectedError` is the redirect-target §H6 rejection (the generic
  fetch-failure `FetchError` and the initial-URL `validate_crawl_url` both live in `fetch_page`, OUTSIDE the
  handler); each caught exit is re-raised (never swallowed); stdlib scheme/loop `HTTPError` (carries `fp`) is
  deliberately NOT caught and remains the sole documented residual. `fp.close()` idempotency makes the redundant
  close on a deeper recursive `parent.open()` hop a no-op. `064.028-T` broadens the guard; `064.027-T` folds two
  fp-closure-on-reject rows (redirect-cap `FetchError`, §H6 `CrawlUrlRejectedError`) into scenario c — scenario
  budget UNCHANGED at 3, no decomposition (width does not exceed policy). §H7 item 2, cards 10e/10f, Risks, and
  feature 064-F DoD all reconciled to the broadened scope.
- **F1 — card 10g wording corrected (attempt-accounting consistency, "no-debit-on-loop" removed).** The
  §H-decomposition card 10g (`064.029-T`) still read "after stdlib scheme/loop validation" and drove a
  "loop-INVALID … debits NOTHING" target — the impossible no-debit-on-loop claim that cycle-12 reconciled
  everywhere else (§H7 item 4a, `064.029-T`/`064.030-T`, `064-F` DoD, Risks) but MISSED here. Corrected to
  "after the stdlib scheme check AND §H6 revalidation"; the no-debit assertion is scoped to scheme-check /
  `redirect_request` `None`-return / §H6 raises; a loop-terminated hop incurs the documented one-attempt
  CONSERVATIVE over-count (stdlib loop detection runs AFTER `redirect_request`). `064.029-T`/`064.030-T`
  conservative-loop semantics are otherwise UNCHANGED.
- **Memory/handoff corrected.** The cycle-12 memory Do-NOT ("Do NOT charge an attempt for a redirect rejected by
  scheme/loop/§H6 validation") and the two `memories.json` durable-handoff "rejected redirects consume no attempt"
  claims were re-scoped to scheme/§H6 rejects with the loop over-count noted. Dependency chain
  (`064.026 → 064.027 → 064.028 → 064.029 → 064.030 → 064.014`), shipment `055-S` (31 members), and red-before-green
  ordering are UNCHANGED.

### Cycle-14 — PR #166 post-decomposition cycle 3 (§H8 external-PDF-engine opt-in gate)

Operator-directed FULL Stage pass (planning/backlog/plan/memory artifacts only) closing the one
remaining unresolved HIGH-RISK Copilot finding on HEAD `872989e` (thread `PRRT_kwDOSsAX4c6dWm-8`,
comment 3885302527, `.backlogit/queue/064.015-T.md:26`): the MCP-specific `process` schema inherits
`pdf_engine="mistral_ocr"`, letting an untrusted local MCP caller consume ambient
Foundry/Mistral credentials and base64-upload workspace PDFs to an external PAID OCR endpoint. Per
operator direction this was routed through further decomposition + a multi-persona adversarial
security/design review, not an ordinary fix cycle.

- **New §H8 hardening item** (external-PDF-engine opt-in gate) added to `## Plan Hardening`, mirroring
  §H1's omit-and-reject: a local-engine ALLOW-LIST `{auto,docling,heuristic}` (fail-closed for future
  external engines), build-time advertise omission in `list_callable_tools()` (the THIRD sanctioned
  MCP-only parity divergence), a runtime dispatch reject (`-32602`) at a single adapter chokepoint
  consulted by both `call_tool` and the public `process()` (so no transport path bypasses it, since
  the shared `ProcessRequest` stays permissive for CLI parity), dual-era parity through the one
  hardened dispatch, and a fail-closed, instance-local, startup-only server-side opt-in
  (`DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES=1` / `--allow-external-pdf-engine`) that a client can never
  spoof from request data. Grounded read-only: `request.pdf_engine` is the SOLE client-controllable
  selector of the external reader (`readers/pdf.py` auto-policy never resolves to `mistral_ocr`,
  `docling` is local, `pdf_mode=triage` ignores `layout_engine`, `MISTRAL_OCR_MODEL` only renames an
  already-selected engine), so gating that field is complete.
- **Decomposition:** six new width-isolated red/green tasks — `064.031-T`/`064.032-T` (adapter policy:
  advertise omit + dispatch chokepoint raising `ExternalEngineNotAllowedError`, `server.py` +
  `exceptions.py`), `064.033-T`/`064.034-T` (transport `-32602` mapping, dual-era, `stdio.py`), and
  `064.035-T`/`064.036-T` (fail-closed instance-local startup opt-in, `__main__.py`). Inserted into
  the single linear chain after `064.023`: `… → 064.023 → 064.031 → 064.032 → 064.033 → 064.034 →
  064.008 → 064.003 → 064.035 → 064.036 → 064.004` (re-thread `064.008`'s dependency `064.023 →
  064.034` and `064.004`'s `064.003 → 064.036`). Chain stays strictly linear and acyclic; the
  runnable executable (`064.003`) lands AFTER the omit+reject gate is green, so no runnable artifact
  ever exposes the engine without opt-in; shipment `055-S` grows to 37 members (`064-F` + 36 tasks).
- **Adversarial review remediations folded in.** Security review: (P1) `ingest_local_dir` — the
  SECOND `pdf_engine`-bearing tool running the same `execute_process` egress — is already excluded
  from the MCP advertise set + `call_tool` allow-list (§H1 Design + §H4/`064.007-T`); §H8 adds an
  explicit negative assertion so it is provably no egress bypass. (P2) belt-and-suspenders — the
  reject lives at the adapter `process()` chokepoint (not `call_tool` alone) so no adapter path
  regains egress. (P2) residual paid-egress once enabled — recorded as an accepted documented risk
  (Risks/SA-2), out of scope to cost-bound here. (P3) spoofed opt-in field + no-secret reject/startup
  logging — added as negative rows/assertions in `064.031`/`064.033`/`064.035`. Design review:
  re-partitioned into adapter-policy (`031/032`) vs transport-mapping (`033/034`) to keep each impl
  within the <3-file/<5-function budget; adopted an ALLOW-LIST over a `mistral_ocr` deny-list; made
  the startup opt-in fail-closed (exact `"1"`) and instance-local (fresh server to `serve(server=…)`,
  no `SERVER` mutation); `064.035` tests the real `main()` wiring.
- **Reconciled artifacts:** feature `064-F` DoD (H1–H7 → H1–H8 + CLI-parity qualification), this plan
  (§H8, decomposition tasks 21–29 renumbered, dependency edges, execution order, Verification,
  Rollback, SA-2, Risks), shipment `055-S` (37 members), affected-task cross-references
  (`064.001`/`064.003`/`064.009`/`064.015`/`064.021`/`064.023`), `memories.json`, and a new Stage
  checkpoint. Validation (YAML/JSON/Markdown, backlog index, acyclic deps, shipment order,
  red-before-green, task size) clean. NOT pushed; no PR actions; Ship not invoked; `055-S`
  queued/unclaimed. Production source unchanged (planning artifacts only).

### Cycle-15 — PR #166 post-decomposition cycle 1 (§H8 exact-token opt-in hardening)

Operator-directed Stage pass (planning/backlog/plan/memory artifacts only) closing two unresolved
Copilot findings on HEAD `36c4b15` against the §H8 startup opt-in RED/GREEN pair:

- **`064.036-T` (thread `PRRT_kwDOSsAX4c6dXIsf`, comment 3885516661):** the impl acceptance criterion
  specified `os.environ.get(name, "").strip() == "1"`. The `.strip()` enabled whitespace/newline-padded
  tokens (`" 1 "`, `"1\n"`), contradicting the exact-token contract and opening paid external egress on
  the untrusted MCP surface. Corrected to RAW exact-token equality
  `os.environ.get("DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES") == "1"` (no strip/trim, no case-fold, no
  coercion; unset -> `None != "1"` -> DISABLED).
- **`064.035-T` (thread `PRRT_kwDOSsAX4c6dXIsc`, comment 3885516655):** the RED harness scenario (a)
  DISABLED rows (`"0"/"false"/"true"/"yes"/""`/whitespace-only) did not discriminate raw equality from a
  `.strip()` impl. Added the padded-`"1"` discriminators (`" 1"`, `"1 "`, `" 1 "`, `"1\n"`) — GREEN only
  under raw `== "1"`, RED under any trim impl — as the TDD guard for the exact-token contract. The two
  edits land atomically (a strip fix without the guard leaves the contract untested; a guard without the
  fix makes `064.036` self-contradictory).
- **Plan §H8 statements unchanged** (already correct: "only the exact token `"1"` enables; any other
  value stays disabled" — §H8 gate item 4 and the Verification harness bullet). Feature `064-F` DoD H8
  ("fail-closed on any non-`"1"` value") unchanged — already exact-token-correct. No other H8 task
  (`064.031`–`064.034`) carries a strip/trim predicate.
- **Adversarial review (this cycle):** verdict — the corrected contract (raw `== "1"` + padded-`"1"`
  DISABLED rows) is sufficient and fail-closed; raw equality is the tightest correct predicate and breaks
  no sanctioned opt-in path (`export …=1`, `.vscode/mcp.json` `"1"`, `-e VAR=1`). Confirmed the CLI flag
  and env token stay independent OR enablers, the module `SERVER` stays external-disabled (startup-only,
  instance-local, never re-read from request data), and the **six-task decomposition + linear
  dependency/shipment order are PRESERVED** — the fix is a text-level correction inside the existing
  RED/GREEN pair's existing files and scenario (a); no new file surface, no new dependency edge, no
  <4-scenario/<3-file budget breach, no split justified. NOT pushed; no PR actions; Ship not invoked;
  `055-S` queued/unclaimed. Production source unchanged (planning artifacts only).

### Cycle-16 — PR #166 H8 round cycle-3 (Finding A id-less-notification reconciliation + Finding B sitemap-CGNAT work item)

Operator-directed FULL Stage pass (planning/backlog/docs artifacts only) on HEAD `d402b10`,
routing two unresolved Copilot findings through further decomposition + a four-persona adversarial
review (Correctness, Security, Scope Boundary, Architecture — cross-model where available) rather
than an ordinary fourth fix.

- **Finding A (thread `PRRT_kwDOSsAX4c6dXgJo`, comment 3885656380; plan line ~259) — id-less ≠
  automatically a notification.** The prior prose ("`None` for any id-less notification"; "an absent
  id stays a notification") could be read to SUPPRESS a malformed id-less payload
  (`{"jsonrpc":"2.0"}`, non-object root) that JSON-RPC 2.0 requires to answer with `-32600` /
  `id:null`. **Resolution:** an ORDERING INVARIANT is made explicit and test-bound — request-shape
  validation over `{root, jsonrpc, method, id-type}` runs BEFORE the id-absent notification-suppression
  branch in the single shared `dispatch()`. An absent id makes a payload silent ONLY when the payload
  is OTHERWISE VALID (object root, `jsonrpc` `"2.0"`, present non-empty-string `method`) — a true
  notification, silent even for an unknown method or malformed `params`; an absent id on a MALFORMED
  payload returns `-32600` with `id:null`, never suppression. Reconciled across the plan
  (dispatch docstring, request-shape section, cycle-9 record), feature `064-F` DoD, and tasks
  `064.002-T` (impl ordering clause), `064.005-T` (legacy/shared red rows), `064.021-T` scenario (c)
  (modern red row). Correctness-review closure folded in: the `method` predicate is unified as
  present+string+**non-empty** in BOTH the shape guard and the notification precondition (empty-string
  `""` → `-32600`; whitespace-only → `-32601`); id-absence is decided by KEY MEMBERSHIP not truthiness
  (a present `id:0`/`id:""` gets a normal echoed response, never suppression); the `-32600` response
  echoes a VALID present id on a non-id defect and uses `id:null` only for an absent/malformed/non-finite
  id; the pre-suppression guard field-set is locked to `{root, jsonrpc, method, id-type}` (`params`
  validation is post-suppression, id-bearing only); and the array-root → single `-32600` (no batching)
  basis is recorded.
- **No new 064 task (Finding A).** Assessed and confirmed by the Scope Boundary + Correctness personas:
  the id-absent-malformed, empty-method, valid-id-echo, and `id:0`/`id:""`-membership cases are added as
  extra PARAMETRIZED ROWS to the EXISTING `-32600` request-shape / notification / dispatch-parity
  scenarios in `064.005-T` (and the modern row in `064.021-T` scenario (c)); scenario count stays 3 (one
  bounded parametrized matrix), the impl is a clause-ORDERING guarantee inside the existing `dispatch()`
  guard (no new function, `≤4`-function / `<3`-file transport budget intact), width stays isolated
  (tests-only vs code-only). Adding a task would be over-decomposition. Shipment `055-S` stays at
  **37 members**, order unchanged.
- **Finding B (thread `PRRT_kwDOSsAX4c6dXgJs`, comment 3885656388; plan line ~2722) — sitemap CGNAT
  gap had no backlog item.** Created a REAL queued high-priority security work item OUTSIDE `055-S`:
  feature `065-F` (chore/security) with red `065.001-T` → green `065.002-T`, in NEW shipment `056-S`,
  grounded in `src/docline/fetch/sitemap.py:173-189` (`_is_unsafe_address`), linked `related_to` `064-F`
  (same address class, different surface) with NO blocking dependency. Plan
  (`docs/plans/2026-08-28-sitemap-cgnat-ssrf-gap-plan.md`) + deliberation
  (`docs/decisions/2026-08-28-sitemap-cgnat-ssrf-gap-deliberation.md`) authored; the `## Risks`
  tracked-follow-up bullet now points at the item.
- **`055-S` proceeds — it does NOT block on the sitemap fix (Security verdict, independently traced).**
  `validate_sitemap_url`/`_is_unsafe_address` has ZERO production callers (the live CLI+MCP crawl path
  routes `mcp/server.py`→`app.execute_fetch`→`elt.execute`→`fetch.crawl`→`fetch.http`→
  `url_policy.validate_crawl_url`; robots handling uses `RobotFileParser.can_fetch`, never
  `discover_sitemaps_from_robots`) — the CGNAT gap is DORMANT defense-in-depth. §H6 (part of `055-S`,
  touching `url_policy.py`/`http.py`) re-implements the classifier with an INDEPENDENT explicit
  `100.64.0.0/10` check, so the SSRF guard `055-S` ships is CGNAT-complete on the live path without
  the sitemap helper. `055-S` scope is NOT expanded. An activation-condition edge is recorded on
  `065-F`: any FUTURE shipment that wires sitemap discovery into the crawl MUST depend on `065-F`.
- **SSRF classifier drift (Security P3 + Architecture P2) tracked.** Post-`064-F`/`065-F` the CGNAT
  literal exists as two independent copies (`url_policy` vs `sitemap`). A per-surface coverage matrix is
  recorded in the deliberation, and the Option-B consolidation onto one canonical classifier is filed as
  stash entry `87F2C06D` (kind=feature, priority=medium) so it cannot be lost.
- **Adversarial outcome (4 personas):** Correctness — reconciliation substantially correct; two P2
  precision fixes (empty-method predicate unification, id-membership-not-truthiness) folded in, plus
  spec advisories. Security — VERDICT `055-S` MUST NOT block (dormant + independent H6 classifier);
  create the separate item (done). Scope — no new 064 task necessary (9/10); Finding B red+green +
  separate shipment correct (8/10); `055-S` isolation verified (10/10). Architecture — `065-F`
  independent of `064-F` (9/10, disjoint files, no merge conflict); separate shipment `056-S` justified
  (8/10); `related_to` (non-blocking) correct (8/10); DAG acyclic; `056-S` is the correct next shipment
  id (the review-prompt's hypothetical `066-S` was NOT materialized — no phantom). NOT pushed; no PR
  actions; Ship not invoked; `055-S` queued/unclaimed. Production source unchanged (planning artifacts
  only).

### Cycle-16 round cycle-1 — PR #166 review round (HEAD `845686a`): H7 byte-semantics re-scope + era-routing discriminator

Operator-directed Stage reconciliation (planning/backlog/docs artifacts only) on HEAD `845686a`,
closing four unresolved Copilot findings in two clusters after a two-model adversarial multi-persona
review (Correctness/Security/Scope/Protocol-Compat, Claude Opus 4.8 + GPT-5.6 Sol). Both approaches
returned sound with no blocking defects; the truthfulness/coverage refinements below were folded in.
No new task; shipment `055-S` stays at **37 members**, order unchanged.

- **H7 byte semantics (comments 3885775394 / 3885775424 on `064.017-T` / `064.016-T`) — the aggregate
  budget counts entity-body bytes, not raw wire bytes.** `len(body_bytes)` is NOT a raw-wire count:
  `urllib`/`http.client` removes HTTP transfer framing (chunk-size lines, trailers) and headers before
  `HTTPResponse.read()` returns, and does not content-decode (`gzip` stays compressed). The
  repeatedly-claimed "exact network-transfer / raw-wire budget" overstated the bound and the
  non-ASCII/invalid-byte tests could not prove it. **Resolution (chosen the simpler, reliable
  re-scope, not lower-level wire accounting — the DoS surface is memory + `output_dir` staging, which
  entity-body bytes DO bound):** the invariant is re-scoped consistently to **entity-body bytes** (the
  undecoded response-content bytes returned by `HTTPResponse.read()`, transfer framing and headers
  excluded, before charset decoding) across §H7 item 3, the design summary, Selected numeric limits
  (`MAX_RESPONSE_BYTES` + `MAX_TOTAL_FETCH_BYTES` boundaries), Verification, Rollback, feature `064-F`
  DoD, tasks `064.016-T`/`064.017-T`/`064.024-T`, and the session memories. `body_byte_count` is
  narrowed to completed-terminal-`FetchResponse` observability only (not the enforcement source, not a
  record of failed/retried/intermediate responses). "at most one crossing byte pulled from the socket"
  is corrected to "`HTTPResponse.read()` returns at most one entity-body byte beyond the allowance"
  (docline cannot constrain socket-level pulls). The non-ASCII multibyte / invalid-byte tests are
  retained and reframed to prove ONLY that enforcement happens below charset decoding (resisting a
  decode/re-encode **undercount**); they explicitly do NOT claim chunk-framing or header-overhead
  coverage. A new accepted-residual `## Risks` bullet records what the entity-body budget does NOT
  bound (headers, transfer framing, raw socket bandwidth, parser CPU, exact post-decode memory/disk).
- **Era routing (comments 3885775403 / 3885775415 on `064.022-T` / `064.021-T`) — ancillary legacy
  `_meta` must not trigger modern validation.** Using per-request `_meta` presence as the era
  discriminator broke retained `2025-11-25` clients: a legacy request may legitimately carry ancillary
  `_meta` (e.g. `_meta.progressToken`) with no 2026 negotiation member, so it would be misrouted to the
  modern validator and rejected. **Resolution:** the discriminator is re-keyed to the **presence** (key
  membership, not truthiness) of a namespaced modern negotiation member — canonically
  `io.modelcontextprotocol/protocolVersion`, equivalently `io.modelcontextprotocol/clientCapabilities`
  (keying on either avoids misrouting a version-less-but-capabilities-bearing modern request to legacy;
  both members are modern-namespaced and absent from legacy clients, so there is no legacy
  false-positive) — plus the explicit `server/discover` (modern-only) rule; otherwise honor the
  established per-process legacy latch, and reject pre-`initialize`. Precedence is explicit: a modern
  member wins **even after** a legacy latch (a `protocolVersion`-bearing request following `initialize`
  is still modern). The Protocol Era Model routing bullet, the Design method-map era-routing note, the
  `064.020-T`/`064.021-T`/`064.022-T`/`064.023-T` tasks, feature `064-F`, the deliberation, and the
  memories are reconciled to this discriminator. `064.021-T` scenario (b) gains three parametrized rows
  (scenario count stays 3): (i) post-`initialize` ancillary-`_meta`-only request stays legacy; (ii)
  pre-`initialize` ancillary-`_meta`-only request is rejected (not the modern `-32602` path); (iii)
  modern-wins-after-latch. `064.020-T` scenario (c) gains a present-but-malformed-`protocolVersion`
  parametrized axis (member present → modern validator → `-32602`/`-32022`, never legacy fallthrough).
  Green attribution: the protocolVersion-keyed discriminator (so ancillary `_meta` is not misclassified
  modern) is delivered by `064.022-T`; the new latch-dependent rows are RED at authoring and green at
  `064.023-T` (they require the per-process legacy latch it owns).
- **Adversarial outcome (2 models × multi-persona):** Both models — VERDICT: approaches sound, no
  blocking defects. Correctness/Protocol-Compat — "entity-body bytes" is the correct term for
  `HTTPResponse.read()` output; the re-scope leaves no memory/disk DoS hole; `protocolVersion`(-or-
  `clientCapabilities`)-keyed precedence is the required fix and modern-wins-after-latch is correct.
  Security — no guard bypass (both eras still funnel through one hardened dispatch); the entity-body
  residual (headers/framing/bandwidth/CPU unbounded) is acceptable and now recorded. Scope — no new
  task warranted; parametrized rows are the correct width; `055-S` unchanged. Refinements folded in:
  drop the "network/real transfer" overclaim, qualify bare "raw" as undecoded, add the pre-init
  ancillary-`_meta` reject + modern-wins rows, correct green attribution, key on either modern member.
  NOT pushed; no PR actions; Ship not invoked; `055-S` queued/unclaimed. Production source unchanged.

### Cycle-16 round cycle-2 — PR #166 review round (HEAD `30fad9b`): 5 findings reconciled (planning/backlog/docs only)

Operator-directed Stage reconciliation on HEAD `30fad9b`, closing five Copilot review findings
after a multi-persona adversarial review (security limits / valid MCP frame sizes / liveness
testability / TDD ordering / IPv4-mapped normalization / scope accounting / shipment isolation / PR
disclosure). No production/test source changed; no new task; shipment `055-S` stays at **37
members**, `056-S` at **3 members**, order unchanged.

- **IPv4-mapped normalization (comment 3885888208 on `065.002-T`).** The sitemap SSRF membership
  test allowed the mapped IPv6 literal `::ffff:100.64.0.1`: an `IPv6Address` is not a member of the
  IPv4 `_CGNAT_NETWORK`, and 3.12 patch levels do not classify mapped special-use addresses
  consistently. **Resolution:** `065.002-T` normalizes `ip` to its embedded IPv4 BEFORE the six-flag
  and CGNAT checks — **guarded for `IPv6Address` only** (`if isinstance(ip, ipaddress.IPv6Address)
  and ip.ipv4_mapped is not None: ip = ip.ipv4_mapped`; an unguarded `ip.ipv4_mapped or ip` would
  raise `AttributeError` on ordinary IPv4 input) — and membership is version-guarded
  (`ip.version == 4 and ip in _CGNAT_NETWORK`). `065.001-T` gains in-place mapped-literal rows
  (class-pin `::ffff:100.64.0.1`→reject; URL `http://[::ffff:100.64.0.1]/sitemap.xml`→`SitemapError`;
  boundary-accept `::ffff:100.63.255.255`→accept). Only `::ffff:0:0/96` maps; the deprecated
  IPv4-compatible `::/96` is not reinterpreted. Reconciled: CGNAT plan, `065-F`, `065.001-T`,
  `065.002-T`.
- **`MAX_FRAME_BYTES` concrete value (comment 3885888241 on `064.006-T`).** The constant was
  referenced in §H2 but never pinned, so the red harness could not fix the accepted boundary.
  **Resolution:** pinned `MAX_FRAME_BYTES = 1 MiB` (`1_048_576` payload bytes) as an explicit
  operational/compatibility bound (NOT a protocol maximum): docline MCP request frames are
  control-plane only (paths/URL/enums/flags; no inline document bytes; batch arrays unsupported →
  `-32600`), so 1 MiB accommodates any realistic request (incl. a large `initialize`/
  `clientCapabilities` `_meta`) while bounding per-frame memory. Boundary (mirrors the
  `MAX_RESPONSE_BYTES` crossing-byte pattern; cap counts payload bytes before `\n`): exact-N accept
  (a `1_048_576`-payload-byte frame + `\n` dispatched), N+1 reject → discard + bounded-memory drain
  to next `\n`/EOF + resync; bounded memory only (total drain time/bytes unbounded for a client that
  never sends `\n`). Revisit if a future tool accepts inline content or batch arrays. Reconciled:
  plan §H2 (Selected numeric limit + design cross-ref), `064-F` DoD H2, `064.006-T` (red exact-N/N+1
  + over-read guard), `064.002-T` (green).
- **Liveness red predecessor (comment 3885888257 on `064.002-T`).** The non-greedy-read +
  per-frame-flush liveness properties were only observable via the downstream `064.008-T` subprocess
  smoke (red merely because the entry point is absent), so they were never observed red before
  `064.002-T` implemented them. **Resolution:** `064.001-T` gains an IN-PLACE instrumented `serve()`
  interactive-liveness assertion (injected non-greedy `read1` stdin + flush-recording stdout that
  withholds the second frame until the first response is flushed; timeout-bounded, deadlock fails
  deterministically), RED here (serve() absent) and green@`064.002-T`; scenario count stays 3.
  `064.008-T` remains the live subprocess/packaging smoke. Reconciled: plan serve() design +
  §H2 liveness note, `064-F` DoD, `064.001-T`, `064.002-T`, `064.008-T`.
- **`064.024-T` scope = 3 functions (comment 3885888272 on `064.024-T`).** The count omitted the
  `crawl()` call-site changes: the request-scoped budget is local to `crawl()`, so threading it into
  the helpers necessarily edits `crawl()` plus `_robots_allow` and `_discover_toc_links`.
  **Resolution:** scope corrected to 3 functions; the call chain is made accurate — `_robots_allow`
  forwards to a DIRECT `fetch_page` call, while `_discover_toc_links` forwards to
  `_fetch_with_retries` (already budget-aware from `064.017-T`, NOT a direct `fetch_page` call); and
  `064.016-T`/`064.024-T` scenario (c)(iii) now requires SEPARATE robots AND TOC variants (not
  either/or). Still <5-function / ≤1-file. Reconciled: `064.024-T`, `064.016-T`, plan decomposition
  entry 10b.
- **Two-shipment PR disclosure (comment 3885888283 on `056-S`).** The PR description discloses only
  `055-S`, but the branch also stages the independently executable `056-S` (sitemap CGNAT SSRF).
  Stage cannot perform PR actions. **Resolution:** the recommended PR title/body amendment (naming
  BOTH `055-S` and `056-S`) is recorded in the cycle-16-round-2 Stage handoff memory, and this plan
  set truthfully names both shipments. One STAGING PR may carry both manifests (planning/backlog/
  memory only, no code); the shipments have no blocking dependency and MUST be claimed, implemented,
  reviewed, and shipped INDEPENDENTLY by Ship on separate shipment-scoped branches/PRs (Ship records
  one `shipment_id` per session) — this PR must never become the implementation PR for both.
- **Adversarial outcome (multi-persona):** approaches sound after one P0 correction folded in — the
  IPv4-mapped normalization MUST be guarded for `IPv6Address` (unguarded `ip.ipv4_mapped or ip`
  crashes on IPv4). Additional refinements folded: honest `MAX_FRAME_BYTES` rationale (operational
  limit, not protocol-derived, not a `MAX_RESPONSE_BYTES` hierarchy claim — different resource
  dimensions); explicit exact-N/N+1 boundary with delimiter-excluded payload counting; liveness
  fake pins `read1` + a synchronization/timeout contract so a greedy read cannot false-green and a
  deadlock cannot hang the suite; accurate `_discover_toc_links`→`_fetch_with_retries` chain and
  both-variant (c)(iii) coverage; bounded-MEMORY (not total-drain) framing. NOT pushed; no PR
  actions; Ship not invoked; production source unchanged.

## Rollback


**Not purely additive.** The release unit adds new modules (`src/docline/mcp/stdio.py`,
`src/docline/mcp/__main__.py`) and one `[project.scripts]` entry-point line, but it ALSO modifies
existing files whose behavior changes for both interfaces:

- `src/docline/mcp/server.py` — adapter `DoclineMcpServer` gains `call_tool` (static allow-list
  dispatch) and the new `list_callable_tools()` method (delivered by task 064.015-T), changing the
  adapter's callable surface. `list_tools()` is unchanged.
- `src/docline/mcp/server.py` + `src/docline/mcp/exceptions.py` + `src/docline/mcp/stdio.py` +
  `src/docline/mcp/__main__.py` — §H8 external-PDF-engine opt-in gate (cycle-3): the adapter gains the
  `_MCP_LOCAL_PDF_ENGINES` allow-list, an `external_pdf_engines_enabled` instance flag, a filtered
  advertise enum, and a dispatch chokepoint raising the new `ExternalEngineNotAllowedError`; the stdio
  transport maps it to `-32602`; `__main__.py` resolves the server-side opt-in (env `"1"` /
  `--allow-external-pdf-engine`) into a fresh server instance. MCP-surface-only — the shared
  `ProcessRequest` model, `readers/pdf.py`, `app.py`, and the CLI are UNCHANGED (tasks
  064.031–064.036). Additive to the MCP transport; reverting restores the prior (unsafe) default where
  an untrusted client could select `mistral_ocr`.
- `src/docline/fetch/url_policy.py` + `src/docline/fetch/http.py` — SSRF-by-resolution hardening
  (§H6): host resolution + address-pinned connect-time validation on the initial URL and every
  redirect. Affects **CLI `docline fetch` too**, not just MCP.
- `src/docline/app_models.py` + `src/docline/fetch/http.py` — per-dimension resource caps (§H7):
  `max_pages` upper bound and streamed `MAX_RESPONSE_BYTES` read (064.012/064.013). Also affects
  CLI fetch.
- `src/docline/fetch/http.py` + `src/docline/fetch/crawl.py` — byte-accurate aggregate accounting
  (§H7 item 3, cycle-3): `FetchResponse` gains a `body_byte_count` field carrying the undecoded
  entity-body byte count, and the crawl enforces `MAX_TOTAL_FETCH_BYTES` via a request-scoped remaining-byte budget
  threaded into `fetch_page`/the bounded reader and decremented per chunk while bytes are read
  (main pages, retries via 064.016/064.017; ancillary robots/TOC via split successor 064.024),
  aborting mid-read. Additive field +
  threaded budget; also affects CLI crawls.
- `src/docline/fetch/http.py` + `src/docline/app_models.py` — request-amplification bound (§H7
  item 4, cycle-8; mechanism reworked cycle-11; redirect-hop placement decomposed cycle-12):
  `fetch_page` seeds a per-request fetch-attempt
  allowance on the shared request-scoped budget and debits it on every direct outbound request (main
  pages, robots, TOC, retries; 064.025/064.026) AND on every FOLLOWED redirect hop in
  `_ValidatingRedirectHandler.redirect_request` after validation (064.029/064.030) — RAISING
  `FetchAttemptBudgetExceededError` (a `DoclineError` subclass of `AggregateBudgetExceededError`)
  once attempts would exceed `MAX_FETCH_ATTEMPTS = 4000`, and `FetchRequest.depth`
    gains a hard `Field(default=0, ge=0, le=64)` upper bound (`MAX_DEPTH_LIMIT`; default preserved),
    rejecting over-limit depth `-32602`
    (064.025/064.026). Tightens accepted request COUNT on the shared path; also affects CLI crawls.
- `src/docline/fetch/http.py` — intermediate-redirect-body drain + closure (§H7 item 2, cycle-10 +
  cycle-12): the
  existing single `_ValidatingRedirectHandler` is extended (with all redirect-code aliases rebound)
  so its bounded proxy reads/counts each intermediate 3xx redirect body against the per-response
  `MAX_RESPONSE_BYTES` cap and the request-scoped aggregate budget, replacing urllib's in-handler
  unbounded `fp.read()`, AND closes the intermediate `fp` on both cap-breach paths
  (064.027/064.028). ONE composite handler; reuses existing caps (no new
  constant); closes the redirect bypass of both byte budgets and the intermediate-connection leak.
  Also affects CLI fetch (a hostile
  redirect chain that previously drained now aborts).
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
(064.010–064.013, 064.016–064.017, 064.024, 064.025–064.026, 064.027–064.028, 064.029–064.030) and the `fetch`-advertising correction (064.019) are
self-contained and revertible on their own. Within the shared-fetch cluster, reverts must proceed in
reverse-dependency (reverse-topological) order — e.g. `064.030-T` (redirect-hop attempt debit) reverts
independently, but `064.028-T` (which threads the budget into the handler and provides the closure
guard) and `064.026-T` (which seeds the `MAX_FETCH_ATTEMPTS` allowance) must NOT be reverted while
`064.030-T` remains; treat the redirect cluster (`064.027`–`064.030`) as an atomic rollback unit when
in doubt.

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
  budget (also decrementing intermediate 3xx redirect bodies), a request-amplification bound
  (`MAX_FETCH_ATTEMPTS` = 4000 outbound-fetch-attempt budget at the `fetch_page` boundary +
  `MAX_DEPTH_LIMIT` = 64 depth upper bound, §H7 item 4), and an extension of the existing
  `_ValidatingRedirectHandler` (all redirect-code aliases rebound) that bounded-reads/counts every
  intermediate 3xx redirect body against the same per-response and aggregate allowances AND closes the
  intermediate `fp` on cap breach (§H7 item 2 + cycle-12 closure,
  closing urllib's in-handler unbounded `fp.read()` bypass and its connection leak), plus a redirect-hop
  fetch-attempt debit placed in `redirect_request` after validation (§H7 item 4a, cycle-12). This tightens accepted inputs on an existing runtime path shared by CLI `docline fetch`
  and the MCP `fetch` tool.
- **targets:** `src/docline/fetch/url_policy.py`, `src/docline/fetch/http.py`,
  `src/docline/fetch/crawl.py`, `src/docline/app_models.py`. Delivered by tasks 064.010–064.013,
  064.016–064.017, 064.024, 064.025–064.026, 064.027–064.028, 064.029–064.030.
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
  H1–H8. §H8 (cycle-3) adds an external-PDF-engine opt-in gate: credential/network-bearing engines
  (`mistral_ocr`) are omitted from the advertised `process` schema AND rejected `-32602` at dispatch
  by default (both eras), available only via a server-side startup opt-in — closing an
  ambient-credential-consumption + external-paid-egress path an untrusted client could otherwise
  trigger with a request field.
- **targets:** new `src/docline/mcp/stdio.py`, `src/docline/mcp/__main__.py`, `[project.scripts]` in
  `pyproject.toml`; modified `src/docline/mcp/server.py` + `src/docline/mcp/exceptions.py`. Delivered
  by tasks 064.001–064.009, 064.015, 064.018–064.023, 064.031–064.036, 064.002–064.004, 064.008.
- **change_kind:** new external contract + adapter callable-surface change (interface/config change);
  introduces an untrusted-input boundary.
- **rollback / containment:** the MCP-only additions (stdio loop, dual-era surface, adapter callable
  surface, entry point) revert independently of the shared-fetch hardening (see `## Rollback`).
  The boundary is contained by fail-closed guardrails: H1 `workspace_root` reject (`-32602`), H3
  error non-disclosure, H4 closed allow-list, H5 stdout hygiene, and H8 external-engine reject
  (`-32602`, default-deny allow-list), applied through ONE hardened dispatch across both protocol
  eras. Revert = drop the feature branch.
- **§H8 residual (accepted, documented):** once the operator opts in, the still-untrusted client can
  drive paid Mistral OCR calls + workspace-PDF upload bounded only by the reader's 120 s per-request
  timeout; enabling the flag is an explicit operator delegation of paid egress to the connected
  client (enable only for trusted local clients). A per-surface cost/egress budget is a potential
  follow-up, out of scope for closing this default-enabled finding.
- **approval_required:** covered by the standing dark-factory authorization for autonomous
  implementation + PR merge; NOT destructive, so no separate destructive-action approval is required.
- **ActionRisk:** `high` — new untrusted attack surface / exposed contract.
- **ActionResult:** `approved` (pre-authorized by the standing dark-factory instruction; execution
  owned by Ship — `planned` for the current Stage artifact, transitions to `applied` when Ship builds
  and merges).

## Risks

- Medium: shared-fetch hardening (§H6/§H7) changes existing CLI `docline fetch` behavior — a
  hostname that resolves to a private address, a crawl exceeding the new `max_pages`/response-byte
  /aggregate caps, or a redirect chain whose intermediate 3xx bodies exceed those caps, now fails
  where it previously succeeded. Mitigated by sizing caps above legitimate
  use and keeping the existing `tests/fetch` suite green (or deliberately updating it for the new bound).
- Medium: dual-era protocol surface adds real complexity (era classification, per-request `_meta`
  negotiation, two result shapes). Mitigated by sourcing identity/versions from a single
  `describe_server()` accessor (no drift), keeping the legacy path unchanged, and gating both eras
  with explicit negotiation/version tests (064.020–064.023). Modern-era features beyond
  discovery + negotiation + tools are explicitly out of scope to bound the surface.
- Medium: §H8 external-engine gate is MCP-surface-only — it intentionally does NOT change the shared
  `ProcessRequest` model or the CLI, so CLI `docline process --pdf-engine mistral_ocr` still works.
  Mitigated by an allow-list (fail-closed for future external engines), a build-time advertise
  omission AND a runtime dispatch reject at a single adapter chokepoint that no transport path
  bypasses, dual-era parity through one hardened dispatch, and a fail-closed instance-local startup
  opt-in that a client cannot spoof. Residual (accepted): once opted in, the still-untrusted client
  can drive paid Mistral OCR calls + workspace-PDF upload bounded only by the reader's 120 s
  per-request timeout (no page/byte/call budget) — operators enable only for trusted clients; a
  per-surface cost/egress budget is a potential follow-up, out of scope for closing this
  default-enabled finding.
- Low: correcting the shared `fetch` description also changes the CLI `--manifest` output text; this
  is intentional (the CLI advertising was equally wrong) and is a text-only change with a parity
  test — no behavior change.
- Low: adding `FetchResponse.body_byte_count` touches a widely-referenced shared dataclass; the
  field is additive with a value derived from bytes the bounded reader already materializes, so
  existing `response.body` consumers are unaffected.
- Low (residual, cycle-16 round-1): the `MAX_RESPONSE_BYTES`/`MAX_TOTAL_FETCH_BYTES` byte budgets
  count **entity-body bytes** — the undecoded response-content bytes returned by `HTTPResponse.read()`
  after `urllib`/`http.client` removes transfer framing (chunk-size lines, trailers) and headers, and
  before docline's charset decoding (a `gzip` body stays content-encoded). They therefore bound the
  memory the reader buffers and the content staged under `output_dir` (the DoS surface that matters),
  but they do **not** bound response headers, transfer framing, raw socket bandwidth, or HTTP-parser
  CPU, and they are not an exact post-charset-decode memory/disk ceiling (`errors="replace"` and
  Python `str` overhead expand staged text above the counted byte total). Header/framing overhead is
  bounded only by a constant factor of the per-response cap plus `http.client`'s own line/header limits
  (`_MAXLINE` 64 KiB × `_MAXHEADERS` 100) × `MAX_FETCH_ATTEMPTS`, i.e. finite bandwidth with no
  retained memory/disk footprint. Accepted as out of scope: docline cannot count raw wire bytes
  without a bespoke transport, and the memory/disk blast radius is what the budget must (and does)
  bound. The non-ASCII multibyte / invalid-byte tests prove only that enforcement happens below
  charset decoding (resisting a decode/re-encode undercount), not any wire-framing bound.
- Low: address-pinned connect (§H6) connects to a validated IP while preserving the `Host` header /
  SNI; verify TLS certificate validation still targets the hostname (not the IP) so pinning does not
  weaken cert checks. Covered by the SSRF harness (064.010-T).
- Medium (tracked follow-up — production code out of scope for this planning reconciliation): the
  shared classifier `_is_unsafe_address` (`src/docline/fetch/sitemap.py:173-189`) does **not** reject
  CGNAT `100.64.0.0/10` — on every Python 3.12.x that range reports `is_private` / `is_reserved` /
  `is_global` all `False`, so the six-flag reject-list lets it through. §H6 closes this on the
  MCP/CLI fetch path via an explicit `100.64.0.0/10` membership check, but
  `sitemap.validate_sitemap_url` still carries the gap. This is now tracked as a REAL queued
  high-priority backlog item — feature `065-F` (tasks `065.001-T` red → `065.002-T` green) in
  shipment `056-S`, OUTSIDE `055-S` — which extends `_is_unsafe_address` with the same explicit
  CGNAT check (`docs/plans/2026-08-28-sitemap-cgnat-ssrf-gap-plan.md`; deliberation
  `docs/decisions/2026-08-28-sitemap-cgnat-ssrf-gap-deliberation.md`). Because
  `validate_sitemap_url` has NO live callers (dormant defense-in-depth) and §H6 uses an
  INDEPENDENT complete public-unicast classifier (re-implemented in `url_policy`, not delegated to
  `_is_unsafe_address`), this gap does NOT block `055-S` MCP safety (see Cycle-16). Relatedly, `ipaddress` special-purpose
  tables are Python-patch-dependent (CVE-2024-4032 hardened `is_private` in 3.12.4) while
  `pyproject.toml` pins `requires-python>=3.12`; the §H6 harness (`064.010-T`) therefore test-pins
  each security-critical class instead of trusting the installed flag table, and raising the floor
  to `>=3.12.4` should be evaluated as a follow-up (manifest not changed here).
- Low: extending the existing `_ValidatingRedirectHandler` to bounded-drain intermediate 3xx bodies
  (§H7 item 2, 064.028-T) overrides stdlib redirect body draining; mitigated by wrapping the
  intermediate `fp` in a bounded proxy and delegating to `super().http_error_302(...)` so the
  existing `redirect_request` (§H6 revalidation + `max_redirects` count) and the stdlib
  Location/loop/scheme logic are preserved, by rebinding all `http_error_301/302/303/307/308` aliases
  to the bounded override, and by a redirect-still-follows scenario (064.027-T) proving legitimate
  redirects are not broken. Resource-ownership (cycle-12, Finding A): because the bounded proxy raises
  a cap error MID-READ inside stdlib `http_error_302`, stdlib's own `fp.close()` (which runs only after
  a completed read) is skipped and the intermediate response `fp` would leak; mitigated by a closure
  guard in the override that closes the real `fp` on both cap-breach paths AND on the two
  `redirect_request`-raised custom exits (redirect-cap `FetchError` + §H6 `CrawlUrlRejectedError`,
  which unlike stdlib `HTTPError` do not carry the `fp`) before re-raising
  (064.028-T; asserted by 064.027-T's fp-closure assertions). Residual (out of scope, cycle-10):
  the stdlib loop-detection/disallowed-scheme paths raise `HTTPError` holding an unread `fp`; those
  are bounded by `max_redirects` (default 5) and terminate the fetch, so they are not a new
  amplification vector — noted for monitoring, not a blocker.
- Low: redirect-hop fetch-attempt accounting (§H7 item 4a, cycle-12 Finding B) must debit only for
  FOLLOWED hops; mitigated by placing the debit in `redirect_request` immediately before returning a
  non-None `Request` (after the stdlib scheme check and §H6 revalidation, before outbound I/O),
  so a redirect rejected by the scheme check or by §H6/stdlib `redirect_request` consumes no attempt —
  proven by the no-debit-on-reject and placement/ordering assertions in 064.029-T (impl 064.030-T).
  `handler.redirect_count` stays observability-only, never post-hoc enforcement. Bounded residual
  (verified against the CPython source, not a blocker): the stdlib loop-detection check fires AFTER
  `redirect_request` returns, so a loop-terminated hop over-counts by exactly one attempt before the
  fetch ends via `HTTPError` — harmless (bounded by `max_redirects`, fetch terminating) and
  unavoidable without reimplementing the stdlib method body; same residual class as the unread-`fp`
  loop-detection note above.
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
  acyclic, test-first sequence of 23 tasks within the 2-hour/width-isolation limits at that Cycle-4
  checkpoint (later cycles grew the chain to the current **36 tasks** — see the post-decomposition
  cycle-2 reconciliation gate below). Runtime
  verification and rollback/blast-radius are covered in `## Verification` and `## Rollback`. Ready
  for the harvested backlog to proceed to Ship.

### Post-decomposition cycle-2 reconciliation gate (current — supersedes the Cycle-4 count above)

- **Trigger:** PR #166 H8 post-decomposition review cycle 2 — reconcile three unresolved review
  threads: (1) stale task-count/next-steps in the darkfactory Stage memory, (2) the
  `docs/ARCHITECTURE.md` domain/dependency-map gap on the docs task `064.004-T`, and (3) a stale
  "current" 30-task order in `.backlogit/memories.json`. Planning/backlog/docs artifacts only — no
  production source, no push, no PR actions.
- **Current chain (authoritative):** a single strictly-linear acyclic test-first sequence of
  **36 tasks**; shipment `055-S` = `064-F` + **36 tasks** (**37 members**). Execution order:
  `064.001 → 005 → 006 → 007 → 010 → 011 → 012 → 013 → 016 → 017 → 024 → 025 → 026 → 027 → 028 →
  029 → 030 → 014 → 015 → 018 → 019 → 002 → 009 → 020 → 021 → 022 → 023 → 031 → 032 → 033 → 034 →
  008 → 003 → 035 → 036 → 004`. `064.004-T` remains terminal (depends on `064.036-T`).
- **Change in this cycle:** the docs task `064.004-T` was augmented IN PLACE (no new task, no
  dependency edge or shipment-membership change) to ALSO own a top-level `docs/ARCHITECTURE.md`
  domain/dependency map (Scope item 4, Task T4, and Verification updated to match). Still
  docs-domain, two files (README.md + `docs/ARCHITECTURE.md`), within the <3-file / 2-hour width
  envelope. The dependency graph and shipment membership/order are unchanged.
- **Gate decision: PASS.** The multi-persona adversarial review (traceability, architecture
  progressive disclosure, task width, exact dependency/order consistency, stale-current-language)
  closed all P1 findings in place; no P0/P1 remains. Ready for the backlog to proceed to Ship.
