---
title: "Deliberation — post-G3 hygiene (CRLF normalization + docling tuning)"
stash_ids: ["F50AD7E6", "5ADD558F"]
status: adopted
date: 2026-06-04
---

# Deliberation: 015-S post-G3 hygiene

## Source

Two low-priority follow-up stash entries surfaced during the G3a–G3c arc:

- `F50AD7E6` (low, task): `_char_bin` CRLF normalization — review F2 advisory from 012-S
- `5ADD558F` (low, task): docling `PdfPipelineOptions` tuning + PictureSink wiring — plan-review F3 advisory from 014-S

## Grouping rationale

Both entries are direct follow-ups to the G3 segmentation + docling arc. They
are independent at the file level (`process/segment.py` vs `readers/pdf.py`)
but share a thematic context: both harden the parts of the pipeline that
become more important once docling is in use as the PDF engine.

- **CRLF normalization** matters because docling on Windows may emit `\r\n`
  in PDF text extracts, which `_char_bin`'s literal `"\n\n"` split would
  fail to break on. Without it, batches that switch from heuristic (which
  emits `\n`) to docling could silently produce single-bin output for
  multi-paragraph pages.
- **Docling tuning + picture wiring** completes the picture-extraction
  story that 014-S laid the plumbing for (`PictureSink`, `media_files`
  manifest field). Without the `generate_picture_images=True` flag plus
  the routing into `PictureSink`, docling-extracted figures never reach
  the sidecar directory.

Grouping them in one shipment is justified by:

- Both are post-G3c hygiene (cohesive theme)
- Both are too small individually for the Stage → Ship overhead
- Files touched are distinct (no merge-conflict risk between tasks)
- Docling-side tests are skip-gated; CI scope is bounded

## Decision

Proceed as a single hygiene shipment (`015-S`) with two TDD-decomposed
work threads. Stage to harvest both into one feature artifact with
sub-tasks per concern.

## Out of scope

- `ED74577A` (cross-OS CI matrix) and `0AA8B223` (Windows tmp_path RCA)
  remain separate because the RCA is investigative (spike-shaped) and
  the matrix depends on the RCA outcome.
- `7AA9FAA0` (PyPI/Releases workflow) defers until a 1.0 release.

## Constitution check

| Principle | Compliance |
|---|---|
| I. Safety-first Python | Typed; no `Any`; small additive changes |
| II. TDD | RED tests first per task |
| VI. Single responsibility | No new dependencies; reuses existing `_char_bin`, `_read_pdf_docling_pages`, `PictureSink` |
| X. Context efficiency | 2 source files modified, 2 small test additions, 1 closure |
| XI. Merge commit history | Standard PR flow |
