---
type: operational-closure
shipment: 055-S
feature: 064-F
pr: 169
merge_commit: 29cf11715ed7b8d638aca6d739fb3a0177c7c20f
date: 2026-08-29
status: closed
---

# 055-S Operational Closure — Local stdio MCP server

## Release summary

Shipment **055-S** (feature **064-F**) delivered a local stdio MCP server for docline
exposing the shared `fetch` / `process` / `export_schema` tools to untrusted MCP clients.
Merged via PR #169 (merge commit `29cf117`) with a merge commit (P-009 honored). All 36
manifest tasks completed under strict TDD.

Delivered surfaces:

- **Transport** (`docline.mcp.stdio`): newline-delimited JSON-RPC 2.0 over stdio; bounded
  non-greedy framing (`MAX_FRAME_BYTES` 1 MiB); per-frame flush; §H3 error-text + structured
  sanitization; §H5 stdout hygiene.
- **Dual-era protocol**: legacy `initialize` handshake (`2025-11-25`) + modern `2026-07-28`
  `server/discover` + per-request `_meta` negotiation (`-32022`/`-32602`, `resultType:"complete"`,
  `cacheScope:"private"`); per-connection legacy latch + pre-initialize reject; guard parity.
- **§H8 external-engine gate** (`docline.mcp.server` + `__main__`): default-deny of
  `mistral_ocr`; advertise-omit + dispatch-deny; startup-only opt-in (`DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES=1`
  or `--allow-external-pdf-engine`); never from request data.
- **Packaging**: `docline-mcp` console script + `python -m docline.mcp`.
- **Docs**: README MCP section + `docs/ARCHITECTURE.md`.

## Verification

| Gate | Result |
|---|---|
| `ruff check .` | pass |
| `ruff format --check .` | pass (CI ruff 0.15.15) |
| `pyright src/` | 0 errors |
| `pytest` | 1843 passed, 17 skipped |
| CI (GitHub Actions, 7 jobs) | all pass on merge SHA |
| Runtime probe | `docline-mcp` answered modern `server/discover` — `resultType:complete`, `supportedVersions:[2026-07-28,2025-11-25]`, `cacheScope:private` |

## Review

Multi-persona adversarial pre-PR review (correctness / security / Python): no P0–P2; P3
hardening applied. Copilot review converged over 5 cycles (9 → 3 → 2 → 1 → 0 findings), all
valid findings fixed and threads resolved:

- cacheScope enum conformance; `arguments` non-object rejection; structuredContent §H3
  sanitization; sanitizer Windows-forward-slash/UNC coverage; multi-address validated connect
  with a single shared deadline; redirect `fp` close on all exception paths; `RemainingByteBudget`
  debit thread-safety; internal-error id echo; connection-pinning tests; doc corrections.

## Monitoring & rollback

- **Monitoring**: the server writes only JSON-RPC frames to stdout; operational diagnostics go
  to stderr. Malformed/oversized input degrades to typed error envelopes without crashing the loop.
- **Rollback**: revert merge commit `29cf117`. Note this reverts the **entire two-slice shipment**,
  not just the MCP package: the first slice also landed cross-interface shared-fetch hardening in
  `fetch/*` (SSRF-by-resolution, address-pinned connect, per-response + aggregate byte budgets,
  redirect revalidation) and `app_models` request limits (`max_pages` ≤ 1000, `depth` ≤ 64), plus a
  corrected shared `fetch` tool description in `app.py`. Reverting therefore also **weakens CLI fetch
  validation and DoS bounds**, so a rollback must be a deliberate whole-shipment decision, not a
  local MCP-only change.
- **Blast radius**: the **MCP interface surface** (`docline.mcp.*`, the `docline-mcp` script) and the
  **§H8 external-engine gate** are MCP-boundary-only — `docline process --pdf-engine mistral_ocr`
  (CLI) is unchanged. The **shared-fetch hardening and request-limit changes are cross-interface**
  and affect both the CLI and MCP fetch paths, so they are not isolated to `docline.mcp`.

## Follow-ups (stashed for Stage)

- `173238FD` — bound crawl() frontier growth independently of `--depth`/`--max-pages`
  (pre-existing crawl concern; deferred at the review-fix cycle-3 limit).

## Preserved stash (for Stage)

`0A56B201`, `87F2C06D`, `0A56B202` — untouched.
