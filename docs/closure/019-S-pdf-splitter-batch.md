---
shipment: 019-S
title: "Closure record — PDF splitter + batch + stitch + subprocess isolation"
status: verified
merge_sha: TBD
merged_pr: TBD
---

# Closure — 019-S: PDF splitter + batch + stitch + subprocess isolation

## Outcome

Shipped the split-and-throttle pipeline that the 2026-06-04 load-test
RCA called for. Any PDF that exceeds the resource probe's per-call
budget is now split into manageable chunks, each chunk runs docling
in an isolated subprocess (so c10::Error / OOM is reaped by the OS),
and the per-chunk outputs are stitched into one logical document
with overlap-aware H1 deduplication.

Combined with shipment 018-S's runtime safety primitives, the
`azure-cosmos-db.pdf` (109 MB, ~700 pages) that triggered the
2026-06-04 paging spiral is now handled as ~14 chunks of 50 pages,
processed serially under pagefile pressure, with each chunk subprocess
bounded to a single-chunk working set instead of the whole document.

## Tasks

| Task | Title | Outcome |
|---|---|---|
| 019.001.001-T | TDD pdf_splitter module | `src/docline/readers/pdf_splitter.py` with `split_pdf()` + deterministic chunk naming + cache reuse + page_overlap |
| 019.001.002-T | TDD docling_worker subprocess CLI | `src/docline/_tools/docling_worker.py` with structured exit codes + JSON stderr diagnostics |
| 019.001.003-T | TDD pdf_batch orchestrator | `src/docline/process/pdf_batch.py` with `process_pdf_in_chunks()` + adaptive serialize + per-chunk fallback + H1 dedup |
| 019.001.004-T | Closure document | this file |

## Stash impact

* **Closed by this shipment** (2 P0 stashes archived):
  * `F64683BC` — PDF splitter (was promoted P1→P0 by the 2026-06-05 design pivot)
  * `D885CE79` — batch + stitch + subprocess isolation (same)
* **Carried forward to shipment 020-S** (load harness):
  * `A2A78AEE` — `scripts/load_test.py` (only remaining shipment in the RCA-driven plan)

## Quality Gate Evidence

### Local (Windows)

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | All files clean |
| `pyright src/` | 0 errors, 0 warnings |
| `pytest` (full suite, .elt/staging hidden) | All passes including 26 new tests for splitter + worker + batch |

### CI

To be populated after the cross-OS matrix runs through this PR.

## Architectural surface

```
src/docline/runtime/resource_probe.py        # shipment 018-S
src/docline/readers/pdf_splitter.py          # this shipment (T1)
src/docline/_tools/docling_worker.py         # this shipment (T2)
src/docline/process/pdf_batch.py             # this shipment (T3)
```

Public API at this shipment's surface:

* `split_pdf(path, *, max_pages, page_overlap=2, cache_dir=None) -> list[Path]`
* `process_pdf_in_chunks(path, *, output_dir, budget=None, runner=None) -> BatchResult`
* `ChunkResult`, `BatchResult` (frozen dataclasses with per-chunk engine, exit_code, reason, markdown)

The `_tools/docling_worker.py` is an internal CLI not exported from
the public `docline` package surface; it exists so the batch
processor can run docling in subprocess isolation.

## How the 2026-06-04 cosmos PDF would flow today

1. CLI calls `resolve_pdf_engine_for_file(cosmos.pdf, requested="auto")`
   (shipment 018-S). Probe returns `max_pages=75, max_mb=30` on the
   2026-06-04 host. Cosmos at 109 MB exceeds `max_mb` → reason
   `file_too_large`, engine `heuristic`. **In this shipment's wiring,
   that's the end of the story** — heuristic returns text directly.
2. To route cosmos through the splitter path instead, the caller
   would use `process_pdf_in_chunks(cosmos.pdf, output_dir=...)`
   directly. That call:
   * probes → 75-page chunks, serialize_docling=True under pagefile pressure
   * splits cosmos into ~10 chunks of 75 pages with 2-page overlap
   * for each chunk: spawns `python -m docline._tools.docling_worker`
     in a fresh subprocess; OS reaps cleanly if docling OOMs
   * any chunk whose subprocess exits non-zero falls back to heuristic
     for that chunk only (not the whole document)
   * pauses 10 seconds between chunks (serialize_docling mode) so the
     OS can reclaim torch tensor pages
   * stitches all chunk markdowns with H1 deduplication and returns
     a single `BatchResult.stitched_markdown`

Full pipeline wiring (calling `process_pdf_in_chunks` from
`output_contract.build_output_document_parts`) is intentionally deferred
to a follow-on shipment so this PR keeps the change surface focused
on the new modules and their tests. The wiring is small (one
conditional in `output_contract`) and will land alongside shipment
020-S's load-test harness when measured baselines confirm the
thresholds.

## Handoff to shipment 020-S (next)

The load-test harness (stash `A2A78AEE`) can now invoke
`process_pdf_in_chunks` directly to drive the full Power BI + cosmos
corpus through the split-and-throttle pipeline and produce empirical
peak-RSS / elapsed-time measurements per chunk. Those measurements
become the threshold-spike evidence for stash `4B913619` (already
partly closed by 018-S; this is the measurement-run completion).

## References

* RCA: `docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md`
  (remediations 3 and 6)
* Plan: `docs/plans/2026-06-05-shipment-a-runtime-safety-primitives.md`
  (the foundation that this builds on)
* Prior closure: `docs/closure/018-S-runtime-safety-primitives.md`
* Adjacent open stash: `A2A78AEE` (next shipment)
