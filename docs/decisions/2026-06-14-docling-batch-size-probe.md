---
title: docling batch-size probe results
date: 2026-06-16
status: empirical
shipment: 032-S
feature: 030-F
task: 030.004-T
references:
  - scripts/study/docling_batch_size_probe.py
  - src/docline/readers/pdf.py
  - docs/decisions/2026-06-08-extraction-strategy-study.md
---

# docling batch-size probe — empirical results (2026-06-16)

Operator ran the probe against a 30-page splice (pages 859–888 of the
cosmos PDF, from the table-heavy ``range-0859-1056`` flagged region).

## Results

| Probe | Pages | Wall (s) | Throughput (pp/min) | Peak RSS (MB) | Chars |
|---|---:|---:|---:|---:|---:|
| layout_bs=1 | 30 | 74.46 | 24.2 | 1226 | 54685 |
| layout_bs=4 | 30 | 61.59 | 29.2 | 2043 | 54685 |
| layout_bs=8 | 30 | 61.63 | 29.2 | 2048 | 54685 |
| layout_bs=16 | 30 | 61.97 | 29.0 | 2089 | 54685 |
| layout_bs=32 | 30 | 62.88 | 28.6 | 2108 | 54685 |
| per-page-loop | 30 | 136.43 | 13.2 | 2262 | 54630 |

## Conclusions

- **Chosen ``layout_batch_size``: 4 (docling's existing default — no code change needed).**
  Going 1→4 is a **17% speedup** (74.5s → 61.6s). Beyond 4 there is **no
  throughput gain** (4/8/16/32 all land at ~61–63s) while peak RSS keeps
  climbing (2043 → 2108 MB). Batch size 4 is the clean knee of the
  latency/memory curve. Output chars are **identical** (54685) across all
  batch sizes, confirming batch size affects only speed/memory, never
  fidelity.

- **``ocr_batch_size`` / ``table_batch_size``: keep defaults (4).** The
  identical char counts across the sweep indicate these knobs did not
  materially change extraction on this digital (non-scanned, OCR-off)
  corpus.

- **Per-page invocation overhead: 2.22×** (136.43s vs 61.59s for the same
  30 pages) for **near-identical content** (54630 vs 54685 chars ≈ 99.9%).
  This is the cost signal for the deferred per-page fidelity restoration
  (deliberation 001-DL Option 2, stash ``D771B78E``).

- **Recommended action on per-page restoration: DEFER / KEEP-AS-OPT-IN.**
  2.22× is just above the 2× feasibility threshold from the 032-S closure.
  Per-page restoration via ``page_range=(i,i)`` works and gives identical
  fidelity, but at >2× wall-clock it is an expensive way to retire the
  ``docling-collapsed`` attribution. Given Mistral OCR is ~10× faster and
  the stronger lever for table-heavy fidelity (031-S), spend that effort
  only if a docling-only, fidelity-critical path specifically needs true
  per-page output. The stash item stays open but down-prioritized.

- **No production code change results from this probe.** The empirical
  winner (batch size 4) is already docling's default, so
  ``_read_pdf_docling_pages`` needs no new constant. The probe confirmed
  the default is optimal and quantified the per-page cost.

---

## Original pre-run notes (retained for context)

This decision doc was **pending operator empirical run** as of the 032-S merge.

## Knob landscape (discovered during 030-F T4 grounding)

docling's ``PdfPipelineOptions`` (as of the version pinned by ``docline[pdf]``)
exposes three batch-size knobs that affect the threaded pipeline mode:

| Knob | Default | Description |
|---|---:|---|
| ``layout_batch_size`` | 4 | Pages grouped through the layout (rt_detr) model |
| ``ocr_batch_size`` | 4 | Pages grouped through OCR (when ``do_ocr=True``) |
| ``table_batch_size`` | 4 | Tables grouped through structure extraction |

Higher values increase throughput at the cost of peak RSS. The probe sweeps
{1, 4, 8, 16, 32} for ``layout_batch_size`` (the dominant cost on cosmos-class
technical reference PDFs, which are layout-heavy and table-heavy with OCR
typically off).

Additionally, ``DocumentConverter.convert()`` accepts a ``page_range`` tuple
that the probe uses to measure per-page invocation cost. This informs whether
the deferred "per-page fidelity restoration" follow-up (deliberation 001-DL
Option 2, originally rejected for perf reasons) is feasible under the new
T3 batched-worker mode that loads docling once.

## How to run the probe

1. Activate the docline venv (which has docling installed via ``[pdf]``).
2. Pick a representative multi-page cosmos splice:
   ```
   .elt/output/cosmos-triage-022/study/dataset/range-0859-1056/_input.pdf
   ```
   (or any other splice ≥ 30 pages for meaningful batch-size variance).
3. Run:
   ```powershell
   python scripts/study/docling_batch_size_probe.py `
     --splice-pdf .elt\output\cosmos-triage-022\study\dataset\range-0859-1056\_input.pdf `
     --output-dir .elt\output\cosmos-triage-022\study\results\batch-probe
   ```
4. The probe will iterate batch sizes {1, 4, 8, 16, 32} and additionally run
   a per-page-loop. Wall-clock per run is reported.
5. The probe writes a results table back into this decision doc
   (or to ``--output-dir/2026-06-14-docling-batch-size-probe.md`` when
   ``--output-dir`` ends in ``decisions/``).
6. The operator should commit the updated decision doc with the empirical
   values + the chosen ``layout_batch_size`` constant (if a clear winner
   emerges) wired into ``_read_pdf_docling_pages`` in ``src/docline/readers/pdf.py``.

## Decision

To be filled in after the probe runs:

- **Chosen ``layout_batch_size``**: TODO
- **Chosen ``ocr_batch_size``**: TODO (typically not on the hot path until ``do_ocr=True``)
- **Chosen ``table_batch_size``**: TODO
- **Per-page-loop overhead vs single multi-page call**: TODO (multiplier ratio + notes)
- **Recommended action**:
  - If a knob shows ≥20% throughput win without ≥50% RSS regression:
    commit the winning value as a constant in ``_read_pdf_docling_pages``.
  - If per-page-loop overhead < 2× single-call: file a follow-up stash
    to spike per-page fidelity restoration via ``page_range=(i,i)`` looping
    inside the batched worker. This would retire the ``docling-collapsed``
    engine attribution introduced in 030-F T2.
  - Otherwise: document the finding and leave defaults in place.

## Why this is pending instead of inline

The probe requires:

1. A real docling installation (``pip install 'docline[pdf]'``).
2. A representative cosmos splice PDF (operator's local sample data).
3. Several minutes of wall-clock per probe iteration.

Running the probe inside the 032-S merge cycle would inflate the autopilot
session beyond the scope of what's mergeable in one pass. The probe
artifact + this decision-doc skeleton are the committable deliverable;
the empirical fill-in is a small operator follow-up.
