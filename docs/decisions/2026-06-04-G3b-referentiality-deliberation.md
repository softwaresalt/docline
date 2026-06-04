---
title: "Deliberation — referentiality frontmatter + chunk anchor default (G3b)"
stash_ids: ["C5CA1740"]
status: adopted
date: 2026-06-04
---

# Deliberation: G3b — referentiality frontmatter + chunk anchor default

## Source

Stash entry `C5CA1740` (high, feature): "Add in-frontmatter referentiality + emit chunk anchors for AST/Tree-sitter graphing."

## Context

Shipment `012-S` (G3a) introduced heading-aware semantic segmentation: PDF and DOCX inputs are now segmented at H1/H2 boundaries with a char-bin fallback. Each segment is emitted as `part-NNNN.md` with shared `OutputDocumentPart` metadata. However, the emitted `.md` files are structurally orphaned at the filesystem level: only `manifest.json` carries the part-order relationships and the `H1` section title produced by G3a is not surfaced in the frontmatter.

In parallel, `_inject_chunk_anchors()` already exists in `src/docline/process/assemble.py` and is exercised by tests, but the `assemble_markdown(..., emit_chunk_anchors=False)` default flows through to the production call site at `src/docline/app.py:274` which never sets it to `True`. So real processed output ships without chunk anchors today.

Graphtor's AST and Tree-sitter graphing layer needs both signals to reconstruct documents as connected graphs.

## Problem frame

For every processed output part, the consumer (graphtor) needs to answer two questions at the frontmatter level alone:

1. **Where in the larger document am I?** Which source did I come from? What is my position? What comes before and after me? What section am I anchored to?
2. **Where are the chunk boundaries inside this part?** Stable identifiers for downstream chunkers that don't have to re-parse heading positions.

The current contract surfaces neither.

## Options considered

| Option | Approach | Verdict |
|---|---|---|
| A. New top-level frontmatter fields | Add `parent_document_id`, `part_index`, etc. directly under the root frontmatter | **Rejected** — pollutes graphtor's expected core fields; risks BaseFrontmatter v1 contract break |
| B. New fields under the existing `docline:` namespace | Add new keys under the existing `docline: dict[str, Any] | None` namespace block | **Chosen** — already established escape hatch for docline-only metadata; `additionalProperties: true` means no schema break |
| C. Emit a separate `references.json` sidecar per part | Keep markdown untouched; emit a sidecar | **Rejected** — adds a second source of truth; graphtor would have to read two files per chunk; defeats the goal of self-contained markdown |
| D. Lazy/opt-in (require `--with-referentiality` CLI flag) | Default-off behavior | **Rejected** — every shipped PDF/DOCX needs this for the graph layer; a flag for the "right" default is friction |

## Chosen direction (Option B)

Add the following keys under the `docline:` namespace of every processed `BaseFrontmatter`:

| Key | Type | Semantic |
|---|---|---|
| `parent_document_id` | `str` | SHA-derived ID shared by every part of a single source. Same algorithm as the existing `_build_document_id` but without the `ingest_order` component, so all parts collide on the same `parent_document_id`. |
| `part_index` | `int` (1-based) | Position of this part inside the source. `1` for single-part outputs. |
| `total_parts` | `int` | Total number of parts the source segmented into. `1` for single-part outputs. |
| `prev_part` | `str \| null` | Relative path to the previous part's `.md` (e.g. `part-0001.md`) or `null` for the first part. |
| `next_part` | `str \| null` | Relative path to the next part's `.md` or `null` for the last part. |
| `section_title` | `str \| null` | The H1 heading text that anchors this part (populated when 012-S H1 split engaged for the part); `null` for non-heading-bounded parts (char-bin fallback). |

And flip the production default by passing `emit_chunk_anchors=True` at the single call site in `src/docline/app.py`. The `assemble_markdown(..., emit_chunk_anchors=...)` signature default stays `False` for unit-test clarity and contract minimization — production explicitly opts in.

## Out of scope

- **Snapshot update at `d:/Source/GitHub/graphtor-docs/schemas/docline/base-frontmatter-v1.schema.json`** — cross-repo file outside docline workspace. **Forbidden by Constitution Principle IV (CLI Workspace Containment).** Will be recorded as a follow-up stash for operator-driven separate PR against the `graphtor-docs` repo. The `docline export-schema` output produced by this shipment is the source of truth that the operator copies into the other repo.
- Migration of older outputs already on disk — no migration; outputs regenerated each `docline process` run.
- Changes to `OutputDocumentPart` dataclass — new fields flow through the frontmatter assembly path, not the dataclass.
- Changes to `manifest.json` schema — manifest already carries `document_id`, `input_path`, `ingest_order`, `output_path`. No additions required for G3b.

## Open questions

None. The feature is fully specified by the stash text; the plan and harvest can proceed.

## Constitution check

| Principle | Compliance |
|---|---|
| I. Safety-first Python | Typed fields; pydantic validation of new keys via the existing `docline: dict[str, Any]` permissive type |
| II. TDD | RED tests first per task `013.001-T` |
| IV. CLI Workspace Containment | Snapshot update at `d:/Source/GitHub/graphtor-docs/...` deferred to operator follow-up |
| VI. Single responsibility | Zero new dependencies; reuses existing `assemble_markdown`, `_build_document_id`, and `docline:` namespace |
| X. Context efficiency | One source-file modification + one app.py one-line flip + new test file + closure |
| XI. Merge commit history | Standard PR flow via Ship |
