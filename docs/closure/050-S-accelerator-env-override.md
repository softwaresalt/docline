---
shipment: 050-S
title: "Closure record — DOCLINE_ACCELERATOR env override for docling device (048-F)"
status: verified
merge_sha: dc427aa
merged_pr: 132
---

## Scope delivered

Feature `048-F` adds an explicit `DOCLINE_ACCELERATOR` env var that pins
docling's compute device. It is the completable, verifiable slice of the GPU
acceleration stash item `3048007A`: docling already auto-detects CUDA/MPS/XPU
(verified against docling 2.97.0, `AcceleratorOptions.device` defaults to
`auto`), so this adds explicit control and a force-CPU escape hatch rather than
changing the default behavior.

| Task | Delivered |
|---|---|
| `048.002-T` | `src/docline/readers/pdf.py` — pure `_resolve_accelerator_device` (normalizes `auto`/`cpu`/`cuda`/`mps`/`xpu`, case-insensitive, trimmed; unset/blank/`auto` → `None` = no override), docling-backed `_accelerator_options_for` (maps a concrete device onto `AcceleratorOptions`, leaving `num_threads` at docling's default), new typed `PdfConfigError`, and constructor-injection of `accelerator_options` into `PdfPipelineOptions`. Resolved before the conversion `try` so an invalid value fails fast rather than being masked as a `PdfReadError`. README subsection documents the variable. |

## Verification

- Wired once in `_read_pdf_docling_pages`, so both the single-file CLI path and
  the batched docling worker (`docling_worker` delegates to the same reader)
  honor the variable — dual-interface parity from a single funnel point.
- Default path unchanged: unset or `auto` leaves docling's implicit
  auto-detection intact (no `accelerator_options` passed).
- `tests/readers/test_pdf_accelerator_env.py` (23 tests): resolver edge cases,
  options-builder device mapping, and end-to-end wiring (env → resolve → build →
  constructor injection) via a faked `DocumentConverter` that skips the OCR
  model load.
- All four gates pass: `ruff check .`, `pyright src/` (0 errors), `pytest`
  (1443 passed, 6 skipped), `ruff format --check .`.

## Copilot review

One finding: the new test module sat at the `tests/` root instead of the
`src/`-mirroring `tests/readers/`. Addressed in `0c9e851` (`git mv` to
`tests/readers/test_pdf_accelerator_env.py`; absolute imports unaffected,
23/23 still pass). Thread resolved. No unresolved Copilot threads at merge.

## Deferred

The GPU throughput benchmark vs a CPU baseline (the remainder of `3048007A`)
needs a GPU-equipped host and stays deferred. Stash `3048007A` is annotated
accordingly.
