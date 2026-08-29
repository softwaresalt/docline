---
title: Plan — Triage-then-repair hybrid PDF pipeline
date: 2026-06-06
source: docs/decisions/2026-06-06-triage-then-repair-pdf-pipeline.md
poc_script: docs/scratch/2026-06-06-fidelity-scorer-poc.py
stash: 1301B14E
related_rca: docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md
related_shipments: 018-S, 019-S, 020-S
---

# Plan — Triage-then-repair hybrid PDF pipeline

## Problem frame

`docline.process.pdf_batch.process_pdf_in_chunks` is the production
entry point for any PDF that exceeds the
`docline.runtime.resource_probe.probe()` budget. It splits the input
into page-aligned chunks, runs the `docline._tools.docling_worker`
subprocess on each chunk, and stitches per-chunk markdown into the
final output. Every page goes through CPU rt_detr layout inference at
~10 sec/page on the RCA host class, regardless of whether the page
needs that fidelity.

We introduce a peer entry point `process_pdf_triaged` (in a new
`src/docline/process/pdf_triage.py`) that runs the heuristic engine
across the whole document for a fast baseline, scores each page with
deterministic fidelity signals via a new `fidelity_scorer.py` module,
coalesces flagged page indices into ranges via a new `page_range.py`
module, splices just those page ranges into temp PDFs using the
existing `pypdf.PdfWriter` machinery from `readers/pdf_splitter.py`,
runs `docling_worker` on each splice, and merges per-page outputs into
a final list. CLI exposure via a new `--pdf-mode triage` selector that
is a peer of the existing `--pdf-engine` resolution paths.

## Requirements trace

| Requirement (from decision doc § Acceptance criteria) | Implementation unit |
|---|---|
| New `--pdf-mode triage` CLI flag | U4 |
| Triage mode produces page-identical output to all-docling for flagged pages and all-heuristic for unflagged | U3 |
| Per-page engine attribution recorded in output contract | U5 |
| `--report-only` mode emits per-page TSV without running docling | U6 |
| `--sample-rate FLOAT` QA tripwire mode | U7 |
| Empirical wall-clock on cosmos ≤ 25 % of baseline | Validated by runtime verification step after U3+U4 land |
| All existing pipeline modes (`auto`, `heuristic`, `docling`) unchanged | Guaranteed by additive flag surface; verified by U4 regression tests |

## Module placement

| New / changed | Purpose |
|---|---|
| `src/docline/process/fidelity_scorer.py` (new, ~250 LOC) | Pure-function per-page signal functions + `score_page()` combiner returning a `PageScore` frozen dataclass |
| `src/docline/process/page_range.py` (new, ~80 LOC) | `coalesce_ranges()` — flagged indices → list of `(start, end)` tuples with context buffer and merge-gap |
| `src/docline/process/pdf_triage.py` (new, ~200 LOC) | `process_pdf_triaged()` 5-pass orchestrator mirroring `pdf_batch.py` shape |
| `src/docline/cli.py` (modified) | Add `--pdf-mode` flag with `auto` (default) / `triage` values; wire `triage` to `process_pdf_triaged` |
| `src/docline/process/output_contract.py` (modified) | Add per-page engine attribution field to part frontmatter; manifest summary statistics |
| `tests/process/test_fidelity_scorer.py` (new) | Per-signal unit tests + combiner + edge cases |
| `tests/process/test_page_range.py` (new) | Coalescer with various flag patterns + boundary conditions |
| `tests/process/test_pdf_triage.py` (new) | End-to-end 5-pass orchestration with mocked docling runner |
| `tests/process/test_pdf_triage_report_only.py` (new) | TSV emission, no-docling-invocation guarantee |
| `tests/process/test_pdf_triage_tripwire.py` (new) | Sample-rate sampling, disagreement counting |
| `tests/cli/test_pdf_mode_flag.py` (new) | CLI flag wiring; regression coverage for existing modes |
| `tests/process/test_output_contract_engine_attribution.py` (new or extension) | Per-page engine field round-trip |

## Implementation units

Each unit follows the 2-hour rule (< 3 files, < 5 functions, < 4 test scenarios),
width isolation (single domain per unit), and atomic milestone (verifiable
state change). Test-first execution posture throughout per Constitution II.

### U1 — Fidelity scorer module

* **Files**: `src/docline/process/fidelity_scorer.py` (new),
  `tests/process/test_fidelity_scorer.py` (new)
* **Changes**: Lift POC from `docs/scratch/2026-06-06-fidelity-scorer-poc.py`
  with the following hardening:
  * Replace hard-coded `_SIGNAL_WEIGHTS` dict with a module-level
    constant that can be overridden via a JSON file path passed to
    `score_page` (loads on first call, cached).
  * Type all public APIs strictly; `PageScore` stays frozen.
  * Custom exception `FidelityScorerError(DoclineError)` for any
    input-validation failure.
* **Tests** (RED first):
  1. Each signal function on a 1-line input that should and should not trigger.
  2. `score_page` combiner: clean prose → no flag; each of the five POC
     failure modes → flagged with the right reason.
  3. `score_page` with `page_metadata=None` falls through gracefully.
  4. Weight override via JSON loads and is applied.
* **Execution posture**: Test-first.

### U2 — Page-range coalescer module

* **Files**: `src/docline/process/page_range.py` (new),
  `tests/process/test_page_range.py` (new)
* **Changes**: Lift `coalesce_ranges` from POC. Add input validation
  (`buffer >= 0`, `merge_gap >= 0`, `total_pages >= 0`).
* **Tests** (RED first):
  1. Empty input → empty output.
  2. Single flagged index → single range with ±buffer.
  3. Adjacent flagged indices merge correctly across the gap threshold.
  4. Boundary clamping: flags at index 0 and `total_pages - 1` clamp.
* **Execution posture**: Test-first.

### U3 — Triage orchestrator module

* **Files**: `src/docline/process/pdf_triage.py` (new),
  `tests/process/test_pdf_triage.py` (new)
* **Changes**:
  * `process_pdf_triaged(path, *, output_dir, budget=None, runner=None,
    scorer=None, buffer=1, merge_gap=2)` — mirrors `process_pdf_in_chunks`
    signature with injectable scorer/runner for tests.
  * 5 passes: heuristic → score → coalesce → splice+docling → merge.
  * Returns a new `TriageResult` dataclass with `pages`, `engine_per_page`,
    `flagged_ranges`, `metadata`.
* **Tests** (RED first):
  1. Mocked scorer flags no pages → all-heuristic path, no docling invocation.
  2. Mocked scorer flags 3 of 10 pages → docling invoked on a single
     coalesced range, splice correctly merges.
  3. Heuristic engine raises on one page → page replaced with empty
     string, batch continues.
  4. Docling subprocess fails for a range → range falls back to heuristic
     pages for that range; logged.
* **Execution posture**: Test-first. Uses `_make_pdf` helper pattern
  from existing `tests/process/test_pdf_batch.py`.

### U4 — CLI `--pdf-mode` flag

* **Files**: `src/docline/cli.py` (modified),
  `tests/cli/test_pdf_mode_flag.py` (new)
* **Changes**:
  * Add `--pdf-mode {auto,triage}` choice arg; default `auto`.
  * When `triage`, route the process phase through `process_pdf_triaged`
    instead of `process_pdf_in_chunks` for PDFs.
  * Preserve all existing `--pdf-engine` behavior; the two flags are
    orthogonal (mode = orchestration strategy; engine = within-mode
    extractor choice).
* **Tests** (RED first):
  1. `docline --manifest` output includes the new flag definition.
  2. Default mode (no `--pdf-mode`) invokes `process_pdf_in_chunks`
     (regression coverage).
  3. `--pdf-mode triage` invokes `process_pdf_triaged`.
  4. Invalid value rejected with argparse error.
* **Execution posture**: Test-first.

### U5 — Output contract per-page engine attribution

* **Files**: `src/docline/process/output_contract.py` (modified),
  `tests/process/test_output_contract_engine_attribution.py` (new
  or extension of an existing test file in the same area)
* **Changes**:
  * Add `engine` field to part frontmatter (values: `heuristic`,
    `docling`).
  * Add manifest-level summary: `triage_stats: {pages_total: N,
    pages_docling: N, pages_heuristic: N, flagged_ranges: N}`.
  * Fields are absent for non-triage runs (no schema break).
* **Tests** (RED first):
  1. Round-trip a `TriageResult` through the contract producer; verify
     each part has the right `engine` value.
  2. Manifest summary matches actual per-page counts.
  3. Non-triage run produces output identical to today (no new fields).
* **Execution posture**: Test-first.

### U6 — `--report-only` validation mode

* **Files**: `src/docline/process/pdf_triage.py` (modified — add
  `report_only` parameter and TSV emitter),
  `tests/process/test_pdf_triage_report_only.py` (new)
* **Changes**:
  * `process_pdf_triaged(..., report_only=False, report_tsv_path=None)`.
  * When `report_only=True`: run passes 1–2 (heuristic + score), emit
    TSV `(page_index, signal_name=value..., aggregate, needs_docling,
    reason)`, return `TriageResult` with `engine_per_page=["heuristic"] *
    total_pages` and `flagged_ranges` populated for reporting.
  * CLI exposure: `--pdf-mode triage-report` or `--triage-report-only`
    boolean; decide in implementation review.
* **Tests** (RED first):
  1. `report_only=True` never invokes the docling runner (assert
     `runner.call_count == 0`).
  2. TSV file is created with the canonical columns and one row per page.
  3. TSV rows are sorted by `page_index` ascending.
* **Execution posture**: Test-first.

### U7 — `--sample-rate` QA tripwire mode

* **Files**: `src/docline/process/pdf_triage.py` (modified — add
  `qa_sample_rate` parameter and disagreement counter),
  `tests/process/test_pdf_triage_tripwire.py` (new)
* **Changes**:
  * `process_pdf_triaged(..., qa_sample_rate=0.0, qa_random_seed=None)`.
  * When `qa_sample_rate > 0`: randomly select that fraction of
    *unflagged* pages, run docling on each, compute markdown diff
    against the heuristic output, record disagreement count in
    `TriageResult.metadata["qa_disagreements"]`.
  * Cap sampled pages at `max(50, int(total_pages * qa_sample_rate))`
    to bound runtime on long docs.
  * Random seed is recorded in metadata for reproducibility.
* **Tests** (RED first):
  1. `qa_sample_rate=0.0` invokes runner only for flagged ranges.
  2. `qa_sample_rate=1.0` invokes runner for every unflagged page
     (subject to cap).
  3. Disagreement counter increments when sampled-docling output
     differs from heuristic.
  4. Random seed makes the sample selection deterministic.
* **Execution posture**: Test-first.

## Dependency graph

```text
U1 (scorer) ────┐
                ├──> U3 (orchestrator) ──> U4 (CLI) ──> runtime verification ──> closure
U2 (coalescer)──┘                       └──> U5 (output contract)
                                        └──> U6 (report-only)
                                        └──> U7 (tripwire)
```

* U1 and U2 are independent and can be implemented in parallel.
* U3 blocks U4, U5, U6, U7.
* U5 is parallel to U4 once U3 lands.
* U6 and U7 can be implemented in either order after U3.
* Calibration of `_SIGNAL_WEIGHTS` (an open question, not an
  implementation unit) becomes possible after U6 ships — pushed to a
  follow-on shipment.

## Decisions and rationale

| Decision | Rationale |
|---|---|
| New `--pdf-mode` flag, peer of `--pdf-engine` | Mode = orchestration strategy; engine = within-mode extractor. Composing them is meaningful (`--pdf-mode triage --pdf-engine docling` could re-run repair pass with engine variations in future). Avoids overloading `--pdf-engine` with mode semantics. |
| Lift POC into `src/` rather than rewrite | POC already passes synthetic discrimination; rewriting risks losing signal nuance. Test-first ensures behavior locks in. |
| Per-page engine attribution in part frontmatter, not just manifest | Downstream graphtor reads part frontmatter directly; manifest is summary-only. Both consumers need the data; both get it. |
| Triage uses sequential subprocess invocations (no parallel chunks) | Matches existing `process_pdf_in_chunks` posture; preserves the 018-S reclaim-pause throttling discipline. Parallel splice processing is deferred to a follow-on shipment after the load-test harness re-runs validate the sequential baseline. |
| Report-only mode emits TSV, not JSON | Matches existing `scripts/load_test.py` TSV pattern; one-row-per-page is the right shape for spreadsheet calibration analysis. |
| Tripwire mode samples *unflagged* pages | Flagged pages will be re-run by docling anyway; the tripwire is specifically for catching false-negative under-flagging. |

## Plan hardening signals (REQUIRED)

| Signal | Present? | Justification |
|---|---|---|
| public API, schema, or contract change | **Yes** (additive) | New CLI flag `--pdf-mode`; new output contract frontmatter field `engine`; new manifest summary block `triage_stats`. All additive — no existing field removed or repurposed. |
| security, auth, permission, or compliance-sensitive behavior | No | No auth, secrets, or external network. Filesystem operations stay under `output_dir` per Constitution III/IV. |
| migration, backfill, destructive data/config action, or irreversible step | No | Opt-in flag; default behavior unchanged. No data migration; no destructive operations. Cache files under `output_dir/chunks` follow existing splitter conventions. |
| external integration, operator checkpoint, or external dependency | No | Uses existing docling extra; pypdf already required; no new dependencies. |
| high runtime, rollout, or rollback risk | **Yes** (mild) | Touches the production batch path when enabled. Rollback path is "use any other `--pdf-mode` value" — flag-driven, no data conversion to reverse. Runtime risk concentrated in scorer accuracy; mitigated by `--report-only` calibration before production use and `--sample-rate` QA tripwire. |

**Requires plan hardening: yes**

Justification: the runtime-risk signal combined with an additive public
API change (output contract) warrants plan-harden review before
implementation begins, even though no individual signal is severe.
plan-harden should deepen: (a) the rollback story for in-flight runs
that produced mixed-engine output, (b) the calibration workflow that
gates production use of triage mode, and (c) the runtime-verification
plan that exercises the `--report-only` mode against the existing
cosmos chunks before any production batch invocation.

## Runtime verification and closure

| Unit | Runtime surface changed? | Verification before closure |
|---|---|---|
| U1 (scorer) | No | Pytest sufficient. |
| U2 (coalescer) | No | Pytest sufficient. |
| U3 (orchestrator) | Yes — new orchestration entry point | Run `process_pdf_triaged` against a small fixture PDF (5–10 pages, mixed page types); verify per-page engine attribution matches expected pattern. |
| U4 (CLI) | Yes — new flag | `docline process --pdf-mode triage` against a small fixture PDF end-to-end; verify TSV/markdown outputs. |
| U5 (output contract) | Yes — new frontmatter field | Inspect emitted part files; confirm `engine` field present in triage runs, absent in non-triage runs. |
| U6 (report-only) | Yes — new mode | Run `--pdf-mode triage --report-only` against the existing 12 completed cosmos chunks; compare flag pattern against where docling actually produced richer output; tune thresholds. **This is the calibration step.** |
| U7 (tripwire) | Yes — new mode | Run with `--sample-rate 0.1` on a small fixture; verify disagreement counter behavior. |
| End-to-end runtime validation | Yes — new pipeline mode | Run full triage pipeline against the cosmos PDF; measure wall-clock; record per-page engine distribution; compare output fidelity against a curated sample from the all-docling run. |

Operational closure artifacts:

* `docs/closure/{NNN}-S-triage-pipeline.md` — verified status, merged PR,
  merge SHA, runtime measurements (cosmos wall-clock before/after,
  per-page engine distribution histogram).
* `docs/compound/2026-06-{NN}-triage-then-repair-pattern.md` — capture
  the pattern itself as a reusable learning for future selective-ML
  orchestration scenarios.
* Update `docs/ARCHITECTURE.md` if pipeline diagram exists, noting
  the new triage entry point as a peer of `process_pdf_in_chunks`.

## Risks and caveats

| Risk | Mitigation |
|---|---|
| Scorer thresholds wrong for non-cosmos PDFs | Mitigated by U6 calibration workflow; weights are externalized to JSON for per-corpus tuning |
| `qa_sample_rate` re-runs become expensive on long docs | Hard cap at 50 sampled pages per run; sampling is opt-in, not default |
| New module trio expands the surface area for future maintenance | Module boundaries are intentionally narrow: scorer is pure functions, coalescer is one function, orchestrator mirrors existing `pdf_batch.py` shape — patterns are consistent |
| CLI flag composition (`--pdf-mode triage --pdf-engine ???`) creates a matrix of behaviors to test | U4 tests enumerate the meaningful combinations; documented in CLI help |
| Existing 020-S load-test harness needs a new flag to drive triage mode | Out of scope for this shipment; loop back as a follow-on task when calibration is complete |
| Bias in the scorer toward false positives could erode the speedup | Calibration step (U6) measures actual flag rate against a curated truth set before production use |

## Plan Hardening

### Hardening required and why

Required: **yes**. Risk triggers from the impl-plan signals:

1. Additive public API surface in the output contract (`engine` field
   per-part frontmatter; `triage_stats` block in manifest summary).
2. New CLI orchestration mode (`--pdf-mode triage`) that touches the
   production batch path when enabled.
3. Scorer-driven routing decisions that can silently degrade fidelity
   if thresholds are wrong for a given corpus.

Although no individual signal is severe, the combination — additive
contract change + new production code path + accuracy-dependent
routing — warrants explicit invariants, operator-visible verification
gates, and a documented rollback path before plan-review.

### Learnings and instructions consulted

| Source | Relevance |
|---|---|
| `docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md` | Motivating incident; confirms the rt_detr CPU inference profile and the need for selective ML invocation |
| `docs/decisions/2026-06-04-spike-h1-header-synthesis.md` | Empirical evidence that the heuristic engine recovers usable content from the cosmos corpus (554 parts under heuristic-only), validating the "heuristic as baseline" premise of triage mode |
| `docs/compound/2026-06-04-pydantic-namespace-merge-vs-overwrite.md` | Pattern lesson for U5 output-contract change: any merge into the `docline:` namespace block must merge, not overwrite — applies directly to where the `engine` field lands |
| `docs/compound/2026-06-04-ship-shipment-commit-traceability-gap.md` | Ship-side closure hygiene; informs the closure artifact format only, not the implementation |
| `.github/instructions/strict-safety.instructions.md` | Action classification vocabulary used below |

### Protected invariants

Implementation MUST NOT violate any of the following. Each invariant
gets at least one regression test.

| Invariant | Verification |
|---|---|
| Default mode behavior (`--pdf-mode auto` or unset) produces output bit-identical to today | U4 regression test asserts byte-equal output for a fixture PDF with and without the flag present at the default value |
| Triage-mode output for fixed `(PDF, scorer weights, runner)` inputs is deterministic | U3 test fixes a deterministic mocked runner + a frozen weights file; asserts identical `TriageResult` across two invocations |
| The `engine` frontmatter field is **merged** into the `docline:` namespace, never overwritten | U5 test seeds the namespace with `source_url` and `crawl_depth`, runs triage emission, asserts all three keys survive (per the 013-S compound lesson) |
| No new dependencies introduced | CI dependency-diff check; ruff/import audit |
| Splice temp files stay within `output_dir`/`cache_dir` (Constitution IV) | U3 test sets `output_dir=tmp_path`, asserts no file writes outside `tmp_path` after orchestration |
| When docling subprocess fails for a flagged range, the range falls back to heuristic — batch never aborts on a single failure | U3 test injects a runner that returns non-zero exit code; asserts range pages are populated from heuristic output and `TriageResult.metadata` records the fallback |

### Risky actions (ProposedAction / ActionRisk / ActionResult)

Carried forward into review, verification, and closure. Each action
must reach `applied` or `abandoned` before the shipment can close.

#### PA1 — Land `--pdf-mode triage` wired to the production batch path

| Field | Value |
|---|---|
| `summary` | New CLI flag routes PDFs through `process_pdf_triaged` when enabled |
| `targets` | `src/docline/cli.py`, `src/docline/process/pdf_triage.py`, `src/docline/process/output_contract.py` |
| `change_kind` | Additive code + opt-in CLI surface |
| `rollback` | Operator omits the flag or sets `--pdf-mode auto`; no data conversion needed |
| `approval_required` | No (additive, opt-in, default unchanged) |
| `ActionRisk` | **moderate** |
| Initial `ActionResult` | `planned` |

#### PA2 — Add `engine` field to part frontmatter `docline:` namespace

| Field | Value |
|---|---|
| `summary` | Output contract gains a per-part `engine` field under the `docline:` namespace |
| `targets` | `src/docline/process/output_contract.py`, all downstream consumers that read part frontmatter |
| `change_kind` | Additive schema change |
| `rollback` | Field is optional in non-triage runs; absent fields are tolerated by all existing consumers — verify before landing |
| `approval_required` | No |
| `ActionRisk` | **moderate** (touches the contract surface that graphtor reads) |
| Initial `ActionResult` | `planned` |

#### PA3 — First end-to-end triage run on `azure-cosmos-db.pdf`

| Field | Value |
|---|---|
| `summary` | Runtime verification: full triage run on the cosmos PDF |
| `targets` | `.elt/data/cosmosdb/azure-cosmos-db.pdf` (input), `.elt/output/` (output) |
| `change_kind` | Local read + local write to test directory; no committed state |
| `rollback` | Delete output directory; no rollback needed for source data |
| `approval_required` | No (read-only on source, write to local test dir) |
| `ActionRisk` | **low** |
| Initial `ActionResult` | `planned` |

#### PA4 — Lock-in default `_SIGNAL_WEIGHTS` based on calibration

| Field | Value |
|---|---|
| `summary` | Replace POC guess-weights with empirically-derived weights file |
| `targets` | `src/docline/process/fidelity_weights.json` (new) |
| `change_kind` | Data file update; reversible |
| `rollback` | Revert the JSON file via git; the scorer falls back to module defaults if the file is absent |
| `approval_required` | No — but the calibration output must be reviewable; emit calibration TSV alongside the JSON file as documentation |
| `ActionRisk` | **low** |
| Initial `ActionResult` | `planned` (cannot proceed until U6 ships) |

### Deepened runtime verification

#### Environment prechecks (before any triage invocation)

* Confirm `docling` extra is installed (existing dependency probe).
* Confirm `pypdf` parses the input without `PdfReadError` (existing check).
* Confirm `output_dir` is writable AND under `cwd` per Constitution IV.
* Confirm the weights JSON file is loadable OR fall through to defaults
  with a logged warning.

#### Calibration gate (before recommending triage mode for production use)

This is the **operator-visible checkpoint** introduced by hardening.
Recommended workflow before triage becomes the default for any corpus:

1. Run `docline process --pdf-mode triage --triage-report-only
   --report-tsv-path logs/triage-report-{corpus}.tsv` against a
   representative subset of the corpus.
2. Inspect the TSV: flag rate should land between **5 % and 25 %**.
   * Below 5 %: thresholds too lenient; scorer is missing degraded
     pages. Raise `_HARD_FLAG_THRESHOLD` downward or increase
     individual signal weights.
   * Above 25 %: thresholds too strict; speedup will be limited.
     Raise thresholds upward.
3. Spot-check 10 flagged + 10 unflagged pages by reading the source PDF
   page alongside the heuristic markdown output.
4. Lock weights into `fidelity_weights.json` only after the spot-check
   agrees with the scorer judgment.

#### Target verification scenarios

| Scenario | What it proves |
|---|---|
| Triage on a 5-page fixture with one mocked-flagged page | End-to-end orchestration: heuristic baseline + 1 docling splice + correct splice-back |
| Triage on cosmos PDF, full run | Wall-clock target ≤ 2.4 h (Acceptance Criterion 6); per-page engine distribution recorded |
| Triage with `--sample-rate 0.05` on cosmos | Tripwire disagreement count is non-zero (proves the sampler runs) but within expected bounds (< 5 % disagreement on cosmos heuristic-quality pages) |
| Existing pipeline regression: full `pytest` suite passes unchanged | No collateral damage to other doc-type paths |
| `docline --manifest` output snapshot | New `--pdf-mode` flag visible in tool definition |

#### Blocked-path handling

If runtime verification cannot reach `applied` for PA3 within one
business day of U4 landing, halt the shipment and re-run calibration
(U6). The shipment MUST NOT close with PA3 in `planned` or `blocked`.

### Deepened operational closure

#### Monitoring signals (recorded automatically per triage run)

* Per-page engine distribution: `pages_total`, `pages_docling`,
  `pages_heuristic`, `flagged_ranges` (emitted in manifest summary
  per U5).
* Per-run wall-clock and pages-per-second throughput (extend the
  existing 020-S load-test TSV columns).
* QA tripwire disagreement count when `--sample-rate > 0`.
* Subprocess fallback count: how many flagged ranges fell back to
  heuristic because docling failed.

#### Rollback triggers (any of these triggers immediate fallback to `--pdf-mode auto`)

1. Triage output fails downstream schema validation.
2. QA tripwire disagreement rate exceeds **20 %** on a single run.
3. Flag rate exceeds **40 %** of pages (scorer is over-firing; speedup
   gone).
4. Subprocess fallback count exceeds **10 %** of flagged ranges
   (docling is broken for splices; triage gives no benefit).

#### Rollback procedure

Triage is opt-in via a CLI flag and adds only optional output-contract
fields. Rollback is a configuration change, not a data migration:

1. Stop invoking `--pdf-mode triage` (revert to `auto`).
2. No data conversion needed — output contract additions are optional;
   existing consumers tolerate their absence.
3. If a partial corpus was processed with triage and downstream
   consumers need uniform output, re-run those documents under
   `--pdf-mode auto` to overwrite.

#### Owner and validation window

* Owner: current docline maintainer (single-maintainer workspace).
* Validation window: monitor the first 5 production triage invocations
  via logs and manifest summary stats. If any rollback trigger fires,
  halt and re-calibrate. After 5 clean runs, triage is considered
  stable for the calibrated corpus.

### Operator checkpoints

| Checkpoint | When | What is decided |
|---|---|---|
| Calibration acceptance | Before triage is recommended for production use on any new corpus | Are signal thresholds correct? Is flag rate in the 5–25 % band? Do spot-checks agree with scorer judgments? |
| First production triage run | After U7 lands and before bulk processing | Run with `--sample-rate 0.05` enabled to catch undetected false negatives early |
| Shipment close | All `ProposedAction` entries above must reach `applied` or `abandoned` | Are PA1–PA4 each resolved with evidence in closure doc? |

### Unresolved decisions still blocking safe execution

| Open question | Resolution path | Blocking? |
|---|---|---|
| Where exactly does the `engine` field live in the part frontmatter — top-level or `docline:` namespace? | Decided by U5 implementation; pydantic-namespace-merge lesson (013-S compound) recommends the `docling:` namespace with explicit merge | Not blocking — implementation decision |
| Should `--triage-report-only` be a separate `--pdf-mode` value or a boolean modifier? | Decided by U6 implementation. Recommend boolean modifier (`--triage-report-only`) for ergonomic composability with `--sample-rate` and weights overrides | Not blocking — UX decision |
| What is the precise weights-JSON schema? | Decided during U6 implementation; trivial flat dict mirroring `_SIGNAL_WEIGHTS` plus a `schema_version` field for forward compat | Not blocking — implementation decision |
| Should the calibration gate workflow be enforced in code (refuse to run triage without a weights file present) or only documented? | Recommend **documented only** in V1; enforcement adds friction without proportionate safety value when defaults exist. Revisit if a rollback trigger fires in production | Not blocking — policy decision |

## Plan Review

**Gate decision**: **ADVISORY** (proceed with operator acknowledgment).

**Hardening compliance**: Hardening was required and is present.
`ProposedAction` / `ActionRisk` / `ActionResult` classification covers
the four risky actions (PA1–PA4). Protected invariants are testable.
Rollback and monitoring are specified. ✓

**Personas spawned**: Constitution Reviewer, Python Reviewer, Scope
Boundary Auditor, Learnings Researcher, Architecture Strategist.
Agent-Native Parity Reviewer and Security Lens Reviewer **not
triggered** (no MCP/agent-facing surface change, no auth/secrets/data
store changes, no external trust-boundary crossings).

**Severity summary**: 0 P0, 0 P1, 2 P2, 4 P3. ADVISORY gate.

### Findings

#### P2 — Function-shape complexity in `process_pdf_triaged`

| Field | Value |
|---|---|
| Persona | Python Reviewer |
| Unit | U3 + U6 + U7 |
| Issue | `process_pdf_triaged` ends up with `(path, *, output_dir, budget, runner, scorer, buffer, merge_gap, report_only, report_tsv_path, qa_sample_rate, qa_random_seed)` — twelve kwargs spanning three orthogonal concerns (orchestration, reporting, QA sampling). |
| Recommendation | During U6 implementation, factor reporting into a sibling function `triage_report_only(path, *, output_dir, ...)` that shares the Pass 1–2 path with the orchestrator. During U7, group QA params into a small `QASampling` frozen dataclass passed as a single kwarg. Keeps the public surface narrow and makes future modes (e.g. parallel splice processing) easier to layer in. |
| Action | Defer to implementation; harness-architect should reflect the factoring in test scaffolds. |

#### P2 — `TriageResult` should be frozen for thread safety and consumer-side caching

| Field | Value |
|---|---|
| Persona | Python Reviewer |
| Unit | U3 |
| Issue | Plan describes `TriageResult` as a dataclass but does not specify `frozen=True`. Existing peer `BatchResult` in `pdf_batch.py` is `@dataclass(frozen=True)`. Consistency matters; downstream code may hash or cache the result. |
| Recommendation | Explicitly require `@dataclass(frozen=True)` for `TriageResult` and `PageScore`. POC already has `PageScore` frozen — propagate the same constraint to `TriageResult` in the U3 spec. |
| Action | Land as a test assertion in U3 RED phase (`assert not dataclasses.replace(result, pages=[])` style — verify immutability). |

#### P3 — `qa_random_seed=None` semantics not specified

| Field | Value |
|---|---|
| Persona | Python Reviewer |
| Unit | U7 |
| Issue | `None` could mean "non-deterministic system clock seed" or "use a fixed default seed". Plan does not say which. |
| Recommendation | Document `None` = system-clock seed (`random.Random()`); explicit integer = deterministic. Record the resolved seed in `TriageResult.metadata` regardless. |
| Action | Resolve in U7 implementation; not blocking. |

#### P3 — `page_range.py` cohesion question

| Field | Value |
|---|---|
| Persona | Architecture Strategist |
| Unit | U2 |
| Issue | The coalescer is one ~80-LOC function used only by `pdf_triage.py`. A separate module is arguably over-decomposed. |
| Recommendation | Keep `page_range.py` as proposed. Rationale: pure-function isolation aids unit testing and possible future reuse by other selective-extraction pipelines (e.g., a future "only extract pages with images" tool). The cost of a tiny module is negligible; the cost of having to extract it later is real. Advisory only. |
| Action | None required. |

#### P3 — Future common abstraction across `pdf_batch.py` and `pdf_triage.py`

| Field | Value |
|---|---|
| Persona | Architecture Strategist |
| Unit | U3 |
| Issue | The splice-then-subprocess-then-stitch pattern is now duplicated across `process_pdf_in_chunks` and `process_pdf_triaged`. They differ in how page ranges are chosen (uniform stride vs scorer-driven) but share the per-range subprocess execution and fallback semantics. |
| Recommendation | Do NOT refactor in this shipment — premature abstraction risks coupling the modes. After triage mode is calibrated and shipped, evaluate whether a `_run_ranges_via_subprocess(ranges, runner, fallback) -> list[ChunkResult]` helper extracted into `pdf_chunk_runner.py` would clean things up. Capture as a stash entry for a future shipment. |
| Action | Add a stash entry after this shipment closes (track in closure doc). |

#### P3 — Explicit reference to `DoclineError` lineage location

| Field | Value |
|---|---|
| Persona | Constitution Reviewer |
| Unit | U1 |
| Issue | Plan says `FidelityScorerError(DoclineError)` but does not cite the import path. Verified locally: `DoclineError` lives at `src/docline/schema/models.py:9`. |
| Recommendation | Add the import path to U1's module placement table so the harness scaffold imports the right symbol. |
| Action | Trivial — captured here, no plan edit required. |

### Constitution principles coverage

| Principle | Plan coverage |
|---|---|
| I — Safety-first Python | ✓ All units state typed APIs; `FidelityScorerError(DoclineError)` follows the typed-exception lineage |
| II — Test-first | ✓ Every unit has explicit RED test list with named scenarios |
| III — Workspace isolation | ✓ All new modules under `src/docline/process/` and `tests/process/` |
| IV — CLI containment | ✓ Invariant tested: no writes outside `output_dir`/`cache_dir` |
| V — Structured observability | ✓ Per-page engine attribution + TSV emission + manifest summary |
| VI — Single responsibility | ✓ Invariant: no new dependencies |
| VII — Destructive approval | ✓ No destructive actions; PA1–PA4 are all moderate/low risk |
| VIII — Safety modes | ✓ Plan-harden completed; ProposedAction vocabulary used (strict-safety pack) |
| IX — Git-friendly persistence | ✓ Output is markdown + YAML; weights as JSON |
| X — Context efficiency | ✓ Frozen dataclasses; pure-function scorer signals |

### Runtime verification and closure coverage

* Runtime surfaces (CLI, output contract, orchestrator) all have
  named verification scenarios. ✓
* Calibration gate is explicit and operator-visible. ✓
* Rollback triggers are quantified (20 % disagreement, 40 % flag
  rate, 10 % subprocess fallback). ✓
* Validation window (5 production runs) is explicit. ✓
* Closure artifacts list compound-refresh entry — appropriate for the
  pattern. ✓

### Gate rationale

No P0 or P1 issues. Two P2 issues are implementation-discipline notes
(function-shape factoring; frozen dataclass) that should be reflected
in the harness scaffolds but do not block harvest. Four P3 items are
advisory; one resolves with a stash entry after shipment close.

Operator may proceed to **harvest**. The harness-architect skill should
reflect P2#1 (function factoring) and P2#2 (frozen dataclass) in the
RED scaffolds so the implementation lands them correctly the first time.

