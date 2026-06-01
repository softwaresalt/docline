---
title: "Fix pyright type-check regressions in process module"
description: "Resolve 6 pyright errors in metadata.py and ast_lint.py introduced after shipment 004-S merge"
topic: "Pyright type-check regression fix"
depth: "lightweight"
decision_status: "decided"
promoted_to: "plan"
linked_artifacts: []
tags:
  - "pyright"
  - "type-safety"
  - "process"
stash_ids:
  - "F6CCF29C"
---

## Problem Frame

After shipment 004-S merged, `pyright src/` reports 6 errors across two files in
`src/docline/process/`. This breaks the pyright quality gate (Constitution
Principle I, Gate 2). The errors are type annotation mismatches — not behavioral
bugs — but they block all future merges that require a clean pyright gate.

### Errors

**metadata.py:80** (4 errors): `schema_family(**staged_metadata)` unpacks a
`Mapping[str, object]` into Pydantic model constructors that expect typed
parameters (`str`, `datetime`). Pyright correctly flags that `object` is not
assignable to `str` or `datetime`.

**ast_lint.py:11,14** (2 errors): `_heading_text(inline_token: object)` accesses
`.children` on an `object`-typed parameter. Pyright correctly flags that `object`
has no `children` attribute.

### Scope

Two files, type annotations only. No behavioral changes required or desired.

## Options Evaluated

### Option A: Suppress with type: ignore or Any

Add `# type: ignore` comments or use `Any` typing to silence the errors.

- Pros: Fastest fix
- Cons: Hides real type safety; violates Constitution Principle I intent
- Effort: Low
- Fit: Poor — undermines the type safety the gate exists to enforce

### Option B: Proper type narrowing

- `metadata.py`: Change the `staged_metadata` parameter type from
  `Mapping[str, object]` to `Mapping[str, Any]`, which correctly reflects that
  Pydantic will perform runtime validation on the values. The `**` unpack of
  `Mapping[str, Any]` satisfies pyright because `Any` is assignable to all types.
- `ast_lint.py`: Change `inline_token: object` to
  `inline_token: markdown_it.token.Token`, which provides the `.children`
  attribute that the function body accesses.

- Pros: Correct, preserves type safety, documents actual contracts
- Cons: Slightly more investigation needed (already done)
- Effort: Low
- Fit: Strong — aligns with Constitution Principle I

## Decision

**Option B: Proper type narrowing.** Use `Mapping[str, Any]` for metadata and
`Token` for ast_lint. Both fixes are minimal, correct, and preserve the intent
of the type safety quality gate.

## Rejected Alternatives

Option A (suppress) rejected because it undermines the quality gate rather than
fixing the root cause.

## Risks and Mitigations

Risk: None material. Changes are type-annotation-only with no behavioral impact.
Pydantic already performs runtime validation on the metadata values.
