---
title: Plan — Shipment A runtime safety primitives
date: 2026-06-05
shipment: 018-S
feature: 019-F
rca: docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md
stashes: 1D945AB5, 4B913619, 15ADD215, C1EB2C6A, CB89952B
---

# Plan — Shipment A: runtime safety primitives

## Goal

Introduce the runtime primitives that make subsequent PDF-splitter + batch shipments safe to enable on the 2026-06-04 host class (i7-4700MQ, 32 GB RAM, no usable GPU). Specifically:

* Adaptive `ResourceBudget` probe (RAM / pagefile / GPU detection)
* Pre-flight size gate that consults the probe before invoking docling
* Broader auto-fallback exception net so a single hostile PDF cannot abort a batch
* Probe-derived PyTorch / BLAS thread caps applied before docling imports
* Side fix: CWD-isolate the manifest-parity test that hangs on a populated `.elt/staging/`

## Constitution check

| Principle | Compliance |
|---|---|
| I — Safety-first Python | All new code typed, exceptions custom-typed via `DoclineError` lineage; no bare except |
| II — TDD non-negotiable | RED tests for each module before implementation; explicit RED→GREEN commit pairs |
| III — Workspace isolation | New module under `src/docline/runtime/`; no out-of-workspace IO |
| VI — Single responsibility | psutil already in dep graph (used by other tests); torch is already an extra |
| X — Context efficiency | Probe returns a frozen dataclass query result, not raw psutil snapshots |

## Module placement

| New / changed | Purpose |
|---|---|
| `src/docline/runtime/__init__.py` (new) | Package marker |
| `src/docline/runtime/resource_probe.py` (new) | `ResourceBudget` frozen dataclass + `probe()` |
| `src/docline/readers/pdf.py` (modified) | Wire probe into `_resolve_layout_engine`, widen exception net at :512, set thread caps before docling import |
| `tests/runtime/__init__.py` (new) | Test package marker |
| `tests/runtime/test_resource_probe.py` (new) | Parameterized RAM tiers, pagefile override, GPU paths (mocked) |
| `tests/runtime/test_thread_caps.py` (new) | Verify OMP/MKL/OPENBLAS env vars set before docling import |
| `tests/readers/test_pdf_engine_resolution.py` (extended) | New tests for probe-gated routing + broader exception net |
| `tests/parity/test_manifest_parity.py` (modified) | Wrap `test_cli_process_no_staging_dir_returns_1` and neighbors in `monkeypatch.chdir(tmp_path)` |

## API contract — `resource_probe`

```python
from dataclasses import dataclass
from typing import Literal

AcceleratorDevice = Literal["cpu", "cuda", "mps"]

@dataclass(frozen=True)
class ResourceBudget:
    available_ram_gb: float
    total_ram_gb: float
    logical_cpus: int
    pagefile_pressure: bool
    accelerator_device: AcceleratorDevice
    gpu_name: str | None
    gpu_vram_gb: float | None
    gpu_compute_capability: tuple[int, int] | None
    recommended_concurrency: int
    recommended_docling_max_pages: int
    recommended_docling_max_mb: int
    serialize_docling: bool
    omp_thread_count: int

def probe() -> ResourceBudget: ...
def should_use_docling(budget: ResourceBudget, *, file_size_mb: float, page_count: int | None) -> tuple[bool, str]: ...
```

## Decision matrix (CPU mode)

| available_ram_gb | concurrency | max_pages | max_mb | serialize | omp_threads |
|---:|---:|---:|---:|---|---:|
| < 4 | 1 | 0 | 0 | n/a | 1 |
| 4 – 8 | 1 | 25 | 10 | True | 1 |
| 8 – 16 | 1 | 50 | 20 | True | 2 |
| 16 – 32 | 2 | 75 | 30 | False | 2 |
| > 32 | min(cpu_count // 2, 4) | 100 | 40 | False | max(2, cpu_count // 4) |

Pagefile pressure (psutil.swap_memory().percent > 50) forces `serialize_docling=True` and halves `max_pages`.

GPU gate (all required for `cuda`): torch importable, `is_available()`, `get_device_capability(0) >= (5, 0)`, `mem_get_info(0)[0] >= 4 GB`, `torch.zeros(1, device='cuda')` succeeds. `DOCLINE_GPU_FORCE=1` overrides the capability gate for testing.

## Task decomposition (6 tasks)

| Task | Title | Files |
|---|---|---|
| 019.001-T | TDD RED + GREEN — resource_probe module | tests/runtime/*, src/docline/runtime/* |
| 019.002-T | Wire pre-flight size gate into _resolve_layout_engine | src/docline/readers/pdf.py, tests/readers/test_pdf_engine_resolution.py |
| 019.003-T | Broaden auto-fallback exception net | src/docline/readers/pdf.py, tests/readers/test_pdf_engine_resolution.py |
| 019.004-T | Probe-derived PyTorch thread caps | src/docline/readers/pdf.py, tests/runtime/test_thread_caps.py |
| 019.005-T | Fix CWD isolation in test_manifest_parity | tests/parity/test_manifest_parity.py |
| 019.006-T | Closure document | docs/closure/018-S-runtime-safety-primitives.md |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| psutil API drift on Windows | Probe wraps each psutil call in try/except returning conservative defaults |
| torch import probe is slow | Lazy: probe only attempts torch import; mocked in all tests |
| Existing tests assume `_resolve_layout_engine` is pure dependency-probe | New behavior is opt-in via a new flag arg; defaults preserve current semantics for the existing test set |
| Thread cap env var leaks across tests | Tests use monkeypatch.setenv / delenv; module-level apply is idempotent |
| Pagefile pressure on CI runners | CI runners typically have low pagefile usage; conservative thresholds avoid false positives |
