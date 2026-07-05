# 051-S ship session memory — OpenAPI/Swagger design spike + session triage

- Date: 2026-07-04
- Agent: orchestrator (inline stage+ship; backlogit MCP down → CLI at C:\Tools\backlogit.exe)
- Shipment: 051-S (feature 049-F, spike). Merged spike PR #134 at 8059eba; closure PR pending.

## Session arc (AFK autonomous full-pipeline run)

1. Closed pending 049-S CI-cost closure (PR #131 merged).
2. Assessed backlog: empty of active/queued shipments; only the 9-entry stash.
3. Shipped **050-S / 048-F** — `DOCLINE_ACCELERATOR` env override (PR #132 + closure #133).
4. Shipped **051-S / 049-F** — this OpenAPI/Swagger design spike (PR #134 + this closure).

## Stash triage (why the rest is not shippable now)

| id | pri | verdict |
|---|---|---|
| F4167E69 Mistral OCR v4 eval | med | BLOCKED — needs AZURE_AI_FOUNDRY_KEY / Foundry creds |
| E32FAF6F hybrid pdf_engine routing | med | BLOCKED — Foundry creds (benchmark needs Mistral) |
| B26003B0 Mistral on forms/invoices | low | BLOCKED — Foundry creds |
| 7AA9FAA0 release/publish workflow | low | BLOCKED — gated on a 1.0 milestone (not yet reached) |
| A3E6D72C OCR calib on scanned corpus | med | BLOCKED — needs scanned/high-mpx corpus. NOTE: the "per-page floor" sub-note is ALREADY shipped (`OCR_PER_PAGE_FLOOR_MB=207` in runtime/ocr_budget.py, 041-F). Only the scanned-corpus re-calibration remains. |
| 4CB606D5 extraction study on new corpora | low | DEFER — needs sci/legal/novel corpora (downloadable via curl but heavy + low pri) |
| 3048007A GPU acceleration | low | PARTIAL — the env-gating slice shipped as 048-F (DOCLINE_ACCELERATOR). docling already auto-detects GPU (device=auto, verified 2.97.0). Remaining = GPU throughput benchmark, needs a GPU host. |
| 935F2694 multi-chunk envelope | low | SKIP — YAGNI; "only worth doing if per-chunk file I/O becomes a measurable hot path" (no evidence). |
| F8E142A1 OpenAPI/Swagger | low(epic) | SPIKED this session → 049-F; annotated with PROCEED verdict + T1–T6, ready to harvest a build feature. |

## Decisions / rationale

- Chose sound-judgment scope over volume: shipped only genuinely completable,
  verifiable work (048-F code + 049-F design). Did NOT ship unverifiable GPU
  code, Foundry-blocked studies, or speculative YAGNI work to "clear" the stash.
- OpenAPI = structured-render, not layout-extract. Per-operation rendering; local
  `$ref` only in v1; no new dep (PyYAML present). External `$ref` = SSRF/traversal
  boundary flagged for the deferred task.

## Next steps for the operator

- Green-light OpenAPI per-operation granularity + v1 scope → harvest F8E142A1 into
  a build feature (T1–T6 in the spike doc).
- Unblock Foundry-gated items (F4167E69 / E32FAF6F / B26003B0) when creds available.
- Recommend restarting the backlogit MCP server before the next session (down all session).
