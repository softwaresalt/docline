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

## Crawl frontier truncation observability

The bounded crawl (`docline.fetch.crawl`) admits at most `MAX_FRONTIER` (10,000)
discovered links per crawl, independent of `max_pages` and `max_depth`. When that
ceiling refuses an eligible link, the crawl records the loss through one signal
that reaches **both** interfaces by construction:

* `crawl()` returns a `CrawlOutcome` carrying `results` and a `frontier_truncated`
  flag. The flag is `True` only when an eligible candidate was actually dropped,
  not when the cap was merely reached.
* A single WARNING is logged once per crawl at default verbosity. Its payload is
  the sanitized crawl **origin** (scheme and host) plus the admission count; it
  omits the path, query, fragment, and userinfo, so a default-visible record
  cannot leak URL-carried credentials.
* `docline.elt.execute` threads the flag into `crawl-manifest.json` (written even
  when zero pages stage) and onto `StagingJob.frontier_truncated`.
* The CLI serializes `StagingJob` verbatim, so the field appears in CLI JSON with
  no CLI-specific change. The MCP path copies it onto `FetchResult.frontier_truncated`.
  Both surfaces report the same value for an equivalent request.

At depth zero, TOC-derived navigation is ordered ahead of in-page anchors, so a
truncated mdBook crawl sheds anchors and keeps the authoritative TOC set. The
signal is deliberately conservative: a depth-zero page that references a TOC
script may report truncation even when that script would have yielded no
admissible links, because confirming otherwise would require the network fetch
the exhausted short-circuit exists to avoid. A false "may be incomplete" prompts
a re-run; a false "complete" would hide data loss.

`MAX_FRONTIER` is not operator-configurable on the CLI or MCP fetch paths, and
the ELT path always uses the default. The remedy for a truncated crawl is to
narrow it with a tighter start URL, a lower `depth`, or a section-scoped entry
point.
