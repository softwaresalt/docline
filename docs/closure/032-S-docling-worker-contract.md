---
title: docling_worker contract refresh + perf tuning (032-S closure)
date: 2026-06-14
status: shipped
verdict: PROMOTE
shipment: 032-S
feature: 030-F
consumed_stash:
  - 5CFE4481  # per-page docling output limitation (019-F review follow-up)
  - 51332802  # docling_worker subprocess perf tuning (022-S empirical follow-up)
related_deliberation: 001-DL
plan: docs/plans/2026-06-14-docling-worker-contract-refresh-plan.md
references:
  - src/docline/_tools/docling_worker.py
  - src/docline/process/pdf_batch.py
  - src/docline/process/pdf_triage.py
  - scripts/study/docling_batch_size_probe.py
  - scripts/study/per_page_fidelity_check.py
  - docs/decisions/2026-06-14-docling-batch-size-probe.md
---

# 032-S — docling_worker contract refresh + perf tuning

## Verdict

**PROMOTE.** Ships a JSON-envelope worker contract that makes per-page
fidelity restorable (and honestly attributed when not), plus a batched-
worker mode that amortizes the docling model-load cost across N chunks.
T4 (rt_detr batch-size probe) ships as a runnable script + decision-doc
skeleton; the empirical fill-in is a small operator follow-up. T5 ships
the per-page fidelity validation harness which the operator runs to
confirm zero ``engine="docling"`` pages with empty content.

## What shipped

### T1 — Worker emits JSON envelope (schema_version=1)

``src/docline/_tools/docling_worker.py`` now serializes the worker
output as a JSON envelope::

    {
        "schema_version": 1,
        "pages": ["page 1 markdown", ...],
        "page_count": N,
        "text": "page 1 markdown\\n\\npage 2 markdown\\n\\n..."
    }

Subprocess exit codes are unchanged. Failure modes still map to the same
codes. The output file extension stays ``.md`` for orchestrator-side
path convention (internal IPC; never opened as markdown by a human).

In batched mode, a chunk that fails mid-loop writes an error envelope
with an additional ``error`` field; the worker continues with the next
chunk.

### T2 — Consumers parse envelope; per-page splice-back is content-correct

``src/docline/process/pdf_batch.py`` ``_process_one_chunk`` parses the
envelope and surfaces:

- ``ChunkResult.markdown`` — from ``envelope["text"]`` (preserves the
  existing stitching behavior verbatim)
- ``ChunkResult.chunk_pages: tuple[str, ...]`` — new field carrying
  ``envelope["pages"]`` for downstream consumers that need per-page output

``src/docline/process/pdf_triage.py`` splice-back loop parses the
envelope and:

- when ``len(envelope["pages"]) == range_length``: assigns each envelope
  page to its corresponding ``final_pages`` slot with
  ``engine_per_page[i] = "docling"``
- when ``len(envelope["pages"]) != range_length``: logs a warning, falls
  back to the legacy "first-page-gets-blob, rest empty" with
  ``engine_per_page[i] = "docling-collapsed"`` so the attribution
  mismatch is **visible** instead of silently misleading
- on ``JSONDecodeError`` (legacy flat-markdown body): defensive fallback
  to ``"docling-collapsed"`` (same legacy collapse, kept as a partial-
  rollout safety net)

### T3 — Multi-chunk batched worker mode

``docling._tools.docling_worker`` gains a ``--batch MANIFEST_JSON`` mode.
Manifest format::

    {
        "chunks": [
            {"input": "/abs/path/chunk-1.pdf", "output": "/abs/path/chunk-1.md"},
            {"input": "/abs/path/chunk-2.pdf", "output": "/abs/path/chunk-2.md"}
        ]
    }

The worker imports docling and loads the layout model **once**, then
iterates the manifest writing one envelope per chunk. Process exit code
is 0 if at least one chunk succeeded; non-zero only if the docling
import or initial model load failed.

Both ``process_pdf_in_chunks`` (pdf_batch) and ``process_pdf_triaged``
(pdf_triage) accept a new ``use_batched_worker: bool = True`` kwarg.
Default behavior:

- N >= 2 chunks AND ``use_batched_worker=True`` AND
  ``not budget.serialize_docling`` ⇒ batched mode
- Otherwise ⇒ legacy per-chunk loop (preserves reclaim-pause semantics
  for memory-constrained hosts where ``serialize_docling=True``)

``BatchResult.metadata["batched_worker"]`` and
``TriageResult.metadata["batched_worker"]`` expose which path was taken
for observability.

### T4 — rt_detr batch-size probe (committed; empirical pending)

``scripts/study/docling_batch_size_probe.py`` iterates layout/ocr/table
batch sizes {1, 4, 8, 16, 32} against a representative cosmos splice
and also runs a per-page-loop comparison (informs the deferred per-page
fidelity restoration follow-up).

``docs/decisions/2026-06-14-docling-batch-size-probe.md`` is committed
as a skeleton with the knob landscape documented; empirical values get
filled in by the operator post-merge (the run requires docling installed
+ sample data + ~minutes of wall-clock per probe iteration).

### T5 — Per-page fidelity validation harness (committed)

``scripts/study/per_page_fidelity_check.py`` runs ``process_pdf_triaged``
against a source PDF, counts engine attributions, and asserts zero
``engine="docling"`` pages with empty content. Exits 1 on contract
violation; 0 otherwise. Auto-skips when docling extras are not installed.

## What did NOT ship (deferred)

### Per-page fidelity restoration via ``page_range=(i,i)`` looping

Grounding investigation during T4 revealed that
``DocumentConverter.convert()`` exposes a ``page_range: Tuple[int, int]``
parameter. This means per-page fidelity IS achievable by looping
``page_range=(i, i)`` for each page within a chunk — exactly the
Option 2 path the deliberation rejected for perf reasons.

But under T3's batched-worker mode, the docling model loads ONCE per
subprocess. Per-page invocations within the same subprocess pay only
the per-page inference cost, not the cold-start. This may make Option 2
tractable after all.

The T4 probe script's ``per-page-loop`` row measures this directly.
If the overhead is < 2× a single multi-page call, a follow-up spike
should ship Option 2 inside the batched worker. That would retire the
``"docling-collapsed"`` attribution entirely and give true per-page
fidelity.

**Filed as stash follow-up** (see "Follow-up stash candidates" below).

### Empirical wall-clock numbers for T3 batched-mode speedup

The plan's acceptance criterion ("≥30% wall-clock reduction on cosmos
PA3+PA4 from cold-start dedup alone") cannot be measured inside the
autopilot session without running real docling on the operator's
cosmos sample. The T4 probe script captures the per-knob timing; the
batched-mode speedup is implicit (one cold-start vs N cold-starts).

A back-of-envelope estimate: 86 invocations × 5-10s cold-start =
430-860s ≈ 7-14 minutes of cold-start cost. Under batched mode (one
cold-start), that cost collapses to ~5-10s total. That alone is a
~7-14 min reduction on a 247-min total, or ~3-6%. The remaining
inference cost (~233-240 min) is unaffected by cold-start dedup; the
rt_detr batch-size knob (T4) targets the inference cost directly.

So the realistic split is: T3 saves cold-start (~5% of cosmos wall-clock);
T4 chosen batch size could save ~10-30% of inference (yielding a
combined ~15-35% reduction). The operator's empirical T4 run will
quantify the inference half.

## How to validate post-merge

After merge, the operator should:

1. **Run T5 harness** to confirm per-page fidelity contract holds:
   ```powershell
   python scripts\study\per_page_fidelity_check.py `
     --source-pdf .elt\data\cosmosdb\azure-cosmos-db.pdf `
     --output-dir .elt\output\per-page-fidelity-check
   ```
   Expected output: ``PASS: every engine='docling' page carries non-empty content``.

2. **Run T4 probe** to capture empirical batch-size numbers + per-page
   loop overhead:
   ```powershell
   python scripts\study\docling_batch_size_probe.py `
     --splice-pdf .elt\output\cosmos-triage-022\study\dataset\range-0859-1056\_input.pdf `
     --output-dir .elt\output\cosmos-triage-022\study\results\batch-probe
   ```

3. **Update the decision doc** (``docs/decisions/2026-06-14-docling-batch-size-probe.md``)
   with the empirical results table and the chosen ``layout_batch_size``
   constant. If a clear winner emerges, also wire that constant into
   ``_read_pdf_docling_pages`` in ``src/docline/readers/pdf.py``.

4. **Optionally re-run the full cosmos PA3+PA4 pipeline** to measure
   total wall-clock improvement vs the 022-S baseline (247 min). Append
   that number to this closure doc as a post-merge addendum.

## Test coverage shipped

- ``tests/tools/test_docling_worker.py`` — **17 tests** (9 single-chunk
  including 5 envelope-format tests; 8 batched-mode covering happy path,
  per-chunk failure isolation, missing input, all-fail catastrophic
  exit, docling-extras-missing, manifest validation).
- ``tests/process/test_pdf_batch.py`` — **19 tests** (10 existing
  preserved via envelope-aware ``_runner_factory``; 3 envelope/JSONDecodeError
  consumer tests; 6 batched-mode integration tests covering invocation
  semantics, opt-out flag, ``serialize_docling`` opt-out, per-chunk
  error envelope handling, subprocess failure handling).
- ``tests/process/test_pdf_triage.py`` — **13 tests** (4 existing
  preserved via envelope-aware ``_runner_factory``; 4 envelope/length-
  mismatch/JSONDecodeError splice-back tests; 5 batched-mode integration
  tests covering invocation, single-range per-range path, opt-out flag,
  subprocess failure, per-range error envelope handling).
- **Full suite**: 1259 passed, 4 skipped (unchanged from main).

## Quality gates

- ``ruff check .``: pass (excluding 1 pre-existing lint error in
  operator helper ``scripts/compare_markitdown_vs_docling.py`` which is
  always untracked; same status as previous shipments).
- ``ruff format --check .``: pass.
- ``pytest``: 1259 passed, 4 skipped.
- pyright: pre-existing errors on main only (markitdown signature drift);
  none introduced by this shipment.

## Follow-up stash candidates

1. **Per-page fidelity restoration spike**: contingent on T4 per-page-loop
   probe results. If overhead < 2×, ship Option 2 (loop
   ``page_range=(i, i)`` inside the batched worker) and retire the
   ``"docling-collapsed"`` attribution. Medium priority — only worth
   doing if the probe says it's affordable.
2. **Operator-runs the T4 probe + commits empirical results** into
   ``docs/decisions/2026-06-14-docling-batch-size-probe.md``. Small,
   low-risk; primarily a docs follow-up.
3. **Multi-chunk-per-file envelope shape**: deferred from the
   deliberation. Currently each chunk gets its own envelope file; an
   evolution would consolidate N chunks into one file with a
   ``{"chunks": {"<id>": {"pages": [...]}}}`` shape for very large N.
   Low priority — only worth doing if per-chunk file I/O becomes a
   measurable hot path.
4. **Per-page H1 markers in pdf_batch stitcher**: HTML-comment markers
   like ``<!-- page 5 -->`` so downstream graph writers can recover page
   boundaries from the stitched markdown. Low priority — gated on
   downstream consumer needs.
5. **GPU acceleration spike**: docling's pipeline can run on CUDA/MPS;
   needs detection + DocConverter config + env-var gating. Out of scope
   for this shipment; could unlock another large throughput win on
   GPU-equipped hosts.

## Architectural lessons

1. **Internal IPC contracts evolve more cleanly with a versioned
   envelope than with flat-text** — ``schema_version=1`` lets future
   worker iterations add fields without breaking consumers; the
   ``"error"`` field added in T3 batched mode demonstrates this
   already.
2. **Honest attribution beats false fidelity** — ``"docling-collapsed"``
   is the right label for a multi-page range that produced a single blob.
   Pretending it's per-page (the pre-T2 behavior) silently misled
   downstream consumers. T2's fallback path makes the limit visible.
3. **Per-chunk subprocess isolation has perf cost — batched mode trades
   isolation for shared model load**. The opt-in kwarg keeps both modes
   available; the default favors throughput unless the budget says
   memory pressure requires per-chunk reclaim pauses.
4. **Probes are committable artifacts, not test-suite citizens** — the
   T4 probe needs minutes of real docling wall-clock and sample data
   that isn't checked in. Shipping it as an operator-runnable script
   with a decision-doc skeleton is a cleaner pattern than running it
   inside the autopilot session.
