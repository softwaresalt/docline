---
date: 2026-07-01
pr: 112
task: 040.002-T
category: windows-venv-redirector-tree-rss
keywords: [psutil, memory_info, rss, peak-memory, subprocess, Popen, Windows, venv, redirector, shim, children, process-tree, docling, ocr, calibration, NoSuchProcess]
confidence: high
evidence: PR #112 / task 040.002-T — OCR memory calibration run reported a uniform ~4.2 MB peak for every docling OCR subprocess; direct-child RSS was the venv shim, not the worker
---

# Sum the process tree, not the direct child, when sampling subprocess peak RSS on Windows venvs

## Problem

`scripts/study/ocr_memory_calibration.py --run` measured docling OCR peak
memory by sampling the spawned worker's resident set size:

```python
proc = subprocess.Popen(cmd, ...)          # python -m docline._tools.docling_worker
ps = psutil.Process(proc.pid)
peak = max(peak, ps.memory_info().rss / 1_000_000.0)
```

Every run reported ~4.2 MB, regardless of render scale, page size, or pages
per group. The fitted cost model was degenerate (base ≈ 4 MB, slope ≈ 0). A
standalone smoke test that summed children showed the true peak was ~1135 MB
for a single page.

## Root Cause

On Windows, `.venv\Scripts\python.exe` is a thin **redirector shim** that
re-execs the base interpreter as a **child process**. So `proc.pid` is the
shim (~4 MB RSS), and the entire docling + OCR working set (~1.1–1.9 GB) lives
in the child. Sampling only `proc.pid` measures the launcher, not the work.

`psutil.Process(pid).memory_info().rss` is correct — it just points at the
wrong process. The direct-child assumption silently holds on Linux/macOS (no
shim) and silently fails on Windows venvs.

## Fix

Sum RSS across the whole process tree (`proc` + `proc.children(recursive=True)`)
each sample, via a testable helper:

```python
def _tree_rss_mb(proc, *, skip_errors=()):
    total = 0.0
    try:
        total += proc.memory_info().rss / 1_000_000.0
        children = proc.children(recursive=True)
    except skip_errors:
        return total
    for child in children:
        try:
            total += child.memory_info().rss / 1_000_000.0
        except skip_errors:   # a descendant that exits mid-walk is skipped
            continue
    return total
```

`measure()` calls `_tree_rss_mb(ps, skip_errors=(psutil.Error,))`. On hosts
with no shim the descendant set is empty and it reduces to the direct RSS, so
the fix is portable.

## Approaches that did NOT work

* **Reading only `proc.pid` RSS** — measures the redirector shim on Windows
  venvs (~4 MB); the docling child is invisible.
* **Bare tree walk with `except psutil.Error: break` in the caller** — a
  descendant exiting between the `children()` snapshot and its `memory_info()`
  read raises `psutil.NoSuchProcess`, which aborted the whole sampling loop and
  under-reported the peak. Fixed by skipping the single dead process instead
  (Copilot review on PR #112).

## Rule

* Any subprocess peak-memory sampler that may run under a Windows venv MUST sum
  the process tree, not the directly spawned PID. Treat a suspiciously tiny,
  scale-invariant RSS (single-digit MB for a heavy workload) as the tell-tale
  of the redirector-shim trap.
* Keep the tree-walk helper psutil-free and unit-testable by injecting the
  exception types to swallow (`skip_errors`) rather than importing psutil at
  module top; pass `(psutil.Error,)` from the psutil-owning caller.
* Guard the per-descendant read so a normal mid-walk child exit is skipped, not
  fatal to the sample.
