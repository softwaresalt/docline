---
title: "007-S Build Complete — Shipment Memory Checkpoint"
date: "2026-05-31"
phase: "build-complete"
shipment_id: "007-S"
feature_id: "007-F"
branch: "feat/fix-pyright-type-regressions"
---

## Items Completed

- `007-F` — Fix pyright type-check regressions in process module → **done**
- `007.001-T` — Fix type annotations in metadata.py and ast_lint.py → **done**

## Files Modified

- `src/docline/process/metadata.py` — Added `from typing import Any`; changed
  `Mapping[str, object]` → `Mapping[str, Any]` on `resolve_document_type` and
  `assemble_frontmatter_payload` signatures.
- `src/docline/process/ast_lint.py` — Added `from markdown_it.token import Token`;
  changed `inline_token: object` → `inline_token: Token` on `_heading_text`.

## Commits

- `209cd5b` — `fix(process): restore pyright type annotations in metadata and ast_lint`

## Quality Gate Results

- `pyright src/` — **0 errors, 0 warnings** ✓
- `ruff check .` — **All checks passed** ✓
- `ruff format --check .` — **81 files formatted** ✓
- `pytest` — **367 passed in 5.49s** ✓

## Review Gate

Correctness Reviewer — zero findings. Gate **PASS**.

## Decisions

- `Mapping[str, Any]` is correct for `**staged_metadata` unpacking into Pydantic models:
  Pydantic validates values at the boundary; `object` was too restrictive for pyright.
- `Token` (from `markdown_it.token`) is the concrete type returned by `MarkdownIt().parse()`;
  using it directly is more accurate than a structural protocol.

## Branch State

Branch `feat/fix-pyright-type-regressions` is clean. No uncommitted changes.
PR not yet created.

## Next Steps

1. Run final quality gate sequence
2. Push branch
3. Create PR and request Copilot review
4. Await operator merge approval
