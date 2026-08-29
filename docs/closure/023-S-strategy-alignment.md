---
title: Closure — 023-S strategy alignment (AST-aware quality metrics + docs)
date: 2026-06-09
shipment: 023-S
feature: 021-F
status: verified
merged_pr: 49
merge_sha: 8eb9634
branch: feat/023-S-strategy-alignment
plan: docs/plans/2026-06-09-023-s-strategy-alignment-plan.md
parent_decisions:
  - docs/decisions/2026-06-08-extraction-strategy-study.md
  - docs/decisions/2026-06-08-source-md-ingestion-extension.md
parent_closures:
  - docs/closure/021-S-triage-then-repair.md
  - docs/closure/022-S-pa4-closure.md
compound_learning: docs/compound/2026-06-08-ast-fidelity-metrics.md
harvested_stashes: 13F608BA, 378C8BC0, A39C3704
archived_stashes: 5A622B72
follow_up_stashes: EFC6C84E, 51332802, 6A4E8059, 4CB606D5
---

## Readiness status

**READY** — merge complete (PR #49, merge commit `8eb9634`).

023-S lands three operational changes plus a compound-learning capture
that institutionalizes the 2026-06-08 extraction-strategy study
findings:

1. **Production AST-quality metrics module** — `QualityMetrics` frozen
   dataclass with 12 fields, `compute_quality_metrics()` pure function,
   re-exported from `docline.process`.
2. **Triage calibration integration** — `triage_report_only` TSV gains
   7 `qm_*` columns; `TriageResult.metadata` gains
   `quality_metrics_summary` block.
3. **Operator-facing docs** — README "PDF processing modes" section,
   021-S closure annotated with strategic reversal, triage diagnostic
   artifact preservation behavior documented.
4. **Compound learning** — `docs/compound/2026-06-08-ast-fidelity-metrics.md`
   captures the durable lesson and empirical thresholds.

## Files changed (1029 passed pytest, 0 regressions)

| Path | Action |
|---|---|
| `src/docline/process/quality_metrics.py` | NEW — production module (12-field QualityMetrics + compute_quality_metrics) |
| `src/docline/process/__init__.py` | MODIFY — re-export new public symbols |
| `src/docline/process/pdf_triage.py` | MODIFY — integrate per-page quality computation + summary into `triage_report_only`; single shared MarkdownIt parser |
| `tests/process/test_quality_metrics.py` | NEW — 16 dedicated tests including Setext-heading regression |
| `tests/process/test_pdf_triage_qm_integration.py` | NEW — 3 integration tests |
| `docs/compound/2026-06-08-ast-fidelity-metrics.md` | NEW — compound learning |
| `README.md` | MODIFY — "PDF processing modes" section |
| `docs/closure/021-S-triage-then-repair.md` | MODIFY — 2026-06-08 strategic reversal annotation; status stays `verified` |
| `scripts/study/evaluate_markdown.py` | MODIFY — docstring note pointing to production module |

## Verification

| Gate | Result |
|---|---|
| pytest (full) | **1029 passed / 3 skipped / 0 failed** |
| pytest (new tests only) | 19 / 19 |
| ruff check | clean on all modified files |
| ruff format --check | clean on all modified files |
| pyright (new module) | 0 errors |
| pyright (repo) | 1 pre-existing markitdown-stub error on `pdf_triage.py:143` (since 022-S; not introduced by this shipment) |
| CI on PR #49 | all 7 jobs green |

## Adversarial review process

Self-review BEFORE PR identified 5 issues, all fixed pre-push:

1. Dead `_TOKEN_RE` in new module — removed (Constitution: no dead code)
2. Bare `except Exception` in `_parse_tokens` — added explanation + `noqa: BLE001`
3. Missing dedicated test for `heading_depth_max` — added
4. Reinvented mean/median helpers in pdf_triage.py — replaced with `statistics.{mean,median}`
5. Per-page MarkdownIt construction would build 3000+ parsers on cosmos — refactored to single shared parser

Copilot review AFTER PR identified 3 valid issues, all fixed via follow-up commit `7f47384`:

1. `heading_count` vs `section_count` inconsistency on Setext headings — switched `_section_lengths` from regex to AST-based using `token.map[0]`; added regression test
2. `triage_report_only` docstring divergence (only 5 original columns documented) — updated to enumerate all 12 columns and mention `quality_metrics_summary` in metadata
3. 026-S vs 026-F naming inconsistency in README — normalized to 026-F (feature) per the multi-week decomposition reality

All 3 Copilot threads replied to + resolved via `gh api graphql resolveReviewThread`.

## Invariants preserved

| Invariant | Verification |
|---|---|
| `compute_quality_metrics` never raises on any string input | `test_compute_metrics_returns_parse_ok_false_on_malformed_input` |
| `QualityMetrics` is immutable | `test_quality_metrics_is_frozen_dataclass` |
| `QualityMetrics` has exactly 12 fields | `test_quality_metrics_has_exactly_twelve_fields` |
| `triage_report_only` TSV preserves existing columns at original positions | `test_triage_report_only_qm_columns_appear_after_existing_signal_columns` |
| Both ATX and Setext headings produce consistent `section_count` | `test_compute_metrics_setext_headings_produce_sections` |
| No behavioral change to `process_pdf_triaged` default path | existing test suite passes unchanged (1010 pre-existing pass + 19 new) |

## Pre-deploy audits

* ✅ All 7 CI jobs PASS (pyright, pytest macOS/ubuntu/windows, ruff lint, ruff format, sdist + wheel)
* ✅ Full local pytest: 1029 passed, 3 skipped, 0 failed
* ✅ Ruff lint + format clean on all new/modified files
* ✅ Adversarial self-review: 5 findings, all fixed pre-push
* ✅ Copilot review on PR #49: 3 valid findings, all fixed in commit `7f47384`; all 3 threads replied + resolved
* ✅ Merge commit history preserved (used `--merge`, not `--squash` or `--rebase`, per Constitution XI / P-009)
* ✅ All 4 task acceptance criteria satisfied

## Risky-action ledger

| ID | ProposedAction | ActionRisk | ActionResult |
|---|---|---|---|
| PA1 | Add new public surface (`QualityMetrics` + `compute_quality_metrics`) to `docline.process` | low | applied (commit `9920428`); reviewed; no callers in production code yet |
| PA2 | Mutate existing `triage_report_only` output (TSV columns + metadata block) | moderate | applied (commit `9920428`); backward-compat preserved via append-only TSV column ordering; reviewed by Copilot (3 follow-ups in `7f47384`) |
| PA3 | Update 021-S closure status text without transitioning to `production-ready` | low | applied — explicit rationale in closure: production-ready transition deferred pending 024-S / 025-S / 026-F |
| PA4 | Archive stash `5A622B72` based on false-premise discovery | low | applied — splice files were already preserved by default; behavior documented |

## Deployment / rollout path

Merge-only. No service deploy. No data migration. No config push. The
new `QualityMetrics` module is purely additive; no existing callers
depend on its presence. The `triage_report_only` integration is
opt-in (only emits when operator runs `--triage-report-only`).

## Post-merge checks

* ✅ `from docline.process import QualityMetrics, compute_quality_metrics` works in a fresh Python session
* ✅ `docline process --pdf-mode triage --triage-report-only` smoke-tested locally; TSV contains `qm_*` columns
* ☐ Operator may run on cosmos corpus to confirm metrics summary populates as expected (not required for this closure)

## Rollback procedure

This shipment is purely additive to library + docs. To revert:

1. **Revert PR #49**: `git revert -m 1 8eb9634` then push to `main`.
   This removes `quality_metrics.py`, the `triage_report_only`
   integration, README section, compound learning, and closure
   annotation in one commit.
2. **No data conversion needed** — no existing data structures
   modified; new `qm_*` TSV columns are append-only.

## Follow-up work captured

Carried forward in `.backlogit/stash.jsonl`:

| Stash | Priority | Description |
|---|---|---|
| `EFC6C84E` | high | INVERT scoring model: source-PDF complexity (target 024-S) |
| `6A4E8059` | high | Source-MD ingestion pathway (target 026-F, multi-shipment) |
| `51332802` | medium | Profile + tune `docling_worker` for batching/GPU (target 025-S) |
| `5CFE4481` | medium | Per-page docling output protocol (review follow-up from 019-F) |
| `4CB606D5` | low | Generalization study on 2-3 additional corpora |
| `24920EFF` | low | Validate `weights_path` for MCP exposure |
| `DE3E7346` | low | Extract shared Pass 1-2 helper |
| `7AA9FAA0` | low | PyPI release workflow |
| `4CA80776` | low | Docling OCR tuning |

## Recommendation

**READY** — strategy alignment complete. The next operationally
valuable shipment is **024-S (scoring inversion, stash `EFC6C84E`)**
which closes the throughput half of the docling-primary direction:
score source-PDF structural complexity BEFORE running any extractor,
eliminating wasted heuristic work on pages destined for docling.

021-S transitions to `production-ready` only after 024-S + 025-S
deliver the throughput improvements, or 026-F (source-MD pathway)
delivers the alternative ingestion path for source-available corpora.
