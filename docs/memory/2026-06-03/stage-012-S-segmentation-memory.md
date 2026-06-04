# 2026-06-03 — Stage shipment 012-S (G3a heading-aware segmentation)

## Outcome

Staged shipment `012-S` from stash `90695245` (G3a only — G3b and G3c held for subsequent orchestrator cycles per scope decision). Backlog and planning artifacts committed on branch `stage/012-segment-by-heading` and opened as **PR #23** against `main`.

## Artifacts produced

| ID | Type | Title |
|---|---|---|
| `012-F` | feature | Heading-aware semantic segmentation for processed output parts |
| `012.001-T` | task (RED) | Write failing tests for `segment_markdown` |
| `012.002-T` | task (GREEN, deps 012.001-T) | Implement `src/docline/process/segment.py` |
| `012.003-T` | task (INTEGRATE, deps 012.002-T) | Wire into `build_output_document_parts` and run 5 gates |
| `012.004-T` | task (CLOSURE, deps 012.003-T) | Author closure document |
| `012-S` | shipment | Shipment 12 — heading-aware semantic segmentation (G3a) |

Plan: `docs/plans/2026-06-03-heading-aware-segmentation-plan.md`
Plan review: `docs/decisions/2026-06-03-heading-aware-segmentation-plan-review.md` (APPROVED)

## Branch / PR

- Branch: `stage/012-segment-by-heading`
- Commit: `6d5f169` — `chore(core): stage shipment 012-S — heading-aware segmentation (G3a)`
- PR: <https://github.com/softwaresalt/docline/pull/23>

## Decisions

- **Skipped `deliberate` skill.** Stash text was precise (algorithm, default `max_chars=12_000`, modules touched, test scenarios, explicit no-schema-break). No structured trade-off analysis required.
- **Skipped `plan-harden`.** Blast radius is moderate: one new module, one modified module, zero new deps, no schema or CLI distribution surface change. Plan-review approved without hardening pass.
- **Used `main` PR flow** (not direct push) because branch protection blocks direct push per orchestrator note (P-014).
- **Sequenced as 4 TDD-ordered tasks** instead of 5: folded "run quality gates" into the integration task (012.003-T) because gates are a Ship-side execution detail, not standalone work.
- **Carry-forward note for closure (012.004-T):** Expected to observe part-count *reduction* on seed PDFs (current `pypdf` yields 0 H1 headings, so the char-bin fallback joins what was previously 20 pages → 1 segment). This is correct graceful-degradation behavior; G3c's docling engine will engage the H1/H2 path naturally once it lands.

## Open questions for Ship

- `tests/elt/test_process_regression.py` line ~320 monkeypatches `docline.app.build_output_document_parts` to inject an error — that test does not depend on internal segmentation behavior and should remain green without fixture updates. If Ship observes a part-count fixture mismatch elsewhere in `tests/elt/`, update the fixture expectation per 012.003-T acceptance criteria.
- Plan-review P2 note: enable `MarkdownIt().enable("table")` in `segment.py` so GFM tables stay at the block level for clean `map`-based slicing. Already captured in 012.002-T implementation notes.

## Stash carry-forward

- `C5CA1740` (G3b, high) — frontmatter referentiality + `emit_chunk_anchors=True`. Depends on 012-F's segmentation contract. Will require graphtor-docs schema snapshot refresh.
- `351170C9` (G3c, high) — docling PDF engine + image sidecars. Large scope; adds `[pdf]` optional extra + ~50MB model cache CI story.
