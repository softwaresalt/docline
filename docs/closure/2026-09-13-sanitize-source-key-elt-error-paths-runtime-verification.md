---
artifact_type: runtime-verification
shipment_id: 063-S
feature_id: 072-F
title: 063-S Sanitize credential-bearing source_key on ELT error/persistence paths — runtime verification
created_at: 2026-09-13T20:15:00-07:00
verifier: ship-agent
commit: 3933dfc335e19bcd602bf104e82728268ae83156
pr: 199
status: PASS_WITH_FOLLOW_UP
---

## Scope

Post-merge runtime verification for shipment **063-S** (feature **072-F**,
PR #199, merge commit `3933dfc335e19bcd602bf104e82728268ae83156`). The
shipment adds a typed-config credential sanitizer (`sanitize_source_key`,
`sanitize_source_id`, `_sanitize_url_field`) to the ELT staging/execute paths
so credential-bearing `source_key` values are never persisted to
`metadata.json` or logged unredacted on error paths.

Runtime surfaces per `.autoharness/workspace-profile.yaml`
`runtime_validation`: `cli` and `api` (MCP). Source environment: Windows,
Python 3.14.3, branch `main` at `3933dfc`.

## Validator manifest coverage

| Surface | Probe | Adapter |
|---|---|---|
| `cli-help` | `docline --help` | command |
| `cli-manifest` | `docline --manifest` | command |
| `mcp-tools-list` | `docline-mcp` stdio `initialize` → `notifications/initialized` → `tools/list` | command (stdio JSON-RPC) |
| `mcp-initialize-handshake` | same stdio session as above | manual checkpoint (automated this session — see note) |

## Probe results

### CLI surface

| Probe | Command | Expected | Observed | Result |
|---|---|---|---|---|
| Help banner | `docline --help` | usage banner, non-error exit | Usage banner listing `fetch`, `process`, `quarantine-viewer`, `export-schema`, `ingest`; exit 0 | PASS |
| Manifest | `docline --manifest` | JSON tool manifest | Valid JSON; tools `fetch, process, export_schema, ingest_local_dir`; exit 0 | PASS |

### MCP / API surface

| Probe | Method | Expected | Observed | Result |
|---|---|---|---|---|
| `initialize` handshake | stdio JSON-RPC `initialize` | Well-formed `result` with `protocolVersion`, `capabilities`, `serverInfo` | `{"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "docline-mcp", "version": "0.1.0"}}` | PASS |
| `tools/list` (post-`initialized`) | stdio JSON-RPC `tools/list` | Tool names per the untrusted-surface callable allow-list | `fetch, process, export_schema` | PASS |
| In-process `list_tools()` (full shared manifest) | `DoclineMcpServer.list_tools()` | Full manifest incl. `ingest_local_dir` | `fetch, process, export_schema, ingest_local_dir` | PASS |

**Note on the manual-checkpoint manifest entry**: `runtime_validation.validator_manifest`
marks `mcp-initialize-handshake` as a manual checkpoint because stdio MCP
handshakes are "not reliably automatable in this environment." This session
successfully automated the full `initialize` → `notifications/initialized` →
`tools/list` round-trip via a short-lived subprocess with redirected
stdin/stdout and a bounded read timeout, so it is recorded here as an
automated PASS rather than an operator note. The manifest's manual-checkpoint
classification is left unchanged for future sessions where this automation
may not be available (e.g., a different transport wrapper or sandboxing).

**Note on CLI/MCP tool-count divergence (pre-existing, not a 063-S regression)**:
`docline --manifest` and the in-process `list_tools()` both enumerate 4 tools
(including `ingest_local_dir`), while the stdio `tools/list` RPC enumerates
only 3 (`fetch`, `process`, `export_schema`). This is **intentional,
documented, pre-existing behavior** — `src/docline/mcp/server.py`
`list_callable_tools()` explicitly excludes `ingest_local_dir` from the
untrusted MCP surface because its `source_path` parameter has no
workspace-containment validator (§H1/§H8 hardening, predates 063-S). Verified
via `git blame`/source inspection that this exclusion is unrelated to and
unmodified by 063-S's diff (which touches only `src/docline/elt/source_keys.py`,
`src/docline/elt/execute.py`, and their tests). Not a 063-S finding; not a
release blocker for this shipment.

## Functional verification (change-specific)

* `pytest tests/elt/test_source_keys.py tests/elt/test_elt_real_execution.py -q`
  → **114 passed**, 0 failed.
* Live probe — end-to-end credential redaction on a representative
  credentialed `web_crawl` source:

  ```python
  from docline.elt.source_keys import sanitize_source_key
  from docline.elt.models import WebCrawlSource

  cfg = WebCrawlSource(type="web_crawl", url="https://user:SECRETPASS@example.com/path?token=ABC123")
  sanitize_source_key(cfg)
  # -> "web_crawl:https://example.com/path"
  ```

  Userinfo (`user:SECRETPASS@`) and the `?token=ABC123` query parameter are
  both fully stripped from the persisted/logged `source_key`. **PASS.**
* `python -m py_compile src/docline/__init__.py` — exit 0. **PASS.**

## Verdict: PASS WITH FOLLOW-UP

All required CLI and API/MCP probes pass; the change-specific credential
sanitization behavior is directly verified end-to-end via live probe plus the
full targeted unit suite (114/114). The single follow-up is **not** a defect
in this shipment:

* **Follow-up (informational only, not blocking)**: the known,
  already-deferred residual sinks/gaps documented in `.backlogit/stash.jsonl`
  (`0F1A653C` default-fetch-path sink, `06A59B1D` credential-param-prefix
  expansion, and the PR #199 body's follow-up list items 1–4: Unicode
  format-character lstrip gap, ambiguous-authority asymmetry, possible
  sanitizer redundancy, pre-existing private-symbol imports) remain
  out-of-scope per P-021 C1 and are not re-litigated here.

## Handoff to Operational Closure

* Verification verdict: **PASS_WITH_FOLLOW_UP**
* Runtime surfaces verified: `cli` (command adapter), `api`/MCP (command/stdio
  JSON-RPC adapter)
* Evidence collected: CLI stdout/exit codes, MCP stdio JSON-RPC transcripts,
  targeted pytest run (114 passed), live sanitizer probe output
* Manual checkpoint evidence: `mcp-initialize-handshake` — automated this
  session (see note above); PASS
* Blocked prerequisites: none
* Follow-up recommendations: none new; existing deferred stash entries stand
  as already recorded
* Releasability handoff: CLI smoke (`docline --help`/`--manifest`) — PASS;
  MCP initialize handshake — PASS (automated); named owner — see closure
  artifact
