# Architecture

docline is a document-to-Markdown ingestion and normalization pipeline exposed
through two interfaces — a CLI and a stdio MCP server — that both resolve through
one shared application façade. This document is the top-level domain map and the
authoritative record of dependency direction. It carries boundaries and direction
only; protocol and design rationale live in the deliberations and plans under
`docs/`.

## Interfaces and domains

```text
docline-mcp (console script)
  └─ docline.mcp.__main__            bootstrap: resolve §H8 opt-in, build server
       └─ docline.mcp.stdio          JSON-RPC 2.0 stdio transport (dual-era)
            └─ docline.mcp.server    DoclineMcpServer adapter (tool allow-list)
                 └─ docline.app      shared application façade / contracts
                      └─ fetch · process · readers · schema

docline (console script)
  └─ docline.cli                     argument parsing, console output
       ├─ docline.app                shared application façade / contracts
       └─ docline.elt.orchestrate    fetch orchestration
            └─ fetch · process · readers · schema
```

| Layer | Package(s) | Responsibility |
|---|---|---|
| MCP interface | `docline.mcp.__main__`, `docline.mcp.stdio`, `docline.mcp.server` | stdio transport, dual-era protocol, tool adapter |
| CLI interface | `docline.cli`, `docline.elt.orchestrate` | argument parsing, orchestration, console output |
| Shared façade | `docline.app`, `docline.app_models` | validated `fetch`/`process`/`export_schema` contracts |
| Core domains | `docline.fetch`, `docline.process`, `docline.readers`, `docline.schema` | I/O, extraction, normalization, schema |

## Dependency-direction invariants

* The shared and core domains (`app`, `fetch`, `process`, `readers`, `schema`) do
  **not** import the interface packages (`docline.mcp.*`, `docline.cli`).
  Dependencies flow inward: interfaces → façade → core.
* Both interfaces reach the same domains through `docline.app`
  (`docline.mcp.server` and `docline.cli` both import `docline.app`), so CLI and
  MCP behavior stay in parity by construction.
* Shared-fetch hardening (SSRF-by-resolution, per-response and aggregate byte
  budgets, redirect revalidation — §H6/§H7) lives in `docline.fetch` and applies
  to **both** the CLI and the MCP surface.
* The §H8 external-PDF-engine opt-in policy is **MCP-boundary-specific**
  (`docline.mcp.server` advertise/dispatch gate, `docline.mcp.stdio` `-32602`
  mapping, `docline.mcp.__main__` startup resolution) and does **not** change CLI
  behavior: `docline process --pdf-engine mistral_ocr` is unaffected.
