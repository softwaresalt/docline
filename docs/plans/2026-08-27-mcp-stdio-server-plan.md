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
  `call_tool` dispatches, so nothing is advertised that cannot be invoked. The shared manifest
  advertises four tools (`fetch`, `process`, `export_schema`, `ingest_local_dir`); the callable
  MCP surface currently implements three. **Default-safe resolution: exclude `ingest_local_dir`
  from the MCP `tools/list`** on the untrusted stdio surface. Its `source_path` is a hand-authored
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
  - Method map: `initialize` → capabilities + pinned `protocolVersion` + serverInfo;
    `tools/list` → filtered manifest (callable allow-list); `tools/call` → `server.call_tool`;
    `ping` → `{}` (optional utility, not required for discovery/use).
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
    the core task (T2); the runtime reject of a client-supplied `workspace_root` is delivered by
    the security task (T2s). The T1 parity assertion normalizes these out — comparing `tools/list`
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
- **H6 — fetch SSRF re-verification.** Re-confirm the crawler's SSRF guard is active on the new
  untrusted path. Negative test drives rejection **through the `tools/call` fetch boundary**
  (stdin JSON → dispatch → `server.fetch` → `execute_fetch`), not the crawler in isolation:
  `http://127.0.0.1` and `http://169.254.169.254` are rejected end-to-end.

## Tasks (decomposition)

Ordered, dependency-aware, one skill domain each (width isolation), each ≤ ~2h and each test
harness task under the repository's <4-test-scenario granularity heuristic. The original single
T1 harness (handshake + discovery/parity + dispatch + four error classes + notifications + H1–H6)
carried well over four scenarios; it is split into four dependency-linked red harness tasks. The
single make-green implementation was likewise too concentrated (all four harnesses + H1–H6 in one
code task, breaching the <5-function / <3-file rule), so it is split into a core dispatch task (T2)
and an H1–H6 security-hardening task (T2s). The subprocess smoke test is pulled out of the packaging
task into its own predecessor harness task so packaging stays width-isolated to the executable
surface.

Backlog IDs are shown in brackets. All harness tasks author into `tests/parity/test_mcp_stdio.py`
(the subprocess smoke test lives alongside, matching the existing `test_manifest_parity.py` pattern)
and are verified **red** before their green implementation.

1. T1 [064.001-T] — Protocol handshake + discovery/parity harness (tests domain, 3 scenarios).
   `initialize` handshake shape; `tools/list` == callable allow-list with semantic (name +
   normalized-schema) parity vs the callable-filtered `get_manifest().tools` (normalizing the
   `parameters`↔`inputSchema` alias, the §H1 `workspace_root` omission, AND the `ingest_local_dir`
   exclusion — not byte-for-byte); every advertised MCP tool is dispatchable. Verify red. No
   dependency (first).
2. T1b [064.005-T] — Dispatch parity + error-envelope + notification harness (tests domain,
   3 scenarios). `tools/call` fetch + process parity vs `execute_fetch`/`execute_process` with
   `success=False` → `isError` result; error envelopes (`-32601`, `-32602`, `-32700`, `-32603`);
   id-less notification is silent. Verify red. Depends on T1.
3. T1c [064.006-T] — Security gates H1–H3 harness (tests domain, 3 scenarios). H1 workspace_root
   escape (`/` and `C:\\`) rejected with `-32602`, nothing written outside workspace; H2 bounded
   input — oversized line, deeply nested array, AND an unterminated/chunked oversized frame
   rejected with bounded memory + loop resync; H3 no absolute paths in envelope OR `isError`
   content. Verify red. Depends on T1b.
4. T1d [064.007-T] — Security gates H4–H6 harness (tests domain, 3 scenarios). H4 unknown/unrouted
   tool (incl. `ingest_local_dir` if excluded, and dunders) fails closed with `-32602`; H5 stdout
   carries only well-formed JSON-RPC frames across a fetch/process call; H6 `tools/call` fetch to
   `127.0.0.1` and `169.254.169.254` rejected end-to-end. Verify red. Depends on T1c.
5. T2 [064.002-T] — Core stdio dispatch loop + adapter `call_tool` allow-list (code domain).
   Implement `DoclineMcpServer.call_tool` (static allow-list), derive the MCP `tools/list` and
   per-tool `inputSchema` from that allow-list at build time (so `ingest_local_dir` is excluded
   and the `process` `inputSchema` omits `workspace_root`), and `docline/mcp/stdio.py`
   (`dispatch` + `serve`, including the bounded binary frame read/drain helper per §H2) to make
   T1/T1b **fully** green — core protocol/dispatch/discovery/error/notification behavior. Depends
   on T1d (the full red harness is authored first). The runtime security guardrails H1–H6
   (including the dispatcher-level `workspace_root` reject) are delivered by T2s.
6. T2s [064.009-T] — H1–H6 stdio security hardening (code domain). Implement the `workspace_root`
   dispatcher-level runtime reject (`-32602`) per §H1 (the build-time `inputSchema` omission is
   already delivered by T2; `extra="forbid"` does not catch a real model field, so an explicit
   pre-construction reject is required), enforce the bounded read/drain
   + `RecursionError`/`ValueError` handling (§H2), generic non-reflective error text on envelope and
   `isError` (§H3), fail-closed unknown tools (§H4), child-stdout redirect (§H5), and SSRF
   re-verification (§H6) to make T1c/T1d pass. Split from T2 so neither implementation task breaches
   the 2-hour/<5-function rule. Depends on T2.
7. T2b [064.008-T] — Subprocess smoke-test harness for the entry point (tests domain, 1 scenario).
   Author the failing automated subprocess test (matching `test_manifest_parity.py::`
   `test_python_m_docline_cli_runs_main`) that spawns `python -m docline.mcp` / `docline-mcp`,
   pipes `initialize`+`tools/list` then EOF, and asserts clean exit + tool names matching the
   advertised MCP tool set (`docline --manifest` minus the excluded `ingest_local_dir`). Red until
   the entry point exists. Depends on T2s (the fully hardened server ships in the executable).
8. T3 [064.003-T] — `docline-mcp` entry point + module bootstrap (packaging surface only —
   width-isolated). Add `docline/mcp/__main__.py` (`main()` reusing `DoclineMcpServer` + `serve`)
   and the `[project.scripts]` `docline-mcp` entry (materializes `docline-mcp.exe` on Windows),
   turning the T2b subprocess harness green. No test-infra authoring in this task. Depends on T2b.
9. T4 [064.004-T] — Documentation (docs domain). README "Running the local stdio MCP server"
   section and a `.mcp.json` client example for `docline-mcp`. Do NOT add a separate design-doc
   transport note — the deliberation already documents the transport surface (avoid duplication).
   Depends on T3.

Dependency edges: T1b→T1, T1c→T1b, T1d→T1c, T2→T1d, T2s→T2, T2b→T2s, T3→T2b, T4→T3.
Execution order: 064.001 → 064.005 → 064.006 → 064.007 → 064.002 → 064.009 → 064.008 → 064.003 → 064.004.

## Verification

- `pytest tests/parity` green (new stdio suite incl. H1–H6 gates + existing adapter/transport
  suites unchanged).
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
  error codes aligned to the tested set (dropped untested `-32600`); T4 design-doc note removed
  (folded into deliberation); manual smoke automated.
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
  (064.009), preserving one skill domain and bounded scope per task.
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

## Rollback

Purely additive (new modules + one entry-point line + docs). Rollback = revert the feature
branch; no data migration, no schema change, no change to existing runtime paths.

## Risks

- Low: stdout contamination would corrupt the JSON-RPC stream — mitigated by routing all logs
  to stderr and asserting clean stdout framing in tests.
- Low: manifest drift between CLI and MCP — mitigated by the T1 parity assertion against the
  single shared manifest source.
