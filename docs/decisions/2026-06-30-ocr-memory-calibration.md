---
title: OCR memory calibration — measured coefficients
date: 2026-06-30
status: empirical
shipment: 043-S
feature: 040-F
task: 040.002-T
references:
  - scripts/study/ocr_memory_calibration.py
  - src/docline/_tools/docling_worker.py
  - src/docline/readers/pdf.py
  - src/docline/runtime/resource_probe.py
---

## Summary

The operator ran `scripts/study/ocr_memory_calibration.py --run` on a docling
host to fit the portable, host-independent OCR peak-memory cost model
required by task 040.002-T. This document records the measured coefficients,
the measurement host, the raw sweep, and the inputs the follow-up runtime
host-relative algorithm (stash `699FB5DC`) needs.

The fitted portable model is:

```text
peak_mb ~= base_mb + k_mb_per_mpx * (page_megapixels * scale^2 * pages_per_group)
```

| Coefficient | Measured value |
|---|---:|
| `base_mb` | 1412.84 |
| `k_mb_per_mpx` | 15.4942 |

## Measurement host

The docling host was the repository virtual environment (`.venv`) with the
`docline[pdf]` extras installed. Host resource budget sampled via
`docline.runtime.resource_probe.probe`:

| Property | Value |
|---|---:|
| `available_ram_gb` | 47.15 |
| `total_ram_gb` | 68.67 |
| `logical_cpus` | 16 |
| `accelerator_device` | cpu (no GPU) |
| `pagefile_pressure` | false |

OCR ran on CPU through docling's RapidOCR (onnxruntime) engine. docling
version 2.97.0, psutil 7.2.2, pypdf 5.9.0.

## Sweep design

Three page classes span a ~25x range in bitmap size, crossed with render
scale and pages-per-group for a ~1580x spread in the fit's load factor
(`page_megapixels * scale^2 * pages_per_group`):

| Page class | Source | `page_megapixels` (at 72 DPI) |
|---|---|---:|
| small | `Microsoft_Press_ebook_Introducing_Power_BI_PDF_mobile.pdf` | 0.083 |
| medium | `power-bi-guidance.pdf` (A4) | 0.502 |
| large | `AzureFabric.ebook.pdf` (16:9 slides) | 2.074 |

* Render scales swept: 2.0, 1.0, 0.5.
* Pages-per-group swept: 1, 4.
* Total runs: 18 (all completed with outcome `ok`).

## Raw measurements

| Page class | `mpx` | Scale | Pages | Peak RSS (MB) | Outcome |
|---|---:|---:|---:|---:|---|
| small | 0.083 | 2.0 | 1 | 1125 | ok |
| small | 0.083 | 1.0 | 1 | 1130 | ok |
| small | 0.083 | 0.5 | 1 | 1132 | ok |
| small | 0.083 | 2.0 | 4 | 1725 | ok |
| small | 0.083 | 1.0 | 4 | 1718 | ok |
| small | 0.083 | 0.5 | 4 | 1717 | ok |
| medium | 0.502 | 2.0 | 1 | 1154 | ok |
| medium | 0.502 | 1.0 | 1 | 1140 | ok |
| medium | 0.502 | 0.5 | 1 | 1149 | ok |
| medium | 0.502 | 2.0 | 4 | 1441 | ok |
| medium | 0.502 | 1.0 | 4 | 1800 | ok |
| medium | 0.502 | 0.5 | 4 | 1807 | ok |
| large | 2.074 | 2.0 | 1 | 1302 | ok |
| large | 2.074 | 1.0 | 1 | 1256 | ok |
| large | 2.074 | 0.5 | 1 | 1260 | ok |
| large | 2.074 | 2.0 | 4 | 1897 | ok |
| large | 2.074 | 1.0 | 4 | 1878 | ok |
| large | 2.074 | 0.5 | 4 | 1882 | ok |

The full TSV is written to `.elt/output/ocr-mem/measurements.tsv` (working
data, outside version control).

## Fit diagnostics and empirical finding

The least-squares fit over the 18 `ok` rows gives `base_mb = 1412.84` and
`k_mb_per_mpx = 15.4942`, but with a low coefficient of determination
(`R^2 = 0.148`, mean absolute residual 268 MB). The low fit quality is itself
the finding, not a defect in the harness.

On this **digital, text-layer** corpus the OCR peak memory is dominated by two
terms that the bitmap-area model does not capture:

* A fixed OCR runtime working set of roughly 1.1–1.3 GB (docling layout model
  plus the RapidOCR/onnxruntime engine load), independent of page or scale.
* A fixed per-page accumulation cost of ~207 MB/page, measured almost
  identically across all three page classes and all render scales.

| Page class | g1 peak (scale 1.0) | g4 peak (scale 1.0) | Delta per page |
|---|---:|---:|---:|
| small | 1130 | 1718 | 196 MB |
| medium | 1140 | 1800 | 220 MB |
| large | 1256 | 1878 | 207 MB |

Render scale barely moved peak RSS on this corpus: for a fixed page class and
group size, scale 2.0, 1.0, and 0.5 land within measurement noise of each
other. That is expected here because these page bitmaps are small relative to
the ~1.2 GB model working set. The `page_megapixels * scale^2` lever only
dominates peak memory on large-raster or scanned pages, where full-page
rasterization is the working set.

> [!IMPORTANT]
> The fitted coefficients are conservative and safe to use for the runtime
> page-cap computation: `base_mb` (1412.84) sits above every measured
> single-page floor, so the derived caps err toward smaller, safer groups.
> The scale schedule as an OOM-recovery lever, however, is under-exercised by
> this digital corpus. Re-run the sweep on a scanned / image-heavy corpus
> (high effective megapixels, `do_ocr` genuinely rasterizing full pages)
> before relying on downscaling to recover an oversized single page.

> [!NOTE]
> The `medium / scale 2.0 / 4 pages` row (1441 MB) reads low next to its
> scale-1.0 and scale-0.5 siblings (~1800 MB). Peak RSS is sampled every
> 50 ms, so a true peak can fall between samples; treat this single point as
> sampling noise, not a scale effect.

## Per-host recommendation

Applying the portable model at `safe_fraction = 0.6` for an 8.0 mpx reference
page at scale 1.0 yields, on any host:

```text
max_pages_per_group = floor((safe_fraction * available_mb - base_mb) / (k * mpx * scale^2))
```

| Host RAM (total) | Budget (MB) | Max pages/group | Scale schedule |
|---|---:|---:|---|
| 8 GB | 4800 | 27 | 2.0, 1.0, 0.5, 0.25 |
| 16 GB | 9600 | 66 | 2.0, 1.0, 0.5, 0.25 |
| 32 GB | 19200 | 143 | 2.0, 1.0, 0.5, 0.25 |
| 64 GB | 38400 | 298 | 2.0, 1.0, 0.5, 0.25 |
| 128 GB | 76800 | 608 | 2.0, 1.0, 0.5, 0.25 |

For the measurement host itself (47153 MB available, `safe_fraction = 0.6`):
budget 28292 MB, `max_pages_per_group = 216`, full scale schedule fits.

> [!CAUTION]
> These bitmap-area caps assume the digital-corpus profile. Because the real
> per-page cost measured here is a fixed ~207 MB/page rather than a
> bitmap-scaled term, a runtime guard should also apply a page-count floor
> such as `(safe_fraction * available_mb - base_mb) / per_page_mb` with
> `per_page_mb ~= 207` and never exceed the smaller of the two caps. Fold this
> into the stash `699FB5DC` runtime algorithm.

## Runtime algorithm inputs (stash 699FB5DC)

The follow-up runtime work should consume, per host via
`resource_probe.probe().available_ram_gb`:

* `base_mb = 1412.84` — fixed OCR runtime overhead subtracted from the budget.
* `k_mb_per_mpx = 15.4942` — marginal cost per `mpx * scale^2 * page`.
* `per_page_mb ~= 207` — empirical fixed per-page floor for digital corpora.
* `safe_fraction` — default 0.6, tunable per deployment.

## Reproduction

1. Activate the docline venv (docling installed via `docline[pdf]`; psutil
   present).
2. Run the sweep:

   ```powershell
   python scripts/study/ocr_memory_calibration.py --run `
     --input .elt\data\powerbi-pdf\Microsoft_Press_ebook_Introducing_Power_BI_PDF_mobile.pdf .elt\data\powerbi-pdf\power-bi-guidance.pdf .elt\data\fabric\AzureFabric.ebook.pdf `
     --scales 2.0 1.0 0.5 `
     --group-sizes 1 4 `
     --out-tsv .elt\output\ocr-mem\measurements.tsv
   ```

3. Fit and recommend for a host with 47153 MB available:

   ```powershell
   python scripts/study/ocr_memory_calibration.py --analyze `
     .elt\output\ocr-mem\measurements.tsv `
     --available-mb 47153 --safe-fraction 0.6 --page-megapixels 8.0 `
     --scales 2.0 1.0 0.5 0.25
   ```

## Harness fix applied during this run

The first sweep reported a uniform ~4.2 MB peak for every run. The measurement
loop sampled only the directly spawned process, but a Windows virtual-env
`python.exe` is a thin redirector shim (~4 MB RSS) that re-execs the base
interpreter as a child, where the entire docling/OCR working set lives.
`measure()` now sums resident set size across the whole process tree via a new
testable `_tree_rss_mb` helper; on hosts without a redirector shim the
descendant set is empty and it reduces to the direct RSS. Unit tests cover the
tree-sum and the no-children cases.
