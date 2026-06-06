---
shipment: 020-S
title: "Closure record — load-test harness"
status: verified
merge_sha: 4bd5d36
merged_pr: 40
---

# Closure — 020-S: load-test harness

## Outcome

Ships `scripts/load_test.py`, the operator-runnable harness that
drives a PDF corpus through the split-and-throttle pipeline
(`process_pdf_in_chunks` from shipment 019-S) and emits per-chunk
TSV measurements. Completes the 3-shipment plan from the 2026-06-04
RCA.

**Operator must run this harness from a plain PowerShell session**, not
from inside an agent's tool calls. The Copilot CLI process co-hosted
with docling triggered the 2026-06-04 paging spiral; running the load
test inside an agent session would risk repeating it.

## Tasks

| Task | Title | Outcome |
|---|---|---|
| 020.001.001-T | Build load_test.py harness | `scripts/load_test.py` + 19 tests |
| 020.001.002-T | Closure document | this file |

## Stash impact

* **Closed by this shipment**:
  * `A2A78AEE` — load-test harness
* **The RCA-driven 3-shipment plan is now fully shipped.** No stashes from the original plan remain open.

## Public API

```python
from scripts.load_test import (
    classify_tier,           # size_mb -> "small" | "medium" | "large"
    iter_corpus,             # corpus_dir -> Iterator[(path, size_mb)]
    run_one_pdf,             # pdf_path -> (BatchResult, elapsed_s, peak_rss_mb)
    build_rows_for_result,   # -> list of TSV-shaped dicts
    write_tsv_rows,          # tsv_path, rows
    main,                    # CLI entry point
)
```

## CLI

```text
python scripts/load_test.py \
    --corpus-dir .elt/pbi \
    --output-dir logs/load-test-output \
    --tsv-path logs/load-test.tsv \
    --tier all \
    --pause-seconds 30
```

| Flag | Default | Purpose |
|---|---|---|
| `--corpus-dir` | required | Directory of input PDFs (non-recursive) |
| `--output-dir` | required | Where per-PDF chunk outputs land |
| `--tsv-path` | required | TSV file for per-chunk measurements |
| `--tier` | `all` | `small` (≤10 MB) / `medium` (10–30 MB) / `large` (>30 MB) / `all` |
| `--pause-seconds` | `30` | Seconds to sleep between PDFs (OS reclaim) |
| `--log-level` | `INFO` | Python logging level |

## TSV columns

```text
timestamp file mb chunk_index engine exit_code elapsed_s peak_rss_mb
output_chars fallback_reason probe_available_gb probe_max_pages probe_serialize
```

Each PDF emits one row per chunk plus a synthetic `summary` row with
the aggregated stitched-output character count and total elapsed time.

## Operator runbook (for the actual measurement run, outside any agent)

```text
1. Close VS Code, agent CLIs, browsers, Teams. Reboot or wait 5 minutes.
2. Confirm free RAM > 24 GB:
     (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
3. Open a fresh PowerShell window. Activate venv:
     .\.venv\Scripts\Activate.ps1
4. Optional thread caps (the resource probe also sets these but
   pre-seeding via shell removes the timing window):
     $env:OMP_NUM_THREADS = 2
     $env:MKL_NUM_THREADS = 2
     $env:OPENBLAS_NUM_THREADS = 2
     $env:TOKENIZERS_PARALLELISM = "false"
5. Run small tier first:
     python scripts/load_test.py --corpus-dir .elt/pbi `
       --output-dir logs/load-test-output --tsv-path logs/load-test-small.tsv `
       --tier small --pause-seconds 30
6. Inspect logs/load-test-small.tsv. Confirm peak_rss_mb stays bounded.
7. Proceed to medium tier, then large tier. STOP if any single PDF
   pushes peak_rss_mb past ~6 GB.
```

## Quality Gate Evidence

### Local (Windows)

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 169 files clean |
| `pyright src/` | 0 errors, 0 warnings |
| `pytest` | 19 new tests pass; full suite unchanged from 019-S baseline |

### CI

To be populated after the cross-OS matrix runs through this PR.

## Adversarial self-review

* Tests cover tier classification (8 parameterized boundary cases including exact thresholds), custom thresholds, corpus iteration with filtering, missing-dir error, build_rows including summary row math, TSV write/append, CLI return codes for missing-corpus and empty-corpus, and an end-to-end smoke against a fake `process_pdf_in_chunks`.
* All exception paths in `main()` log structured errors rather than crashing the corpus run mid-loop.
* The harness only IMPORTS `process_pdf_in_chunks` from `docline.process.pdf_batch`; it adds zero source-tree changes outside `scripts/` and `tests/scripts/`.
* No security findings. No dead code.

## RCA-driven plan: SHIPPED

This closes the original 3-shipment plan in
`docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md`:

| Shipment | Status |
|---|---|
| **A** — runtime safety primitives (018-S) | shipped at `e44ad54` (PR #36) |
| **B** — PDF splitter + batch + stitch + subprocess isolation (019-S) | shipped at `1431c63` (PR #38) |
| **C** — load-test harness (020-S) | this shipment |

The remaining open work (`4B913619` measurement run) is now a pure
**operator task**: run the harness, collect the TSV, and the empirical
threshold spike's recommendation table is produced from the measurements.
That run cannot happen inside this agent session.

## References

* RCA: `docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md`
* 018-S closure: `docs/closure/018-S-runtime-safety-primitives.md`
* 019-S closure: `docs/closure/019-S-pdf-splitter-batch.md`
* Plan: `docs/plans/2026-06-05-shipment-a-runtime-safety-primitives.md` (covers the foundation)
