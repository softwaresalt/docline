---
title: Findings — seam-integrity heading/AST lint of assembled cosmos output
date: 2026-06-28
kind: investigation
status: complete
feature: 037-F
shipment: 040-S
references:
  - scripts/study/seam_lint.py
  - tests/test_seam_lint.py
  - src/docline/process/ast_lint.py
  - src/docline/process/heading_validation.py
  - src/docline/process/assemble.py
  - src/docline/process/output_contract.py
  - docs/decisions/2026-06-28-merge-gap-tuning-verdict.md
---

# Findings — seam-integrity heading/AST lint

## Summary

**The available assembled cosmos output passes the heading-hierarchy ingestion
gate — 0 failures, 0 AST depth issues across all 12 documents.** A reusable,
tested harness (`scripts/study/seam_lint.py`) now performs this check. One scope
caveat applies: the available corpus is uniformly in the auto-tolerated
include-fragment class, so it does not yet *strictly* exercise the
heuristic↔docling seam under H1→H2→H3 enforcement.

## What was built

`scripts/study/seam_lint.py` — an agent-safe harness (no docling import, pure
markdown ingest) that, per assembled document:

* strips YAML frontmatter to the body (as the assembler does),
* runs the **heading-hierarchy gate** by reusing
  `heading_validation.validate_heading_hierarchy` with the same sparse-hierarchy
  auto-tolerance the assembler applies (`body_should_skip_heading_validation`,
  028-S), and
* runs the **AST depth lint** by reusing `ast_lint.lint_markdown_ast`
  (informational — H4–H6 are tolerated by the ingestion contract).

The hierarchy result is the pass/fail gate; AST depth notes are surfaced
separately. Covered by 12 unit tests (`tests/test_seam_lint.py`) including a
real non-tolerated disorder case (H2 before any H1), a sparse-tolerated case,
and the AST-vs-hierarchy separation.

## Result over `.elt/output/azure-cosmos-db/chunk-0001..0012.md`

```text
SUMMARY: 12 document(s), 0 hierarchy failure(s), 12 tolerated (sparse), 0 AST depth note(s).
VERDICT: PASS — all documents satisfy the heading-hierarchy gate
```

All 12 chunks are **H2-dominant** (tens to hundreds of H2s, no enforceable H1,
no H3). The few `# ...` lines present are inside fenced code blocks, which the
validator correctly excludes — so every chunk is an "include fragment" (no H1
anywhere), the pattern the ingestion contract auto-tolerates by design. No real
H1/H2/H3 disorder exists, and no heading exceeds H3.

## Scope caveat (what this does not yet prove)

* The corpus is uniformly auto-tolerated (no H1), so strict H1→H2→H3 enforcement
  never engaged. The harness *would* catch real disorder (the unit tests prove
  it), but this corpus has none to catch.
* The `azure-cosmos-db/chunk-*.md` files are chunked-path output. No assembled
  `process_pdf_triaged` single document (the path that interleaves heuristic and
  docling engines) is available in-workspace — only per-range comparison files
  and the triage summary/TSV.

To strictly close the cross-seam question, run the harness over an assembled
triage output from an operator cosmos run (heavy docling inference on the dev
box). The harness accepts that input as-is:

```powershell
python scripts/study/seam_lint.py --paths <assembled-triage-output-dir-or-file>
```

## Conclusion

For the concern that gates graphtor-docs ingestion — a coherent, ingestible
heading hierarchy — the assembled cosmos output is clean, and the project now
has a tested, repeatable check. The deeper strict-seam verification is unblocked
and tooled, pending an operator-run assembled-triage artifact.
