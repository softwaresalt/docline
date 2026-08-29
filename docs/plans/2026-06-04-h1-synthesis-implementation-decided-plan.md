---
type: decided-plan
source_plan: 2026-06-04-h1-synthesis-implementation-stub.md
consolidated_at: 2026-08-29
status: shipped
---

## Decision Summary

The shipped H1 synthesis design added a deterministic assemble-time hybrid synthesizer for headerless parts. The approved A to B to C escalation promotes reliable frontmatter titles, then usable first H2 headings, then usable first paragraphs, while leaving already titled parts unchanged and preserving strict parentage behavior for unrescued parts.

The decision explicitly rejected SLM-based synthesis for this shipment. Deterministic synthesis was sufficient to rescue most headerless parts, and provenance flags let graphtor distinguish synthetic anchors from author-supplied headings.

## Implementation Units

* Add `src/docline/process/header_synthesis.py` with `SynthesisTier`, frozen `SynthesisResult`, and `synthesize_section_title`
* Wire synthesis in `assemble.py` after segmentation and before strict parentage validation
* Emit `docline.section_title_synthesized` and `docline.section_title_synthesis_tier` for rescued titles
* Preserve `--allow-heading-disorder` while adding a deprecation warning
* Add unit, integration, and regression tests for tier behavior and corpus impact

## Key Constraints

* No SLM dependency in this shipment
* No-op for parts that already have non-null `section_title`
* Provenance flags are required for every synthesized title
* Keep reader modules extraction-only; synthesis belongs at assemble time
* Verify additive schema impact against the frontmatter namespace merge behavior

## Rejected Alternatives

* SLM title synthesis — rejected as unnecessary for the first shipment and better as a future opt-in extra
* Read-time synthesis in individual readers — rejected because synthesis needs post-segmentation part bodies and consistent provenance
* Removing `--allow-heading-disorder` immediately — rejected for compatibility during the transition release
* Promoting placeholder titles such as `X Part 100` or `Untitled` — rejected to avoid low-quality anchors

## Review Outcome

This source was a design stub rather than a full reviewed implementation plan. The durable decisions were the deterministic tiered algorithm, assemble-time integration point, required provenance fields, and deferred SLM follow-up.

## Traceability

Full deliberation history archived at docs/archive/plans/2026-06-04-h1-synthesis-implementation-stub.md

