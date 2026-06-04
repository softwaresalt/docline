---
title: "Deliberation — docling PDF engine + image sidecars (G3c)"
stash_ids: ["351170C9"]
status: adopted
date: 2026-06-04
---

# Deliberation: G3c — docling PDF engine + image sidecars

## Source

Stash entry `351170C9` (high, feature): "Wire docling as PDF engine + sidecar image extraction for DOCX/PDF to preserve tables, figures, code blocks, and layout structure in emitted markdown."

## Context

Shipments `012-S` (G3a heading-aware segmentation) and `013-S` (G3b
referentiality + chunk anchors) shipped the segmentation and referentiality
contract that graphtor's AST/Tree-sitter graph builder needs — but they
operate on the **rendered markdown body**. The body itself is only as
rich as what the upstream reader produced.

Current readers:

- **PDF**: `src/docline/readers/pdf.py` uses `pypdf` by default and emits
  flat text only (zero tables, zero figures from ~50 real-PDF outputs).
  An optional `docling` path exists scaffolded — `_read_pdf_docling_pages`
  at line 469 — and `_SUPPORTED_LAYOUT_ENGINES = {"heuristic", "docling"}`
  is already defined. The call site in
  `src/docline/process/output_contract.py` invokes `read_pdf(file_path)`
  with no `layout_engine` argument, so production always lands on the
  heuristic path even when docling is installed.
- **DOCX**: `src/docline/readers/docx.py` already handles headings, tables
  (via `<w:tbl>` → GFM table emission in `_render_table`), and lists. But
  `<w:drawing>` elements are dropped — a sample DOCX with 31 `<w:drawing>`
  elements produces zero image references in the output markdown.

The 012/013-S graph layer can re-attach chunks only when the body
preserves the document's visual structure. Tables and figures matter.

## Problem frame

For every processed source, the downstream graph layer needs:

1. **PDF tables and figures** to survive into the markdown body — not as
   prose paraphrases but as GFM tables and inline image references.
2. **DOCX embedded images** to survive into the markdown body as
   `![alt](media/figure-NNNN.ext)` references with the underlying image
   bytes extracted to a sidecar directory.
3. **Manifest awareness** of every emitted media artifact so consumers
   can discover sidecar files without filesystem walks.

## Python baseline confirmation

The earlier stash text flagged Python 3.14 + torch/onnxruntime wheel
compatibility as a risk. **The project's baseline is Python 3.12 across
the board** — production target, CI runners, and the local development
venv at `.venv/` are all Python 3.12 (`pyproject.toml: requires-python =
">=3.12"`). docling 2.97 supports >=3.10; torch and onnxruntime both
ship 3.12 wheels. **No ecosystem spike is required.**

Implementation note for executing agents: invoke `.\.venv\Scripts\python.exe`
(or `uv run`) rather than the bare `python` command on Windows shells
where the system `PATH` may resolve to a 3.14 install. CI is unaffected
(GitHub Actions installs 3.12 explicitly).

## Options considered

| Option | Approach | Verdict |
|---|---|---|
| A. Make docling a required dependency | Add `docling>=2,<3` to the core `dependencies` block | **Rejected** — docling drags in torch + onnxruntime (~1–2 GB). Optional is the right scope. |
| B. Add docling as an optional extra | New `[project.optional-dependencies] pdf = ["docling>=2,<3"]`; runtime probe via existing `dependencies.pdf_available()`; `layout_engine="auto"` resolves to docling when present, heuristic otherwise | **Chosen** — preserves the small default install; docling already partially scaffolded; clear opt-in story |
| C. Use a different layout engine (unstructured, Marker, etc.) | Replace pypdf with a different layout-preserving engine | **Rejected** — docling is already wired in the codebase; adding a second engine multiplies maintenance |
| D. Defer PDF image sidecars; ship only DOCX images now | Reduce scope to DOCX-only image extraction | **Rejected** — the manifest field and emission contract are the hard part; once those exist, PDF sidecars layer on cleanly via docling's `PdfPipelineOptions(images_scale>0)` |

## Chosen direction (Option B)

1. **Optional extra**: add `[project.optional-dependencies] pdf = ["docling>=2,<3"]` to `pyproject.toml`. Establishes the optional-deps convention.
2. **Layout engine resolution**: extend `_SUPPORTED_LAYOUT_ENGINES` to include `"auto"` and add a small resolver — when caller passes `layout_engine="auto"`, return `"docling"` if `pdf_available()` else `"heuristic"`.
3. **Wiring**: `output_contract.build_output_document_parts` calls `read_pdf(file_path, layout_engine=<resolved>)`. The resolved value is configurable via:
   - CLI flag `docline process --pdf-engine {auto,docling,heuristic}` (default `auto`)
   - `ProcessRequest.pdf_engine: str = "auto"` field
4. **DOCX image sidecar**: extend `read_docx_blocks` (or add a sibling extractor) to:
   - walk `<w:drawing>` → `<a:blip r:embed="rIdN"/>`
   - resolve `rIdN` via `word/_rels/document.xml.rels`
   - extract `word/media/imageN.{png,jpg,...}` bytes
   - return a list of `(block_index, image_filename, mime, bytes)` tuples alongside the text blocks
   - emit `![alt](media/figure-NNNN.ext)` markdown at the source position
   - write extracted bytes to `{output_root}/{job_id}/media/figure-NNNN.ext`
5. **PDF image sidecar via docling**: when `layout_engine` resolves to `docling`, configure `PdfPipelineOptions(images_scale=2.0, generate_picture_images=True)` and route the resulting picture refs through the same `media/figure-NNNN.ext` sink. Tests for this path are skip-gated on `dependencies.pdf_available()` because CI does not install docling.
6. **Manifest `media_files` field**: extend the per-source manifest entry with an optional `media_files: list[str]` field listing the relative paths (under `{job_id}/`) of every extracted media artifact for that source. Empty list when no media.

## Out of scope

- Cross-repo `graphtor-docs` schema snapshot refresh — operator-action follow-up (already stashed as `752CA1E4` from 013-S closure).
- Docling configuration tuning beyond `images_scale=2.0` and basic options. Performance tuning is a separate cycle.
- Backward-compatible removal of `read_pdf_pages` — it stays for `test_pdf_baseline_characterization.py` and `test_pdf_docling_optin.py`.
- Migration of older outputs — outputs regenerate each `docline process` run.

## Open questions

1. **CI without docling**: PDF docling-engine tests must skip when `pdf_available()` is False. ✓ Already established pattern (`tests/readers/test_pdf_docling_optin.py` uses `pytest.skip` for this).
2. **DOCX image filename collisions**: if two source DOCX files in the same job produce `image1.png`, they'd collide at `media/figure-NNNN.ext`. Solution: scope the `figure-NNNN` counter per-source (i.e., per-`input_path`), not per-job. Sidecars live at `{job_id}/{source_basename_without_ext}/media/figure-NNNN.ext` so the namespace mirrors the existing multi-part output layout.

## Constitution check

| Principle | Compliance |
|---|---|
| I. Safety-first Python | Typed signatures throughout; `defusedxml` used for any XML reading; no new untyped imports |
| II. TDD | RED tests first per task `015.001-T`; image extraction has dedicated fixture |
| III. Workspace isolation | All writes to `{output_root}/{job_id}/...` only |
| VI. Single responsibility | One new optional extra (`pdf`); reuses existing `docling`, `dependencies`, `defusedxml` |
| X. Context efficiency | Modify `readers/pdf.py`, `readers/docx.py`, `app.py`, `app_models.py`, `cli.py`, `process/output_contract.py`; new tests file; one closure |
| XI. Merge commit history | Standard PR flow |
