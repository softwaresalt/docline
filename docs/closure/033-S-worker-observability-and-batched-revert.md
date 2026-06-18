---
title: 033-S worker observability + batched-default revert (032-S regression fixes)
date: 2026-06-17
status: shipped
verdict: PROMOTE
shipment: 033-S
feature: 031-F
supersedes_behavior: 032-S batched-by-default
references:
  - src/docline/process/pdf_triage.py
  - src/docline/process/pdf_batch.py
  - src/docline/_tools/docling_worker.py
  - docs/closure/032-S-docling-worker-contract.md
  - docs/decisions/2026-06-14-docling-batch-size-probe.md
  - .elt/output/cosmos-triage-022/pa3-summary.json
---

# 033-S — 032-S regression fixes (worker observability + batched-default revert)

## How it surfaced

The post-032-S operator validation runs against the cosmos PDF exposed a
silent regression:

| Run | Result | Signal |
|---|---|---|
| `per_page_fidelity_check.py` (T5) | `PASS` (hollow) | `subprocess_fallback_count: 86/86`; engine dist `{heuristic: 3426}` — **zero docling**. The assertion passed only because there were no docling pages to check. |
| `docling_batch_size_probe.py` (T4) | clean | docling works **in-process**; `layout_batch_size=4` is the knee. |
| `run_pa3_pa4_cosmos_022.ps1` | docling 0%, 32m23s | `subprocess_fallback_count: 86/86`; QA tripwire 34/34 also failed. |
| Single-chunk worker diagnostic | **success** | 30-page splice → 108 KB envelope, 54,685 chars (identical to T4 in-process). |

## Root cause

The single-chunk worker **succeeds** standalone, but the cosmos run failed
100%. The difference: 032-S's batched mode (`use_batched_worker=True` by
default) runs **all** flagged ranges — for cosmos, **86 ranges / 1,818
pages** — in **one** long-lived subprocess.

That defeats the per-chunk torch-memory reclaim the original design relied
on. The `docling_worker` module docstring states it directly:

> *Running each chunk in its own subprocess gives the OS a chance to
> reclaim torch tensor working set between calls (PyTorch's CPU allocator
> does not return memory to the OS reliably).*

Accumulating ~1,818 pages of docling/torch working set in one process
exhausts memory; the process is killed → non-zero exit → **every** range
falls back to heuristic. A single 30-page splice fits in memory, so the
diagnostic and the T4 probe both succeed.

Two compounding 032-S defects made this invisible and worse:

1. **Observability gap (Constitution V):** every worker call site discarded
   `completed.stderr`, so the operator saw `86/86` fallback with no cause.
2. **QA envelope-parsing miss:** the QA tripwire read the worker's JSON
   envelope (032-S T1 format) as raw markdown, garbaging the disagreement
   metric whenever docling succeeds.

## What shipped

### 1. Batched-default revert (the functional fix)

`use_batched_worker` now defaults to **False** in both
`process_pdf_in_chunks` (pdf_batch) and `process_pdf_triaged` (pdf_triage).
The default is the proven per-chunk/per-range subprocess loop — one process
per chunk, memory reclaimed between chunks. Batched mode remains available
as an explicit opt-in, with a docstring warning about the large-corpus
memory risk. This restores docling functionality on the cosmos corpus
(correct-but-slower beats fast-but-broken). The batched perf win it gives
up was modest (~5% cold-start dedup, per the 032-S closure estimate).

### 2. Worker stderr observability (Constitution V)

Every worker failure path now logs the captured stderr / error-envelope
detail at WARNING:
- `pdf_triage`: batched-splice, per-range loop, QA tripwire, batched
  per-chunk error-envelope (logs `envelope.error`).
- `pdf_batch`: `_run_chunks_batched` + `_process_one_chunk`.

### 3. QA envelope-text parsing

New `_worker_output_text()` helper parses the envelope `text` field; the QA
tripwire uses it instead of reading raw JSON as markdown.

### 4. T4 decision doc

`docs/decisions/2026-06-14-docling-batch-size-probe.md` filled in with the
operator's empirical results: `layout_batch_size=4` is the knee (already
docling's default, so no production code change); per-page loop is 2.22×
overhead for identical content (per-page restoration stays deferred).

## Tests

- `test_per_chunk_loop_is_the_default_for_multi_chunk` (pdf_batch) and
  `test_triage_per_range_is_the_default_for_multi_range` (pdf_triage) —
  regression guards asserting batched mode is opt-in, default per-chunk,
  and `--batch` is never invoked by default.
- `test_qa_tripwire_compares_envelope_text_not_raw_json` — spies
  `_content_similarity`, asserts parsed envelope text (not raw JSON).
- `test_worker_subprocess_failure_logs_stderr_diagnostic` — `caplog`
  asserts the worker stderr marker is logged.
- Existing batched tests updated to opt in with `use_batched_worker=True`.
- **Full suite: 1263 passed, 4 skipped.**

## Follow-ups filed

- `6E6754D4` (high) → **RESOLVED by this shipment** (root cause identified:
  batched-mode memory exhaustion). Kept for the operator's confirmation
  re-run with observability on.
- `1182227F` (medium) — bounded sub-batching to recover the batched perf
  win safely (cap each subprocess at ~32–48 pages, fresh process per
  group). Recommend a deliberation before building.
- `F676E692` (medium) — batched-mode partial-crash recovery (gate per-chunk
  on own envelope, not whole-batch returncode).

## Operator next step

Re-run the cosmos pipeline with this build. With the default now per-chunk,
docling should actually run (slower than the broken 32m heuristic-only run,
but producing real docling output). If any individual range still fails, the
new WARNING logs will show the worker's exact stderr diagnostic.
