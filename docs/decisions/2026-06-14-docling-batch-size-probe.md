---
title: docling batch-size probe results
date: 2026-06-14
status: pending-empirical
shipment: 032-S
feature: 030-F
task: 030.004-T
references:
  - scripts/study/docling_batch_size_probe.py
  - src/docline/readers/pdf.py
  - docs/decisions/2026-06-08-extraction-strategy-study.md
---

# docling batch-size probe — pending empirical run

This decision doc is **pending operator empirical run** as of the 032-S merge.
The probe script (``scripts/study/docling_batch_size_probe.py``) is committed
and runnable; the empirical values below will be filled in by the operator
post-merge when a representative cosmos splice PDF is available and docling
is installed on the running host.

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
