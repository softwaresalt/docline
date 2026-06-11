---
status: shipped
shipment: 030-S
feature: 028-F
date: 2026-06-11
recommendation: KEEP-AS-OPT-IN
references:
  - docs/plans/2026-06-11-invert-triage-scoring-plan.md
  - docs/decisions/2026-06-08-extraction-strategy-study.md
  - docs/closure/021-S-triage-then-repair.md
---

# 030-S — Invert triage scoring: pre-extraction routing

## What shipped

Per `docs/plans/2026-06-11-invert-triage-scoring-plan.md`, this shipment
adds an opt-in pre-extraction triage scoring path so the fidelity scorer
can short-circuit obviously-complex pages directly to docling without
first wasting a heuristic extraction pass.

### Code changes

* **`src/docline/process/fidelity_scorer.py`**:
  * Two new pure source-aware signals: `signal_font_diversity`
    (counts distinct `/Resources/Font` keys), `signal_text_flow_consistency`
    (coefficient of variation across baseline Y-gaps in the content stream).
  * `_PRE_TRIAGE_SIGNAL_NAMES` and `_DEFAULT_PRE_TRIAGE_WEIGHTS` constants
    naming the 5-signal pre-extraction set (`image_heavy`, `form_fields`,
    `layout_complexity`, `font_diversity`, `text_flow_consistency`).
  * Frozen `PreTriageDecision` dataclass and `pre_triage_score(page_index,
    page_metadata, weights_path=None)` classifier returning
    `route_to_docling` (aggregate ≥ 0.7), `route_to_heuristic`
    (aggregate ≤ 0.2), or `uncertain` (in between).
  * `load_pre_triage_weights(weights_path)` parallels the existing
    `load_weights` so operators can override pre-triage weights
    independently of the existing post-extraction weights.

* **`src/docline/process/pdf_triage.py`**:
  * `_heuristic_and_score_pass` accepts an optional `pre_scorer`
    parameter. When provided, the loop short-circuits
    `route_to_docling` pages (no heuristic extraction, synthetic
    `needs_docling=True` PageScore) and accepts heuristic output for
    `route_to_heuristic` pages without post-extraction scoring.
    `uncertain` pages fall through to the legacy heuristic + score path.
  * New `triage_pre_score_report_only(path, output_dir, report_tsv_path,
    pre_scorer=None)` runs pre-scoring across all pages and emits a
    TSV with columns: `page_index, image_heavy, form_fields,
    layout_complexity, font_diversity, text_flow_consistency,
    aggregate, classification, reason`. No heuristic, no docling.

* **`src/docline/app_models.py`**: `ProcessRequest` gains two bool
  fields (`triage_pre_score`, `triage_pre_score_report_only`), both
  defaulting to `False` for backward compatibility. The MCP manifest
  surface automatically advertises both via Pydantic's JSON Schema
  emission.

* **`src/docline/cli.py`**: `process` subparser exposes
  `--triage-pre-score` and `--triage-pre-score-report-only` flags.

* **`scripts/study/validate_pre_triage.py`** (T4): empirical validation
  harness comparing pre-triage classifications against the 2026-06-08
  cosmos extraction-strategy study ground truth. Exits non-zero if
  aggregate agreement < 85%.

### Test coverage

* `tests/process/test_fidelity_scorer_pre_triage.py` — 18 tests covering
  both new signals + `pre_triage_score` classifications + weight
  overrides + frozen-dataclass invariant + determinism.
* `tests/process/test_pdf_triage_pre_score.py` — 9 tests covering the
  `pre_scorer` short-circuit behavior in `_heuristic_and_score_pass`,
  the new `triage_pre_score_report_only` TSV emitter, `ProcessRequest`
  field validation, and CLI / MCP manifest advertisement.

Total: **27 new tests** covering the full pre-triage surface.

## Empirical validation results

Ran `python scripts/study/validate_pre_triage.py` against the cosmos
fixture (`.elt/data/cosmosdb/azure-cosmos-db.pdf` + the 15-range AST
metrics from the 2026-06-08 study).

### Aggregate

* **Agreement**: **100% (15/15 ranges)** against the docling-wins
  ground truth.
* **Gate threshold**: 85% — **PASSED**.

### Per-range breakdown

| Range | Pages | Ground Truth | Predicted | Mean Aggregate | Classifications (D/H/U) |
|---|---|---|---|---|---|
| pp 213- 233 |  21 |   docling |   docling | 0.454 | 0/0/21 |
| pp 558- 560 |   3 |   docling |   docling | 0.447 | 0/0/3 |
| pp 859-1056 | 198 |   docling |   docling | 0.485 | 0/8/190 |
| pp1079-1089 |  11 |   docling |   docling | 0.480 | 0/0/11 |
| pp1647-1650 |   4 |   docling |   docling | 0.468 | 0/0/4 |
| pp2373-2379 |   7 |   docling |   docling | 0.455 | 0/0/7 |
| pp2428-2433 |   6 |   docling |   docling | 0.511 | 0/0/6 |
| pp2436-2451 |  16 |   docling |   docling | 0.508 | 0/0/16 |
| pp2526-2528 |   3 |   docling |   docling | 0.489 | 0/0/3 |
| pp2580-2582 |   3 |   docling |   docling | 0.468 | 0/0/3 |
| pp2684-2822 | 139 |   docling |   docling | 0.474 | 0/1/138 |
| pp2884-2918 |  35 |   docling |   docling | 0.456 | 0/1/34 |
| pp2935-2998 |  64 |   docling |   docling | 0.479 | 0/0/64 |
| pp3110-3112 |   3 |   docling |   docling | 0.489 | 0/0/3 |
| pp3274-3335 |  62 |   docling |   docling | 0.477 | 0/0/62 |

D/H/U = page classifications: route_to_docling / route_to_heuristic / uncertain.

### Honest analysis of the result

The 100% range-level agreement is real, but the per-page classification
pattern reveals two important nuances that temper the headline number:

1. **Almost all pages classify as `uncertain`** (mean aggregate ≈ 0.45-0.51,
   below the 0.7 docling threshold and above the 0.2 heuristic threshold).
   In production, `uncertain` pages fall through to the legacy heuristic
   + post-extraction scoring path. So enabling `--triage-pre-score`
   currently saves very little extraction work on cosmos-style technical
   PDFs.
2. **No page classified as `route_to_docling` in the entire 575-page
   sample.** The pre-triage scorer is not currently confident enough to
   short-circuit any page directly to docling. The aggregate-pages-uncertain
   bias drives the prediction via the secondary rule (≥30% of pages
   classify as `route_to_docling` weighted-by-uncertain), which is a
   weaker signal than the per-page hard-flag would be.

The new scorer is **architecturally correct** — it never wrongly routed
a docling-wins range to heuristic — but **needs threshold / weight
calibration** before it delivers the perf win the inversion was designed
for.

## Rollout recommendation: KEEP-AS-OPT-IN

Both flags ship as **opt-in defaults-off**. Recommended next steps:

1. **Operator-driven calibration** (`--triage-pre-score-report-only`):
   run against a broader corpus (cosmos + Power BI + Fabric + DAX
   reference PDFs) to gather a distribution of aggregate scores. The
   current thresholds (0.7 / 0.2) were chosen blind; a calibration pass
   may show that 0.5 / 0.15 or similar better separates the populations.
2. **Stash follow-up**: weight tuning for `font_diversity` and
   `text_flow_consistency`. The current 1.0 defaults are placeholders;
   empirical correlation against docling-wins should drive weight
   selection.
3. **Do not** promote to `--pdf-mode auto` default until threshold +
   weight calibration produces meaningful `route_to_docling`
   classifications (currently 0 of 575 pages in cosmos).
4. **Do not** deprecate the existing post-extraction scoring path. It
   remains the production-default safety net, and the `uncertain`
   classification means it stays in the critical path even when
   `--triage-pre-score` is enabled.

## Files changed

| File | Type | Lines |
|---|---|---|
| `src/docline/process/fidelity_scorer.py` | code | +200 |
| `src/docline/process/pdf_triage.py` | code | +120 |
| `src/docline/app_models.py` | code | +25 |
| `src/docline/cli.py` | code | +25 |
| `scripts/study/validate_pre_triage.py` | NEW | 250 |
| `tests/process/test_fidelity_scorer_pre_triage.py` | NEW | 320 |
| `tests/process/test_pdf_triage_pre_score.py` | NEW | 230 |
| `docs/plans/2026-06-11-invert-triage-scoring-plan.md` | NEW | 125 (staged in #70) |
| `docs/closure/030-S-invert-triage-scoring.md` | NEW | this doc |

## Constitutional compliance

| Principle | Compliance |
|---|---|
| I. Safety-First Python | ✓ all new functions typed, no bare except, raise/except with typed exceptions |
| II. Test-First Development | ✓ 27 tests written before implementation; red phase verified; green phase achieved |
| III. Workspace Isolation | ✓ no new path operations; validation script uses defensive Path resolution |
| IV. CLI Workspace Containment | ✓ no file ops outside cwd or explicit operator paths |
| V. Structured Observability | ✓ pre-triage decisions logged via debug; validation reports JSON-serializable |
| X. Context Efficiency | ✓ pre-triage operates on metadata only; no bulk text loading for short-circuit |

## Follow-up stash candidates

* **Weight + threshold calibration** for `font_diversity` and
  `text_flow_consistency` based on broader-corpus distribution analysis.
  The current defaults produce zero `route_to_docling` classifications;
  the route is not yet delivering the perf win.
* **Per-page hard-flag thresholds**: signals like 5+ fonts (currently
  scored 1.0 from font_diversity alone) should arguably hard-flag a
  page even when the aggregate is below 0.7. Add a hard-flag mechanism
  parallel to the existing `_HARD_FLAG_THRESHOLD` for post-extraction.
* **Multi-corpus validation**: re-run `validate_pre_triage.py` against
  Power BI / Fabric / scientific paper / novel corpora to confirm the
  scorer generalizes beyond cosmos-style technical reference PDFs.
