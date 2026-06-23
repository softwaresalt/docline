---
title: Docling worker subprocess confirmation — 6E6754D4 root-cause closure
date: 2026-06-22
status: confirmed
kind: investigation
bug: 6E6754D4
supersedes_hypothesis: "docling convert-time error inside the worker subprocess"
references:
  - docs/closure/033-S-worker-observability-and-batched-revert.md
  - docs/closure/034-S-batched-crash-recovery.md
  - src/docline/_tools/docling_worker.py
  - src/docline/readers/pdf.py
  - src/docline/process/pdf_triage.py
  - src/docline/process/pdf_batch.py
---

# Docling worker subprocess confirmation (6E6754D4)

## Question

Bug `6E6754D4` carried two competing root-cause hypotheses for the
2026-06-16 cosmos run that produced `subprocess_fallback_count=86/86`
(zero docling, all heuristic):

1. **033-S hypothesis** — batched-mode memory exhaustion. With
   `use_batched_worker=True` (the 032-S default), all 86 coalesced ranges
   (1,818 pages) ran in **one** long-lived subprocess. Torch working set
   accumulates because PyTorch's CPU allocator does not reliably return
   memory to the OS, so the process was OOM-killed and every range fell
   back to heuristic.
2. **Stash hypothesis** — a docling **convert-time** error inside the
   worker subprocess specifically (model-load/offline, API drift, or a
   per-page crash), with the real exception discarded by the pre-033-S
   observability gap.

The entry called for a single-range worker diagnostic on the 033-S build
to discriminate between them.

## Method

Ran the exact diagnostic the entry specified against the real corpus
(`.elt/data/cosmosdb/azure-cosmos-db.pdf`, 3,426 pages):

```text
.venv\Scripts\python.exe -m docline._tools.docling_worker \
  logs\docling-diag\splice1.pdf logs\docling-diag\out1.md 2> err1.txt
```

`splice1.pdf` is page index 10 of the cosmos PDF, spliced with
`pypdf.PdfWriter` exactly as `pdf_triage` builds its ranges.

## Result

The single-range worker **succeeded**:

- Exit `0`; `out1.md` is a valid `schema_version=1` envelope (3,081 bytes).
- Real content extracted — an Azure Cosmos DB vs. DocumentDB comparison
  table rendered as Markdown, identical in character to the in-process
  T4 probe.
- No exception, no `error` field, no diagnostic on stderr.

[!IMPORTANT]
docling converts a cosmos page cleanly **inside the worker subprocess**.
The stash hypothesis (a docling convert-time error) is refuted. The 033-S
root cause — batched-mode memory exhaustion — stands, and the shipped fix
(`use_batched_worker` defaults to `False` in both `pdf_batch` and
`pdf_triage` since 033-S) is the correct functional remedy. Per-chunk mode
runs each range in its own subprocess, so torch memory is reclaimed
between ranges and the OOM cannot recur.

## Disposition

`6E6754D4` is **resolved**. The fix is in `main`; this single-range
diagnostic is the operator-confirmation re-run the 033-S closure deferred,
performed at proportionate scale (a full 3,426-page re-run is hours of CPU
inference and is unnecessary to discriminate the hypotheses).

## New finding — OCR runs by default on native-text PDFs

The worker stderr exposed RapidOCR (onnxruntime) loading three Chinese
PP-OCRv4 ONNX models on a native-text page:

```text
[INFO] [RapidOCR] Using engine_name: onnxruntime
[INFO] [RapidOCR] ... ch_PP-OCRv4_det_mobile.onnx
[INFO] [RapidOCR] ... ch_ppocr_mobile_v2.0_cls_mobile.onnx
[INFO] [RapidOCR] ... ch_PP-OCRv4_rec_mobile.onnx
```

`_read_pdf_docling_pages` (src/docline/readers/pdf.py) builds
`PdfPipelineOptions` without setting `do_ocr`, so it inherits docling's
default of **`True`**. OCR therefore executes on every page of a
native-text corpus that needs none, dominating per-page wall time (a
single page including cold start took several minutes).

Two consequences:

- This is the likely driver of the ~247-minute cosmos CPU baseline and a
  contributing amplifier of the batched-mode memory pressure 033-S
  identified (OCR working set stacks on top of layout/table working set).
- Stash entry `4CA80776` ("enable `do_ocr=True` for scanned PDFs") is
  built on a false premise — OCR is already on. The real work is the
  inverse: make OCR **conditional** (off for native-text pages, on only
  when a page lacks an extractable text layer), which needs deliberation
  because a blanket disable would regress genuine scanned-PDF handling.

Filed as a new stash entry linked to `4CA80776`.
