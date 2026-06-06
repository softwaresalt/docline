---
shipment: 018-S
title: "Closure record — runtime safety primitives"
status: verified
merge_sha: e44ad54
merged_pr: 36
---

# Closure — 018-S: runtime safety primitives

## Outcome

Shipped the four runtime safety primitives identified by the 2026-06-04
load-test RCA, plus the side fix for a CWD-isolation bug that surfaced
while clearing the pytest baseline. The pipeline is now ready to absorb
the PDF splitter + batch + stitch shipment (next).

## Tasks

| Task | Title | Commit | Outcome |
|---|---|---|---|
| 018.001.001-T | TDD resource_probe module | (T1) | new `src/docline/runtime/resource_probe.py` with `ResourceBudget` + `probe()` + `should_use_docling`; 20 tests |
| 018.001.002-T | Pre-flight size gate | (T2) | new `resolve_pdf_engine_for_file(path, requested)`; 10 tests |
| 018.001.003-T | Broader auto-fallback exception net | (T3) | widened catch to `(PdfReadError, RuntimeError, MemoryError, OSError)`; 4 tests |
| 018.001.004-T | Probe-derived thread caps | (T4) | new `_apply_docling_thread_caps()` before docling import; 4 tests |
| 018.001.005-T | Fix `test_cli_process_no_staging_dir` CWD isolation | (T5) | wrapped in `monkeypatch.chdir(tmp_path)` |
| 018.001.006-T | Closure document | (this file) | — |

## Stash impact

* **Closed by this shipment** (5 stashes archived):
  * `1D945AB5` — adaptive resource probe (RAM / pagefile / GPU detection)
  * `4B913619` — size gate implementation piece (the threshold-spike
    measurement run is still future work for shipment C)
  * `15ADD215` — broader auto-fallback exception net
  * `C1EB2C6A` — probe-derived thread caps
  * `CB89952B` — test CWD isolation bug
* **Carried forward to shipment 021-S** (PDF splitter + batch + stitch):
  * `F64683BC` (P0 critical) — PDF splitter
  * `D885CE79` (P0 critical) — batch + stitch + subprocess isolation
* **Carried forward to shipment 022-S** (load harness):
  * `A2A78AEE` — `scripts/load_test.py`

## Quality Gate Evidence

### Local (Windows)

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | All files clean |
| `pyright src/` | 0 errors, 0 warnings |
| `pytest` | All 873 prior + 38 new tests pass (911 total) |

### CI

To be populated after the cross-OS matrix runs through this PR.

## Design summary — split-and-throttle pivot, primitives layer

The runtime probe is the single source of truth for every throttling
decision in docline. The decision matrix it returns (RAM tier ×
pagefile pressure → max pages / max MB / serialize / concurrency /
omp threads) is consumed by:

* `resolve_pdf_engine_for_file` — routes oversize PDFs to heuristic
  instead of docling
* `_apply_docling_thread_caps` — bounds PyTorch/BLAS thread fan-out
  before docling imports (writes are setdefault-only so operator
  overrides win)
* (Future) the PDF splitter (`F64683BC`) — splits PDFs that exceed the
  probe's per-call page limit into chunks
* (Future) the batch processor (`D885CE79`) — chooses serial vs
  concurrent chunk processing based on `serialize_docling`

The auto-fallback exception net (`15ADD215`) is the safety belt under
all of the above: even if the size gate misclassifies a PDF or the
probe misreads system state, docling crashes can no longer abort the
batch.

GPU detection is wired but dormant on the current 2026-06-04 host
(GTX 770M sm_30 fails the Maxwell+ capability gate). Any future
contributor on RTX 3060+ hardware (8+ GB VRAM, sm_75+) transparently
gets CUDA acceleration with no code change.

## Handoff to shipment 021-S (next)

The next shipment builds on `resource_probe.probe()` and
`should_use_docling`. Concrete consumers waiting on this primitives
shipment:

1. `src/docline/readers/pdf_splitter.py` (stash `F64683BC`) — calls
   `probe().recommended_docling_max_pages` to decide the chunk size.
2. `src/docline/process/pdf_batch.py` (stash `D885CE79`) — calls
   `probe()` to decide between serial and concurrent chunk processing.
3. `src/docline/_tools/docling_worker.py` (new, part of batch
   shipment) — subprocess CLI invoked per chunk by the batch
   orchestrator.

## References

* Plan: `docs/plans/2026-06-05-shipment-a-runtime-safety-primitives.md`
* RCA: `docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md`
* Decision: `docs/decisions/2026-06-04-spike-h1-header-synthesis.md`
  (the spike whose corpus generation triggered the OOM)
