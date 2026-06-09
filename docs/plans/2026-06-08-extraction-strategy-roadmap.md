---
title: docline extraction strategy roadmap (post-022-S, post-extraction-study)
date: 2026-06-08
status: proposed
decision: docs/decisions/2026-06-08-extraction-strategy-study.md
parent_closures:
  - docs/closure/021-S-triage-then-repair.md
  - docs/closure/022-S-pa4-closure.md
new_stashes:
  - 13F608BA
  - 378C8BC0
  - EFC6C84E
  - A39C3704
  - 5A622B72
  - 51332802
  - 4CB606D5
superseded_stashes:
  - 79F23BDE
  - 0AF15C3D
---

## Context

The 2026-06-08 extraction-strategy study established that **docling is
the right primary engine** for docline's stated downstream uses
(graph databases, vector embeddings, LLMs). The triage-then-repair
pattern shipped in 021-S is still valuable, but its role inverts:
rather than "heuristic by default, docling on flagged pages", the
correct framing is "docling by default, heuristic shortcut only when
the source page is structurally simple enough to suffice."

See `docs/decisions/2026-06-08-extraction-strategy-study.md` for the
empirical evidence and decision rationale.

## Roadmap

The roadmap groups the 7 new stashes into 3 thematic shipments, plus
a final research spike. Sequence reflects dependency order.

### Shipment 023-S — strategy alignment (recommended next)

**Goal**: lock in the study's findings as durable institutional
knowledge and update operator-facing docs so the new direction is
official.

**Composition (4 stashes)**:

| Stash | Kind | Description |
|---|---|---|
| `13F608BA` | task | Capture compound learning: AST metrics, not char counts |
| `A39C3704` | task | Update docs: `--pdf-mode auto` recommended for cosmos-class PDFs |
| `5A622B72` | feature | Add `--keep-page-pdfs` flag (small CLI surface change) |
| `378C8BC0` | feature | AST-aware QA mode (`structural_density`, `section_count`, `heading_count` in `--triage-report-only`) |

**Effort estimate**: ~1-2 days. Mostly docs + small library additions.
The `378C8BC0` AST-QA work has the reference implementation already
in `scripts/study/evaluate_markdown.py` — promote it to
`src/docline/process/quality_metrics.py` with test coverage.

**Acceptance criteria**:
- New compound learning at `docs/compound/2026-06-08-ast-fidelity-metrics.md`
- README + ARCHITECTURE.md updated with new default-mode guidance
- 021-S closure annotated with the new findings + transition to
  `production-ready` (or explicit decision to leave at `verified` due
  to the strategy pivot)
- `quality_metrics.py` with ≥10 metric functions and parser-error
  handling; integration with `triage_report_only`

**Risks**: low — no behavioral changes to default extraction path.

### Shipment 024-S — scoring model inversion (the real win)

**Goal**: rewrite the scorer to predict source-PDF structural
complexity BEFORE running any extractor, eliminating wasted markitdown
work on pages destined for docling.

**Composition (1 stash, but substantial)**:

| Stash | Kind | Description |
|---|---|---|
| `EFC6C84E` | feature | INVERT scoring: source-PDF complexity signals (font diversity, image presence, text-flow consistency, X-clusters) |

**Effort estimate**: ~3-5 days. Touches the scoring pipeline,
introduces new signals, requires re-validation against cosmos corpus.

**Acceptance criteria**:
- New `score_source_page(pypdf_page) -> SourceComplexityScore` API in
  `src/docline/process/source_complexity.py`
- ≥4 source-side signals: layout_complexity (existing, moved),
  font_diversity, image_presence, text_flow_consistency
- Orchestrator routes high-complexity pages directly to docling
  without running markitdown baseline first
- New PA3 cosmos run shows wall-clock reduction (target: ≤2h vs
  current 4h07m) while maintaining ≥80% of the AST-quality wins
  shown in the 2026-06-08 study
- 8-signal heuristic-output scorer deprecated (kept as fallback
  for backward compatibility)

**Risks**: medium. The new signal set requires empirical tuning.
Mitigation: use the existing 577-page sampled dataset under
`.elt/output/cosmos-triage-022/study/dataset/` as the calibration
target (do not need a fresh cosmos run for initial tuning).

### Shipment 025-S — docling speed-up (orthogonal improvement)

**Goal**: reduce per-page docling cost by batching, profiling, and
optionally GPU-accelerating.

**Composition (1 stash, possibly with spike first)**:

| Stash | Kind | Description |
|---|---|---|
| `51332802` | task | Profile + tune `docling_worker` for larger per-subprocess batches; consider GPU |

**Effort estimate**: unknown without a spike. Recommend a 1-day
spike first to characterize:
- Current per-subprocess overhead (model load time, GIL impact)
- Memory growth at various batch sizes
- GPU availability in target deployment environments
- Realistic best-case wall-clock improvement

**Acceptance criteria** (post-spike):
- Defined target speedup (e.g. ≥30% wall-clock reduction on cosmos)
- Implementation plan with rollback path
- New PA3 run validating the speedup

**Risks**: medium-high. ML model performance tuning has unpredictable
outcomes; GPU adds deployment complexity.

### Research spike — generalization study

**Goal**: verify the docling-wins finding holds across corpus classes
beyond cosmos.

**Composition**:

| Stash | Kind | Description |
|---|---|---|
| `4CB606D5` | task | Re-study with 2-3 additional corpora |

**Effort estimate**: ~1 day per corpus, parallelizable. Reuse
`scripts/study/` pipeline; only the input PDFs change.

**Suggested corpora**:
- Scientific paper (arXiv preprint, 8-15 pages, high formula density)
- Legal contract (50-100 pages, dense prose, hierarchical headings)
- Novel / long-form article (200+ pages, prose-only, no tables)

**Decision impact**: if any corpus class shows markitdown competitive
or winning, revise the global "docling primary" recommendation to
"docling primary EXCEPT for {corpus class}". Otherwise the cosmos
finding generalizes and no further policy change is needed.

## Critical-path summary

```
023-S (strategy alignment, 1-2 days)
   ↓  unlocks documented direction; no behavioral risk
024-S (scoring inversion, 3-5 days)
   ↓  major architectural improvement; risk-managed via existing dataset
025-S (docling speed-up, depends on spike)
   ↓  orthogonal, can run in parallel with 024-S
Research spike (per-corpus generalization, ~1 day each)
```

## Open questions for operator before staging 023-S

1. **021-S production-ready transition**: should it transition to
   `production-ready` (acknowledging the new doc-update commitment)
   or remain at `verified` until 024-S completes? The study's
   evidence is sufficient to make the call now.
2. **Compound learning placement**: `docs/compound/2026-06-08-ast-fidelity-metrics.md`
   as a new file, or merge into the existing
   `docs/compound/2026-06-06-triage-then-repair-pattern.md` as a
   "lesson learned" section? Probably new file (different concern).
3. **Branch hygiene**: PR #46 (pdfminer fix) is still open. Order of
   operations recommendation: merge PR #46 first → cherry-pick study
   artifacts onto fresh main → open 023-S branch.

## Snapshot of artifacts produced tonight

| Path | Status |
|---|---|
| `docs/decisions/2026-06-08-extraction-strategy-study.md` | committed to study branch |
| `docs/plans/2026-06-08-extraction-strategy-roadmap.md` | committed to study branch (this file) |
| `scripts/study/build_comparison_dataset.py` | committed to study branch |
| `scripts/study/evaluate_markdown.py` | committed to study branch |
| `scripts/study/analyze_study.py` | committed to study branch |
| `.elt/output/cosmos-triage-022/study/` | gitignored — local evidence only |
| `.backlogit/stash.jsonl` | 7 new high/medium/low stashes added |
| `docs/memory/2026-06-08/extraction-study-memory.md` | committed to study branch |

## Recommended morning sequence

1. **Operator review** of `docs/decisions/2026-06-08-extraction-strategy-study.md`
2. Open VS Code diffs on 2-3 of the sampled comparison ranges under
   `.elt/output/cosmos-triage-022/study/dataset/range-*/` to confirm
   the study's finding visually
3. If aligned: merge PR #46, then open 023-S to start the strategy
   alignment shipment
4. If skeptical: stash 4CB606D5 (generalization study) can run first
   on 1-2 additional corpora before committing to the new direction
