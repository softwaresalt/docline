---
title: Closure — 021-S triage-then-repair hybrid PDF pipeline
date: 2026-06-06
shipment: 021-S
feature: 019-F
status: verified
merged_pr: 42
merge_sha: 4071549
branch: feat/021-S-triage-then-repair
decision: docs/decisions/2026-06-06-triage-then-repair-pdf-pipeline.md
plan: docs/plans/2026-06-06-triage-then-repair-plan.md
review: docs/closure/021-S-review.md
related_rca: docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md
compound_learnings: docs/compound/2026-06-06-triage-then-repair-pattern.md
follow_up_stashes: 5CFE4481, 24920EFF, DE3E7346
---

# Closure — 021-S triage-then-repair hybrid PDF pipeline

## Readiness status

**READY WITH CONDITIONS** — merge to `main` is complete (PR #42, merge
commit `4071549`). Production use of `--pdf-mode triage` requires two
explicitly named conditions before being recommended for routine work:

1. **PA3 — cosmos runtime verification** (must run from a plain
   PowerShell session per the 2026-06-04 RCA; NOT inside an agent
   process) — verifies the end-to-end wall-clock target on the
   real ≥100 MB / ≥3,000-page corpus.
2. **PA4 — `_SIGNAL_WEIGHTS` calibration** — run
   `docline process --pdf-mode triage --triage-report-only
   --report-tsv-path logs/triage-calibration-cosmos.tsv` against
   the 12 completed cosmos chunks; tune weights; commit
   `src/docline/process/fidelity_weights.json`.

Default-mode behavior (`--pdf-mode auto`, the existing
split-and-throttle batch pipeline) is unchanged and verified by the
989-test full suite. Triage is opt-in only; the merge does not put any
existing flow at risk.

## Change summary

Added an opt-in `--pdf-mode triage` PDF processing pipeline:

1. Heuristic baseline across the whole PDF (per-page extraction via
   `pypdf` directly, not the empty-page-filtering `read_pdf_pages`).
2. Deterministic per-page fidelity scoring across seven signals.
3. Flagged-page coalescing into ranges with context buffer + merge gap.
4. Per-range docling subprocess via the existing `docling_worker`.
5. Splice-back into a per-page final list with engine attribution.

Plus the QA tripwire (`QASampling` dataclass) for random re-runs of
unflagged pages to detect false negatives, and the `--triage-report-only`
calibration mode that emits per-page TSV without invoking docling.

**Expected wall-clock impact** on long technical reference PDFs:
~6–8× reduction. The 3,426-page `azure-cosmos-db.pdf` should go from
the observed ~9.5 h all-docling baseline to ~70–90 min triage. This
target is validated by PA3.

## Invariants to preserve

| Invariant | Verification |
|---|---|
| Default mode (`--pdf-mode auto` or unset) is bit-identical to pre-merge behavior | `test_pdf_mode_auto_dispatches_to_existing_batch_pipeline`; `test_default_mode_is_auto`; existing `test_cli_process.py` regression suite (3 tests) |
| `TriageResult` is a frozen dataclass; cannot be mutated post-construction | `test_triage_result_is_frozen` asserts `FrozenInstanceError` on attempted mutation |
| `engine` field MERGES into `docline:` namespace; never overwrites existing keys | `test_engine_field_merges_into_docline_namespace_without_destroying_existing_keys` seeds `source_url` + `crawl_depth` and asserts all three keys survive (per 013-S compound) |
| Splice and QA temp files stay under `output_dir`; no writes outside the workspace tree | U3 tests use `tmp_path` as `output_dir` and assert no files written outside (Constitution IV) |
| Docling subprocess failure for a flagged range falls back to heuristic for that range; batch never aborts | `test_docling_failure_falls_back_to_heuristic_per_range` asserts metadata `subprocess_fallback_count >= 1` and engine attribution flips back to `heuristic` |
| `triage_report_only` never invokes any subprocess | `test_report_only_never_invokes_subprocess` patches `subprocess.run` and asserts call count is zero |

## Pre-deploy audits

This change is library + CLI; no service deploy. Pre-merge audits
satisfied:

* ✅ All 7 CI jobs PASS (`pyright`, `pytest` macos/ubuntu/windows,
  `ruff lint`, `ruff format check`, `sdist + wheel`)
* ✅ Full local pytest: 989 passed, 3 skipped, 0 failed
* ✅ Ruff lint + format clean on all new/modified files
* ✅ Plan-review gate: ADVISORY (0 P0/P1)
* ✅ Code-review gate: PASS (0 P0/P1)
* ✅ Copilot Review on PR #42: 2 valid findings, both addressed in
  commit `603f3cd`, threads replied + resolved
* ✅ Merge commit history preserved (used `--merge`, not `--squash` or
  `--rebase`, per Constitution XI / P-009)
* ✅ All 7 task acceptance criteria satisfied

## Deployment / rollout path

Merge-only. No service deploy. No data migration. No config push.

Adoption pattern for end users:

1. **Phase 0 — current state (post-merge)**: Triage mode is wired but
   gated behind explicit `--pdf-mode triage`. Default behavior
   unchanged.
2. **Phase 1 — calibration (PA4)**: Run `--triage-report-only`
   against a representative corpus; tune `_SIGNAL_WEIGHTS`; commit
   `fidelity_weights.json`.
3. **Phase 2 — runtime verification (PA3)**: Full triage run on
   cosmos PDF from a plain shell; record wall-clock + per-page engine
   distribution.
4. **Phase 3 — recommended for production**: After Phases 1 + 2
   complete and the rollback triggers below are not firing, triage
   becomes the recommended mode for long technical PDFs.

## Post-deploy / post-merge checks

Run after this merge lands (smoke tests, not the full PA3 cosmos run):

* ✅ `docline --manifest` lists `--pdf-mode` in the `process` tool
  schema (verified pre-merge by `test_manifest_includes_pdf_mode_flag`)
* ☐ Spot-check on a small (≤ 50 page) sample PDF:
  ```
  docline process --pdf-mode triage --staging-dir .elt/staging --output-dir output-triage
  ```
  Expect: completes without error; output `manifest.json` includes
  `triage_stats` block.
* ☐ Regression: same PDF with `--pdf-mode auto` produces output
  identical to current behavior.

## Risky-action ledger

Carried forward from plan hardening. Each must reach `applied` or
`abandoned` before this closure is considered complete.

| ID | ProposedAction | ActionRisk | ActionResult |
|---|---|---|---|
| **PA1** | Land `--pdf-mode triage` wired to production batch path | moderate | **applied** (commit `15e3036`; CLI wiring fix in `603f3cd`) |
| **PA2** | Add `engine` field to part frontmatter `docline:` namespace | moderate | **applied** (commit `14e7856`) |
| **PA3** | First end-to-end triage run on `azure-cosmos-db.pdf` | low | **planned** — operator action; must run from plain shell per RCA; capture wall-clock + per-page engine distribution as evidence |
| **PA4** | Lock-in default `_SIGNAL_WEIGHTS` based on calibration | low | **planned** — depends on PA3 sample data; commits `fidelity_weights.json` |

## Healthy signals (what success looks like)

When triage mode is used in production after PA3 + PA4:

* Per-page engine distribution shows the expected mix (typically
  10–30 % docling, 70–90 % heuristic on prose-heavy corpora)
* Wall-clock for the target document is ≤ 25 % of all-docling
  baseline (cosmos target: ≤ 2.4 h)
* Manifest `triage_stats` block accurately reflects per-page counts
* `subprocess_fallback_count` is low (single-digit % of flagged ranges)
* When `--sample-rate > 0` is used, `qa_disagreements` is < 5 % of
  sampled clean pages

## Failure signals (what triggers rollback)

Any of the following on a production triage run is a rollback trigger:

1. Triage output fails downstream schema validation
2. `qa_disagreements / qa_sampled_count > 0.20` on a single run
   (false-negative under-flagging)
3. Flagged-page rate > 40 % of total pages on a representative
   corpus (scorer is over-firing; speedup lost)
4. `subprocess_fallback_count > 10 %` of flagged ranges (docling is
   broken for splices; triage gives no benefit)
5. Default-mode runtime regression detected in CI

## Rollback procedure

Triage mode is a CLI flag, not a code path that auto-activates. Rollback
is a configuration change, not a data migration:

1. **Immediate**: stop invoking `--pdf-mode triage`; revert to `auto`
   (one-flag change in the calling script / docs).
2. **No data conversion needed** — output contract additions are
   optional; existing consumers already tolerate their absence (verified
   by `test_non_triage_runs_do_not_emit_engine_field`).
3. **If a partial corpus was processed with triage** and downstream
   consumers need uniform output, re-run those documents under
   `--pdf-mode auto` to overwrite.
4. **If a code-level regression is suspected** (e.g., default-mode
   behavior changed), revert the merge commit:
   `git revert -m 1 40715490` then push to `main`.

## Monitoring plan

This is a CLI tool. No always-on monitoring; per-run signal capture:

* Log output during each triage run records `flagged_pages_count`,
  `flagged_ranges_count`, `subprocess_fallback_count`, and (when QA
  sampling is enabled) `qa_disagreements`, `qa_random_seed_used`
* Manifest summary includes the `triage_stats` block for offline
  inspection
* The `--triage-report-only` mode produces per-page TSV for
  threshold-tuning analysis

For the load-test harness (`scripts/load_test.py`) integration, see
the follow-on task captured below.

## Validation window

* **First 5 production triage invocations** on representative
  corpora — manually inspect logs and `triage_stats` to verify the
  failure signals above are not firing.
* **After 5 clean runs**, triage is considered stable for the
  calibrated corpus class.
* **Re-calibrate weights** when adopting on a new corpus class
  (e.g., scientific papers vs. reference manuals).

## Owner

* **Implementation owner**: docline maintainer (current single-maintainer
  workspace)
* **Calibration owner**: same — operator runs PA3 + PA4 from a plain
  shell per the 2026-06-04 RCA constraint
* **Watch window**: 1 week / 5 invocations, whichever comes first

## Follow-up work captured

| Stash | Priority | Description |
|---|---|---|
| `5CFE4481` | medium | Per-page docling output limitation in splice-back: docling_worker returns single blob per range; consider per-page subprocess invocation or JSON envelope |
| `24920EFF` | low | Validate `weights_path` in `load_weights` against workspace containment when MCP exposes triage with caller-controlled paths |
| `DE3E7346` | low | Extract shared Pass 1-2 helper between `process_pdf_triaged` and `triage_report_only` |

Plus implicit follow-ups not yet stashed (capture in next session if
they become priorities):

* Load-test harness integration: extend `scripts/load_test.py` to
  drive `--pdf-mode triage` and produce comparison TSVs against the
  existing all-docling baseline (PA3 enablement)
* Calibration script: dedicated `scripts/calibrate_fidelity_weights.py`
  that produces `fidelity_weights.json` from a TSV + truth set (PA4
  enablement)

## Compound learning

This shipment produced a reusable architectural pattern. See:
`docs/compound/2026-06-06-triage-then-repair-pattern.md`.

The pattern (cheap-baseline + scorer-driven selective-ML-repair +
splice-back) applies anywhere a pipeline has a fast non-ML path that's
good-enough for most inputs and an expensive ML path that's only
worth its cost on a minority of inputs. Likely future applications in
docline: image-only PDF subset routing to OCR; selective re-extraction
of malformed DOCX tables; selective re-fetch of stale web content.

## Recommendation

**READY WITH CONDITIONS** — merge has landed. Triage mode is available
behind the opt-in flag and is safe to experiment with on small
fixtures. **Do not adopt for production runs** on long PDFs until PA3
and PA4 complete.

Operator next actions (in order):

1. Run PA3 from a plain PowerShell session on the cosmos PDF; record
   wall-clock + per-page engine distribution as evidence.
2. Run `--triage-report-only` against the 12 existing cosmos chunks;
   compare flag pattern to where docling actually produced richer
   output; tune `_SIGNAL_WEIGHTS`.
3. Commit `src/docline/process/fidelity_weights.json` (PA4 close).
4. Update this closure artifact with PA3 and PA4 evidence; transition
   `status:` frontmatter from `verified` to `production-ready` once
   both conditions are satisfied.
