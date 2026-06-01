---
title: "Fix pyright type-check regressions in process module"
source: "docs/decisions/2026-05-31-fix-pyright-type-regressions-deliberation.md"
stash_ids:
  - "F6CCF29C"
status: "ready"
---

## Problem Frame

`pyright src/` reports 6 type errors across 2 files in `src/docline/process/`,
breaking Quality Gate 2. Both files need type annotation corrections — no
behavioral changes.

### Error Sites

| File | Line(s) | Error Count | Root Cause |
|---|---|---|---|
| `src/docline/process/metadata.py` | 80 | 4 | `Mapping[str, object]` unpacked into Pydantic model expecting typed params |
| `src/docline/process/ast_lint.py` | 11, 14 | 2 | `inline_token: object` has no `.children` attribute |

## Requirements Trace

| Requirement | Implementation Action |
|---|---|
| Restore `pyright src/` to 0 errors | Fix type annotations in both files |
| No behavioral changes | Annotation-only edits; existing tests must still pass |
| Preserve type safety (Constitution I) | Use proper types, not `Any` suppression (except `Mapping[str, Any]` where Pydantic validates at runtime) |

## Implementation Units

### Unit 1: Fix type annotations in metadata.py and ast_lint.py

**Files affected** (2):

- `src/docline/process/metadata.py` — change `staged_metadata` parameter type
  from `Mapping[str, object]` to `Mapping[str, Any]` on both
  `resolve_document_type` (line 18) and `assemble_frontmatter_payload` (line 65).
  Add `from typing import Any` import.
- `src/docline/process/ast_lint.py` — change `inline_token: object` to
  `inline_token: Token` on `_heading_text` (line 9). Add
  `from markdown_it.token import Token` import.

**Verification**:

- `pyright src/` exits with 0 errors
- `pytest tests/process/test_frontmatter_payload.py tests/process/test_ast_lint.py` passes
- `ruff check src/docline/process/metadata.py src/docline/process/ast_lint.py` passes

**Execution posture**: Direct fix (no test-first needed — this is a type
annotation correction, not a behavioral change; existing tests cover the
behavior).

**Acceptance criteria**:

- `pyright src/` reports 0 errors, 0 warnings
- All existing tests pass unchanged
- No `# type: ignore` comments added

## Dependency Graph

Single unit — no dependencies.

## Decisions and Rationale

**`Mapping[str, Any]` instead of removing `Mapping` or using `dict[str, str]`**:
The metadata dictionary carries heterogeneous values (`str`, `datetime`, etc.)
that Pydantic validates at runtime. `Any` correctly expresses "Pydantic will
validate this at the boundary" while satisfying pyright's static analysis.
`object` was too restrictive for `**` unpacking into typed parameters.

**`Token` instead of a Protocol or structural type**: `markdown_it.token.Token`
is the actual type returned by `MarkdownIt().parse()`. Using the concrete type
is simpler and more accurate than defining a structural protocol for a single
private helper function.

## Risks and Caveats

No material risks. Changes are type-annotation-only with no runtime impact.

## Plan Hardening Signals

- Public API, schema, or contract change: **No** — both functions are internal
  to the process module
- Security, auth, permission, or compliance-sensitive behavior: **No**
- Migration, backfill, destructive data/config action: **No**
- External integration, operator checkpoint, or external dependency: **No**
- High runtime, rollout, or rollback risk: **No**

Requires plan hardening: no

## Runtime Verification and Closure

No runtime surface changes. Verification is fully covered by the pyright quality
gate and existing test suite. No operational closure artifact needed.

## Constitution Check

| Principle | Status |
|---|---|
| I. Safety-First Python | Restored — pyright gate passes |
| II. Test-First Development | N/A — annotation-only fix; existing tests cover behavior |
| III–IV. Workspace Isolation | N/A |
| V. Structured Observability | Commit message traces to stash ID |
| VI. Single Responsibility | No new dependencies |

## Plan Review

<!-- plan-review-attempt: 1 -->

**Gate decision: PASS** (advisory findings only — no revision required)

### Findings

| # | Persona | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | Python Reviewer | P2 | `Mapping[str, Any]` widens the contract; keep localized | Accepted — plan already limits change to 2 signatures |
| 2 | Python Reviewer | P2 | `Token` type is correct; preserve existing `hasattr` guard | Accepted — plan makes no behavioral changes |
| 3 | Constitution Reviewer | P3 | "No new tests" acceptable for annotation-only fix | Acknowledged — `pyright src/` is the acceptance check |
| 4 | Scope Boundary Auditor | P3 | Scope is appropriately minimal | Acknowledged |

### Hardening Assessment

Plan declares `Requires plan hardening: no`. No hardening signals present.
Confirmed: no hardening required.

### Verdict

All findings are P2/P3 advisory. No P0 or P1 blockers. Plan proceeds to harvest.
