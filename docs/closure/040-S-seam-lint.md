---
title: Closure — 040-S seam-integrity lint harness
date: 2026-06-28
shipment: 040-S
feature: 037-F
status: verified
merged_pr: 108
merge_sha: bc55c8a
branch: feat/040-S-seam-lint
---

## Readiness status

**VERIFIED** — merged to `main` (PR #108, merge commit `bc55c8a`, two-parent
per P-009). Feature `037-F` and task `037.001-T` complete; shipment archived.

## What shipped

`scripts/study/seam_lint.py` — an agent-safe harness that validates assembled
triage markdown for a coherent, ingestible heading hierarchy across the
heuristic↔docling engine seams, reusing `validate_heading_hierarchy` (the
ingestion gate, with 028-S sparse-tolerance) and `lint_markdown_ast`
(informational AST depth). 13 unit tests; ruff/pyright/pytest clean.

## Result

Over `.elt/output/azure-cosmos-db/chunk-0001..0012.md`: 0 hierarchy failures,
0 AST depth issues. The corpus is H2-dominant include-fragment content (no
enforceable H1), auto-tolerated by design. Findings in
`docs/decisions/2026-06-28-seam-integrity-lint-findings.md`.

## Open follow-up (operator-run)

Strict cross-seam validation needs an assembled `process_pdf_triaged`
single-document artifact (heavy docling; dev box). The harness accepts it as-is:
`python scripts/study/seam_lint.py --paths <assembled-triage-output>`.

## Review

One Copilot finding (untested `main()` AST-depth report path) fixed in `7e1ffee`,
replied, and resolved. 1 pre-existing unrelated failure remains in the suite
(`test_get_markitdown_silences_noisy_pdfminer_loggers`, markitdown `enable_plugins`
API drift) — not in scope.
