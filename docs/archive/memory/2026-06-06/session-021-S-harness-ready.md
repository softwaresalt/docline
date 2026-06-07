---
type: session-memory
date: 2026-06-06
agent: orchestrator
shipment: 021-S
feature: 019-F
branch: feat/021-S-triage-then-repair
status: harness-ready
next_phase: build-feature
---

# Session memory — 021-S triage-then-repair pipeline run

## Origin

Operator asked about why `scripts/load_test.py` was taking ~9.5 hours on
`.elt/data/cosmosdb/azure-cosmos-db.pdf` (3,426 pages, 47 chunks of 75
pages each, ~12 min/chunk and rising). Diagnosis: CPU rt_detr layout
inference dominates; ~10 sec/page over 3,426 pages = ~9.5 h. Operator
asked for a hybrid heuristic-first + targeted-docling design.

Triage-then-repair design landed end-to-end through the orchestrator
pipeline in one session.

## Completed phases

### Stage

| Step | Artifact | Notes |
|---|---|---|
| Idea capture | stash `1301B14E` | high priority; archived after harvest |
| Decision | `docs/decisions/2026-06-06-triage-then-repair-pdf-pipeline.md` | 5 options compared; C selected |
| Plan | `docs/plans/2026-06-06-triage-then-repair-plan.md` | 7 units, dep graph, hardening signals |
| Plan hardening | appended in same file | 4 ProposedActions (PA1–PA4), 6 invariants, rollback triggers |
| Plan review | appended in same file | gate: **ADVISORY** (0 P0/P1, 2 P2, 4 P3) |
| Harvest | feature `019-F` + 7 tasks `019.001-T`…`019.007-T` | parent-first; 7 deps wired; spike-ref to `018-F` |
| Shipment assembly | `021-S` | parent-first item order |
| Staging gate | commit `0334f73` on origin/main | branch protection bypassed by operator admin rights |

### Ship (in progress)

| Step | Artifact | Notes |
|---|---|---|
| Claim shipment | `021-S` status → active | |
| Feature branch | `feat/021-S-triage-then-repair` | |
| harness-architect | 4 production stubs + 7 RED test files | commit `8d70895` pushed |
| Compilation | PASS | |
| Red phase | **34 failed, 0 passed** | clean — all expected NotImplementedError or AssertionError |
| Existing regression | `test_media_sidecars_in_manifest.py` (6 tests) PASS | output_contract.py extension is non-breaking |

## Files added or modified

### Source

* `src/docline/process/fidelity_scorer.py` (new, ~120 LOC stub)
* `src/docline/process/page_range.py` (new, ~40 LOC stub)
* `src/docline/process/pdf_triage.py` (new, ~180 LOC stub — includes
  `TriageResult`, `QASampling`, `process_pdf_triaged`,
  `triage_report_only`, `dispatch_pdf_mode`)
* `src/docline/process/output_contract.py` (extended with
  `apply_triage_attribution`, `build_triage_part_payloads`,
  `build_triage_manifest_stats` stubs)

### Tests

* `tests/process/test_fidelity_scorer.py` (7 RED, U1)
* `tests/process/test_page_range.py` (7 RED, U2)
* `tests/process/test_pdf_triage.py` (4 RED, U3)
* `tests/process/test_pdf_triage_report_only.py` (3 RED, U6)
* `tests/process/test_pdf_triage_tripwire.py` (4 RED, U7)
* `tests/process/test_output_contract_engine_attribution.py` (4 RED, U5)
* `tests/test_pdf_mode_flag.py` (5 RED, U4)

### Reference

* `docs/scratch/2026-06-06-fidelity-scorer-poc.py` — POC scorer with
  7 signal functions + coalescer. Validated against synthetic samples
  (gitignored per scratch convention; harness scaffold lifts from it).

## What the next session needs to do

**Run `build-feature` skill** on the harness-ready tasks. Dependency
order is encoded in the backlog (see plan § Dependency graph):

```
U1 (019.001-T) and U2 (019.002-T)  ← parallel; no deps
    ↓
U3 (019.003-T)                      ← blocks on U1+U2
    ↓
{U4 (019.004-T), U5 (019.005-T), U6 (019.006-T), U7 (019.007-T)}
    ↑   (U6 also blocks on U4)
```

Recommended single-session approach:

1. Implement U1 and U2 in parallel (no deps, small modules, ~2 h each).
2. Implement U3 (the orchestrator — biggest unit, ~3 h with all
   the splice/runner/fallback handling).
3. Implement U4 and U5 in parallel (CLI flag + output contract).
4. Implement U6 (calibration mode) and U7 (QA tripwire).
5. Run full pytest suite to verify nothing else broke.
6. Then `review` → `fix-ci` → `pr-lifecycle`.

The POC at `docs/scratch/2026-06-06-fidelity-scorer-poc.py` is the
reference implementation for U1 — lift it largely as-is, add typed
exception (`FidelityScorerError(DoclineError)`), JSON weight loader,
and explicit type annotations.

## Harness command

```powershell
.\.venv\Scripts\python.exe -m pytest tests/process/test_fidelity_scorer.py tests/process/test_page_range.py tests/process/test_output_contract_engine_attribution.py tests/process/test_pdf_triage.py tests/process/test_pdf_triage_report_only.py tests/process/test_pdf_triage_tripwire.py tests/test_pdf_mode_flag.py -p no:cacheprovider --tb=short
```

## Decisions captured for the next session

* P2 from plan review: `process_pdf_triaged` MUST NOT take 12 kwargs.
  U6 implements a sibling function `triage_report_only`. U7 introduces
  a `QASampling` frozen dataclass kwarg.
* P2 from plan review: `TriageResult` MUST be `@dataclass(frozen=True)`.
  Already enforced in stub.
* Plan hardening Invariant #3: U5 must MERGE into `docline:` namespace,
  never overwrite (compound learning 013-S applies).
* Calibration step: run `--triage-report-only` against the 12 completed
  cosmos chunks under `.elt/output/azure-cosmos-db/chunks-md/` before
  recommending triage mode for production use. Calibration produces
  `src/docline/process/fidelity_weights.json`. **Defer to follow-on
  shipment**; this shipment only delivers the mechanism.

## Open follow-on stash items (not included in 021-S)

* `7AA9FAA0` — PyPI release workflow (low priority, deferred)
* `4CA80776` — docling OCR tuning (low priority, deferred; would
  conflict with triage work on `_read_pdf_docling_pages` if both ran
  concurrently)

## Pipeline state

* `021-S` shipment: **active** on `feat/021-S-triage-then-repair`
* `019-F` feature: active
* 7 tasks `019.001-T`…`019.007-T`: active, harness-ready
* Stash: 2 items remaining (both low priority, both deferred)
* No PR yet — needs build-feature → review → fix-ci before PR creation.

## Constraint reminder

Per the 2026-06-04 RCA: docling load tests MUST be run from a plain
PowerShell session, NOT inside an AI agent's tool calls — the Copilot
CLI co-hosted process can trigger the paging spiral. This shipment's
runtime verification step (PA3 — full cosmos triage run) should
follow that constraint.
