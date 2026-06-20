---
title: Closure — 035-S Documentation (PDF engine selection guide + engram CLI grounding)
date: 2026-06-19
shipment: 035-S
feature: 033-F
status: verified
merged_pr: 90
merge_sha: 3997945
branch: docs/035-S-engine-selection-and-engram
---

## Readiness status

**READY** — merge to `main` is complete (PR #90, merge commit `3997945`, a true
two-parent merge commit per P-009). Feature 033-F is fully complete (both tasks
done) and archived with the shipment.

## What shipped

Documentation-only shipment. No code, no docling inference.

### 033.001-T — PDF engine selection matrix

`README.md` gains a "Choosing a PDF engine" section documenting the
`--pdf-engine` flag (`auto` / `docling` / `mistral_ocr` / `heuristic`) and a
fidelity-vs-throughput matrix that recommends an engine per corpus class
(technical reference, table-heavy, scientific papers, forms/invoices, prose,
offline). Evidence: 031-S (Mistral PROMOTE-AS-PEER — tables mean +33.9%, ~10×
throughput, headings −8.4%) and the 2026-06-08 extraction strategy study
(docling wins 14/15 sampled technical-reference ranges). 029-S (ADI removed) is
noted as historical record.

The stash entry referenced `ARCHITECTURE.md`, which does not exist in the repo.
The architecture-side engine note was added to the canonical design doc
`docs/design-docs/DocumentIngestion&ValidationPipelineDesign.md` (Extraction
Engines section), cross-referencing the README matrix.

### 033.002-T — Engram CLI grounding compound learning

New `docs/compound/2026-06-19-engram-cli-grounding.md` capturing the CLI↔MCP 1:1
mapping, the session-start probe protocol, the stale-process (shim vs. daemon)
diagnostic, and the DB-locked retry-once envelope.

## Verification

- `--pdf-engine` choices verified against source: `cli.py` (argparse choices)
  and `app_models.py` (`Literal["auto","docling","mistral_ocr","heuristic"]`,
  default `auto`; `mistral_ocr` never auto-selected).
- `markdownlint-cli2` against the repo `.markdownlint.json` (MD001/MD025/MD041) —
  0 errors across all changed files.
- All internal doc links resolve (031-S, 029-S, 2026-06-08 study present).
- No Python touched → no pytest/ruff/pyright impact. Docline CI is paused by
  design (`ci.yml`).
- Copilot review: clean, fresh on merged HEAD, zero unresolved threads.

## Follow-ups

- Code/security task `24920EFF` (validate `weights_path` workspace containment
  in `fidelity_scorer.load_weights`) remains in the stash for a future hardening
  cycle.
- Operator-gated docling work (bug `6E6754D4`, spikes `D771B78E`/`E32FAF6F`,
  study `4CB606D5`, blocked `032.001-T`/`032.003-T`) awaits operator-run docling
  inference.
