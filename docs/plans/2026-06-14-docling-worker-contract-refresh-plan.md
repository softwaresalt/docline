---
title: "docling_worker contract refresh + perf tuning"
date: 2026-06-14
status: draft
shipment: 032-S
feature: 030-F
consumes_stash: ["5CFE4481", "51332802"]
related_deliberation: 001-DL
references:
  - src/docline/_tools/docling_worker.py
  - src/docline/process/pdf_batch.py
  - src/docline/process/pdf_triage.py
  - docs/decisions/2026-06-08-extraction-strategy-study.md
  - docs/closure/031-S-mistral-ocr-spike.md
---

# Implementation Plan — docling_worker contract refresh + perf tuning

## Problem

Two coupled medium-priority follow-ups from prior shipments:

1. **`5CFE4481` (per-page fidelity, from 019-F review)** — The `docline._tools.docling_worker` subprocess returns one flat markdown blob per invocation. The pdf_triage splice-back loop attaches this blob to the FIRST page of a flagged range and leaves all other pages of the range as `""`, while still labeling every page in the range as `engine="docling"`. This is a fidelity/attribution mismatch.

2. **`51332802` (perf tuning, from 022-S empirical data)** — Cosmos PA3+PA4 ran 86 docling subprocess invocations averaging 24 pages each over 247 wall-clock minutes. The dominant cost is **model-load overhead** (~5-10s per invocation × 86 ≈ 7-14 min just in cold starts), plus per-page layout-model inference where rt_detr batch size is unknown/untuned.

The two are coupled because **the worker output contract is the choke point for both**: a richer envelope unlocks per-page fidelity AND lets the worker process multiple chunks per invocation (sharing the docling model load).

Deliberation `001-DL` selected **Option 1 — JSON envelope** for the contract refresh. The current plan extends that decision with two perf strategies and a measurement harness.

## Constitution Check

| Principle | Compliance |
|---|---|
| I. Safety-First Python | Type hints on all changed signatures; ruff/pyright clean |
| II. Test-First Development | Each task starts with failing tests (harness-architect skill) |
| III. Workspace Isolation | Worker paths remain inside output_dir; no escape |
| IV. CLI Containment | No new file ops outside cwd |
| V. Structured Observability | Worker stderr diagnostics extended with envelope-format errors |
| VI. Single Responsibility | No new dependencies; uses stdlib `json` for envelope |
| VII. Destructive Approval | None — internal contract change |
| VIII. Safety Modes | careful-mode applies to subprocess contract change (T1) |
| IX. Git-Friendly Persistence | Markdown + YAML frontmatter for closure |
| X. Context Efficiency | Envelope is a structured JSON object, queryable by index |
| XI. Merge Commit History | PR will use --merge |

No violations.

## Scope

### In scope

- T1: Worker JSON envelope output (`{"pages": [...], "page_count": N, "text": "..."}`)
- T2: pdf_batch.py + pdf_triage.py consumer migration to read the envelope
- T3: Multi-chunk batched worker mode (one invocation, multiple input PDFs, output keyed by chunk id) — addresses the `5-10s × N invocations` model-load overhead
- T4: rt_detr layout-model batch size probe — empirical investigation; document findings; commit chosen batch size as a worker constant (NOT a per-call knob)
- T5: Per-page fidelity validation harness + closure — re-run cosmos triage and verify per-page attribution is now content-accurate

### Out of scope (deferred to stash)

- GPU acceleration option (separate spike — needs CUDA/MPS detection, DocConverter config, env-var gating)
- Per-page H1 markers in `_stitch_chunk_markdown` (low-priority docs follow-up)
- Multi-chunk-per-file envelope shape (T3 uses per-chunk separate output paths)

## Architectural decisions

### D1: Envelope schema

```json
{
  "pages": ["page 1 markdown", "page 2 markdown", "..."],
  "page_count": N,
  "text": "joined markdown for legacy convenience",
  "schema_version": 1
}
```

- `pages` — per-page list as `_read_pdf_docling_pages` returns. **The fidelity payload.**
- `page_count` — redundant integrity check; consumers MAY assert `len(pages) == page_count`.
- `text` — `"\n\n".join(pages)`. Kept so `pdf_batch._process_one_chunk` can hand it to `_stitch_chunk_markdown` without re-joining.
- `schema_version` — future-proofing for the multi-chunk shape in T3.

### D2: File extension stays `.md`

The output path naming convention (`chunk-NNNN.md`, `splice-SSSS-EEEE.md`) is referenced in many tests and operator-facing logs. Keeping `.md` and writing JSON content inside is less disruptive than renaming. Worker docstring + a banner comment in each consumer will flag the contract.

**Alternative considered and rejected**: rename to `.json`. Rejected because: (a) ripples to ~20 test fixtures and operator log expectations; (b) the file is internal subprocess IPC, never opened by a human as markdown.

### D3: Multi-chunk batched worker invocation shape

Worker CLI gains a second mode:

```text
# Single-chunk (existing):
python -m docline._tools.docling_worker INPUT_PDF OUTPUT_MD

# Multi-chunk (new in T3):
python -m docline._tools.docling_worker --batch BATCH_MANIFEST_JSON
```

where `BATCH_MANIFEST_JSON` is a path to a JSON file:

```json
{
  "chunks": [
    {"input": "/path/a.pdf", "output": "/path/a.md"},
    {"input": "/path/b.pdf", "output": "/path/b.md"}
  ]
}
```

The worker loads docling **once**, then iterates the manifest writing one envelope per chunk to its output path. On per-chunk failure, writes an envelope `{"pages": [], "page_count": 0, "text": "", "error": "..."}` and continues. Process exit code is 0 if at least one chunk succeeded; non-zero only if the docling import or model load itself failed (so the parent can decide whether to retry single-chunk or fall back to heuristic).

This shape **preserves** the existing per-chunk path-routing assumptions in pdf_batch and pdf_triage — they still get one output file per chunk.

### D4: rt_detr batch size probe

`docling.document_converter.DocumentConverter` accepts pipeline options. The rt_detr layout model exposes a batch size that affects per-page latency. T4 will:

1. Write a probe script in `scripts/study/docling_batch_size_probe.py` that runs a representative chunk (one of the cosmos splice ranges) at batch sizes {1, 4, 8, 16, 32} and records wall-clock + peak RSS.
2. Pick the knee of the latency/memory curve.
3. Commit the chosen batch size as a **constant** in `_read_pdf_docling_pages` (or wherever the converter is constructed). Not a per-call knob; not an env var; not exposed to public API. The empirical study artifact lives under `docs/decisions/`.

If docling does not expose rt_detr batch size at the supported API surface, T4 documents that finding and exits without code change — measurement value alone is worthwhile.

## Tasks

### T1 — Worker emits JSON envelope (5CFE4481 Option 1)

Update `src/docline/_tools/docling_worker.py`:

1. Replace `markdown = "\n\n".join(pages)` + `output_path.write_text(markdown)` with:
   ```python
   envelope = {
       "schema_version": 1,
       "pages": pages,
       "page_count": len(pages),
       "text": "\n\n".join(pages),
   }
   output_path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
   ```
2. Extend module docstring to document the envelope format and schema_version.
3. Preserve all exit codes (0/2/3/4/5/6). If `json.dumps` raises (extremely unlikely for str-only content), exit 6 with diagnostic.

**Acceptance**: worker writes valid JSON; existing exit codes unchanged; failure modes unchanged.

**Estimate**: 1 hour.

### T2 — Consumers parse envelope; per-page splice-back is content-correct

Update `src/docline/process/pdf_batch.py` `_process_one_chunk`:

1. After exit 0, parse `output_path.read_text()` as JSON.
2. Use `envelope["text"]` as the `markdown` field of `ChunkResult` (preserves stitching behavior).
3. Add `chunk_pages: tuple[str, ...]` to `ChunkResult` carrying `envelope["pages"]` for downstream consumers that need per-page output.

Update `src/docline/process/pdf_triage.py` splice-back (lines 470-483):

1. Parse `splice_md.read_text()` as JSON.
2. Iterate `envelope["pages"]` and assign each to `final_pages[start + i]`.
3. If `len(envelope["pages"]) != (end - start + 1)`, log a warning and fall back to the old "first page gets blob, rest empty" behavior with `engine_per_page[i] = "docling-collapsed"` so the attribution mismatch becomes visible.

**Acceptance**: per-page fidelity restored; engine attribution accurate; new `chunk_pages` field on `ChunkResult` documented; backward-compat warning path exercised by unit test.

**Estimate**: 2-3 hours including tests.

### T3 — Multi-chunk batched worker mode (51332802 Strategy A)

Add `--batch BATCH_MANIFEST_JSON` mode to `docline._tools.docling_worker`. Update `pdf_batch.process_pdf_in_chunks` and `pdf_triage._splice_and_run_docling` to use the batched mode when `len(chunks) > 1` (configurable via a kwarg, default on).

**Acceptance**: a single subprocess invocation produces one envelope file per chunk; per-chunk fallback semantics preserved (failed chunks get error envelopes, healthy ones get pages); cosmos PA3+PA4 wall-clock improvement measurable (target: ≥30% reduction from cold-start dedup alone).

**Estimate**: 4-5 hours including tests + opt-in flag for cautious rollout.

### T4 — rt_detr batch size probe + commit chosen value

Write `scripts/study/docling_batch_size_probe.py`. Run against 2-3 representative cosmos splice ranges. Produce `docs/decisions/2026-06-14-docling-batch-size-probe.md` with results table and the chosen value (or "no exposed knob" finding). If a knob is exposed, set it as a constant in `_read_pdf_docling_pages`.

**Acceptance**: probe script runs end-to-end; decision doc committed; if batch size knob exists, it is set to the empirical winner; ruff/pyright clean.

**Estimate**: 2-3 hours empirical + 1 hour write-up.

### T5 — Per-page fidelity validation harness + closure

Add `scripts/study/per_page_fidelity_check.py` that:

1. Runs `process_pdf_triaged` against the cosmos sample.
2. For every page where `engine_per_page[i] == "docling"`, asserts `pages[i] != ""`.
3. For a stratified sample (5-10 pages), spot-checks that the docling-attributed content for page i actually corresponds to the visual content of page i (manual eyeball, with side-by-side PDF page screenshot + extracted markdown).

Write `docs/closure/032-S-docling-worker-contract.md` with:

- Verdict (likely PROMOTE — the change is purely additive)
- Per-page fidelity results
- Wall-clock improvement from T3 (cosmos PA3+PA4 before vs after)
- rt_detr batch size finding from T4
- Follow-up stash candidates (GPU spike, multi-chunk-per-file envelope, etc.)

**Acceptance**: zero `engine="docling"` pages with empty content; closure doc committed with empirical numbers; follow-ups filed.

**Estimate**: 2-3 hours.

## Total estimate

11-15 hours of focused work across T1-T5. Conforms to the 2-hour-per-task constitutional guidance after T2/T3 are decomposed during harvest if needed.

## Risk + rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Envelope schema breaks an unknown consumer | grep confirms only pdf_batch + pdf_triage read the worker output; CI runs full pytest | Revert T1; consumers fall back to text-read path on a JSONDecodeError catch (T2 adds this defensively) |
| Batched mode introduces a cross-chunk side-effect (docling state leak) | T3 unit-tests run 3+ chunks back-to-back and assert per-chunk output equals single-chunk output for each | Disable batched mode via the `--batch` flag default; orchestrator falls back to per-chunk loop |
| rt_detr batch size knob doesn't exist or isn't safe to set | T4 documents the finding and exits without code change | n/a |
| Per-page splice-back hits an edge case where docling collapses pages internally (e.g. continuous flow text) | T2 falls back to "first page gets blob, rest empty" with `engine="docling-collapsed"` attribution so downstream sees the mismatch explicitly | n/a — fallback is the rollback |
| Subprocess JSON parse failures mid-batch | Worker writes error envelopes per failed chunk; T3 unit-tests cover mixed success/failure batches | Single-chunk mode is unchanged and remains the fallback |

## Acceptance criteria (shipment-level)

1. Worker writes JSON envelopes; all existing tests pass; new envelope-format tests pass.
2. pdf_triage splice-back produces non-empty content for every page index where `engine="docling"`.
3. Multi-chunk batched mode is opt-in via a kwarg, defaults on for splice-back where N≥2 chunks.
4. Wall-clock improvement on a representative cosmos run is empirically measured and recorded.
5. rt_detr batch size is empirically probed; either a winning value is set as a constant, or the "no exposed knob" finding is documented.
6. Per-page fidelity validation harness passes against the cosmos sample.
7. Closure doc `032-S-docling-worker-contract.md` is committed with the verdict and follow-ups.
8. ruff check, ruff format, pyright, pytest all green.
9. PR merged via merge commit (P-009/P-011 compliant).
10. Two stash entries (`5CFE4481`, `51332802`) archived through harvest.
