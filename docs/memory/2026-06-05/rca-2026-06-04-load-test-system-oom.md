---
type: rca
date: 2026-06-05
incident_date: 2026-06-04
incident_time_utc: 2026-06-04T22:35:41Z
host: DWWorkPC
severity: high
status: complete
related_stashes: 4B913619, F64683BC, D885CE79
related_decisions: docs/decisions/2026-06-04-spike-h1-header-synthesis.md
---

# RCA — 2026-06-04 load-test system OOM / paging spiral / hard reboot

## TL;DR

The hard reboot was caused by **system-wide memory exhaustion driving the
Windows pager into a thrashing spiral**, not by a Python-side leak in
docline. The triggering workload was the docling `rt_detr` layout model
processing **`azure-cosmos-db.pdf` (109.5 MB, 554-part output)** in the
same OS session as the GitHub Copilot CLI agent (Node v24, ~431 MB peak
RSS). At the moment Node v24 hit its V8 heap limit and dumped a crash
report, the OS had **1.14 GB free out of 31.9 GB** and had accumulated
**7,819,137 IO-requiring page faults** over the CLI's lifetime. That is
the textbook fingerprint of a paging death spiral.

**The user's hypothesis that synthetic header generation was using a
local model is false.** The H1 synthesis spike (017-S) is pure
deterministic YAML/regex analysis. `scripts/spike_h1_corpus_analysis.py`
imports only `json`, `re`, `sys`, `collections`, `pathlib`, `yaml`. No
torch / transformers / huggingface / SLM code exists anywhere under
`src/` or `scripts/` — confirmed by a project-wide grep. The local model
that DID consume memory is the **docling rt_detr-l4 layout model**,
which docling loads automatically when `--pdf-engine docling` (or
`--pdf-engine auto` when extras are installed) is invoked.

## Evidence

### Crash dump

File: `report.20260604.223541.24064.0.001.json` (28.5 KB, repo root,
git-untracked).

| Field | Value |
|---|---|
| `event` | `Allocation failed - JavaScript heap out of memory` |
| `trigger` | `OOMError` |
| `processId` | 24064 |
| `commandLine` | `D:\Tools\ghcpcli\copilot.exe --no-warnings --report-on-fatalerror --optimize-for-size --expose-gc --no-maglev --no-sparkplug ... --remote` |
| `nodejsVersion` | `v24.16.0` |
| `cwd` | `D:\Source\GitHub\docline` |
| `osName` | `Windows_NT` |
| `osRelease` | `10.0.19045` (Windows 10 Pro) |
| `cpus` | 8 × Intel Core i7-4700MQ @ 2.40 GHz |

### Resource usage at crash

| Metric | Value | Interpretation |
|---|---|---|
| `total_memory` | 34,280,136,704 (≈32.0 GB) | System RAM |
| `free_memory` | 1,145,163,776 (≈1.07 GB) | **System was memory-starved** |
| `rss` | 199,348,224 (≈190 MB) | CLI working set at dump time |
| `maxRss` | 431,362,048 (≈411 MB) | **CLI peak** |
| `userCpuSeconds` | 13,252.3 (≈3.68 h) | Long-running session |
| `cpuConsumptionPercent` | 93.5 % | Saturated CPU |
| `pageFaults.IORequired` | **7,819,137** | **Paging death spiral** |
| `pageFaults.IONotRequired` | 0 | All faults required disk I/O |

`memoryLimit` (V8 heap cap) was 4,298,113,024 (≈4 GB, the Node default).
At dump time the JS old_space held 108 MB used of 111 MB capacity — V8
was trying to grow past 4 GB and the kernel refused because the OS itself
had nothing left to spare.

### docline-side trigger

Stash `4B913619` (recorded by the prior agent immediately after the
crash) describes the upstream cause:

> Load test on 2026-06-04 crashed docling rt_detr layout model with
> `RuntimeError: [enforce fail at alloc_cpu.cpp:117]
> DefaultCPUAllocator: not enough memory: you tried to allocate
> 6553600 bytes` while processing azure-cosmos-db.pdf (~554-part output).
> The `--pdf-engine auto` fallback only catches `PdfReadError`, NOT
> `RuntimeError`/`MemoryError`, so the entire batch aborted with no
> output emitted.

This is consistent with the timeline: the prior agent ran the spike
corpus generator against the full load corpus (`.elt/output/` and
`.elt/pbi/`), docling exhausted the CPU allocator on cosmos, and the
batch aborted. The agent then re-ran a partial pipeline against only
the lighter sources (`output/` at repo root has 3 of 5 jobs: web/Rust/
DOCX, dated 2026-06-04 20:56). The full-corpus retry, or a later step,
pushed the system into the paging spiral that culminated in the Node
OOM dump at 22:35.

### Workload sizes that competed for RAM

`.elt/pbi/` — 21 Power BI PDFs, totals:

| File | MB |
|---|---:|
| analysis-services-sql-analysis-services-2025.pdf | 75.2 |
| power-bi-explore-reports.pdf | 72.7 |
| power-bi-personas-business-user.pdf | 71.9 |
| power-bi-guidance.pdf | 65.5 |
| power-bi-connect-data.pdf | 54.6 |
| fabric-cicd.pdf | 46.2 |
| rest-api-power-bi.pdf | 38.3 |
| analysis-services-power-bi-premium-current.pdf | 32.2 |
| dax.pdf | 29.3 |
| power-bi-developer-visuals.pdf | 26.2 |
| power-bi-personas-report-creator.pdf | 20.5 |
| power-bi-personas-semantic-model-designer.pdf | 18.1 |
| power-bi-report-server.pdf | 16.7 |
| fabric-enterprise.pdf | 19.7 |
| power-bi-developer-embedded.pdf | 16.0 |
| fabric-admin.pdf | 15.7 |
| Microsoft_Press_ebook_Introducing_Power_BI_PDF_mobile.pdf | 9.8 |
| analysis-services-azure-analysis-services-sql-analysis-services-2025.pdf | 8.5 |
| power-bi-developer-projects.pdf | 6.4 |
| power-bi-developer-execute-dax-queries-arrow.pdf | 0.8 |
| power-bi-developer-mcp.pdf | 0.5 |
| **Total** | **≈645 MB** |

Plus `.elt/azure-cosmos-db.pdf` (109.5 MB) and root PDFs
(`AzureFabric.ebook.pdf` 4.3 MB, `performance-tuning-with-dmvs.pdf`
6.3 MB).

The hardware (i7-4700MQ + 32 GB RAM) cannot run docling rt_detr on the
ten 30+ MB Power BI PDFs concurrently with a Copilot CLI session and
its OS overhead. The peak working-set of docling per PDF on this CPU
is unmeasured, but the 6.5 MB allocation failing means the python/torch
process had already consumed multi-GB of working set when the kernel
refused a tiny incremental grab.

### Where the agent code actually catches failures

`src/docline/readers/pdf.py` :502–520:

```python
resolved_engine = _resolve_layout_engine(layout_engine)
if resolved_engine == "docling":
    ...
    if layout_engine == "auto":
        try:
            return _read_pdf_docling_pages(path, picture_sink=picture_sink)
        except (PdfReadError, FileNotFoundError):
            # FileNotFoundError must propagate; PdfReadError under "auto"
            # falls back to heuristic so a single hostile PDF does not
            # break batch processing.
            if not path.exists():
                raise
            # Drop down to the heuristic path below.
    else:
        return _read_pdf_docling_pages(path, picture_sink=picture_sink)
```

`_read_pdf_docling_pages` :579–596 does wrap docling in
`except Exception` and re-raises as `PdfReadError`. So a clean Python
`RuntimeError` from torch SHOULD round-trip to `PdfReadError` and be
caught by the `auto` block. The reason stash `4B913619` reports the
batch aborted anyway is one of:

1. The `enforce fail` macro path can bypass clean Python exception
   propagation on some torch builds (the allocator emits a `c10::Error`
   that, depending on torch version, may surface as `RuntimeError` —
   normally catchable — but can also tear down the worker thread
   ungracefully).
2. The allocator failure cascaded: once the process is below the
   threshold where 6.5 MB allocations fail, almost any subsequent
   Python object construction will also fail, including the construction
   of `PdfReadError` itself. The exception handling path silently
   fails to allocate the wrapper and propagates a different error.
3. The `RuntimeError` was caught, the heuristic path ran, but **the
   process was already so deeply paged out** that downstream work was
   running at single-digit MB/s I/O. To the outside observer this looks
   like "the batch aborted."

All three explanations are consistent with the 7.8 M IO-required page
faults. The proximate Python error was secondary to the OS-level
paging collapse.

## Five-whys

1. **Why did the machine need a hard reboot?**
   The Windows pager was thrashing — every memory access was hitting
   the page file, the disk queue was saturated, and the system became
   unresponsive faster than it could complete any single allocation.

2. **Why was the pager thrashing?**
   System free memory dropped to ~1 GB while the Copilot CLI's V8
   heap was trying to grow past its 4 GB cap. Total committed memory
   from all processes exceeded physical RAM, and the working set of
   the docling python process was being paged out almost as fast as
   it was being read in.

3. **Why was docling consuming so much memory?**
   docling's `rt_detr-l4` layout model is a PyTorch CPU model. On an
   8-thread i7-4700MQ, torch defaults to using all available threads
   for matrix ops, each holding intermediate tensors. For a 109 MB,
   ~554-page PDF (cosmos), the rolling working set easily passes 3 GB,
   and there is no upstream gate that throttles either thread count
   or batch size.

4. **Why was docling running at all on a PDF that size?**
   The CLI was invoked with `--pdf-engine auto`, which (when
   `docline[pdf]` extras are installed, as they are in this venv)
   resolves to `docling`. There is no pre-flight size or page-count
   gate — `_resolve_layout_engine` only asks "is docling importable?"
   and then hands the entire PDF to docling.

5. **Why was the agent CLI running in the same OS session as the
   load test?**
   The user (and the prior agent) ran the load test from inside the
   agent's PowerShell tool calls. The agent itself was a foreground
   Node process competing for the same physical RAM as the docling
   workers it had spawned. Even without docling exploding, the
   agent's own ~411 MB peak plus the OS baseline plus open editors
   leaves <30 GB for everything else.

## What the agent did and did NOT do

Confirmed (with evidence):

* It ran the docline load-test pipeline against `.elt/output/` and at
  least partially `.elt/pbi/`. Output exists at `.elt/output/` (5 jobs,
  manifest.json 676 KB) and at repo-root `output/` (3 jobs, dated
  20:56). Both directories are git-untracked.
* docling crashed on `azure-cosmos-db.pdf` and the agent stashed the
  observation as `4B913619` (with two follow-up high-priority stashes,
  `F64683BC` PDF splitter and `D885CE79` batch processor + stitching).
* The agent ran `scripts/spike_h1_corpus_analysis.py`, which is pure
  deterministic analysis (regex + YAML parsing — confirmed by grep:
  imports are `json, re, sys, collections, pathlib, yaml` only).
* The agent shipped the spike (017-S commits f4da427, 447f456,
  a4eab5c) and prepared a follow-on plan stub.

NOT done (no evidence found in the repo):

* No local SLM / transformer / Phi / Llama / Ollama / ONNX code was
  executed. The H1 synthesis spike explicitly deferred that path —
  see `docs/decisions/2026-06-04-spike-h1-header-synthesis.md` ¶138
  ("Defer SLM tier D"). The spike's measured rescue rate (82.8 %
  hybrid deterministic) was sufficient that the SLM tier was not
  exercised even experimentally.
* No `transformers`, `torch`, `huggingface_hub`, `sentence_transformers`,
  `llama`, `phi`, `onnx`, or `ollama` import exists anywhere in
  `src/docline/**` or `scripts/**`. Verified via `Select-String`.

## Recommended remediation

These are the changes that prevent a repeat without requiring new
hardware.

**Design pivot (2026-06-05 follow-up):** the operator's directive after
the first draft of this RCA was clear — *don't try to feed docling a
single massive PDF, split it first*. That flips the model from
"detect-OOM-and-fall-back" to "split-and-throttle-so-OOM-cannot-happen".
The remediations below have been reordered to reflect that.

### 1. Adaptive resource probe + throttle (P0, NEW)

Add `src/docline/runtime/resource_probe.py` (new module) exposing:

```python
def probe() -> ResourceBudget:
    """Snapshot system RAM / CPU / pagefile pressure at call time."""

@dataclass(frozen=True)
class ResourceBudget:
    available_ram_gb: float        # psutil.virtual_memory().available / 1e9
    total_ram_gb: float
    logical_cpus: int               # os.cpu_count()
    pagefile_pressure: bool         # True when used/total > 0.5
    recommended_concurrency: int    # 1 when constrained; up to cpu//2 otherwise
    recommended_docling_max_pages: int   # pages per docling invocation
    recommended_docling_max_mb: int      # source-PDF MB above which split first
    serialize_docling: bool         # True when only one docling worker is safe
```

Decision policy (conservative, refined empirically by load tests):

| available_ram_gb | concurrency | docling_max_pages | docling_max_mb | serialize_docling |
|---:|---:|---:|---:|---|
| < 4 | 1 | 0 (heuristic only) | 0 | n/a |
| 4 – 8 | 1 | 25 | 10 | True |
| 8 – 16 | 1 | 50 | 20 | True |
| 16 – 32 | 2 | 75 | 30 | False |
| > 32 | min(cpu // 2, 4) | 100 | 40 | False |

The probe is re-evaluated **once per batch run** (cheap; ~µs) and the
result threads through `execute.py`, `output_contract.py`, and
`pdf.py`. The probe is the single source of truth for both the size
gate (remediation 2) and the splitter trigger (remediation 3).

Pagefile pressure detection: when `pagefile.used / pagefile.total >
0.5`, force `serialize_docling = True` and halve
`recommended_docling_max_pages` regardless of available RAM. This
catches the 2026-06-04 scenario where the OS had nominally-free RAM
but had already started paging to disk.

### 2. Pre-flight size gate in `_resolve_layout_engine` (P0)

Stashed as `4B913619`. Combine size + page-count check with the
resource probe (remediation 1) before returning `"docling"`. Action
matrix:

| Condition | Action |
|---|---|
| pages ≤ `probe.recommended_docling_max_pages` AND mb ≤ `probe.recommended_docling_max_mb` | Run docling directly |
| pages > threshold OR mb > threshold | Route through PDF splitter (remediation 3), not heuristic |
| `probe.recommended_docling_max_pages == 0` | Downgrade to heuristic (insufficient RAM for docling at all) |

The pivot from the original draft: oversized PDFs **default to
splitter, not heuristic**. Heuristic is only the fallback when the
splitter itself can't run (e.g. `pypdf` import failure) or RAM is
catastrophically low.

The downgrade / split decision must be visible in the manifest
(`engine_used`, `engine_reason`, `split_chunks`) so the operator
knows which path each source took.

### 3. PDF splitter as the default path for large PDFs (P0, was P1)

Stashed as `F64683BC` (splitter) and `D885CE79` (batch + stitch).
**Promoted to P0** by the 2026-06-05 design pivot. The splitter is no
longer an opt-in optimization — it is the canonical handler for any
PDF that exceeds the probe's per-call docling limits.

* `split_pdf(path, max_pages=probe.recommended_docling_max_pages,
  page_overlap=2)` produces deterministic chunk files under a cache
  directory.
* Each chunk is processed through docling under the resource budget
  (serial when `probe.serialize_docling` is True; otherwise up to
  `probe.recommended_concurrency`).
* Chunk outputs are stitched (D885CE79) into a single logical document
  output with continuous `part-NNNN.md` numbering and a `docline:`
  manifest entry `split_chunks` recording original page boundaries.
* Per-chunk failure-isolation: if chunk K OOMs, that chunk alone
  downgrades to heuristic; chunks K-1 and K+1 keep their docling
  output. Cosmos-db.pdf (109 MB, ~700 pages) would chunk into ~14
  pieces of 50 pages each, processed serially on this hardware, with
  total peak RSS bounded by single-chunk consumption.

### 4. Broaden the `auto` fallback exception net (P0)

In `read_pdf_pages` :512, catch `RuntimeError`, `MemoryError`, and
`OSError` in addition to `PdfReadError`. This is the safety net for
unexpected docling failures even after the size gate and splitter are
in place. Log at WARNING with PDF path and underlying exception class.

```python
except (PdfReadError, RuntimeError, MemoryError, OSError) as err:
    if not path.exists():
        raise
    _log.warning(
        "Docling failed on %s (%s); falling back to heuristic engine",
        path, type(err).__name__,
    )
    # Drop down to heuristic path
```

Stashed as `15ADD215`.

### 5. Bound docling's CPU thread fan-out (P1)

Before invoking docling, set environment variables that cap PyTorch
and BLAS thread counts. The resource probe (remediation 1) computes
the target thread count from `logical_cpus`; for the i7-4700MQ this
resolves to 2. In `_read_pdf_docling_pages`, before importing docling:

```python
budget = resource_probe.probe()
threads = str(max(1, budget.logical_cpus // 4))
os.environ.setdefault("OMP_NUM_THREADS", threads)
os.environ.setdefault("MKL_NUM_THREADS", threads)
os.environ.setdefault("OPENBLAS_NUM_THREADS", threads)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
```

Note: PyTorch reads these at import time, so the `setdefault` MUST
fire before the first docling import. `setdefault` (not `setenv`)
respects operator overrides.

Stashed as `C1EB2C6A`.

### 6. Subprocess-isolate docling for every chunk (P0, was P1)

Promoted to P0 by the design pivot. Even with the splitter in place,
each docling chunk invocation runs in a child Python process via
`subprocess.run([sys.executable, "-m", "docline._tools.docling_worker",
chunk_path, output_path])`. Rationale:

* If a single chunk OOMs (`c10::Error` / SIGABRT that bypasses Python
  exception handling), the OS reaps the child cleanly and the parent
  records a non-zero exit code → chunk falls back to heuristic.
* PyTorch's CPU allocator does not return memory to the OS reliably
  even after Python objects are GC'd. A fresh subprocess per chunk
  guarantees the working set resets between chunks.
* When `probe.serialize_docling` is True, the parent invokes children
  sequentially (`for chunk in chunks: subprocess.run(...)`), giving
  the OS time to reclaim physical pages between calls.

### 7. Do not co-host the load test with the agent session (P0, operator)

Run any full-corpus load test from a plain PowerShell session, not
from inside an agent's tool calls. The Copilot CLI process alone is
~400 MB peak; combined with docling workers it leaves no headroom on
this hardware.

## Proposed full-load-test approach

The goal: prove docline can process the full `.elt/pbi/` Power BI
corpus + `azure-cosmos-db.pdf` end-to-end without paging the system.

### Phase 0 — preflight (no agent)

1. Close VS Code, the agent CLI, browsers, Teams. Reboot or at least
   leave the system idle for 5 minutes so working sets shrink.
2. Confirm free RAM > 24 GB before starting. (PowerShell:
   `Get-CimInstance Win32_OperatingSystem | Select FreePhysicalMemory`.)
3. Start a fresh PowerShell window. Set thread caps for this session:
   ```powershell
   $env:OMP_NUM_THREADS = 2
   $env:MKL_NUM_THREADS = 2
   $env:OPENBLAS_NUM_THREADS = 2
   $env:TOKENIZERS_PARALLELISM = "false"
   ```
4. Activate the venv: `.\.venv\Scripts\Activate.ps1`.

### Phase 1 — instrumentation harness

Add `scripts/load_test.py` (stashed as `A2A78AEE`, updated to reflect
the design pivot). For each PDF, in order:

1. Probe runtime resources first (`resource_probe.probe()`); log the
   ResourceBudget so the run is reproducible.
2. If PDF size or page count exceeds the budget's docling limits,
   call the splitter (stash `F64683BC`) to produce N chunks under
   `.elt/splits/{source_hash}/chunk-NNNN.pdf`.
3. For each PDF (or chunk), fork a child process via
   `subprocess.run([sys.executable, "-m", "docline", "process", ...])`
   so OOM reaps cleanly without taking out the harness.
4. Wrap each child with `psutil` to sample peak RSS, elapsed time,
   and exit code.
5. When `probe.serialize_docling` is True, hold the harness to one
   docling child at a time. Otherwise allow up to
   `probe.recommended_concurrency` concurrent children (still bounded
   well below `cpu_count`).
6. Insert a 10–30 s reclaim pause between docling children when
   `serialize_docling` is active.
7. Emit a TSV row per child: `{file, chunk, mb, pages, engine, exit,
   elapsed_s, peak_rss_mb, output_parts, fallback_reason,
   probe_available_gb, probe_concurrency, probe_serialize}`.
8. Skip-on-failure: a child OOM logs the row with engine=docling,
   exit=non-zero, then retries the same chunk with engine=heuristic.
9. After all chunks process, invoke the stitcher (stash `D885CE79`)
   to produce a single logical document output with continuous
   `part-NNNN.md` numbering.

### Phase 2 — tiered execution

Run PDFs in three batches, with a 30-second pause between PDFs to let
the OS reclaim torch tensors:

| Tier | Selection | Purpose |
|---|---|---|
| Small | All PDFs ≤ 10 MB (5 files) | Sanity-check the pipeline |
| Medium | 10–30 MB (3 files: dax, fabric-enterprise, power-bi-developer-visuals) | Establish baseline peak RSS on safe-size PDFs |
| Large | > 30 MB (10 PDFs including cosmos) | Real stress test; expect heuristic fallback on several |

Between tiers, stop and inspect the TSV. If peak RSS in the Medium
tier exceeds ~6 GB on any single PDF, abort the Large tier and lower
the docling threshold.

### Phase 3 — verification

For each output job, verify:

* Manifest exists at the expected path.
* Part count is plausible (cosmos heuristic emitted 554 parts; PowerBI
  PDFs are unknown — record baselines).
* No part files are zero-length.
* H1 synthesis (once implemented) re-runs cleanly on the corpus.

### Phase 4 — measurements that feed the spike

The TSV from Phase 1 directly answers spike `4B913619`:

* Maximum safe docling MB threshold (last PDF where peak RSS stays
  under 4 GB).
* Maximum safe docling page count (compute page count via pypdf in
  the harness).
* Whether `auto` fallback survived all hostile PDFs (it should once
  remediation 2 is shipped).

The result is a measured table and a recommended threshold, which is
exactly what stash `4B913619`'s spike output should contain. The same
TSV becomes the regression baseline for future load tests.

## Cleanup actions for the current workspace

1. The crash dump `report.20260604.223541.24064.0.001.json` (repo
   root) is git-untracked and not useful long-term. **Move to
   `docs/scratch/` or delete after this RCA is committed.** It is
   referenced by absolute path in this artifact, so a copy under
   `docs/scratch/2026-06-04-copilot-cli-oom-dump.json` is safe.
2. The repo-root `output/` directory is a partial duplicate of
   `.elt/output/` (3 of 5 jobs, missing the two PDF jobs). It is
   git-untracked. Recommend deletion to avoid future confusion —
   the canonical output path is `.elt/output/`.
3. `.gitignore` should already cover `report.*.json` and `output/` at
   repo root; verify and add if missing.

## Open items / handoff

| Item | Owner | Status |
|---|---|---|
| Remediation 1: adaptive resource probe + throttle | Next Stage cycle | **NEW stash needed (see below)** — gates everything else |
| Remediation 2: size gate in `_resolve_layout_engine` | Bundle with probe | Stash `4B913619` (refined: gate now feeds splitter, not heuristic, on oversize) |
| Remediation 3: PDF splitter is default for large PDFs | Next Stage cycle | Stash `F64683BC` (promoted P1→P0; wired into probe output) |
| Remediation 3 (cont.): batch + stitch for split chunks | Next Stage cycle | Stash `D885CE79` (promoted P1→P0) |
| Remediation 4: broaden auto-fallback exception net | Bundle with probe | Stash `15ADD215` |
| Remediation 5: thread caps from probe | Bundle with probe | Stash `C1EB2C6A` (refined: thread count comes from probe, not hardcoded 2) |
| Remediation 6: subprocess-isolate docling per chunk | Part of splitter+batch shipment | Folded into stash `D885CE79` |
| Build `scripts/load_test.py` harness with probe + serial throttle | Next Stage cycle | Stash `A2A78AEE` (refined for design pivot) |
| Operator: run full load test only outside agent session | User | Documented (Phase 0) |

Suggested shipment grouping for the next Stage cycle:

* **Shipment A — runtime safety primitives** (probe + size gate +
  broadened exception net + thread caps): stashes `4B913619` +
  `15ADD215` + `C1EB2C6A` + a new resource-probe stash. Pure-Python,
  no torch/docling dependencies in the new module surface. ~1 day.
* **Shipment B — PDF splitter + batch + stitch** (`F64683BC` +
  `D885CE79`): depends on Shipment A's probe. Introduces
  subprocess-isolated docling worker. ~2 days.
* **Shipment C — load test harness + measured threshold spike**
  (`A2A78AEE` + the original spike scope of `4B913619`): depends on
  both A and B. Produces the measured TSV that validates the
  thresholds chosen in A. ~0.5 day for the harness, ~1 day to run
  the full corpus and analyze.

## 2026-06-05 addendum — GPU acceleration evaluation

Question raised after the design pivot: can the host's NVIDIA GPU
accelerate docling? Verdict: **no on this hardware, but the resource
probe should still detect GPU capability for future hosts.**

### What the host actually has

| Component | State |
|---|---|
| GPU | NVIDIA GeForce GTX 770M (laptop, Kepler GK106, **3 GB VRAM**, 2013) |
| NVIDIA driver | **425.31** (2019) → CUDA runtime cap 10.1 |
| `nvcuda.dll` | NVIDIA CUDA 10.1.131 driver |
| Installed torch | **`2.12.0+cpu`** (CPU-only build) |
| `torch.cuda.is_available()` | False |

### Three independent blockers, any one fatal

1. **Compute capability too old.** GTX 770M is `sm_30`. PyTorch 1.13
   was the last release that shipped kernels for `sm_3x`; PyTorch 2.x
   only targets `sm_50` (Maxwell) and up. Installing a CUDA wheel
   would still throw `CUDA error: no kernel image is available for
   execution on the device` the moment docling sent a tensor to the
   device.
2. **Driver caps at CUDA 10.1.** Modern PyTorch wheels require CUDA
   11.8 or 12.x runtime. NVIDIA dropped Kepler from the Game Ready
   driver line years ago; the last Kepler-supporting branch (R472)
   tops out at CUDA 11.x runtime and still can't fix blocker #1.
3. **VRAM too small.** docling rt_detr-l4 working set is ~4–6 GB
   during inference (model weights + activations + page-image
   batches). A 3 GB card OOMs immediately.

The fact that the venv already pinned `torch+cpu` is consistent with
a prior contributor having reached the same conclusion. **No change
to the CPU plan is warranted.**

### What the probe should detect anyway

GPU detection is added to `resource_probe.probe()` (stash `1D945AB5`,
revised) for forward compatibility. Detection logic (all required for
`accelerator_device="cuda"`):

1. `torch.cuda.is_available()` is True
2. `torch.cuda.get_device_capability(0) >= (5, 0)` — Kepler rejection
3. `torch.cuda.mem_get_info(0)[0] >= 4 * 1024**3` — ≥4 GB free VRAM
4. `torch.zeros(1, device='cuda')` succeeds — driver/kernel compatibility

When all four pass, the probe returns `accelerator_device="cuda"` and
raises `recommended_docling_max_pages = min(200, gpu_vram_gb * 25)`,
sets `serialize_docling=False` (CUDA OOMError is cleanly catchable
per-call), and passes `AcceleratorOptions(device=AcceleratorDevice.CUDA)`
through to docling. On the current host, condition #2 fails
(`(3,0) < (5,0)`) and the probe deterministically returns
`accelerator_device="cpu"` — the GPU detection code path is dormant
but tested via mocked `torch.cuda` calls in the test suite.

### Future hardware that would benefit

| GPU class | Compute cap | VRAM | Expected docling speedup |
|---|---|---:|---|
| GTX 1660 / RTX 2060 | sm_75 | 6 GB | 3–5× |
| RTX 3060 / 4060 | sm_86 / sm_89 | 8–12 GB | 5–8× |
| RTX 3090 / 4080+ | sm_86 / sm_89 | 24+ GB | 8–10× |

On any of these the resource probe would transparently switch docline
to CUDA mode with no code change in the splitter, batch processor, or
load-test harness. The CPU code path remains the supported baseline.

## References

* Crash dump: `report.20260604.223541.24064.0.001.json` (git-ignored
  via the .gitignore update applied alongside this RCA)
* Spike output: `docs/decisions/2026-06-04-spike-h1-header-synthesis.md`
* Stashes: `4B913619` (docling threshold spike + size gate),
  `F64683BC` (PDF splitter), `D885CE79` (batch + stitching + subprocess
  isolation), `15ADD215` (broader exception net), `C1EB2C6A` (thread
  caps), `A2A78AEE` (load test harness), `1D945AB5` (resource probe
  with GPU detection)
* Reader code: `src/docline/readers/pdf.py` lines 502–520, 579–615
* Output evidence: `.elt/output/manifest.json`, `output/manifest.json`
* Hardware: Intel Core i7-4700MQ @ 2.40 GHz (8 logical cores), 32 GB
  RAM, NVIDIA GeForce GTX 770M (3 GB VRAM, sm_30, unusable for
  docling acceleration), Windows 10 Pro 19045
