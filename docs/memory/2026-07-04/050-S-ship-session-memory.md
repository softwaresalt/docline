# 050-S ship session memory — accelerator env override

- Date: 2026-07-04
- Agent: orchestrator (inline stage+ship; backlogit MCP down → CLI)
- Shipment: 050-S (feature 048-F, task 048.002-T)
- PR: #132 (impl) merged at dc427aa; closure PR pending.

## Completed

- Assessed backlog: no active/queued shipments; 9 stash entries, most externally
  blocked (Foundry creds, GPU hardware, scanned/extra corpora, 1.0 milestone).
- Selected 3048007A's verifiable slice: `DOCLINE_ACCELERATOR` env override.
- Verified docling 2.97.0 defaults `AcceleratorOptions.device=auto` (GPU already
  auto-detected); canonical import is `docling.datamodel.accelerator_options`
  (pyright `reportPrivateImportUsage` flags the `pipeline_options` re-export).
- TDD: `tests/readers/test_pdf_accelerator_env.py` (23) → impl in
  `readers/pdf.py` (pure resolver + options builder + `PdfConfigError` +
  constructor injection). README documented.
- 4 gates green. Copilot flagged test-tree mirroring → moved to `tests/readers/`.

## Decisions / rationale

- Default `auto` = zero behavior change; only `cpu`/`cuda`/`mps`/`xpu` override.
  Force-CPU is the real value (escape hatch for unreliable auto-detected GPU).
- Resolve accelerator BEFORE the conversion `try` so `PdfConfigError` isn't
  masked as `PdfReadError`.
- `num_threads` left at docling default (4) → no thread-behavior regression.
- Single funnel (`_read_pdf_docling_pages`) gives CLI + batch-worker parity.

## Backlogit friction

- Creating the task with `--status done` auto-archived it (no merge SHA);
  done→active transition is blocked. Force-deleted the stray and recreated as
  `active` (id shifted 048.001-T → 048.002-T). Fixed shipment items + `sync`.
- Lesson: create feature/task/shipment as `active` during impl; archive only at
  `shipment ship` so the merge SHA is recorded.

## Next steps

- Merge closure PR for 050-S.
- Then: OpenAPI/Swagger design spike (049-F, stash F8E142A1); annotate blocked
  stash items.
