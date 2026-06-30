---
date: 2026-06-29
shipment: 041-S
category: pyright-pypdf-duck-typing
keywords: [pyright, pypdf, page_metadata, reportAttributeAccessIssue, Any, hasattr, getattr, callable, typecheck]
confidence: high
evidence: 041-S Ship session — fidelity_scorer.signal_font_diversity pyright error; hasattr/getattr+callable narrowing failed, Any alias fixed it
---

# Narrow pypdf page-metadata to `Any` for duck-typed probes — `hasattr`/`getattr` do not satisfy pyright

## Problem

Helpers that probe a pypdf `PageObject` are typed `page_metadata: object | None`
(loose, because the pypdf surface varies: `DictionaryObject`, `IndirectObject`).
After `if page_metadata is None: return 0.0`, pyright narrows the value to
`object`, which has **no** `.get` / `.get_object` / `.keys`. Calling them raises
`reportAttributeAccessIssue` and **fails the `pyright src/` quality gate**.

This is latent across `fidelity_scorer.py` (every `signal_*` that reads
`/Resources`, `/Font`, content streams, etc.).

## Approaches that did NOT work

1. **Inline `hasattr` guard** — `x.get(...) if hasattr(x, "get") else None`.
   Pyright does not narrow an explicitly `object`-typed value via `hasattr`, so
   the `.get` access still errors.
2. **`getattr` + `callable`** — `g = getattr(x, "get", None); g(...) if callable(g) else None`.
   This *removed* the first error but **cascaded** it: pyright then typed the
   result concretely as `object`, so the *next* duck-typed call
   (`resources.get_object()`, `resources.get("/Font")`) errored instead.

## Fix

Alias the metadata to `Any` once, immediately after the `None` guard, then do all
the duck-typed probing on the alias:

```python
if page_metadata is None:
    return 0.0
# pypdf's PageObject API surface varies; alias to Any so the duck-typed
# .get/.get_object/.keys probes below type-check.
meta: Any = page_metadata
resources = meta.get("/Resources", None)
...
```

`Any` propagates through derived locals (`resources`, `font_dict`), so no
cascade. Behaviour is identical to the original `page_metadata.get(...)`.

## Rule

- For pypdf (or any variable-surface C-extension object) accessed via duck
  typing under an `object | None` annotation, **bind a single `meta: Any = value`
  alias** after the `None` guard rather than sprinkling `hasattr`/`getattr`
  guards or `# type: ignore`.
- The repo runs `pyright src/` as a **blocking gate**; verify with
  `uv run pyright src/` (uses the locked pyright, matching CI) before pushing.
