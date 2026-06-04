---
shipment: 013-S
title: "Closure record — frontmatter referentiality + chunk anchor default (G3b)"
status: verified
merge_sha: fe614ea
merged_pr: 26
---

This document captures the implementation evidence for shipment `013-S`,
which adds the `docline:` namespace referentiality fields and flips
`emit_chunk_anchors=True` at the production call site so every processed
`.md` part carries the metadata graphtor needs to reconstruct the
document graph and address chunks by stable identifier.

## Scope

* **Source helper**: [`src/docline/process/segment.py`](../../src/docline/process/segment.py) — added `extract_section_title(segment) -> str | None`
* **Dataclass extension**: [`src/docline/process/output_contract.py`](../../src/docline/process/output_contract.py) — added `OutputDocumentPart.section_title: str | None = None` (additive, default None)
* **Frontmatter assembly**: [`src/docline/app.py`](../../src/docline/app.py) — added `_build_parent_document_id`, `_relative_sibling_basename`, `_build_docline_namespace`; extended `_build_markdown_with_frontmatter` with a `docline_namespace` kwarg that **merges** (does not overwrite) any existing `docline:` namespace from `WebFrontmatter` auto-routing; passes `emit_chunk_anchors=True` to `assemble_markdown` at the production call site
* **Tests**: [`tests/process/test_referentiality.py`](../../tests/process/test_referentiality.py) — 10 new integration tests
* **Tests**: [`tests/process/test_segment.py`](../../tests/process/test_segment.py) — 3 new `extract_section_title` helper tests
* **Tests**: [`tests/elt/test_process_regression.py`](../../tests/elt/test_process_regression.py) — updated `test_html_output_has_consistent_h1_root_for_crawled_pages` to accept chunk-anchor prefixes
* **Plan**: [docs/plans/2026-06-04-G3b-referentiality-plan.md](../plans/2026-06-04-G3b-referentiality-plan.md)
* **Plan review**: [docs/decisions/2026-06-04-G3b-referentiality-plan-review.md](../decisions/2026-06-04-G3b-referentiality-plan-review.md) (APPROVED)
* **Source stash**: `C5CA1740` (harvested and archived during Stage)

## Files changed

| Path | Change |
|---|---|
| `src/docline/process/segment.py` | MODIFY — add `extract_section_title` + export in `__all__` |
| `src/docline/process/output_contract.py` | MODIFY — add `section_title` field to `OutputDocumentPart`; populate via `extract_section_title` |
| `src/docline/app.py` | MODIFY — three new helpers + `docline_namespace` kwarg + `emit_chunk_anchors=True` flip + namespace merge logic |
| `tests/process/test_referentiality.py` | NEW (10 tests) |
| `tests/process/test_segment.py` | MODIFY — 3 tests added |
| `tests/elt/test_process_regression.py` | MODIFY — one assertion updated for chunk-anchor prefix |
| `docs/closure/013-S-referentiality.md` | NEW |

## Quality gate evidence

All five CI gates green at HEAD `7a894f6`:

| Gate | Command | Result |
|---|---|---|
| Format | `ruff format --check .` | `146 files already formatted` |
| Lint | `ruff check .` | `All checks passed!` |
| Typecheck | `pyright src/` | `0 errors, 0 warnings, 0 informations` |
| Tests | `pytest` | `832 passed, 5 skipped in 18.28s` |
| Build | `python -m build` | `Successfully built docline-0.1.0.tar.gz and docline-0.1.0-py3-none-any.whl` |

## New `docline:` namespace shape

Every emitted `.md` part now carries the following YAML block under `docline:`:

```yaml
docline:
  parent_document_id: "751d32df15271ada"   # 16-char SHA prefix, shared by all parts of a source
  part_index: 1                              # 1-based position within the source
  total_parts: 3                             # total parts the source segmented into
  prev_part: null                            # basename of previous sibling part, or null at boundary
  next_part: "part-0002.md"                  # basename of next sibling part, or null at boundary
  section_title: "Introduction"              # H1 anchoring this part (null for char-bin fallback)
```

For web/crawl inputs, the existing `WebFrontmatter` auto-routed keys
(`source_url`, `crawl_depth`, etc.) remain in the same `docline:` block —
the new G3b keys are **merged** with them, not overwritten. This was the
critical correctness fix during implementation (initial overwrite would
have lost web crawl metadata).

## Call-site flip rationale

`assemble_markdown(...)` keeps `emit_chunk_anchors=False` as the signature
default for unit-test clarity (tests that drive the assembler directly
must opt in deliberately). Production opts in explicitly at
`src/docline/app.py` in the single `_build_markdown_with_frontmatter`
call. The result: every processed output `.md` body now contains
`<a id="chunk-NNNN"></a>` markers before each H1/H2/H3 (skipping headings
inside fenced code blocks).

## Behavior change summary

| Surface | Old | New |
|---|---|---|
| `docline:` namespace in emitted YAML | Present only for web inputs (auto-routed `source_url`/`crawl_depth`) | Present for **all** inputs with referentiality fields; web inputs also retain auto-routed keys via merge |
| Processed `.md` body chunk anchors | Absent (gated `emit_chunk_anchors=False`) | Present by default; H1/H2/H3 each preceded by `<a id="chunk-NNNN"></a>` |
| `OutputDocumentPart.section_title` | Did not exist | Optional `str | None`, populated from segment's leading H1 |
| `parent_document_id` per source | Did not exist | 16-char SHA shared by every part of a source |
| `BaseFrontmatter` schema source | Unchanged | **Unchanged** — new keys use existing permissive `docline: dict[str, Any]` |
| `docline export-schema` output | (baseline) | Unchanged (no schema source modifications) |

## Contract preservation

| Surface | Status |
|---|---|
| `OutputDocumentPart` dataclass | Additive — `section_title: str | None = None` (default-None back-compat) |
| `build_output_document_parts` signature | Unchanged |
| `_relative_output_path` (filename convention `part-NNNN.md`) | Unchanged |
| `assemble_markdown(...)` signature | Unchanged — default `emit_chunk_anchors=False` preserved |
| HTML / MD / TXT branches | Unchanged routing; `section_title` populated from any first H1 in the body |
| BaseFrontmatter v1 contract | Preserved (zero schema source changes; new keys use existing permissive map) |
| Dependency graph | Unchanged — zero new dependencies |

## Cross-repo follow-up (operator action required)

The `graphtor-docs` repository carries a snapshot of the BaseFrontmatter
schema at `d:/Source/GitHub/graphtor-docs/schemas/docline/base-frontmatter-v1.schema.json`.
This snapshot needs to be refreshed to surface the new `docline:` namespace
keys at the JSON Schema level for downstream tooling. **This action is
forbidden inside the docline workspace per Constitution Principle IV (CLI
Workspace Containment) and must be performed by the operator separately:**

1. After the 013-S PR merges, run:
   ```powershell
   python -m docline export-schema > base-frontmatter-v1.schema.json
   ```
2. Copy the generated file into the graphtor-docs repository at the path above.
3. Open a separate PR in `graphtor-docs` for that snapshot refresh.

A stash follow-up will be recorded by Ship Step 6.6 to track this.

## Review findings

Inline review during Ship Step 4.4 (`mode:report-only`) returned:

- 0 P0, 0 P1, 0 P2
- 2 P3 advisories

| ID | Severity | Class | Finding |
|---|---|---|---|
| F1 | P3 | advisory | `extract_section_title` is now also applied to HTML/MD/TXT bodies, so HTML inputs whose first heading is `<h1>X</h1>` now carry `section_title: "X"`. This is a semantically appropriate behavior — HTML body extraction produces `# X` markdown — but it is a slight scope expansion versus the strict PDF/DOCX framing in the plan. Documented above in *Behavior change summary*. |
| F2 | P3 | advisory | `_relative_sibling_basename` uses `list.index()` which is O(n) per call (O(n²) per source). Negligible for realistic part counts (< 100). Acceptable. |

The plan-review F1 finding (concerning how to surface `section_title` from `segment_markdown`) was resolved by extending `OutputDocumentPart.section_title` rather than changing the `segment_markdown` return type — preserving the 012-S public API.

The critical correctness issue discovered during implementation — that `WebFrontmatter` already auto-routes `source_url`/`crawl_depth` into a `docline:` block — was caught by the regression test suite and resolved by switching the namespace assignment from overwrite to merge. This deserves a compound learning entry (added in Ship Step 6.5 of this shipment's closure cycle).

## Runtime verification

Runtime verification is **not required** for this shipment. The change is purely additive to the YAML frontmatter and the markdown body; no CLI surface, MCP tool, configuration field, or schema source is added, removed, or renamed. The behavior change is observable in the YAML output and is fully covered by the new tests.

## Rollback

`git revert {merge_sha}` cleanly restores the prior frontmatter shape and disables chunk anchors. Outputs regenerate on each `docline process` run; consumers tolerate missing optional `docline:` keys.
