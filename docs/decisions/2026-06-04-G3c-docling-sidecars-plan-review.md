---
title: "Plan review — G3c docling + image sidecars"
plan: "docs/plans/2026-06-04-G3c-docling-sidecars-plan.md"
shipment: "014-S"
date: 2026-06-04
verdict: APPROVED
personas: [architecture, python, security, scope-boundary, constitution, test-discipline, learnings]
---

# Plan review — G3c docling + image sidecars

## Verdict: **APPROVED** (0 P0, 0 P1, 2 P2, 3 P3)

## Personas applied

| Persona | Outcome |
|---|---|
| Architecture | ✅ `PictureSink` protocol + `CountingPictureSink` cleanly separates extraction from persistence; reuses existing `dependencies.pdf_available` probe; per-source media root mirrors the multi-part output layout. |
| Python | ✅ Typed signatures throughout (`Literal["auto","docling","heuristic"]`, `Protocol`, frozen `MediaReference`); `defusedxml` for new XML parsing; no `Any` introduced. |
| Security | ✅ Path-traversal defense in DOCX `Target` parsing is called out (must not start with `/` or contain `..`); XXE protected via `defusedxml`. |
| Scope-boundary | ✅ Cross-repo schema snapshot explicitly out of scope (already stashed `752CA1E4`); docling performance tuning deferred; PDF picture extraction wiring lands but runtime path is skip-gated. |
| Constitution | ✅ I/II/III/IV/VI/X/XI all satisfied. |
| Test-discipline | ✅ 21 test scenarios named across 4 test files; TDD RED phase explicit. |
| Learnings | ✅ Compound `2026-06-04-pydantic-namespace-merge-vs-overwrite.md` is informational here (no `docline:` namespace change); not directly applicable but reviewed. |

## Findings

| ID | Severity | Class | Detail |
|---|---|---|---|
| F1 | P2 | manual | `media_files` on `OutputDocumentPart` is typed `tuple[str, ...]` for frozen-dataclass safety. The plan's manifest-entry code uses `list(document_part.media_files)` to convert when writing manifest — good. But `OutputDocumentPart` is currently created with a list comprehension in `build_output_document_parts` that does **not** populate `media_files`. Implementer (`015.004-T`) must ensure DOCX branch builds the per-part `media_files` from the `(MediaReference, ...)` returned by `read_docx_blocks_with_media` (cast to tuple of relative paths). PDF branch should pass `()` when `picture_sink` did not emit anything. Make this explicit in the implementation notes for 015.004-T. |
| F2 | P2 | manual | The plan describes per-source media root as `{output_root}/{job_id}/{source_basename_without_ext}/media/`. For single-part outputs the existing `_relative_output_path` returns `{relative_input_path}.md` (e.g. `guide.md`), NOT `guide/part-0001.md`. So a single-part DOCX would have its `.md` at `{job_id}/guide.md` but media at `{job_id}/guide/media/figure-0001.png`. Markdown reference `![](media/...)` from `guide.md` would resolve to `{job_id}/media/...` — broken. Implementer must either (a) always emit `{source_basename}/{source_basename}.md` when media is present so `media/` is a sibling, OR (b) emit `![](../{source_basename}/media/figure-0001.png)` which is ugly. Prefer (c): change the per-source media root to `{output_root}/{job_id}/media/{source_basename}/figure-NNNN.ext` so it's always one consistent path regardless of part count, and the markdown reference becomes `![](../media/{source_basename}/figure-0001.png)` for multi-part or `![]({source_basename}/figure-0001.png)` for single-part — also ugly. **Cleanest**: when ANY media is present for a source, force the multi-part output layout (`{source_basename}/part-0001.md` + `{source_basename}/media/figure-NNNN.png`) even if only one segment exists. Markdown reference becomes simple `![](media/figure-0001.png)`. Decision must be made and reflected in 015.004-T. |
| F3 | P3 | advisory | The plan defers `do_table_structure` and other docling tuning. Without it, docling may emit tables as text rather than GFM tables — partially defeating the goal. Reasonable to defer for a follow-up, but stash a tracking item during closure to make it visible. |
| F4 | P3 | advisory | `tests/test_cli_process.py` may not currently exist. The plan says "MODIFY (or NEW if missing)". Implementer should verify and add a fresh test module if needed. |
| F5 | P3 | advisory | The compound learning from 013-S (Pydantic namespace merge-vs-overwrite) is not directly applicable to this shipment because `media_files` lives on the *manifest entry* (a plain dict), not in `BaseFrontmatter.docline`. But the implementer should still double-check that nothing in `_build_markdown_with_frontmatter` accidentally tries to attach `media_files` to `payload_dict["docline"]` — that would be wrong placement. |

## Adoption decision

**APPROVED for harvest** with F1 and F2 as embedded refinements:

- F1 → implementation note in **015.004-T** explicitly: "wire `media_files` from DOCX branch into `OutputDocumentPart.media_files`; PDF branch passes `()` when no sidecars produced"
- F2 → implementation note in **015.004-T** explicitly: "when any media is extracted for a source, force the multi-part output layout (`{source_basename}/part-0001.md` + `{source_basename}/media/figure-NNNN.png`) so the markdown `![](media/figure-0001.png)` reference is always sibling-relative"

F3/F4/F5 are advisory; no scope change.

## Risk profile

| Dimension | Level |
|---|---|
| Blast radius | Moderate — touches readers, app, CLI, schema (additive), manifest schema (additive) |
| Reversibility | High — revert merge; outputs regenerate without sidecars |
| Cross-cutting | 7 source files modified, 1 new |
| External dependency | One new optional extra (`pdf`) |
| Operator approval gates | Standard P-014 merge gate |

`plan-harden` not required — additive changes with deterministic rollback.
