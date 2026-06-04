---
title: "Implementation plan — post-G3 hygiene (015-S)"
stash_ids: ["F50AD7E6", "5ADD558F"]
shipment: "015-S"
status: approved
requires_plan_hardening: no
---

# Post-G3 hygiene (015-S)

**Date**: 2026-06-04
**Source deliberation**: [`docs/decisions/2026-06-04-post-g3-hygiene-deliberation.md`](../decisions/2026-06-04-post-g3-hygiene-deliberation.md)
**Target shipment**: `015-S`
**Depends on**: `012-S` (segmentation), `013-S` (referentiality), `014-S` (docling + sidecars)

## Goal

Address two low-priority follow-up advisories from the G3 arc:

1. Normalize CRLF line endings on entry to `segment_markdown` so paragraph
   detection survives Windows-extracted PDF text.
2. Enable docling `PdfPipelineOptions(do_table_structure=True,
   table_structure_options=TableStructureOptions(do_cell_matching=True),
   generate_picture_images=True, images_scale=2.0)` and route
   docling-rendered pictures through `PictureSink` so figures
   extracted from PDFs land alongside the per-source markdown.

## Scope

### In scope

- **`src/docline/process/segment.py`**: normalize `\r\n` → `\n` at the top
  of `segment_markdown` so `_char_bin`'s literal `\n\n` split works on
  Windows-extracted text regardless of upstream extractor.
- **`src/docline/readers/pdf.py`**:
  - Extend `_read_pdf_docling_pages(path)` signature to
    `_read_pdf_docling_pages(path, *, picture_sink: PictureSink | None = None)`.
  - When `picture_sink` is provided, configure
    `DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(
        pipeline_options=PdfPipelineOptions(
            do_table_structure=True,
            table_structure_options=TableStructureOptions(do_cell_matching=True),
            generate_picture_images=True,
            images_scale=2.0,
        ),
    )})`.
  - After conversion, iterate `result.document.pictures` and for each
    picture with rendered bytes, emit through `picture_sink.emit(...)`.
  - Replace `[](media/figure-NNNN.ext)` placeholders or inline image
    references in the produced markdown with sibling-relative
    `![](media/figure-NNNN.ext)` references (the existing PictureSink
    naming convention).
- **Wiring in `output_contract.py`**: thread the existing `picture_sink`
  through to `read_pdf` and onward to `_read_pdf_docling_pages`. Currently
  the docling path doesn't accept a sink. Add a `picture_sink` kwarg to
  `read_pdf` and `read_pdf_pages` that is passed only when the resolved
  engine is `docling`.

### Out of scope

- OCR enabling (`do_ocr=True`) — separate cycle if needed; docling's
  default is OCR-off which avoids the Tesseract / EasyOCR ML dependency
  cost.
- Replacing existing PictureSink reference-emission with a richer caption
  extraction (e.g., reading docling picture `caption_text`). Future
  enhancement.
- DOCX picture extraction tuning — 014-S already covered the `<w:drawing>`
  path; no docling-side DOCX rendering in scope.

## Design

### CRLF normalization

```python
# src/docline/process/segment.py (top of segment_markdown)
def segment_markdown(markdown: str, *, max_chars: int = _DEFAULT_MAX_CHARS) -> list[str]:
    """..."""
    if not markdown or not markdown.strip():
        return [""]
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    # remainder uses `normalized` instead of `markdown`
    ...
```

The double replacement (`\r\n` → `\n` then `\r` → `\n`) handles both
Windows (`\r\n`) and legacy classic Mac (`\r`) line endings safely. The
existing tests use `\n` so behavior is preserved; new test covers `\r\n`.

### Docling picture extraction wiring

```python
# src/docline/readers/pdf.py
def _read_pdf_docling_pages(
    path: Path,
    *,
    picture_sink: PictureSink | None = None,
) -> list[str]:
    """..."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            TableStructureOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as err:
        raise DependencyUnavailableError(
            "Install the optional 'docling' package to use "
            "layout_engine='docling' (extras: docline[pdf]; missing import: docling)"
        ) from err
    try:
        pipeline_options = PdfPipelineOptions(
            do_table_structure=True,
            table_structure_options=TableStructureOptions(do_cell_matching=True),
            generate_picture_images=picture_sink is not None,
            images_scale=2.0,
        )
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
        result = converter.convert(str(path))
        markdown = result.document.export_to_markdown()

        if picture_sink is not None:
            markdown = _route_docling_pictures(
                result.document, markdown, picture_sink
            )
    except DependencyUnavailableError:
        raise
    except Exception as err:  # noqa: BLE001
        raise PdfReadError(f"docling failed to convert PDF: {path}") from err
    markdown = markdown.strip()
    if not markdown:
        return []
    return [markdown]


def _route_docling_pictures(
    document: object, markdown: str, picture_sink: PictureSink
) -> str:
    """Emit docling-rendered pictures through ``picture_sink`` and
    rewrite the markdown to reference the assigned sidecar filenames.

    Iterates ``document.pictures``; for each picture with a rendered
    PIL image attached (via ``generate_picture_images=True``), persists
    the image bytes through the sink and replaces any
    ``![Image](path/to/picture)`` or ``<!-- image -->`` placeholder
    in the markdown with the standard ``![](media/figure-NNNN.ext)``
    reference.
    """
    ...
```

The picture-extraction details depend on the docling 2.x API for picture
representations. Implementation reads docling's `document.pictures` list
and writes via `picture_sink.emit(mime="image/png", data=png_bytes)`.

### Wiring through `read_pdf` / `read_pdf_pages`

Add `picture_sink: PictureSink | None = None` kwarg to both functions.
Pass it to `_read_pdf_docling_pages` when the resolved engine is
`"docling"`. Heuristic path ignores the sink.

### Wiring through `build_output_document_parts`

The DOCX branch already passes `picture_sink`. Mirror for PDF: pass
`picture_sink` to `read_pdf(layout_engine=layout_engine, picture_sink=picture_sink)`.

## Test plan (TDD RED phase first)

| File | Test | Coverage |
|---|---|---|
| `tests/process/test_segment.py` | `test_segment_handles_crlf_paragraph_separator` | text with `\r\n\r\n` separators splits at paragraph boundaries |
| | `test_segment_handles_classic_cr_separator` | text with `\r\r` separators (legacy Mac) |
| | `test_segment_normalizes_mixed_endings` | mixed `\r\n` and `\n` produce identical output to all-`\n` |
| `tests/readers/test_pdf_docling_optin.py` (extend) | `test_docling_accepts_picture_sink_kwarg` (skip if no docling) | call signature accepts `picture_sink` |
| | `test_docling_tuning_options_enabled_when_available` (skip if no docling) | inspect that DocumentConverter was constructed with `do_table_structure=True` |
| `tests/process/test_media_sidecars_in_manifest.py` (extend) | `test_pdf_path_passes_picture_sink_to_read_pdf` | mock `read_pdf` and assert `picture_sink` kwarg flows through |

Docling-specific behavior tests are skip-gated on `dependencies.pdf_available()`
to keep CI green without the optional extra.

## Constitution check

| Principle | Compliance |
|---|---|
| I. Safety-first Python | Typed kwargs; no `Any` |
| II. TDD | RED tests first |
| VI. Single responsibility | Zero new dependencies; reuses existing `PictureSink`, docling |
| X. Context efficiency | 2 source modules modified, 1 test module modified, 1 new test, 1 closure |

## Risk and rollback

| Risk | Mitigation |
|---|---|
| Docling API drift on `generate_picture_images` field name | Tests skip-gate; if the field renames in a future docling version, the kwarg becomes silently a no-op — caught by snapshot tests |
| `_char_bin` CRLF normalization changes existing output | The replacement is idempotent for already-`\n` input; the 016 segment tests already exercise `\n` and will continue to pass |
| Picture rendering significantly slows docling conversion | `images_scale=2.0` adds rendering work; performance is acceptable for the small batch sizes targeted; can be tuned later |
| Docling pictures don't include rendered bytes by default | The `generate_picture_images=True` flag triggers rendering; if the flag is absent, the picture list is metadata-only and the route-helper is a no-op |

**Rollback**: revert the shipment merge commit. No data migration.

## Sequencing (TDD-ordered)

1. **016.001-T** — Write failing tests for CRLF normalization + docling sink wiring (RED).
2. **016.002-T** — Implement CRLF normalization in `segment_markdown` (GREEN-1).
3. **016.003-T** — Wire `picture_sink` through `read_pdf`/`read_pdf_pages` and implement `_read_pdf_docling_pages` tuning + picture routing (GREEN-2).
4. **016.004-T** — Closure document.

## Acceptance criteria

- `segment_markdown` normalizes `\r\n` and `\r` to `\n` on entry
- `_read_pdf_docling_pages` accepts a `picture_sink` kwarg
- Docling pipeline configured with `do_table_structure=True`, `table_structure_options.do_cell_matching=True`, `generate_picture_images=True` (when sink provided), `images_scale=2.0`
- `read_pdf` and `read_pdf_pages` accept and forward `picture_sink`
- `build_output_document_parts` PDF branch passes `picture_sink` through to `read_pdf`
- 6 new tests pass (3 CRLF + 3 docling-side, with 2 of the docling-side tests skip-gated)
- All 5 CI gates green
- `docline export-schema` output unchanged
- Closure document records the new behavior plus tests
