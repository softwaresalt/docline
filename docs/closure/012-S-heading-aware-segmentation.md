---
shipment: 012-S
title: "Closure record — heading-aware semantic segmentation (G3a)"
status: verified
merge_sha: 7d4579f
merged_pr: 24
---

This document captures the implementation evidence for shipment `012-S`,
which replaces the page-based and char-bin output segmentation in
`docline process` with heading-aware semantic segmentation driven by
ATX H1 and H2 boundaries.

## Scope

* New module: [`src/docline/process/segment.py`](../../src/docline/process/segment.py) — commit `b326752`
* Wiring: [`src/docline/process/output_contract.py`](../../src/docline/process/output_contract.py) — commit `867ee53`
* Tests (RED): [`tests/process/test_segment.py`](../../tests/process/test_segment.py) — commit `582eab7`
* Regression fixture refresh: [`tests/elt/test_process_regression.py`](../../tests/elt/test_process_regression.py) — commit `867ee53`
* Plan: [docs/plans/2026-06-03-heading-aware-segmentation-plan.md](../plans/2026-06-03-heading-aware-segmentation-plan.md)
* Plan review: [docs/decisions/2026-06-03-heading-aware-segmentation-plan-review.md](../decisions/2026-06-03-heading-aware-segmentation-plan-review.md) (APPROVED — P2 finding `MarkdownIt().enable("table")` incorporated in `segment.py:_parse`)
* Source stash: `90695245` (harvested by Stage during shipment assembly)

## Files changed

| Path | Change | Reason |
|---|---|---|
| `src/docline/process/segment.py` | NEW | Public `segment_markdown(markdown, *, max_chars=12_000) -> list[str]` and helpers |
| `src/docline/process/output_contract.py` | MODIFY | PDF and DOCX branches now route through `segment_markdown`; remove `_chunk_text_blocks` and `_DOCX_SEGMENT_CHAR_LIMIT`; drop `read_pdf_pages` import |
| `tests/process/test_segment.py` | NEW | 16 tests (13 named scenarios + 3 parametrized `max_chars`) |
| `tests/elt/test_process_regression.py` | MODIFY | `test_multi_page_pdf_output_is_segmented_with_standardized_manifest_fields` updated to use H1-prefixed fixture content; new `test_flat_pdf_without_headings_emits_single_part` captures the documented behavior change |

## Quality gate evidence

All five CI gates green at HEAD `867ee53`:

| Gate | Command | Result |
|---|---|---|
| Format | `ruff format --check .` | `145 files already formatted` |
| Lint | `ruff check .` | `All checks passed!` |
| Typecheck | `pyright src/` | `0 errors, 0 warnings, 0 informations` |
| Tests | `pytest` | `819 passed, 5 skipped in 17.66s` |
| Build | `python -m build` | `Successfully built docline-0.1.0.tar.gz and docline-0.1.0-py3-none-any.whl` |

## Observed part-count deltas

Behavior change measured against representative inputs. The previous
behavior split PDFs per physical page and DOCXs per 6000-char greedy
bin. The new behavior is heading-driven with a char-bin safety net.

| Input shape | Old part count | New part count | Notes |
|---|---|---|---|
| 3-page PDF, plain text per page, no H1 markdown | 3 | **1** | Flat text → char-bin fallback; joined content under `max_chars` |
| 3-page PDF, each page prefixed with `# ` (H1) | 3 | **3** | Heading-driven split matches physical pages by coincidence |
| Single rendered doc with H1 + 2 oversize H2 sections (~60k chars) | ~10 (char-bin per ~6k) | **6** | Hard split at H1, sub-split at H2; one H2 sub-part fell to char-bin |
| 30-paragraph no-heading prose (~36k chars) | ~6 (char-bin per ~6k) | **4** | Char-bin fallback engaged; paragraphs >12k preserved whole |
| Empty / whitespace-only input | 1 (single empty part) | **1** | Empty-segment contract preserved (`[""]`) |

**Real-PDF implication**: `pypdf` (the current PDF extractor) emits flat
text with no markdown structure. Real PDFs processed through `docline
process` today will collapse to a **single-part output per source PDF**
under heading-aware semantics — the existing seed PDFs do not contain
extractable H1 markers. Multi-part PDF output will re-engage naturally
once G3c (stash `351170C9`) wires `docling` as the PDF engine, since
docling preserves layout structure and emits markdown headings.

**DOCX implication**: DOCX inputs that contain `<w:pStyle w:val="Heading1"/>`
already emit `# ` lines via `read_docx_blocks` paragraph-style mapping
(see `tests/readers/test_docx_style_mapping.py`). Such DOCX inputs will
split at H1 boundaries as intended starting with this shipment.

## Contract preservation

| Surface | Status |
|---|---|
| `OutputDocumentPart` dataclass | Unchanged |
| `build_output_document_parts` signature | Unchanged |
| `_relative_output_path` (filename convention `part-NNNN.md`) | Unchanged |
| HTML / MD / TXT branches | Unchanged |
| `docline export-schema` output | Unchanged — `src/docline/schema/` directory carries zero diff vs `origin/main` |
| BaseFrontmatter v1 contract | Preserved (no schema source modifications) |
| Dependency graph | Unchanged — zero new dependencies; reuses existing `markdown-it-py>=4,<5` |

## Review findings

The review skill (mode `report-only`) was invoked at the end of the
build loop with the following persona coverage: Constitution, Python,
Correctness, Maintainability, Learnings Researcher, Scope Boundary
Auditor.

**Outcome**: 0 P0, 0 P1, 0 P2, 3 P3 advisories.

| ID | Severity | Class | Finding |
|---|---|---|---|
| F1 | P3 | advisory | `segment_markdown` parses tokens twice (once for the H1 probe, once inside `_split_at_level`). Negligible perf cost for realistic input sizes. |
| F2 | P3 | advisory | `_char_bin` splits on literal `"\n\n"` only. `read_pdf` and `read_docx_blocks` emit `\n`, so risk is low — but explicit normalization would harden against future extractor changes. |
| F3 | advisory | informational | Page-split → heading-split is a meaningful behavior change for downstream consumers. Documented above in **Observed part-count deltas**. |

## Carry-forward work

The following stash entries explicitly build on this shipment and are
staged for separate shipments:

| Stash ID | Priority | Theme | Relationship to 012-S |
|---|---|---|---|
| `C5CA1740` | high (feature) | **G3b** — in-frontmatter referentiality + chunk anchors | Adds `parent_document_id`, `part_index`, `total_parts`, `prev_part`, `next_part`, `section_title` to BaseFrontmatter; flips `emit_chunk_anchors=True`. **Depends on 012-S**: G3b's `section_title` field is populated from the H1 boundary that 012-S now establishes. |
| `351170C9` | high (feature) | **G3c** — docling PDF engine + image sidecars | Wires `docling` as the PDF engine and extracts figures/tables as sidecar files. **Independent of 012-S**: G3c will populate the H1 markdown structure that G3a's segmenter then consumes. After G3c lands, real PDFs will naturally split into multiple parts. |

## Runtime verification

Runtime verification is **not required** for this shipment. The change
is a pure refactor of an internal segmentation strategy; no runtime
surface (CLI flag, MCP tool, schema field, configuration field) is
added, removed, or renamed. The behavior change is observable in
output filenames (`part-0001.md` etc.) and part counts, both of which
are covered by the updated regression tests
(`tests/elt/test_process_regression.py`).

## Rollback

`git revert {merge_sha}` cleanly restores the prior page-based and
char-bin segmentation. No data migration is required because output is
regenerated on each `docline process` invocation.
