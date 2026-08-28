# Stage session memory — dark-factory stash sweep (2026-08-27)

- Agent: Stage (dark-factory / AFK autonomous mode)
- Scope: full Stage pipeline (Steps 0.0–6) over all 8 active backlogit stash entries.
- Starting state: no active/queued shipments; queue empty; 8 active stash entries.

## Triage outcome

| Stash | Kind | Priority | Disposition | Durable artifact |
|---|---|---|---|---|
| 14E46B47 | feature | medium | EXECUTABLE → full pipeline + shipment | 064-F (shipment 055-S) |
| B26003B0 | task | low | BLOCKED (Foundry creds + paid calls + forms corpus) | 060.001-T under 060-F |
| E32FAF6F | task | medium | BLOCKED (Foundry creds + paid calls + cosmos) | 060.002-T under 060-F |
| F4167E69 | spike | medium | BLOCKED (Foundry creds + paid calls) | 061.001-T under 061-F |
| 4CB606D5 | task | low | BLOCKED (missing corpora) | 062.001-T under 062-F |
| A3E6D72C | task | medium | BLOCKED (missing scanned/high-mpx corpus) | 062.002-T under 062-F |
| 3048007A | task | low | DEFERRED (no GPU host) | 063.001-T under 063-F |
| 935F2694 | task | low | DEFERRED (YAGNI, no measured I/O hot path) | 063.002-T under 063-F |

All 8 stash entries archived (reason: harvested) after successful harvest to durable backlog.
This matches the actual `reason` value recorded in `.backlogit/archive/stash.jsonl` for every
consumed entry (they were archived by the harvest path, not a bare archive), so future
traceability checks resolve against the real `harvested` reason.

## Executable work — MCP stdio server (064-F, shipment 055-S)

- Deliberation: `docs/decisions/2026-08-27-mcp-stdio-server-deliberation.md` (chose Option A —
  dependency-free stdio JSON-RPC loop wrapping the existing `DoclineMcpServer`; rejected the
  `mcp` SDK / FastAPI to avoid a runtime dependency).
- Plan: `docs/plans/2026-08-27-mcp-stdio-server-plan.md`.
- Key repo finding: the MCP *adapter* (`DoclineMcpServer.list_tools/fetch/process/export_schema`),
  shared manifest, transport guard, and parity tests already exist. The gap is the runnable
  JSON-RPC stdio loop + `docline-mcp` console entry point. This release unit is NOT purely
  additive: it also changes the existing adapter's callable surface (adds `call_tool` +
  `list_callable_tools()`; `list_tools()` unchanged) and hardens the SHARED fetch code
  (`fetch/url_policy.py`, `fetch/http.py`, `app_models.py`), which affects the CLI too.
- Adversarial multi-persona plan review: Architecture ADVISORY, Scope ADVISORY,
  **Security FAIL → PASS after hardening**.
  - Security P0 (real): `ProcessRequest.workspace_root` is unvalidated; exposing `process`
    over untrusted stdio lets a client set `workspace_root:"/"` and escape workspace isolation
    (Principle III). Closed via plan §H1 with a SINGLE behavior: the MCP boundary **rejects** a
    client-supplied `workspace_root` (`-32602`, not pin/strip/ignore), **omits** it from the
    advertised `process` `inputSchema`, and **pins** the root to the server-configured workspace
    (process cwd). Blocking test. Re-review returned Security PASS.
  - Arch/Scope P1/P2: shared manifest advertises 4 tools (incl. `ingest_local_dir`) but adapter
    routes 3 → advertise-but-uncallable gap. Closed via manifest-driven `call_tool` allow-list +
    new `list_callable_tools()`; advertised (callable) set == dispatchable set; `list_tools()`
    stays full-manifest so the existing parity test is unchanged; parity test asserts every
    advertised MCP tool is dispatchable.
  - Additional hardening H2–H7: stdin DoS bounds (+RecursionError), error-text non-disclosure
    (envelope + isError), closed allow-list fail-closed, stdout hygiene, **restored `-32600`
    Invalid Request (non-object root / bad-or-missing `jsonrpc` / missing-or-non-string
    `method`)**, **SSRF by DNS resolution — resolve + address-pinned connect-time validate the
    initial URL and every redirect, reject any hostname resolving to loopback/private (H6)**, and
    **fetch resource caps — hard `max_pages` upper bound + streamed `MAX_RESPONSE_BYTES` cap incl.
    redirects + aggregate `MAX_TOTAL_FETCH_BYTES` crawl budget (H7)**.
  - Cycle-2b multi-persona re-review (Consistency/Security/Architecture/Scope) closed 1 P1 + P2s:
    064-F DoD → H1-H7; address-pinned connect (DNS-rebinding) in-scope; aggregate crawl-byte budget
    added; adapter surface extracted to 064.015-T with the `list_tools()`-parity-only /
    `list_callable_tools()`-sole-advertise invariant; 064.009 narrowed to H1/H3/H4/H5 (shared-fetch
    guards auto-enforce via `execute_fetch`, no boundary wiring); explicit red-only harness milestone
    model; Rollback names `src/docline/mcp/server.py`.
  - **Cycle-3 review (PR #166, 4 threads) — closed here.** (1) Aggregate byte accounting made
    enforceable: `FetchResponse` must retain the raw body byte count (`body_byte_count`) from the
    bounded reader before decode, and the crawl sums that exact value (non-ASCII/invalid-byte
    tested); split into a byte-accurate pair 064.016-T/064.017-T (per-dimension caps 064.012/064.013
    narrowed accordingly). (2) MCP `2026-07-28` protocol claim **verified against the official spec**
    (`modelcontextprotocol/modelcontextprotocol` `docs/specification/2026-07-28`): `server/discover`
    MUST, per-request `_meta` protocolVersion (no `initialize` handshake), `-32022`, `ping` removed —
    all confirmed → planned a **dual-era server** (retain legacy `initialize`; add modern
    discovery/negotiation/-32022/resultType + era routing) as tasks 064.020-064.023 (2 harness +
    2 impl, explicit negotiation/version tests). (3) Memory reason corrected `archived`→`harvested`.
    (4) `fetch` advertising corrected to HTTP(S)-only (shared description matches `execute_fetch`),
    parity-tested; tasks 064.018-T/064.019-T. Plan + deliberation + 064-F DoD updated to match.
    Cycle-3 edits were then put through an internal 4-persona adversarial re-review
    (Architecture/Security/Scope/Consistency): closed Security P1 (dual-era guardrail parity — modern
    stateless/pre-handshake path must enforce H1/H3/H5 identically; parity scenario in 064.021,
    criterion in 064.023), Architecture P2 (crisp 064.022=modern-branch / 064.023=legacy-branch
    ownership) + P2 (describe_server() moved into adapter task 064.015 so identity single-source
    holds at every commit), Consistency P2 (064.013 title retitled off "aggregate"), and P3s
    (aux robots/TOC bytes accrue to the aggregate; 064.021 scenario-a reframed as regression anchor).
  - **Cycle-4 review (PR #166, 12 threads) — closed here.** Planning/backlog/memory only (no
    production/test code). (1) Plan scope narrowed: the §H6/§H7 shared-fetch hardening explicitly
    DOES change `execute_fetch` for both interfaces and is in scope; only `execute_process` and
    non-hardening fetch changes are excluded. (2) Frame reader gains a **carry-over buffer**
    (preserve post-newline bytes in normal + oversized-drain paths) + two-frames-in-one-chunk test
    (§H2, 064.006/064.002). (3+12) Aggregate byte budget is enforced by a **request-scoped
    remaining-byte budget threaded into `fetch_page`/the bounded reader, decremented while chunks
    are read** (aborting mid-read), counting retried failures + ancillary robots/TOC fetches — NOT
    a post-return accumulator (§H7 item 3, 064.016/064.017; 064.013 delegation note). (4) SSRF pin
    also **disables inherited proxies** (empty ProxyHandler) so `HTTP(S)_PROXY` cannot re-resolve
    (§H6 item 3, 064.010/064.011). (5) H4 maps the **adapter's typed unknown-tool error** to
    -32602; no allow-list duplicated in `stdio.py` (§H4, 064.009). (6) Memory feature ID
    `64-F`→`064-F`. (7) 064.018 locates the fetch tool **by name** (`.tools` is a list, not a dict).
    (8) `DiscoverResult` carries required **`ttlMs`/`cacheScope`** (CacheableResult; 064.020/064.022).
    (9) Modern `_meta` validates **both `protocolVersion` AND `clientCapabilities`** (064.020/064.022).
    (10) `server/discover` is NOT a description surface — fetch-desc correction limited to CLI
    `--manifest` + `tools/list` (064.019). (11) 064.021 scenario-a is a legacy-only green anchor;
    the initialize-vs-discover no-drift equality stays RED until discovery (064.022) exists. Plan +
    memory reconciled; the 23-task chain and edges are unchanged.
  - **Cycle-4 internal 4-persona plan-review (Security/Architecture/Scope/Correctness) — closed here.**
    Architecture returned a blocking P1: an aggregate-budget AggregateBudgetExceededError (DoclineError
    subclass) would be swallowed by crawl.py's FOUR broad `except (DoclineError, OSError)` handlers
    (crawl main loop, _fetch_with_retries, _robots_allow, _discover_toc_links). Closed by requiring
    `except AggregateBudgetExceededError: raise` at all four sites (mirroring the existing
    CrawlUrlRejectedError re-raise) so crawl() RAISES (064.016/064.017, plan §H7). Also folded in:
    modern guard-funnel intrinsic at 064.022 (064.023 verifies), clientCapabilities rejection pinned to
    -32602 (version-first precedence), named UnknownToolError caught before -32603, body_byte_count
    default on the frozen dataclass, get_manifest (not get_mcp_manifest) as the description edit target,
    function/split guards on 064.017/064.022, scenario-budget attestations on 064.020/064.021, SSRF
    address normalization (IPv4-mapped/ULA/CGNAT/0.0.0.0) + empty-ProxyHandler system-proxy suppression,
    and a per-request disk-exhaustion residual in Risks. Gate: PASS after in-place remediation.
- **Cycle-5 review (PR #166, HEAD b90fa77, 7 threads) — closed here.** Planning/backlog/memory only
  (no production/test code; operator's uncommitted config/agent/.gitignore edits preserved and NOT
  staged). Thread→fix: (1) era classifier — legacy era is now **latched per-process by `initialize`**;
  metadata-free operations before that latch are **rejected**, never served as legacy; the modern
  `_meta` branch stays **request-stateless**; added a **pre-initialize operation test** (plan Protocol
  Era Model + Verification; 064.021-T scenario b, greened by the legacy branch in 064.023-T; feature
  DoD). (2) feature 064-F H7 DoD — replaced the insecure post-return `body_byte_count` accumulator with
  the **request-scoped during-read remaining-byte budget** (decremented per chunk, counts retries +
  ancillary robots/TOC, aborts mid-read); `body_byte_count` retained ONLY as per-response observability
  (matches 064.016/064.017 + §H7). (3) 064.015-T — allow-list values are **uniform (arguments: dict)
  adapter callables** (fetch/process build a request object; `export_schema` accepts only `{}`); the
  dispatchability test **invokes all three tools** (plan Design + H4 + Task 12). (4/5/7) `get_manifest()`
  is the description **edit target** (re-exposed by `get_mcp_manifest()`) at the Design fetch-advertising
  note, Task 14, and the Rollback inventory. (6) `.backlogit/memories.json`
  `stage-2026-08-27-darkfactory-stash-sweep` regenerated to the during-read budget + `get_manifest()`
  target so a future session cannot restore the rejected approach. Internal 4-persona adversarial
  re-review (Security/Correctness/Consistency/Scope) surfaced two P1s — remnant plan passages (Scope,
  §H7 cap-tasks, Tasks narrative, Verification) still prescribing the accumulator, and the feature DoD
  claiming `server/discover` advertises the fetch description — both **remediated in-place** and
  re-verified clean. Added plan `### Cycle-5 review remediation` subsection. Gate: PASS.
- Tasks (test-first, width-isolated, single linear/acyclic chain of **23**; execution order):
  064.001-T (protocol/parity harness) → 064.005-T (dispatch/error incl. -32600 harness) →
  064.006-T (H1-H3 harness) → 064.007-T (H4-H6 literal harness) → 064.010-T (shared-fetch SSRF
  harness) → 064.011-T (shared-fetch SSRF + address-pinned connect impl) → 064.012-T (per-dimension
  cap harness) → 064.013-T (per-dimension cap impl: max_pages + response byte) → 064.016-T
  (aggregate byte-accounting harness) → 064.017-T (raw-byte retention + byte-accurate aggregate
  impl) → 064.014-T (MCP untrusted-fetch end-to-end boundary harness) → 064.015-T (adapter
  call_tool + list_callable_tools) → 064.018-T (fetch HTTP(S)-only advertising parity harness) →
  064.019-T (fetch description correction impl) → 064.002-T (core stdio transport loop, legacy-era
  base: dispatch/serve/-32600/H2) → 064.009-T (stdio runtime guardrails H1/H3/H4/H5) → 064.020-T
  (dual-era discovery/modern-negotiation harness) → 064.021-T (legacy + era-routing harness) →
  064.022-T (modern negotiation impl: server/discover + _meta + -32022) → 064.023-T (dual-era
  routing + legacy retention impl) → 064.008-T (subprocess smoke harness) → 064.003-T (docline-mcp
  entry point) → 064.004-T (README/.mcp.json docs).
- Shipment 055-S = 064-F + **23 tasks** (queued, priority high). Handoff token to Ship.

## Blocked/deferred backlog (durable, NOT shipped)

Covering features 060-F, 061-F, 062-F, 063-F (status blocked). Each child task carries explicit
EVIDENCE / UNBLOCK requirements and `Do NOT fabricate` guardrails. Semantic links: 061.001-T
`informs` 060.001-T and 060.002-T (a Mistral v4 win could change forms + hybrid tasks).

## Commits / working-tree notes

- Committed ONLY backlog/planning artifacts: `.backlogit/queue/*`, `.backlogit/stash.jsonl`,
  `.backlogit/archive/stash.jsonl`, `docs/decisions/...`, `docs/plans/...`, `docs/memory/...`.
- PRESERVED and did NOT stage operator's pre-existing uncommitted changes:
  `.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`,
  `.github/agents/_ship.agent.md`, `.gitignore`.
- Role boundary honored: no push, no PR, no shipment claim, no build/test, no production code.

## Next steps

- Ship claims shipment 055-S → harness-architect authors the linear red harness chain, then
  build-feature turns it green in execution order (23-task chain above). Key make-green order:
  shared-fetch SSRF+pinned-connect+proxy-disable 064.011 → per-dimension caps 064.013 → threaded
    during-read aggregate budget 064.017 → adapter 064.015 (call_tool + list_callable_tools) → fetch-desc correction 064.019 →
  core transport 064.002 (legacy-era base; greens the fetch boundary 064.014 via routing) → stdio
  guardrails 064.009 (H1/H3/H4/H5) → modern negotiation 064.022 (server/discover + _meta + -32022)
  → dual-era routing 064.023 → entry point 064.003 (greens smoke 064.008) → docs 064.004 →
  review/CI/PR → merge. Cross-interface blast radius: 064.011/064.013/064.017 change shared fetch
  behavior (url_policy/http/crawl/app_models) for the CLI too; 064.019 changes the CLI --manifest
  advertising text; the dual-era surface (064.020-064.023) is additive to the transport with no
  legacy-client behavior change.
- Blocked features 060–063 remain blocked until their evidence requirements are met; re-triage
  when Foundry credentials, representative corpora, a GPU host, or production I/O profiling
  become available.
