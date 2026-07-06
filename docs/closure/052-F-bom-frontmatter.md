---
title: "Closure — 052-F UTF-8 BOM in Markdown frontmatter parsing"
status: verified
feature: 052-F
merged_pr: 138
merge_sha: 6889c4e
date: 2026-07-05
---

Fixed a latent BOM defect in the Markdown ingestion path. A leading U+FEFF
before the YAML frontmatter fence defeated `_parse_md_frontmatter`, so
BOM-prefixed Microsoft Learn files fell back to raw-body output with no
assembled frontmatter and no chunk anchors.

## Delivered

- `_parse_md_frontmatter` (`process/output_contract.py`) drops a leading BOM
  before the `---` fence check.
- `build_output_document_parts` reads `.md/.txt` staged files with `utf-8-sig`
  so no BOM reaches the DocFx-include, normalize, or frontmatter passes.

## Verification

- Unit + parts regression tests (`test_source_md_frontmatter.py`).
- Runtime: re-ingested `bi-shared-docs/docs/analysis-services/tutorial-tabular-1400`
  (previously warning-heavy) → zero "Failed to build frontmatter" warnings;
  output now carries proper docline frontmatter.
- Gates: ruff clean, pyright (venv) 0 errors, pytest 1507 passed / 6 skipped,
  format clean.
- Adversarial review: `052-F-bom-frontmatter-review.md` (no P0/P1).

## Follow-up

None. Non-BOM files decode byte-for-byte identically. The standalone
`readers/text.py::read_text` (not on the ingestion path) was deliberately left
unchanged.
