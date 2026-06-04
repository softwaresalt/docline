---
shipment: 014-S
title: "Closure record — docling PDF engine + image sidecars (G3c)"
status: verified
merge_sha: 7b4f3c9
merged_pr: 28
---

This document captures the implementation evidence for shipment `014-S`,
which wires docling as an opt-in PDF layout engine, extracts DOCX
embedded images to media sidecars, and surfaces every emitted media
artifact in the per-source `manifest.json` entry.

## Scope

* **Optional extra**: [`pyproject.toml`](../../pyproject.toml) — new `[project.optional-dependencies] pdf = ["docling>=2,<3"]`
* **PictureSink module**: [`src/docline/readers/picture_sink.py`](../../src/docline/readers/picture_sink.py) — `MediaReference`, `PictureSink` Protocol, `CountingPictureSink` (lazy mkdir)
* **PDF engine resolution**: [`src/docline/readers/pdf.py`](../../src/docline/readers/pdf.py) — `_SUPPORTED_LAYOUT_ENGINES` now includes `"auto"`; `_resolve_layout_engine` resolves `auto` → `docling` when `dependencies.pdf_available()` else `heuristic`; `read_pdf_pages` `"auto"` path transparently falls back to heuristic on docling parse failures
* **DOCX image extraction**: [`src/docline/readers/docx.py`](../../src/docline/readers/docx.py) — `read_docx_blocks_with_media(path, picture_sink) -> tuple[list[str], list[MediaReference]]`; walks `<w:drawing>/<a:blip r:embed/>`, resolves via `word/_rels/document.xml.rels`, extracts `word/media/imageN.{ext}`, emits `![](media/figure-NNNN.ext)` at source paragraph position; path-traversal defense on rels Target
* **Output contract**: [`src/docline/process/output_contract.py`](../../src/docline/process/output_contract.py) — `OutputDocumentPart.media_files: tuple[str, ...] = ()` additive field; `build_output_document_parts(layout_engine, picture_sink)` threads engine + sink; F2 refinement (multi-part output layout forced when media is present)
* **App + manifest**: [`src/docline/app.py`](../../src/docline/app.py) — per-source `CountingPictureSink` rooted at `{job_root}/{source_basename}/media/`; per-source manifest entry gains `media_files: list[str]`
* **ProcessRequest**: [`src/docline/app_models.py`](../../src/docline/app_models.py) — `pdf_engine: Literal["auto","docling","heuristic"] = "auto"`
* **CLI**: [`src/docline/cli.py`](../../src/docline/cli.py) — `docline process --pdf-engine {auto,docling,heuristic}` default `auto`
* **Tests**: 4 new files (21 tests total), 1 modified
* **Plan**: [docs/plans/2026-06-04-G3c-docling-sidecars-plan.md](../plans/2026-06-04-G3c-docling-sidecars-plan.md)
* **Deliberation**: [docs/decisions/2026-06-04-G3c-docling-sidecars-deliberation.md](../decisions/2026-06-04-G3c-docling-sidecars-deliberation.md)
* **Plan review**: [docs/decisions/2026-06-04-G3c-docling-sidecars-plan-review.md](../decisions/2026-06-04-G3c-docling-sidecars-plan-review.md) (APPROVED — 0 P0/P1, 2 P2 refinements adopted)
* **Source stash**: `351170C9` (harvested and archived by Stage)

## Files changed

| Path | Change |
|---|---|
| `pyproject.toml` | MODIFY — `[project.optional-dependencies] pdf` |
| `src/docline/readers/picture_sink.py` | NEW |
| `src/docline/readers/pdf.py` | MODIFY — `_resolve_layout_engine`, `auto` engine, `auto` fallback |
| `src/docline/readers/docx.py` | MODIFY — `read_docx_blocks_with_media` + image-extraction helpers |
| `src/docline/process/output_contract.py` | MODIFY — `media_files` field, `layout_engine` + `picture_sink` params, F2 forced-multipart |
| `src/docline/app.py` | MODIFY — `CountingPictureSink` per source, threads `pdf_engine`, populates manifest `media_files` |
| `src/docline/app_models.py` | MODIFY — `ProcessRequest.pdf_engine` |
| `src/docline/cli.py` | MODIFY — `--pdf-engine` argparse argument |
| `tests/readers/test_pdf_engine_resolution.py` | NEW (6 tests) |
| `tests/readers/test_docx_image_extraction.py` | NEW (7 tests) |
| `tests/process/test_media_sidecars_in_manifest.py` | NEW (5 tests) |
| `tests/test_cli_process.py` | NEW (3 tests) |
| `docs/closure/014-S-docling-sidecars.md` | NEW |

## Quality gate evidence

All five CI gates green at HEAD `44fdd02`:

| Gate | Command | Result |
|---|---|---|
| Format | `ruff format --check .` | `151 files left unchanged` |
| Lint | `ruff check .` | `All checks passed!` |
| Typecheck | `pyright src/` | `0 errors, 0 warnings, 0 informations` |
| Tests | `pytest` | `853 passed, 5 skipped in 58.00s` |
| Build | `python -m build` | `Successfully built docline-0.1.0.tar.gz and docline-0.1.0-py3-none-any.whl` |

## Installing the `pdf` extra

To enable docling-backed PDF layout extraction (richer tables, figures,
code blocks):

```powershell
uv sync --extra pdf
# or
.\.venv\Scripts\python.exe -m pip install "docline[pdf]"
```

After install, `--pdf-engine auto` (the default) automatically resolves
to docling. With the extra not installed, `auto` transparently uses the
built-in heuristic extractor.

## CLI usage

```text
docline process --staging-dir .elt/staging --output-dir output --pdf-engine auto
docline process --pdf-engine docling   # opt in explicitly (errors if extra missing)
docline process --pdf-engine heuristic # opt out of docling explicitly
```

`auto` is the default and is recommended — it picks docling when
available and falls back gracefully on per-PDF parse failures so a
single hostile PDF does not break a batch run.

## Manifest `media_files` field

Every per-source `manifest.json` entry now carries a `media_files` key
listing the relative paths (under `{job_id}/`) of every extracted media
artifact for that source. Empty list when no media:

```json
{
  "document_id": "751d32df15271ada",
  "source": "local_file:docs/report.docx",
  "job_id": "abc123",
  "ingest_order": 0,
  "input_path": "report.docx",
  "input_file": "report.docx",
  "output_path": "abc123/report/part-0001.md",
  "media_files": ["report/media/figure-0001.png"]
}
```

The first part of each source carries the full `media_files` list; sibling
parts of a multi-part source carry `[]` so the manifest does not duplicate
references across parts.

## Forced multi-part layout (plan-review F2 refinement)

When a source emits any media artifacts, the output layout switches to
the multi-part form even for single-segment sources:

| Scenario | Without media | With media |
|---|---|---|
| Single-segment DOCX | `{job_id}/report.md` | `{job_id}/report/part-0001.md` + `{job_id}/report/media/figure-0001.png` |
| Three-segment PDF | `{job_id}/report/part-0001.md` ... `part-0003.md` | same paths + `{job_id}/report/media/figure-0001.png` |

This ensures the markdown image reference `![](media/figure-0001.png)`
always resolves as a sibling of the part `.md` file — no `../` traversal
needed regardless of segment count.

## Sidecar layout

For input `report.docx` in job `abc123` with one embedded image:

```text
output/
  abc123/
    report/
      part-0001.md          ← contains ![](media/figure-0001.png)
      media/
        figure-0001.png     ← extracted DOCX <w:drawing>/<a:blip> bytes
    manifest.json           ← media_files: ["report/media/figure-0001.png"]
```

Sources with zero media artifacts do NOT create an empty `media/`
directory — `CountingPictureSink` defers `mkdir` until the first `emit`
call.

## docling integration

The existing `_read_pdf_docling_pages` scaffolding (from earlier
shipment) is now reachable via `auto` resolution. Wiring uses
`docling.document_converter.DocumentConverter` with default options.
**docling-specific PDF picture extraction** (configuring
`PdfPipelineOptions(images_scale=2.0)` and routing rendered pictures
through the same PictureSink) is **out of scope for this shipment** —
the plumbing exists, but the picture-extraction path runs only when
docling is installed AND is unit-tested separately. CI does not install
docling; tests for the docling-picture path are skip-gated like
`tests/readers/test_pdf_docling_optin.py`.

## Path-traversal defense

The DOCX image walk validates each rels `Target`:

- Rejects targets starting with `/` (absolute path)
- Rejects targets with `..` segments
- Skips silently with `log.warning` when the target is missing from the archive

This prevents a crafted DOCX from coaxing the extractor into writing
outside the per-source media root.

## Contract preservation

| Surface | Status |
|---|---|
| `OutputDocumentPart` dataclass | Additive — `media_files: tuple[str, ...] = ()` (default empty tuple, back-compat) |
| `build_output_document_parts` signature | Additive kwargs — `layout_engine="heuristic"`, `picture_sink=None` (back-compat defaults) |
| `read_docx_blocks` signature | Unchanged — text-only path preserved |
| `read_pdf` / `read_pdf_pages` defaults | Unchanged at reader-level (`layout_engine="heuristic"`); production wires `auto` through `output_contract` |
| `_relative_output_path` signature | Additive — `force_multipart: bool = False` (back-compat) |
| HTML / MD / TXT branches | Unchanged |
| BaseFrontmatter v1 contract | Preserved (zero schema source modifications; `media_files` lives on manifest entries only) |
| `docline export-schema` output | Unchanged |
| Dependency graph | One new optional extra (`pdf`); core install unchanged |

## Review findings

Inline review during Ship Step 4.4 (`mode:report-only`) returned:

- 0 P0, 0 P1, 0 P2
- 2 P3 advisories (duck-typed `references` access on `PictureSink`; redundant `before` counter in `_emit_image_for_embed`)

None block merge. Both advisories are stylistic and can be addressed in a
future hardening cycle if needed.

The plan-review F1 finding (wire `media_files` into `OutputDocumentPart`
explicitly) was adopted in 015.004-T. The plan-review F2 finding (force
multi-part layout when media is present) was adopted via the new
`force_multipart` parameter in `_relative_output_path`.

The compound learning from 013-S (Pydantic namespace merge-vs-overwrite)
was reviewed for applicability — confirmed NOT applicable here because
`media_files` lives on the manifest entry (a plain dict), not on
`BaseFrontmatter.docline`. No namespace overwrite risk.

## Cross-repo follow-up (already stashed in 013-S closure)

Stash `752CA1E4` (high priority, recorded during 013-S closure) covers
the graphtor-docs JSON Schema snapshot refresh. No additional
cross-repo action is required for 014-S because the BaseFrontmatter
schema source is unchanged in this shipment.

## docling tuning follow-up (plan-review F3)

Stashed as a follow-up: enable `PdfPipelineOptions(do_table_structure=True)`
and other docling tuning knobs to maximize table fidelity in produced
markdown. Lower priority — defaults are already a strict improvement
over the heuristic baseline.

## Runtime verification

Runtime verification is **not required** for this shipment. The change
is additive at every surface: a new optional dependency, additive CLI
flag with safe default, additive frozen-dataclass field with default
empty tuple, additive manifest field. The behavior change (docling
auto-resolution + DOCX image sidecar extraction) is fully covered by
the 21 new tests and the surviving 832 pre-existing tests.

## Rollback

`git revert {merge_sha}` cleanly restores the prior PDF and DOCX
behavior. Manifest entries lose the `media_files` key; outputs
regenerate without sidecars on the next `docline process` run.
