---
title: "Implementation plan — referentiality frontmatter + chunk anchor default (G3b)"
stash_ids: ["C5CA1740"]
shipment: "013-S"
status: approved
requires_plan_hardening: no
---

# G3b — referentiality frontmatter + chunk anchor default

**Date**: 2026-06-04
**Source stash**: `C5CA1740` (high, feature)
**Source deliberation**: [`docs/decisions/2026-06-04-G3b-referentiality-deliberation.md`](../decisions/2026-06-04-G3b-referentiality-deliberation.md)
**Target shipment**: `013-S`
**Depends on**: `012-S` (heading-aware segmentation, merged at `7d4579f`)

## Goal

Add six referentiality fields under the `BaseFrontmatter.docline` namespace and flip `emit_chunk_anchors=True` at the production call site so every processed `.md` part carries:

1. Filesystem-visible part relationships (`parent_document_id`, `part_index`, `total_parts`, `prev_part`, `next_part`)
2. Section anchoring (`section_title` — the H1 that bounds this part, when 012-S's heading-aware splitter produced one)
3. Per-heading chunk anchors (`<a id="chunk-NNNN"></a>` before every H1/H2/H3)

## Scope

### In scope

- **Schema**: extend `BaseFrontmatter.docline` namespace populated in `src/docline/app.py` frontmatter assembly. No new pydantic field — uses the existing `docline: dict[str, Any] | None` permissive container.
- **Source**: `src/docline/app.py` — populate the new `docline:` keys during `_assemble_part_markdown` (or equivalent assembly path) and add `emit_chunk_anchors=True` to the `assemble_markdown(...)` call at line 274.
- **Source**: `src/docline/process/output_contract.py` — surface the H1 section title from `segment_markdown` output so it can flow into `section_title`. Will require returning structured segments (`list[Segment]` with `body` and `section_title`) instead of plain strings, OR a separate helper that re-parses the segment to find its leading H1.
- **Tests**: new `tests/process/test_referentiality.py` exercising:
  - All six fields present and correctly populated for multi-part DOCX/PDF output
  - `prev_part`/`next_part` chain end-to-end
  - `parent_document_id` identical across all parts of a single source
  - `section_title` populated when an H1 exists; `null` for char-bin-fallback segments
  - `chunk-NNNN` anchors present in the emitted markdown body
- **Tests**: update existing `tests/process/test_chunk_anchor_emission.py` if behavior changes (the call-site flip does not change `assemble_markdown` defaults, so unit tests remain green)
- **Tests**: update `tests/elt/test_process_regression.py` only if any existing assertion checks for the absence of chunk anchors or `docline:` keys
- **Closure**: `docs/closure/013-S-referentiality.md`

### Out of scope (deferred via stash follow-ups)

- **Cross-repo snapshot refresh**: `d:/Source/GitHub/graphtor-docs/schemas/docline/base-frontmatter-v1.schema.json`. Operator must run `docline export-schema` after merge and copy the result to the other repo. **Forbidden under Constitution P-IV (CLI Workspace Containment).** Stash a follow-up after harvest.
- G3c (docling PDF engine) — separate shipment.

## Design

### Section-title surfacing from `segment_markdown`

The G3a segmenter currently returns `list[str]`. We have two options:

**Option 1: Add a sibling helper.** Keep `segment_markdown` returning `list[str]`; add `extract_section_title(segment: str) -> str | None` in the same module. Call it from `build_output_document_parts` after segmentation. Pros: zero API churn on the new G3a public function; helper is independently testable. Cons: re-parses each segment with `MarkdownIt`.

**Option 2: Return structured segments.** Change `segment_markdown(...) -> list[Segment]` where `Segment` is a frozen dataclass with `body: str, section_title: str | None`. Pros: single parse; richer contract. Cons: breaks 012-S's public API one day after shipping; renames cascade through tests.

**Chosen: Option 1** — the helper approach. Less churn; segments are small so re-parsing cost is negligible; we keep the 012-S contract stable.

```python
# src/docline/process/segment.py (added)
def extract_section_title(segment: str) -> str | None:
    """Return the H1 heading text from ``segment`` or ``None`` if absent.

    Returns the first H1's inline text, stripped of leading '# ' and any
    trailing whitespace. Returns ``None`` for segments produced by the
    char-bin fallback (no H1).
    """
    ...
```

### Frontmatter assembly changes (`src/docline/app.py`)

Add a new internal helper that builds the `docline:` namespace dict for a part:

```python
def _build_docline_namespace(
    *,
    parent_document_id: str,
    part_index: int,
    total_parts: int,
    output_path: Path,
    all_output_paths: list[Path],
    section_title: str | None,
) -> dict[str, object]:
    """Build the docline: namespace dict for a processed output part."""
    return {
        "parent_document_id": parent_document_id,
        "part_index": part_index,
        "total_parts": total_parts,
        "prev_part": _relative_sibling(output_path, all_output_paths, offset=-1),
        "next_part": _relative_sibling(output_path, all_output_paths, offset=+1),
        "section_title": section_title,
    }
```

And a small helper:

```python
def _relative_sibling(
    current: Path, all_paths: list[Path], *, offset: int
) -> str | None:
    """Return the basename of the sibling part at ``offset`` or ``None``."""
    idx = all_paths.index(current)
    target = idx + offset
    if target < 0 or target >= len(all_paths):
        return None
    return all_paths[target].name
```

Reuse the existing `_build_document_id` for `parent_document_id` by calling it with `ingest_order=0` for every part of the same source — this collapses the per-part variance and gives a deterministic shared id.

Pass the dict into `base_data["docline"]` before `assemble_frontmatter_payload`. `BaseFrontmatter` already accepts `docline: dict[str, Any] | None`, so no model change required.

### Call-site default flip

```python
# src/docline/app.py:274
return assemble_markdown(
    payload.model_dump(mode="json"),
    body,
    allow_heading_disorder=allow_heading_disorder,
    emit_chunk_anchors=True,  # NEW — production default per G3b
)
```

`assemble_markdown`'s signature default stays `False` so unit-test callers must opt in deliberately.

## Constitution check

| Principle | Compliance |
|---|---|
| I. Safety-first Python | typed signatures; no `Any` introduced (uses existing permissive `dict[str, Any]`) |
| II. TDD | RED tests first in `013.001-T` |
| IV. CLI Containment | Cross-repo snapshot update deferred to operator follow-up stash |
| VI. Single responsibility | Zero new dependencies; reuses existing assemble + segment infrastructure |
| X. Context efficiency | 1 modified source module (`app.py`), 1 source helper added in `segment.py`, 1 new test file, 1 closure doc |
| XI. Merge commit history | Standard PR flow |

## Test plan (TDD RED phase first)

`tests/process/test_referentiality.py` covers:

| Test | Input | Expected |
|---|---|---|
| `test_single_part_output_has_unit_referentiality` | Single-page DOCX (1 part) | `part_index=1, total_parts=1, prev_part=None, next_part=None, parent_document_id` present |
| `test_multi_part_output_part_index_and_total_parts` | Three-H1 PDF → 3 parts | Each part: `part_index in {1,2,3}, total_parts=3` |
| `test_multi_part_output_prev_next_chain` | Three-H1 PDF → 3 parts | Part 1: `prev=None, next=part-0002.md`; Part 2: `prev=part-0001.md, next=part-0003.md`; Part 3: `prev=part-0002.md, next=None` |
| `test_parts_share_parent_document_id` | Three-H1 PDF → 3 parts | All three parts share the same `parent_document_id` value |
| `test_parent_document_id_deterministic_for_same_input` | Run process twice on same source | Same `parent_document_id` both runs (assuming same `job_id`) |
| `test_section_title_populated_when_h1_present` | DOCX with H1 heading | `section_title` matches the H1 text |
| `test_section_title_null_for_char_bin_fallback` | Flat PDF (no H1) → 1 part via char-bin | `section_title is None` |
| `test_chunk_anchors_emitted_by_default_in_processed_output` | Any source with H1/H2/H3 headings | Output `.md` body contains `<a id="chunk-0001"></a>` before the first heading |
| `test_chunk_anchors_skip_fenced_code` | Source with `# heading` inside ``` fence | No chunk anchor emitted inside the fence |
| `test_docline_namespace_serializes_to_frontmatter_yaml` | Multi-part output | The `docline:` block appears in the YAML frontmatter of each emitted `.md` |

And `tests/process/test_segment.py` gets one new test for `extract_section_title`:

| Test | Input | Expected |
|---|---|---|
| `test_extract_section_title_returns_h1_text` | `"# Chapter One\n\ncontent"` | `"Chapter One"` |
| `test_extract_section_title_returns_none_when_no_h1` | `"just prose with no heading"` | `None` |
| `test_extract_section_title_returns_first_h1` | Multi-H1 segment | first H1's text |

## Risk and rollback

| Risk | Mitigation |
|---|---|
| Existing `test_chunk_anchor_emission.py` may break if default flip leaks | The flip is at the call site only; `assemble_markdown` signature default stays `False`; unit tests explicitly pass `emit_chunk_anchors=True` already |
| `test_graphtor_ingestion_contract.py` tests may need to expect chunk anchors in produced output | Run full suite during `013.003-T`; update assertions for any test that consumes `_assemble_part_markdown` output and expects anchor-free body |
| Adding `docline:` to every part bloats frontmatter | Six small keys; YAML adds ~150 bytes per part — negligible |
| Cross-repo snapshot drift | Operator follow-up stash; closure doc reminds to run `docline export-schema` and copy |
| `parent_document_id` collision across unrelated sources | Reuses existing SHA-derived `_build_document_id` algorithm; collisions are cryptographically improbable |

**Rollback**: revert the shipment merge commit. Output regenerates without referentiality on next `docline process`; consumers tolerate missing optional `docline:` keys.

## ProposedAction / ActionRisk (strict-safety)

| Action | Risk | Approval |
|---|---|---|
| Add `extract_section_title` to `src/docline/process/segment.py` | `low` | None — net-new helper |
| Extend `_assemble_part_markdown` in `src/docline/app.py` with `docline:` namespace builder | `moderate` | None — covered by RED test gate; behavior change is additive |
| Flip `emit_chunk_anchors=True` at `src/docline/app.py:274` | `moderate` | None — covered by tests; body content change is additive (anchor injection) |
| Adjust `tests/process/test_chunk_anchor_emission.py` or `tests/test_graphtor_ingestion_contract.py` IF assertions break | `low` | None |

No destructive actions. No high-blast-radius surfaces. `plan-harden` not invoked.

## Sequencing (TDD-ordered)

1. **013.001-T** — Write failing tests for referentiality + chunk-anchor default (RED).
2. **013.002-T** — Implement `extract_section_title` and `_build_docline_namespace`; populate `base_data["docline"]` in `_assemble_part_markdown` (GREEN).
3. **013.003-T** — Flip `emit_chunk_anchors=True` at the call site; reconcile any regression tests; run all 5 quality gates.
4. **013.004-T** — Closure document.

## Acceptance criteria

- `extract_section_title(segment) -> str | None` exists in `src/docline/process/segment.py`
- `_build_docline_namespace` (or equivalent) populated and assigned into `base_data["docline"]` in `src/docline/app.py`
- `emit_chunk_anchors=True` is set at the `assemble_markdown` call site in `src/docline/app.py`
- `tests/process/test_referentiality.py` covers all 10 referentiality scenarios + 3 helper scenarios and is green
- All 5 CI gates pass on the PR: `ruff format --check`, `ruff check .`, `pyright src/`, `pytest`, `python -m build`
- `docline export-schema` still produces valid output (the `docline:` field accepts the new keys via the existing `additionalProperties: true`-equivalent permissive `dict[str, Any]`)
- Closure document records the new field shape, the call-site flip rationale, and the cross-repo follow-up stash for `graphtor-docs`

## Files touched (summary)

| Path | Change |
|---|---|
| `src/docline/process/segment.py` | MODIFY — add `extract_section_title` helper |
| `src/docline/app.py` | MODIFY — add `_build_docline_namespace`, `_relative_sibling`; populate `base_data["docline"]`; pass `emit_chunk_anchors=True` to assemble |
| `src/docline/process/output_contract.py` | MODIFY (small) — pass the section title list alongside segments via a tuple/dict so the assembler can populate it |
| `tests/process/test_referentiality.py` | NEW |
| `tests/process/test_segment.py` | MODIFY — add 3 helper tests |
| `tests/process/test_chunk_anchor_emission.py` | NO CHANGE expected (unit-level tests against `assemble_markdown` default-False) |
| `tests/test_graphtor_ingestion_contract.py` | POSSIBLE MODIFY — update if `process` integration assertions hit the new default |
| `docs/closure/013-S-referentiality.md` | NEW |
