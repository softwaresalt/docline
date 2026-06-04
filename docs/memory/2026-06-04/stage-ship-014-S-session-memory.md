---
type: session-memory
date: 2026-06-04
session: stage-and-ship-014-S
shipment: 014-S
branch: feat/014-docling-sidecars
status: pr-pending
---

# Stage + Ship session — shipment 014-S (G3c docling + sidecars)

## Summary

Single autonomous session executing both Stage and Ship workflows for shipment `014-S`. Stage harvested stash `351170C9` into feature `015-F` + 5 TDD-ordered tasks. Ship executed all five tasks end-to-end. All 5 quality gates green at HEAD `44fdd02`.

## Operator clarifications during session

1. Python baseline is 3.12 across the board (CI, production, local `.venv`). The bare `python` PowerShell command resolved to a system-wide 3.14 install; switched all venv-bound commands to `.\.venv\Scripts\python.exe`. No 3.14 / torch wheel risk applies.

## Tasks completed

| Task | Status | Commit | Description |
|---|---|---|---|
| `015.001-T` | done | `dae7d94` | TDD RED — 21 failing tests (engine resolution + DOCX walk + sidecar manifest + CLI) |
| `015.002-T` | done | `8bb044e` | GREEN-1 — pyproject extra, PictureSink module, `_resolve_layout_engine`, `auto` fallback |
| `015.003-T` | done | `8cfae97` | GREEN-2 — `read_docx_blocks_with_media` with `<w:drawing>` walk and rels resolution |
| `015.004-T` | done | `44fdd02` | GREEN-3 — wire pdf_engine through CLI + ProcessRequest + output_contract + manifest |
| `015.005-T` | done | (closure commit pending) | Closure document |
| `015-F` | done | (closure commit pending) | Feature archived |

## Critical bug fix during implementation

`read_pdf_pages` `"auto"` path had an orphaned `return _read_pdf_docling_pages(path)` after the `if/else` block, bypassing the try/except fallback. Caught by sidecar manifest tests when docling failed on synthetic PDFs. Removed the dead-code return.

## Decisions

1. **Reader-level defaults stay `"heuristic"`** (back-compat with direct callers and existing tests); production wires `"auto"` through `output_contract.build_output_document_parts`.
2. **`"auto"` engine path silently falls back** to heuristic on `PdfReadError` from docling (preserves batch runs through hostile PDFs).
3. **`OutputDocumentPart.media_files`** is `tuple[str, ...]` for frozen-dataclass safety; manifest entries serialize via `list(...)`.
4. **First-part-only attachment**: media_files appear on the first part of a source; sibling parts get `[]` to avoid duplication.
5. **Forced multi-part layout** (plan-review F2): when any media is present, the source uses `{source}/part-NNNN.md` layout regardless of segment count so `![](media/figure-0001.png)` resolves sibling-relative.
6. **Cross-repo schema snapshot** is unchanged in this shipment (no BaseFrontmatter source changes); the existing 013-S `752CA1E4` follow-up still covers it.

## Review findings

Ship Step 4.4 mode `report-only`: 0 P0, 0 P1, 0 P2; 2 P3 advisories. None block merge.

## Open / next steps

1. Commit closure + push branch + create PR
2. Copilot review polling per §1.2
3. P-014 readiness gate + operator approval
4. Post-merge closure (Step 6) — no new cross-repo follow-up needed (schema unchanged)
5. Stash follow-up for docling tuning (5ADD558F already recorded during closure)

## Stash inventory after this cycle

| Stash ID | Priority | Theme |
|---|---|---|
| `5ADD558F` | low | **NEW** — docling PdfPipelineOptions tuning + PictureSink wiring (014-S follow-up) |
| `752CA1E4` | high | graphtor-docs schema snapshot refresh (013-S follow-up, still pending operator) |
| `5E87FCDD` | medium | P-009 rebase merge disable |
| `ED74577A` | medium | Cross-OS CI matrix |
| `0AA8B223` | low | Windows tmp_path RCA |
| `F50AD7E6` | low | `_char_bin` CRLF hardening |
| `7AA9FAA0` | low | PyPI/Releases workflow |
