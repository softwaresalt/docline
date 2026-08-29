---
type: decided-plan
source_plan: 2026-05-31-fix-pyright-type-regressions-plan.md
consolidated_at: 2026-08-29
status: shipped
---

## Decision Summary

The shipped fix restored the `pyright src/` quality gate by correcting process-module type annotations only. `metadata.py` widened staged metadata mappings to `Mapping[str, Any]` where Pydantic performs runtime validation, and `ast_lint.py` typed heading inline tokens as `markdown_it.token.Token`.

The decision was intentionally non-behavioral: no parsing, validation, or output semantics changed, and no `type: ignore` suppressions were allowed.

## Implementation Units

* Fix `resolve_document_type` and `assemble_frontmatter_payload` staged metadata annotations to `Mapping[str, Any]`
* Import `Any` only where needed in `metadata.py`
* Type `_heading_text` inline tokens as concrete `Token`
* Verify with `pyright src/`, targeted process tests, and ruff on touched files

## Key Constraints

* Annotation-only change with no runtime behavior change
* Keep the existing `hasattr` guard in `ast_lint.py`
* Avoid `Any` except at the Pydantic validation boundary
* Add no `# type: ignore` comments

## Rejected Alternatives

* Keep `Mapping[str, object]` — too restrictive for `**` unpacking into typed Pydantic parameters
* Use `dict[str, str]` — inaccurate because metadata values are heterogeneous
* Define a structural protocol for tokens — unnecessary for a private helper when `Token` is the actual parser type

## Review Outcome

Plan review passed with advisory findings only. Review accepted the localized contract widening, concrete `Token` type, no-new-tests posture for annotation-only work, and minimal scope.

## Traceability

Full deliberation history archived at docs/archive/plans/2026-05-31-fix-pyright-type-regressions-plan.md

