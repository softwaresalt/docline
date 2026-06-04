---
shipment: 015-S
title: "Closure record — post-G3 hygiene (CRLF + docling tuning)"
status: verified
merge_sha: pending
merged_pr: pending
---

Captures the implementation evidence for shipment `015-S`, the post-G3
hygiene cycle. Addresses two low-priority follow-up advisories from the
G3 segmentation + docling arc shipped in 012-S, 013-S, and 014-S.

## Scope

* **CRLF normalization**: [`src/docline/process/segment.py`](../../src/docline/process/segment.py) — `segment_markdown` normalizes `\r\n` and bare `\r` to `\n` on entry (review F2 advisory from 012-S, stash `F50AD7E6`)
* **Docling tuning + picture routing**: [`src/docline/readers/pdf.py`](../../src/docline/readers/pdf.py) — `_read_pdf_docling_pages` accepts an optional `picture_sink` kwarg and configures `PdfPipelineOptions(do_table_structure=True, table_structure_options=TableStructureOptions(do_cell_matching=True), generate_picture_images=picture_sink is not None, images_scale=2.0)`; new `_route_docling_pictures` helper emits rendered pictures through the sink (plan-review F3 advisory from 014-S, stash `5ADD558F`)
* **Sink threading**: [`src/docline/process/output_contract.py`](../../src/docline/process/output_contract.py) — PDF branch passes `picture_sink` through to `read_pdf`
* **Plan**: [docs/plans/2026-06-04-post-g3-hygiene-plan.md](../plans/2026-06-04-post-g3-hygiene-plan.md)
* **Plan review**: [docs/decisions/2026-06-04-post-g3-hygiene-plan-review.md](../decisions/2026-06-04-post-g3-hygiene-plan-review.md) (APPROVED — 0 P0/P1, 1 P2 refinement adopted)

## Files changed

| Path | Change |
|---|---|
| `src/docline/process/segment.py` | MODIFY — line-ending normalization on entry to `segment_markdown` |
| `src/docline/readers/pdf.py` | MODIFY — `picture_sink` kwarg through `read_pdf`/`read_pdf_pages`/`_read_pdf_docling_pages`; tuning options enabled; `_route_docling_pictures` helper |
| `src/docline/process/output_contract.py` | MODIFY (small) — PDF branch threads `picture_sink` through to `read_pdf` |
| `tests/process/test_segment.py` | MODIFY — 3 CRLF tests added |
| `tests/readers/test_pdf_docling_optin.py` | MODIFY — 2 docling-side tests added (skip-gated) |
| `tests/process/test_media_sidecars_in_manifest.py` | MODIFY — 1 sidecar threading test added |
| `docs/closure/015-S-post-g3-hygiene.md` | NEW |

## Quality gate evidence

All five CI gates green at HEAD `f97b5d9`:

| Gate | Command | Result |
|---|---|---|
| Format | `ruff format --check .` | `151 files already formatted` |
| Lint | `ruff check .` | `All checks passed!` |
| Typecheck | `pyright src/` | `0 errors, 0 warnings, 0 informations` |
| Tests | `pytest` | `859 passed, 5 skipped in 54.87s` |
| Build | `python -m build` | `Successfully built docline-0.1.0.tar.gz and docline-0.1.0-py3-none-any.whl` |

## CRLF normalization rationale

`_char_bin` splits paragraphs on literal `"\n\n"`. Without normalization,
input with Windows line endings (`"\r\n\r\n"`) or legacy Mac (`"\r\r"`)
would never split, producing one oversized bin per source. The two-step
replace order matters:

```python
normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
```

Doing `\r` → `\n` first would convert Windows CRLF into `"\n\n"`,
spuriously creating paragraph breaks where none existed. The current
order is idempotent for already-`\n` input (verified by 19 pre-existing
segment tests continuing to pass).

## Docling tuning options enabled

```python
PdfPipelineOptions(
    do_table_structure=True,            # detect table cells from layout
    table_structure_options=TableStructureOptions(
        do_cell_matching=True,          # match cells to row/column structure
    ),
    generate_picture_images=picture_sink is not None,  # only when sink active
    images_scale=2.0,                   # 2x DPI for picture rendering
)
```

The picture-generation flag is gated on `picture_sink` being provided
to avoid the rendering cost when sidecars aren't wanted (e.g., the
`auto`-engine fallback path or callers that pass no sink).

## Docling picture routing behavior

```python
def _route_docling_pictures(document, picture_sink) -> None:
    pictures = getattr(document, "pictures", None)
    if not pictures:
        return
    for picture in pictures:
        image = getattr(picture, "image", None)
        if image is None:
            continue
        pil_image = getattr(image, "pil_image", image)
        try:
            buffer = io.BytesIO()
            pil_image.save(buffer, format="PNG")
            png_bytes = buffer.getvalue()
        except Exception as err:
            _log.warning("Failed to serialize docling picture to PNG: %s", err)
            continue
        try:
            picture_sink.emit("image/png", png_bytes)
        except Exception as err:
            _log.warning("PictureSink failed to accept docling picture: %s", err)
            continue
```

Defensive guards (per plan-review F1):

- `getattr` chains tolerate docling API drift in attribute names
- Each `try`/`except` block scopes a single picture's failure — markdown flow continues
- Empty/missing `document.pictures` returns silently — no error condition

## Test skip-gating

Docling-side tests use the same pattern as `test_pdf_docling_optin.py`:

```python
if not dependencies_module.pdf_available():
    pytest.skip("docling not installed; skipping picture_sink kwarg surface test")
```

This keeps the test count high in dev environments where docling is
installed via `uv sync --extra pdf`, but lets CI (which does not install
the extra) green without false failures.

## Contract preservation

| Surface | Status |
|---|---|
| `read_pdf` signature | Additive kwarg (`picture_sink: PictureSink | None = None`, default `None` is back-compat) |
| `read_pdf_pages` signature | Same |
| `_read_pdf_docling_pages` signature | Same |
| `build_output_document_parts` signature | Unchanged externally (already had `picture_sink`) |
| `OutputDocumentPart` | Unchanged |
| Manifest entries | Unchanged |
| BaseFrontmatter v1 contract | Preserved |
| `docline export-schema` output | Unchanged |
| Dependency graph | Unchanged (uses existing `docling` extra) |

## Review findings

Inline review during Ship Step 4.4 (`mode:report-only`) returned:

- 0 P0, 0 P1, 0 P2, 0 P3 advisories

The plan-review F1 refinement (graceful skip when docling picture API
differs) was adopted in `_route_docling_pictures` via `getattr` chains
plus defensive `try`/`except` per picture. F2 (consolidate CRLF tests
into parametrize) was advisory only and not adopted — the three scenarios
test distinct behaviors (CRLF, classic CR, mixed) more clearly as
separate functions.

## docline as producer for graphtor (boundary respected)

This shipment improves what docline produces (richer table fidelity,
optional picture sidecars from docling-extracted PDFs, CRLF-safe
segmentation) without writing to or depending on the graphtor-docs
workspace. The downstream graphtor ingestion consumes the resulting
markdown bodies + frontmatter + `media_files` manifest entries — those
contract surfaces are unchanged in this shipment.

## Runtime verification

Runtime verification is **not required** for this shipment. CRLF
normalization is unit-tested in `test_segment.py` against constructed
strings. Docling-side tests are skip-gated and behavior is covered by
the existing 014-S sidecar tests when run in a docling-enabled
environment.

## Rollback

`git revert {merge_sha}` cleanly restores the prior behavior. CRLF
normalization disappears (LF-only inputs continue to work as today);
docling reverts to default `PdfPipelineOptions` and the picture-routing
helper is removed (rendered pictures stop reaching sidecars on the
docling path — DOCX picture extraction in 014-S is unaffected).

## Stash follow-up

Plan-review F3 advisory: docling `do_ocr=True` could enable scanned-PDF
text extraction. Lower priority because the current heuristic baseline
also doesn't OCR. To be stashed during this shipment's closure cycle.
