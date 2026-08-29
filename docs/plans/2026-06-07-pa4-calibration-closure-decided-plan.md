---
type: decided-plan
source_plan: 2026-06-07-pa4-calibration-closure-plan.md
consolidated_at: 2026-08-29
status: shipped
---

## Decision Summary

The shipped PA4 calibration closure changed triage's baseline toward richer markdown by using markitdown for the opt-in triage path, replacing brittle normalized-text disagreement checks with token-set Jaccard similarity, and adding a layout-complexity signal so structured pages route to docling. The goal was to close 021-S PA4 with a convergent post-merge cosmos rerun rather than tune weights against a weak pypdf baseline.

Hardening accepted the larger dependency footprint because empirical bench results showed materially better prose, list, and code extraction. Auto mode remained unchanged, and pypdf stayed available as a fallback and compatibility baseline.

## Implementation Units

* U1: add `baseline_engine` to `process_pdf_triaged` and `triage_report_only`, defaulting to markitdown and recording metadata
* U2: replace `_normalize_markdown` with `_content_similarity` using Jaccard token similarity and QA similarity histograms
* U3: add `signal_layout_complexity` and default weight to the fidelity scorer
* U4: add `markitdown[pdf]` as a required dependency, tightened to `<0.2` per review guidance
* U5: update `scripts/pa3_triage_cosmos.py` with baseline-engine and similarity-histogram reporting

## Key Constraints

* `--pdf-mode auto` remains bit-identical to pre-merge behavior
* markitdown import failure must fall back to pypdf and record `baseline_engine_fallback`
* Jaccard similarity handles empty inputs and code-fence/whitespace-only changes sensibly
* Layout-complexity scoring returns `0.0` without metadata and uses narrow exception handling
* CI install time and dependency footprint are monitored
* Post-merge PA3 and PA4 cosmos reruns gate closure

## Rejected Alternatives

* Keep pypdf as the triage default — rejected because markitdown produced strictly richer AST-relevant markdown in the bench
* Use normalized Levenshtein distance — rejected as too expensive for sampled long-corpus comparisons
* Keep `_normalize_markdown` alongside similarity — rejected because it was private and no tests imported it
* Expose `--baseline-engine` as a CLI flag in this shipment — deferred because a code-level kwarg was enough for rollback
* Make markitdown optional extras-only — rejected to avoid an extra remembered install step for the recommended triage path
* Let auto mode adopt markitdown — explicitly out of scope to protect default behavior

## Review Outcome

Plan review was advisory. The P2 guardrail verified no test imports of `_normalize_markdown`; P3 findings tightened tokenization, exception handling, unit sequencing, markitdown version range, and post-merge supply-chain audit expectations.

## Traceability

Full deliberation history archived at docs/archive/plans/2026-06-07-pa4-calibration-closure-plan.md

