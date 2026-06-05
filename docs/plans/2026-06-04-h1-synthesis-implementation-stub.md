---
title: Plan stub — H1 header synthesis implementation
date: 2026-06-04
status: stub
follow_on_to: 017-S
spike: docs/decisions/2026-06-04-spike-h1-header-synthesis.md
intended_for: next-Stage-cycle
---

# Plan stub — H1 header synthesis implementation

This is a stub, not a full plan. It captures the design contract the
spike (017-S) approved so the next Stage cycle can hydrate quickly and
produce a complete implementation plan.

## What this stub covers

* Module placement
* API sketch
* Integration point
* Test surface required (RED-list scaffold)
* Estimated task decomposition for the next Stage cycle to harvest
* Hard constraints from the spike

## What this stub does NOT cover

* Detailed step-by-step implementation
* Per-task acceptance criteria
* Specific test method names (only the RED-list scaffold is here)
* Constitution Check section (the next plan owns that)
* Plan-review (the next plan owns that)

## Module placement

`src/docline/process/header_synthesis.py` (new). Sibling of
`segment.py` and `assemble.py`. The module owns the deterministic
hybrid synthesizer and the provenance flag emission.

## API sketch

```python
from dataclasses import dataclass
from enum import Enum

class SynthesisTier(Enum):
    NONE = "none"            # Already had a section_title; no synthesis
    TITLE = "title"          # Tier A: promoted frontmatter title
    FIRST_H2 = "first_h2"    # Tier B: promoted first H2 to H1
    FIRST_PARA = "first_para"  # Tier C: first paragraph fallback
    UNRESCUED = "unrescued"  # No tier succeeded; section_title stays null

@dataclass(frozen=True)
class SynthesisResult:
    section_title: str | None
    tier: SynthesisTier
    synthetic_body_prefix: str | None  # Optional "# <title>\n" to inject

def synthesize_section_title(
    body: str,
    frontmatter: dict[str, object],
) -> SynthesisResult:
    """Apply Tier A -> B -> C escalation; return rescue result + provenance."""
```

## Integration point

**Assemble time**, in `src/docline/process/assemble.py`, after segmentation
but before strict-parentage validation and before frontmatter rendering.

* For each part where `docline.section_title` is null, call
  `synthesize_section_title(body, frontmatter)`.
* If the result rescues, write the title to `docline.section_title`,
  set `docline.section_title_synthesized = True`,
  set `docline.section_title_synthesis_tier = result.tier.value`,
  and prepend `result.synthetic_body_prefix` to the body so the strict
  parentage check passes.
* If unrescued, leave `section_title` null and let the existing strict
  check raise unless `--allow-heading-disorder` is passed (which keeps
  its current behavior).

Rationale for assemble-time rather than read-time:

* Readers stay focused on extraction; they should not invent content.
* Synthesis needs to see the post-segmentation part body, not the raw
  reader output, so the first-paragraph filter works against the same
  text the consumer will read.
* Putting synthesis behind a single entry point keeps the provenance
  flag emission consistent across DOCX/PDF/HTML.

## Test surface (RED-list scaffold)

`tests/process/test_header_synthesis.py` (new). RED tests must precede
GREEN.

### Unit tests

* `test_already_titled_returns_none_tier` — when `section_title` is
  already set, returns `SynthesisTier.NONE` and does not touch the body
* `test_tier_a_promotes_title_when_no_heading` — frontmatter `title:
  "Real Title"` and no body heading → result.section_title == "Real Title"
* `test_tier_a_rejects_placeholder_title` — frontmatter `title:
  "X Part 100"` → Tier A declines, escalates
* `test_tier_a_rejects_untitled` — frontmatter `title: "Untitled"` →
  Tier A declines
* `test_tier_a_rejects_too_long` — title length > 100 → Tier A declines
* `test_tier_b_promotes_first_h2_to_h1_when_no_h1` — body opens with
  `## Section X` → result.section_title == "Section X" and
  synthetic_body_prefix == None (the H2 is just retagged)
* `test_tier_b_no_op_when_body_has_h1` — body opens with `# Real H1` →
  Tier B declines because section_title would already be non-null
* `test_tier_c_promotes_first_paragraph_when_usable` — body has no
  heading, first paragraph "A reasonable intro line" → Tier C rescues
* `test_tier_c_rejects_too_short_paragraph` — first paragraph
  length < 10 → Tier C declines, escalates to unrescued
* `test_tier_c_rejects_too_long_paragraph` — > 120 → declines
* `test_tier_c_rejects_markdown_image_line` — first paragraph is
  `![](media/figure-0001.gif)` → declines
* `test_tier_c_rejects_url_only_line` — first paragraph is bare URL →
  declines
* `test_hybrid_escalation_order_a_then_b_then_c` — verify A wins over B
  wins over C
* `test_unrescued_returns_none_section_title` — no tier matches → result
  has section_title == None and tier == UNRESCUED

### Integration tests

* `test_assemble_uses_synthesis_for_headerless_parts` — assemble pass
  invokes synthesis for parts where section_title is null and writes the
  provenance flag
* `test_assemble_records_synthesized_provenance_flag` — verify
  `docline.section_title_synthesized: true` appears in frontmatter
* `test_assemble_records_synthesis_tier` — verify
  `docline.section_title_synthesis_tier: "first_para"` (etc.)
* `test_assemble_strict_parentage_passes_after_synthesis_h1` — when
  synthesis injects a `# <title>` prefix, the strict parentage check no
  longer raises
* `test_assemble_strict_parentage_still_raises_when_unrescued` — when
  synthesis returns UNRESCUED and `--allow-heading-disorder` is not set,
  the strict check still raises

### Regression tests

* Re-run `scripts/spike_h1_corpus_analysis.py` on a post-synthesis
  corpus and verify `sect=null` drops to ≤ 79 / 965 (the spike's
  unrescued baseline).

## Hard constraints from the spike

1. **No SLM dependency in this shipment.** The hybrid A → B → C is
   deterministic and rescues 82.8 % of headerless parts; that's enough
   to ship. SLM is a future opt-in extra (`docline[h1-slm]`), not part
   of this shipment.
2. **Provenance flag is required.** Every synthesized title MUST carry
   `docline.section_title_synthesized: true` and a tier label so
   graphtor can distinguish synthetic from author-supplied anchors.
3. **`--allow-heading-disorder` is preserved.** Do NOT remove the flag
   in this shipment; emit a deprecation warning when it is passed, but
   keep its behavior for one release after synthesis lands.
4. **Backwards compat.** Parts that already have a non-null
   `section_title` MUST be a no-op for the synthesizer.
5. **Schema bump consideration.** Adding two new optional
   `docline.*` fields is additive and likely does not require a schema
   version bump, but the next plan must verify against
   `src/docline/schema/library.py` and the WebFrontmatter auto-routing
   rules from 013-S (Pydantic namespace merge-vs-overwrite trap —
   see `docs/compound/2026-06-04-pydantic-namespace-merge-vs-overwrite.md`).

## Estimated task decomposition for the next Stage cycle to harvest

| Task | Title | Effort |
|---|---|---|
| TDD RED | Write failing tests covering A/B/C/hybrid/no-op/unrescued/integration | ~1.5 h |
| TDD GREEN-1 | Implement `header_synthesis.py` module (deterministic tiers + escalator) | ~1.5 h |
| TDD GREEN-2 | Wire synthesis into `assemble.py`; emit provenance flags; deprecation warning for `--allow-heading-disorder` | ~1 h |
| Regression | Re-run corpus analysis on post-synthesis output; verify ≤ 79 unrescued | ~30 min |
| Closure | Closure record with merge SHA, before/after sect=null counts | ~30 min |

Total estimated: ~5 h. Fits one shipment.

## Open questions for the next Stage cycle

* Should the synthesis also set `title` frontmatter when it was a
  placeholder? (Probably yes for PDFs where `title` is `"X Part N"` and
  synthesis produces a real heading.) Decide during plan authoring.
* Should the deprecation warning on `--allow-heading-disorder` be a
  P-005 telemetry event or a stderr line? Probably stderr to keep noise
  low; revisit if the flag survives more than one release.

## References

* Spike: `docs/decisions/2026-06-04-spike-h1-header-synthesis.md`
* Plan: `docs/plans/2026-06-04-h1-header-synthesis-spike.md`
* Compound: `docs/compound/2026-06-04-pydantic-namespace-merge-vs-overwrite.md`
* Closure context: `docs/closure/012-S-heading-aware-segmentation.md`,
  `docs/closure/013-S-referentiality.md`, `docs/closure/015-S-post-g3-hygiene.md`
