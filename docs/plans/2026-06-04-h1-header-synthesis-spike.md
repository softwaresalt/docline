---
title: Plan — H1 header synthesis spike
date: 2026-06-04
status: ready
shipment: 017-S
feature: 018-F
deliberation: docs/decisions/2026-06-04-deliberation-h1-header-synthesis.md
stash: CD9F1913
---

# Plan — H1 header synthesis spike (017-S)

## Goal

Produce a measured, evidence-backed recommendation for how docline should
synthesize missing H1 headers so that every emitted part has a non-null
`section_title` and the strict graphtor parentage check no longer needs the
`--allow-heading-disorder` escape hatch.

## Non-goals

* Implementing the synthesizer in production code.
* Adding an SLM dependency.
* Touching `process/assemble.py` parentage enforcement.
* Replacing the `--allow-heading-disorder` flag (the follow-on shipment will).

## Deliverables

1. **Corpus analysis script** at `scripts/spike_h1_corpus_analysis.py`
   (one-shot, not added to the package). Parses every `.md` part under
   `.elt/output/` (965 parts) and reports:
   * Count of parts with `section_title: null` per source job
   * Count of parts where the body's first heading is H2/H3 (no H1)
   * Count of parts where `title` frontmatter could plausibly serve as H1
     (length ≤ 100 chars, not a placeholder like "Untitled" or "Part N")
   * Count of parts where the first non-empty paragraph is a sensible
     candidate (length 10–120 chars, no markdown image syntax, no URL-only)
2. **Decision artifact** at
   `docs/decisions/2026-06-04-spike-h1-header-synthesis.md` with:
   * Corpus stats (table per source job)
   * Per-tier rescue rate (how many headerless parts each deterministic
     tier would fix)
   * Approach comparison with measured numbers, not guesses
   * Recommendation (likely hybrid deterministic-first with SLM gated
     behind an explicit opt-in extra)
   * Risk register (what could go wrong, what the spike did NOT measure)
3. **Follow-on shipment plan stub** at
   `docs/plans/2026-06-04-h1-synthesis-implementation-stub.md` with:
   * Module placement (likely a new normalization pass in
     `src/docline/process/header_synthesis.py`)
   * API sketch
   * Where it wires in (read time vs assemble time vs separate pass)
   * Test surface required
   * Estimated task decomposition for the next Stage cycle
4. **Closure record** at `docs/closure/017-S-h1-header-synthesis-spike.md`
   with merge SHA and the decision artifact's recommendation summary.

## Tasks

| Task | Title | Estimated effort |
|---|---|---|
| 018.001-T | Build corpus analysis script and run it against `.elt/output/` | ~45 min |
| 018.002-T | Author decision artifact with measured tier rescue rates and recommendation | ~60 min |
| 018.003-T | Author follow-on shipment plan stub | ~30 min |
| 018.004-T | Author closure record for 017-S | ~15 min |

Total budget: ~2.5 hours. Hard ceiling: 4 hours.

## Constitution Check

| Principle | Check |
|---|---|
| I. Safety-First Python | Spike script lives outside `src/`; no production change |
| II. Test-First Development | Spike script is a one-shot analysis, exempt from TDD |
| III. Workspace Isolation | Only reads from `.elt/output/`; writes only under `docs/` and `scripts/` |
| IV. CLI Containment | All paths resolve under cwd |
| V. Structured Observability | Decision artifact captures all measured numbers |
| VI. Single Responsibility | No new dependencies in this shipment |
| VII. Destructive Approval | No destructive operations |
| VIII. Safety Modes | careful mode if SLM evaluation is added; this spike does NOT plan to load any SLM |
| X. Context Efficiency | Decision artifact is the queryable output, not the corpus dump |
| XI. Merge Commit | Merge commit only |

## Quality Gate Plan

This shipment is documentation + a throwaway script. No production code
change, no test change. Quality gates will be:

* `ruff check .` — must pass (spike script lives under `scripts/` which is
  ruff-included)
* `ruff format --check .` — must pass
* `pyright src/` — unchanged (no src/ change)
* `pytest` — unchanged (no test change)
* `python -m build` — unchanged (no packaging change)

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Corpus is too small for representative rescue rates | Medium | Decision artifact explicitly calls out sample size and recommends a corpus-expansion follow-up if needed |
| Spike concludes SLM is mandatory | Low | Operator approval gate on the follow-on shipment plan stub |
| Spike runs over budget | Low | Hard ceiling of 4 hours; if hit, halt and document partial findings |

## References

* Deliberation: `docs/decisions/2026-06-04-deliberation-h1-header-synthesis.md`
* Stash: `CD9F1913`
* Load test artifacts: `.elt/output/`
* Closure context: `docs/closure/012-S-heading-aware-segmentation.md`,
  `docs/closure/013-S-referentiality.md`, `docs/closure/015-S-post-g3-hygiene.md`
