---
shipment: 046-S
title: "Closure record — per-page boundary markers in stitched batch markdown (043-F)"
status: verified
merge_sha: 6f1a559
merged_pr: 122
---

## Scope delivered

Feature `043-F` adds an **opt-in** per-page boundary marker capability to the
batch stitcher so downstream graph writers (graphtor-docs, now installed as an
MCP ingestion consumer) can recover page boundaries from the stitched markdown.

| Task | Delivered |
|---|---|
| `043.001-T` | `src/docline/process/pdf_batch.py` — new `page_markers: bool = False` flag on `process_pdf_in_chunks`; new `_stitch_chunk_markdown_with_markers` emits a monotonic `<!-- page N -->` comment before each page, driven by `ChunkResult.chunk_pages`. Skips `page_overlap`-duplicated boundary pages (guarded by `len(pages) > page_overlap` so tiny/defensively-parsed chunks are never dropped); heuristic chunks emit one marker for the whole body. The `recommended_docling_max_pages <= 0` early heuristic path also honors the flag. Tests in `tests/process/test_pdf_batch.py`. |

## Design decisions

- **Opt-in / default-off**: `page_markers=False` keeps the stitched output
  byte-identical to prior behavior; all pre-existing tests are unchanged.
- **Overlap numbering**: for chunks after the first, the leading `page_overlap`
  (= 2, from `split_pdf`) pages duplicate the previous chunk's trailing pages
  and are skipped, keeping the 1-based page counter source-relative and removing
  duplicate content — but only when `len(pages) > page_overlap`, so short or
  defensively-parsed chunks are never dropped.
- **Heuristic fallback**: chunks without per-page data (`chunk_pages` empty)
  emit a single marker for the whole chunk body (documented best-effort).

## Verification

- `ruff check .` — clean
- `pyright src/` — 0 errors
- `pytest` — full suite green (1401 passed, 6 skipped; 6 new tests)
- `ruff format --check .` — clean
- Copilot review on PR #122 — 3 threads, all resolved: 2 valid fixes (early
  heuristic path honoring the flag + its regression test) and 1 declined false
  positive (`status: review` is a valid WIT status).

CI remains paused in `.github/workflows/ci.yml` (tags / releases / manual
dispatch only); gates were run locally under `uv run`.

## Notes

- The `page_markers` flag is not yet wired to the CLI/MCP surface — this
  shipment delivers the stitcher capability; exposing it to end users is a
  separate follow-up if/when graphtor-docs ingestion needs it.
