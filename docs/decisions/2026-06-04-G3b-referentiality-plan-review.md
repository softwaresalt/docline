---
title: "Plan review — G3b referentiality"
plan: "docs/plans/2026-06-04-G3b-referentiality-plan.md"
shipment: "013-S"
date: 2026-06-04
verdict: APPROVED
personas: [architecture, python, security, scope-boundary, constitution, test-discipline]
---

# Plan review — G3b referentiality

## Verdict: **APPROVED** (0 P0, 0 P1, 1 P2, 2 P3)

## Personas applied

| Persona | Outcome |
|---|---|
| Architecture | ✅ Helper-based approach (Option 1) preserves 012-S API stability; reuses existing `_build_document_id` for `parent_document_id` — coherent with the prior cycle |
| Python | ✅ Typed signatures throughout; uses existing permissive `dict[str, Any]` so no schema source change required |
| Security | ✅ No new external input, no PII handling change, no path/URL surface change |
| Scope-boundary | ✅ Snapshot update at `d:/Source/GitHub/graphtor-docs/...` correctly identified as out-of-scope (Constitution P-IV) and routed to follow-up stash |
| Constitution | ✅ I, II, IV, VI, X, XI all satisfied |
| Test-discipline | ✅ 13 test scenarios listed; RED phase explicit; covers fall-back cases |

## Findings

| ID | Severity | Class | Detail |
|---|---|---|---|
| F1 | P2 | manual | The plan says `output_contract.py` requires a small modification to "pass the section title list alongside segments via a tuple/dict". This is an API change to `build_output_document_parts` return shape OR an internal change to how `_assemble_part_markdown` consumes segments. The plan should be explicit: my recommendation is to extend `OutputDocumentPart` with an optional `section_title: str \| None = None` field (frozen dataclass already, so additive default-None is back-compat), populated by `extract_section_title` in `build_output_document_parts`. Implementer (013.003-T or 013.002-T) should adopt this. |
| F2 | P3 | advisory | `_relative_sibling` uses `all_paths.index(current)` which is O(n) per lookup; for very large multi-part outputs this is O(n²). Negligible for realistic part counts (< 100). Acceptable. |
| F3 | P3 | advisory | The closure document should remind the operator to run `docline export-schema > path-to-snapshot` after merge so the `graphtor-docs` snapshot stays in sync. Already captured in plan acceptance criteria. |

## Adoption decision

The plan is **APPROVED** for harvest with F1 as an embedded refinement: extend `OutputDocumentPart` with `section_title: str | None = None`. The harvest will reflect this in task 013.002-T or 013.003-T's implementation notes.

F2 and F3 are advisory; no action required.

## Risk profile

| Dimension | Level |
|---|---|
| Blast radius | Low — additive frontmatter fields + single call-site flip |
| Reversibility | High — revert merge commit; output regenerates |
| Cross-cutting | One source module (`app.py`), one helper module (`segment.py`), one test file |
| External dependency | None |
| Operator approval gates | Standard P-014 merge gate |

`plan-harden` not required.
