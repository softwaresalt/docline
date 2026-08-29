---
type: decided-plan
source_plan: 2026-06-09-023-s-strategy-alignment-plan.md
consolidated_at: 2026-08-29
status: shipped
---

## Decision Summary

The shipped 023-S strategy alignment made the 2026-06-08 extraction-study findings durable and aligned docline's triage calibration output with AST-aware quality goals. It promoted quality metrics from research scripts into production code and updated operator-facing guidance to explain when all-docling versus triage mode is appropriate.

The key strategic decision was that character count is not a fidelity metric for graph, embedding, or LLM consumers. Structural density, section count, heading count, and table cell count became the preferred indicators for markdown extraction quality.

## Implementation Units

* T1: capture the AST fidelity metric lesson in `docs/compound/2026-06-08-ast-fidelity-metrics.md`
* T2: promote `compute_quality_metrics` and frozen `QualityMetrics` into `src/docline/process/quality_metrics.py`
* T3: add AST-aware metric columns and summary output to `triage_report_only`
* T4: update README, architecture, and 021-S closure guidance to make docling-primary and triage-narrowing guidance official

## Key Constraints

* `compute_quality_metrics` is pure, side-effect-free, typed, and never raises on malformed markdown
* `QualityMetrics` is immutable and exported from the `docline.process` namespace
* Existing `process_pdf_triaged` behavior stays unchanged outside report-only output enrichment
* `markdown-it-py` is reused as an existing runtime dependency
* 021-S remains `verified` rather than `production-ready` until later scoring/source-MD work lands

## Rejected Alternatives

* Use character count as a quality proxy — rejected by the study evidence showing identical char counts with very different structural density
* Keep metrics in `scripts/study/evaluate_markdown.py` only — rejected because calibration needed a production single source of truth
* Emit metrics only in documentation — rejected because report-only calibration needs machine-readable TSV and summary fields
* Change default PDF mode guidance to triage for all technical PDFs — rejected; triage stays opt-in for prose-dominated corpora
* Transition 021-S directly to production-ready — rejected until 024-S or 026-F follow-up evidence exists

## Review Outcome

The source kept plan-review notes as a placeholder rather than appended substantive findings. The shipped decision surface remained the four-task strategy alignment, with scope explicitly excluding scoring inversion, source-MD expansion, docling speedup, and generalized study work.

## Traceability

Full deliberation history archived at docs/archive/plans/2026-06-09-023-s-strategy-alignment-plan.md

