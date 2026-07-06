---
title: "Adversarial review — 052-F UTF-8 BOM in Markdown frontmatter parsing"
type: review
date: 2026-07-05
feature: 052-F
status: reviewed
reviewers:
  - correctness
  - python
  - constitution
  - security
  - maintainability
  - scope-boundary
---

Adversarial multi-persona review of the 052-F BOM fix before opening the PR.
The change is minimal: strip a leading U+FEFF in `_parse_md_frontmatter` and
read `.md/.txt` staged files with `utf-8-sig` in `build_output_document_parts`.

## Findings

| # | Severity | Persona | Finding | Resolution |
|---|---|---|---|---|
| 1 | P3 | Scope | `readers/text.py::read_text` (a standalone text reader) does not strip a BOM. | **Accepted / out of scope** — it is not imported by any module and is not on the live ingestion path (the process pass reads directly in `build_output_document_parts`). Fixing it would touch a public reader's default encoding for no in-path benefit. |

## Persona notes (no actionable findings)

- **Correctness**: BOM stripping is offset-safe (all fence/body offsets are taken
  after the strip); `text[1:]` removes exactly one BOM (files carry at most one).
  `utf-8-sig` decodes non-BOM files identically to `utf-8`, so non-BOM behavior is
  byte-for-byte unchanged (asserted by the unchanged existing tests). The two
  layers (read-time decode + parse-time strip) are complementary, not conflicting.
- **Python/Constitution**: no new dependency; no type or signature changes; typed
  behavior preserved; TDD red→green followed.
- **Security**: no security surface; BOM handling cannot introduce traversal or
  injection.
- **Scope**: only `src/docline/process/output_contract.py` changed (+ tests).
  HTML/else read branches deliberately left as-is.

## Verification

- Unit + parts tests: `test_parse_md_frontmatter_strips_leading_bom`,
  `..._strips_bom_without_frontmatter`, `test_build_output_document_parts_handles_bom_prefixed_md`.
- Runtime: re-ingested the previously-warning corpus dir
  `bi-shared-docs/docs/analysis-services/tutorial-tabular-1400` — **zero**
  "Failed to build frontmatter" warnings; sampled output now carries assembled
  docline frontmatter (`doc_type`, `content_sha256`, chunk anchors).
- Gates: ruff clean, pyright (venv) 0 errors, pytest 1507 passed / 6 skipped,
  format clean.

## Runtime verification recommendation

Mode: **manual** — already exercised via the targeted re-ingest above. No API or
browser surface. No strict-safety destructive-action classification required
(additive parse fix; no deletes, migrations, or contract changes).
