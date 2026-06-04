---
title: "Implementation plan — docling PDF engine + image sidecars (G3c)"
stash_ids: ["351170C9"]
shipment: "014-S"
status: approved
requires_plan_hardening: no
---

# G3c — docling PDF engine + image sidecars

**Date**: 2026-06-04
**Source stash**: `351170C9` (high, feature)
**Source deliberation**: [`docs/decisions/2026-06-04-G3c-docling-sidecars-deliberation.md`](../decisions/2026-06-04-G3c-docling-sidecars-deliberation.md)
**Target shipment**: `014-S` (next sequential shipment id)
**Depends on**: `012-S` (segmentation), `013-S` (referentiality)

## Goal

Preserve PDF and DOCX layout structure (tables, figures, code blocks) in
emitted markdown. Wire docling as an opt-in PDF engine; extract DOCX
embedded images as media sidecars; surface every emitted media artifact
in `manifest.json`.

## Scope

### In scope

- **`pyproject.toml`**: add `[project.optional-dependencies] pdf = ["docling>=2,<3"]`.
- **`src/docline/readers/pdf.py`**:
  - Extend `_SUPPORTED_LAYOUT_ENGINES` with `"auto"`.
  - Add `_resolve_layout_engine(requested: str) -> str` — returns the requested engine for `heuristic` / `docling` (passes through validation), and resolves `auto` → `docling` when `dependencies.pdf_available()` else `heuristic`.
  - `read_pdf` and `read_pdf_pages` accept `layout_engine="auto"` as the new default-safe alias.
  - Extend `_read_pdf_docling_pages` to optionally emit picture sidecars when a `picture_sink: PictureSink | None` is provided (new protocol defined in `src/docline/readers/picture_sink.py`).
- **`src/docline/readers/docx.py`**:
  - Extend `read_docx_blocks` to optionally return image references alongside text blocks. New helper `read_docx_blocks_with_media(path, picture_sink) -> tuple[list[str], list[MediaReference]]` — adds the image-walk + extraction; returns markdown blocks with `![alt](media/figure-NNNN.ext)` substitutions and a list of `MediaReference(filename, mime, bytes)` for each extracted image.
- **`src/docline/process/output_contract.py`**:
  - `build_output_document_parts` accepts a `layout_engine: str = "auto"` kwarg and threads it to `read_pdf(layout_engine=layout_engine)`.
  - DOCX branch routes through `read_docx_blocks_with_media(path, picture_sink)` when a sink is provided; otherwise falls back to current `read_docx_blocks` text-only path.
  - Returns `OutputDocumentPart` with optional `media_files: list[str] = field(default_factory=list)` (additive field).
- **`src/docline/app.py`**:
  - Build a `PictureSink` per source with output root `{job_output_root}/{source_basename_without_ext}/media/`.
  - Surface `media_files` (relative to `job_id/`) in the manifest entry's new `media_files` field.
  - Read `request.pdf_engine` and pass through to `build_output_document_parts(..., layout_engine=request.pdf_engine)`.
- **`src/docline/app_models.py`**:
  - Add `pdf_engine: str = "auto"` field to `ProcessRequest` with literal validation `{"auto", "docling", "heuristic"}`.
- **`src/docline/cli.py`**:
  - Add `--pdf-engine {auto,docling,heuristic}` argument to the `process` subparser (default `auto`).
- **Test fixtures** (inline, byte-built): minimal DOCX with one embedded PNG via `<w:drawing>/<a:blip r:embed="rId1"/>` + `word/_rels/document.xml.rels` + `word/media/image1.png`.
- **Tests**:
  - `tests/readers/test_docx_image_extraction.py` (new) — DOCX image walk, sidecar extraction, markdown emission
  - `tests/readers/test_pdf_engine_resolution.py` (new) — `auto` resolution behavior (mocks `pdf_available`)
  - `tests/process/test_media_sidecars_in_manifest.py` (new) — end-to-end `execute_process` produces `media_files` in manifest entries and on disk
  - `tests/test_cli_process.py` (extend) — `--pdf-engine` flag accepted and threaded into `ProcessRequest`
  - `tests/readers/test_pdf_docling_optin.py` (extend if needed) — `auto` engine returns docling when available, heuristic when not (skip-gated on `pdf_available()`)

### Out of scope (deferred)

- **Cross-repo `graphtor-docs` schema snapshot refresh** — already stashed (`752CA1E4`).
- **PDF image sidecars via docling**: the *plumbing* (PictureSink, manifest field, output dir layout) lands in this shipment; **the docling-specific picture extraction path runs only when docling is installed**. CI won't install it. The wiring is gated on `dependencies.pdf_available()`; unit tests for the docling path are `pytest.skip`-gated like the existing `test_pdf_docling_optin.py`.
- **Docling performance tuning** (e.g., `do_ocr`, `do_table_structure` toggles beyond defaults).
- **Removal of `read_pdf_pages`** — keeps backward compatibility for the existing baseline tests.

## Design

### `PictureSink` protocol

```python
# src/docline/readers/picture_sink.py
"""Sink for media (picture) artifacts extracted from source documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class MediaReference:
    """A single media artifact emitted from a source document.

    Attributes:
        filename: Sidecar filename relative to the per-source media root
            (e.g. ``"figure-0001.png"``).
        mime: MIME type of the bytes (``"image/png"``, ``"image/jpeg"``).
        data: Image bytes.
    """

    filename: str
    mime: str
    data: bytes


class PictureSink(Protocol):
    """Receives extracted media artifacts and assigns sidecar filenames."""

    def emit(self, mime: str, data: bytes, hint: str | None = None) -> MediaReference:
        """Persist ``data`` as a media sidecar; return its reference."""
        ...


class CountingPictureSink:
    """Default ``PictureSink`` that writes files to a directory and assigns sequential names."""

    def __init__(self, media_root: Path) -> None:
        self._media_root = media_root
        self._counter = 0

    def emit(self, mime: str, data: bytes, hint: str | None = None) -> MediaReference:
        ext = _ext_for_mime(mime)
        self._counter += 1
        filename = f"figure-{self._counter:04d}{ext}"
        self._media_root.mkdir(parents=True, exist_ok=True)
        (self._media_root / filename).write_bytes(data)
        return MediaReference(filename=filename, mime=mime, data=data)
```

### `_resolve_layout_engine`

```python
def _resolve_layout_engine(requested: str) -> str:
    """Resolve ``"auto"`` to ``"docling"`` when available, else ``"heuristic"``.

    Validates the requested engine first via :func:`_validate_layout_engine`.
    """
    _validate_layout_engine(requested)
    if requested != "auto":
        return requested
    return "docling" if dependencies.pdf_available() else "heuristic"
```

`_SUPPORTED_LAYOUT_ENGINES` becomes `frozenset({"auto", "heuristic", "docling"})`.

### DOCX image walk (overview)

```python
# Added to src/docline/readers/docx.py

_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_RELS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_BLIP_TAG = f"{{{_DRAWING_NS}}}blip"
_R_EMBED_ATTR = f"{{{_RELS_NS}}}embed"


def read_docx_blocks_with_media(
    path: Path, picture_sink: PictureSink | None
) -> tuple[list[str], list[MediaReference]]:
    """Read DOCX blocks and optionally extract embedded images to ``picture_sink``.

    When ``picture_sink`` is provided, every ``<a:blip r:embed="rIdN"/>``
    inside ``<w:drawing>`` is resolved via
    ``word/_rels/document.xml.rels``, the corresponding
    ``word/media/imageN.<ext>`` bytes are passed to the sink, and the
    paragraph emits ``![alt](media/<assigned_filename>)`` in place.

    When ``picture_sink`` is ``None``, this function delegates to
    :func:`read_docx_blocks` for the text-only path (back-compat).
    """
```

The walk uses `defusedxml` for `document.xml` and `document.xml.rels`
(security carry-over from F4). MIME is inferred from the relationship's
`Target` extension (`.png` → `image/png`, `.jpeg`/`.jpg` → `image/jpeg`,
`.gif` → `image/gif`, anything else → `application/octet-stream`).

### `OutputDocumentPart.media_files`

Additive field:

```python
@dataclass(frozen=True)
class OutputDocumentPart:
    body: str
    relative_output_path: Path
    title_suffix: str | None = None
    section_title: str | None = None
    media_files: tuple[str, ...] = ()  # NEW — relative to {job_id}/, e.g. ("multi/media/figure-0001.png",)
```

`tuple` (not `list`) keeps the frozen-dataclass `eq`/`hash` semantics
intact. Default `()` is back-compat.

### Manifest entry `media_files`

```python
manifest_entry: dict[str, object] = {
    "document_id": ...,
    "source": ...,
    "job_id": ...,
    "ingest_order": ...,
    "input_path": ...,
    "input_file": ...,
    "output_path": ...,
    "media_files": list(document_part.media_files),  # NEW; empty list when no media
}
```

### Per-source media root

For input `guides/index.docx` in job `abc123`, media root is
`{output_root}/abc123/guides/index/media/`. Filenames are
`figure-NNNN.{ext}`. The `media_files` list contains
`["guides/index/media/figure-0001.png", ...]` (relative to `{output_root}/abc123/`).

This mirrors the existing multi-part filename pattern
(`{source}/part-NNNN.md`), keeping all per-source artifacts under a
single directory.

### CLI flag

```python
process_parser.add_argument(
    "--pdf-engine",
    choices=("auto", "docling", "heuristic"),
    default="auto",
    help="PDF layout extractor. 'auto' resolves to 'docling' when the optional "
         "docline[pdf] extras are installed, else 'heuristic'.",
)
```

`main` builds `ProcessRequest(..., pdf_engine=args.pdf_engine)`.

### `ProcessRequest.pdf_engine`

```python
class ProcessRequest(BaseModel):
    ...
    pdf_engine: Literal["auto", "docling", "heuristic"] = "auto"
```

## Constitution check

| Principle | Compliance |
|---|---|
| I. Safety-first Python | typed signatures; `defusedxml` for any XML/rels parsing; no `Any` |
| II. TDD | RED tests first in 015.001-T |
| III. Workspace isolation | All writes under `{output_root}/{job_id}/...` only |
| IV. CLI containment | No writes outside workspace; docling output routed through PictureSink |
| VI. Single responsibility | One new optional extra; reuses `dependencies`, `defusedxml`, existing docling scaffolding |
| X. Context efficiency | 7 source files modified, 1 new (`picture_sink.py`); 3 new test files; 1 closure |
| XI. Merge commit history | Standard PR flow |

## Test plan (TDD RED phase first)

| File | Test | Coverage |
|---|---|---|
| `tests/readers/test_pdf_engine_resolution.py` | `test_auto_resolves_to_docling_when_pdf_available` | monkeypatch `pdf_available` True; assert `_resolve_layout_engine("auto") == "docling"` |
| | `test_auto_resolves_to_heuristic_when_pdf_unavailable` | monkeypatch False; assert `"heuristic"` |
| | `test_heuristic_passthrough` | assert `"heuristic"` → `"heuristic"` regardless of probe |
| | `test_docling_passthrough_when_available` | monkeypatch True; assert `"docling"` → `"docling"` |
| | `test_docling_raises_when_unavailable` | monkeypatch False; `read_pdf_pages(layout_engine="docling")` raises `DependencyUnavailableError` (existing behavior — regression coverage) |
| | `test_invalid_engine_rejected` | `_resolve_layout_engine("bogus")` raises `ValueError` |
| `tests/readers/test_docx_image_extraction.py` | `test_docx_with_no_images_returns_empty_media_list` | minimal DOCX without `<w:drawing>` |
| | `test_docx_with_one_embedded_png_produces_one_media_reference` | fixture DOCX with `image1.png` |
| | `test_docx_image_emission_inserts_markdown_image_at_source_position` | assert `![](media/figure-0001.png)` appears in the block where `<w:drawing>` lived |
| | `test_docx_with_two_images_assigns_sequential_filenames` | figure-0001, figure-0002 |
| | `test_docx_with_unresolvable_embed_id_is_skipped_silently` | `<a:blip r:embed="rId99"/>` with no matching rel |
| | `test_docx_jpeg_image_mime_detected_from_extension` | `.jpg` in rels Target → `image/jpeg` |
| | `test_docx_image_walk_uses_defusedxml` | confirm `defusedxml.ElementTree.fromstring` is used (XXE safety) |
| `tests/process/test_media_sidecars_in_manifest.py` | `test_docx_image_sidecar_written_to_media_root` | execute_process emits `{job_id}/{source_basename}/media/figure-0001.png` on disk |
| | `test_manifest_entry_includes_media_files_relative_paths` | manifest entry has `media_files: ["{source_basename}/media/figure-0001.png"]` |
| | `test_pdf_without_docling_produces_empty_media_files` | flat PDF + no docling → `media_files: []` |
| | `test_html_source_has_empty_media_files` | HTML branch returns `media_files: []` |
| | `test_outputs_without_media_omit_media_root_dir` | no `media/` subdir created when nothing extracted |
| `tests/test_cli_process.py` | `test_process_subparser_accepts_pdf_engine_flag` | argparse accepts `--pdf-engine docling` |
| | `test_process_subparser_pdf_engine_defaults_to_auto` | omitted flag → `auto` |
| | `test_process_subparser_rejects_unknown_pdf_engine_value` | `--pdf-engine bogus` exits non-zero |

## Risk and rollback

| Risk | Mitigation |
|---|---|
| `OutputDocumentPart.media_files` tuple breaks existing tests that compare dataclass equality | Default `()` is hashable + back-compat; existing test assertions ignore the field unless they probe it directly |
| Manifest `media_files` field consumers (graphtor) not expecting the key | Additive only; absent in pre-013 outputs; consumers tolerate missing keys (no schema break) |
| DOCX walk skips legitimate images due to malformed rels | Silent-skip behavior is by design (covered by `test_docx_with_unresolvable_embed_id_is_skipped_silently`); errors logged via existing `_log.warning` pattern |
| PictureSink writes outside workspace via path traversal in DOCX rels `Target` | `Target` is validated: must not start with `/` or contain `..`; resolved against `word/` only |
| docling PDF picture extraction unavailable in CI | Tests for that path are skip-gated; production wiring still validated by unit tests against mocked `pdf_available` |
| Performance hit for large DOCX with many images | Extraction is O(N) images; no per-image network or compute cost; acceptable |

**Rollback**: revert the shipment merge commit. `media_files` field disappears from manifest entries; outputs regenerate on next `docline process` without sidecars.

## ProposedAction / ActionRisk (strict-safety)

| Action | Risk | Approval |
|---|---|---|
| Add `[project.optional-dependencies] pdf = ["docling>=2,<3"]` to `pyproject.toml` | `low` | None — establishes the pattern |
| Add `_resolve_layout_engine` + `"auto"` to `_SUPPORTED_LAYOUT_ENGINES` | `low` | None — additive |
| New `src/docline/readers/picture_sink.py` | `low` | None — net new module |
| Extend `read_docx_blocks` with image walk | `moderate` | None — covered by RED gate; back-compat path preserved via `read_docx_blocks_with_media(picture_sink=None)` |
| Add `media_files` to `OutputDocumentPart` and manifest entry | `moderate` | None — additive default-empty fields |
| Wire `pdf_engine` through CLI + ProcessRequest + output_contract | `moderate` | None — additive with default `auto` |
| Add `--pdf-engine` CLI flag | `low` | None — additive |

No destructive actions. No high-blast-radius surfaces. `plan-harden` not required.

## Sequencing (TDD-ordered)

1. **015.001-T** — Write failing tests for engine resolution + DOCX image extraction + manifest sidecar surfacing (RED).
2. **015.002-T** — Add `pyproject` optional extra + `picture_sink.py` + `_resolve_layout_engine` + `auto` engine; tests for engine resolution pass.
3. **015.003-T** — Implement `read_docx_blocks_with_media` with `<w:drawing>` walk and rels resolution; DOCX image tests pass.
4. **015.004-T** — Wire `pdf_engine` through `ProcessRequest`, CLI `--pdf-engine`, `build_output_document_parts`, and `_assemble_part_markdown`; populate `media_files` in `OutputDocumentPart` and manifest; manifest sidecar tests pass.
5. **015.005-T** — Closure document.

## Acceptance criteria

- `[project.optional-dependencies] pdf = ["docling>=2,<3"]` exists in `pyproject.toml`
- `_SUPPORTED_LAYOUT_ENGINES` includes `"auto"`; `_resolve_layout_engine` exposed
- `read_pdf` and `read_pdf_pages` default to `layout_engine="auto"`
- `src/docline/readers/picture_sink.py` exists with `PictureSink` protocol + `MediaReference` + `CountingPictureSink`
- `read_docx_blocks_with_media(path, picture_sink)` extracts embedded images and emits `![...](media/figure-NNNN.ext)` markdown at source positions
- `OutputDocumentPart.media_files: tuple[str, ...] = ()` added
- Manifest entries gain `media_files: list[str]`
- CLI `--pdf-engine {auto,docling,heuristic}` accepted; default `auto`
- `ProcessRequest.pdf_engine: Literal["auto","docling","heuristic"] = "auto"` accepted
- All 5 CI gates pass: `ruff format --check`, `ruff check .`, `pyright src/`, `pytest`, `python -m build`
- `docline export-schema` output unchanged (no schema source modifications — `media_files` is per-manifest-entry, not in `BaseFrontmatter`)
- Closure document at `docs/closure/014-S-docling-sidecars.md` records test fixture content, observed manifest deltas, and the operator action for installing the `pdf` extra

## Files touched (summary)

| Path | Change |
|---|---|
| `pyproject.toml` | MODIFY — add `[project.optional-dependencies] pdf` |
| `src/docline/readers/pdf.py` | MODIFY — `_resolve_layout_engine`, `"auto"` in supported set, default to `"auto"` |
| `src/docline/readers/docx.py` | MODIFY — add `read_docx_blocks_with_media`, image walk helpers |
| `src/docline/readers/picture_sink.py` | NEW |
| `src/docline/process/output_contract.py` | MODIFY — `layout_engine` + media propagation; `OutputDocumentPart.media_files` |
| `src/docline/app.py` | MODIFY — build `PictureSink` per source; populate manifest `media_files`; thread `pdf_engine` |
| `src/docline/app_models.py` | MODIFY — add `pdf_engine` field to `ProcessRequest` |
| `src/docline/cli.py` | MODIFY — `--pdf-engine` argument |
| `tests/readers/test_pdf_engine_resolution.py` | NEW |
| `tests/readers/test_docx_image_extraction.py` | NEW |
| `tests/process/test_media_sidecars_in_manifest.py` | NEW |
| `tests/test_cli_process.py` | MODIFY (or NEW if missing) — `--pdf-engine` coverage |
| `docs/closure/014-S-docling-sidecars.md` | NEW |
