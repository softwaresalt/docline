---
type: decided-plan
source_plan: 2026-06-06-triage-then-repair-plan.md
consolidated_at: 2026-08-29
status: shipped
---

## Decision Summary

The shipped triage-then-repair pipeline introduced an opt-in `--pdf-mode triage` path that runs a fast heuristic baseline over the full PDF, scores pages with deterministic fidelity signals, coalesces flagged pages into ranges, repairs only those ranges with docling, and stitches the final per-page output. The design preserved existing `auto`, `heuristic`, and `docling` behaviors while adding report-only calibration and QA tripwire modes.

Hardening treated the new pipeline as moderate risk because it adds a CLI orchestration mode, output-contract fields, and accuracy-dependent routing. Calibration, quantified rollback triggers, and per-page observability were required before production use.

## Implementation Units

* U1: pure fidelity scorer with frozen `PageScore`, typed signals, overrideable weights, and `FidelityScorerError`
* U2: page-range coalescer with buffer, merge-gap, and boundary validation
* U3: `process_pdf_triaged` orchestrator with frozen `TriageResult`, heuristic baseline, scoring, splice repair, merge, and fallback handling
* U4: `--pdf-mode {auto,triage}` CLI wiring without changing `--pdf-engine` semantics
* U5: per-page engine attribution in `docline:` frontmatter plus manifest `triage_stats`
* U6: `triage_report_only` TSV calibration mode that does not invoke docling
* U7: QA sampling tripwire with seeded sampling and disagreement metadata

## Key Constraints

* Default PDF mode remains bit-identical to previous behavior
* Triage is opt-in and rollback is using `--pdf-mode auto`
* `engine` metadata must merge into the `docline:` namespace without overwriting existing keys
* Scorer calibration must precede recommending triage for a corpus
* Runtime verification must include a cosmos PDF full run, flag-rate analysis, and QA sampling
* Splice temp files stay under `output_dir` or cache directory

## Rejected Alternatives

* Overload `--pdf-engine` with orchestration-mode semantics — rejected because mode and engine are orthogonal
* Rewrite the POC from scratch — rejected because the POC already captured useful signal nuance
* Store engine attribution only in the manifest — rejected because graphtor reads part frontmatter directly
* Parallelize splice processing in this shipment — rejected until the load-test harness validates the sequential baseline
* Use JSON for report-only output — rejected in favor of TSV matching existing calibration tooling
* Sample flagged pages in the QA tripwire — rejected because flagged pages already route to docling

## Review Outcome

Plan review was advisory with two P2 implementation-discipline findings: factor report-only and QA concerns to avoid an overwide `process_pdf_triaged` signature, and make `TriageResult` frozen. P3 follow-ups covered seed semantics, future shared range-runner abstraction, and explicit `DoclineError` import path.

## Traceability

Full deliberation history archived at docs/archive/plans/2026-06-06-triage-then-repair-plan.md

