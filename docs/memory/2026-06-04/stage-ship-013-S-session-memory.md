---
type: session-memory
date: 2026-06-04
session: stage-and-ship-013-S
shipment: 013-S
branch: feat/013-frontmatter-referentiality
status: pr-pending
---

# Stage + Ship session — shipment 013-S (G3b referentiality)

## Summary

Single autonomous session executing both Stage and Ship workflows for shipment `013-S` (G3b frontmatter referentiality + chunk anchor default). Stage harvested stash `C5CA1740` into feature `014-F` + 4 TDD-ordered tasks; Ship executed all four tasks end-to-end. All five quality gates green at HEAD `1b01caa`.

## Tasks completed

| Task | Status | Commit | Description |
|---|---|---|---|
| `014.001-T` | done | `308089e` | TDD RED — 10 referentiality + 3 helper tests; all failed |
| `014.002-T` | done | `7a894f6` | TDD GREEN — implementation |
| `014.003-T` | done | `7a894f6` | Bundled with 014.002-T (single-line flip) |
| `014.004-T` | done | `1b01caa` | Closure document |
| `014-F` | done | `1b01caa` | Feature archived |

## Critical correctness fix discovered during implementation

Initial implementation overwrote `payload_dict["docline"]` with the new G3b namespace dict. This silently destroyed the pre-existing `docline:` block that `WebFrontmatter` auto-populates for web/crawl sources (`source_url`, `crawl_depth`, `http_status`, etc.). Caught by `test_html_output_uses_per_page_source_url_and_crawl_depth` regression in the first GREEN gate run. Fixed by switching to a merge: existing namespace keys preserved, G3b keys layered on top.

**Compound learning candidate**: "Pydantic auto-routing to a namespace dict is invisible from the call site — always merge, never overwrite, when extending namespaces that may already be populated."

## Decisions

1. **`section_title` on `OutputDocumentPart`** rather than altering `segment_markdown` return shape — preserves 012-S API contract.
2. **`extract_section_title` applied to ALL body inputs** — HTML also benefits. Documented as P3 advisory.
3. **`assemble_markdown` signature default stays `False`** — production opts in explicitly.
4. **`parent_document_id = _build_document_id(job_id, input_path, ingest_order=0)`** — collapses per-part variance.
5. **Cross-repo `graphtor-docs` snapshot deferred to operator** per Constitution P-IV. Closure records the command.

## Review findings

Ship Step 4.4 mode `report-only`: 0 P0, 0 P1, 0 P2; 2 P3 advisories. None block merge.

## Open / next steps

1. Push branch + create PR
2. Copilot review polling per §1.2
3. P-014 readiness gate + operator approval
4. Post-merge closure (Step 6)
5. Compound entry for the WebFrontmatter namespace merge insight
6. Mandatory stash for cross-repo graphtor-docs snapshot refresh
