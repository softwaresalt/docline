---
date: 2026-06-30
shipment: 043-S
category: importlib-dataclass-sys-modules
keywords: [importlib, spec_from_file_location, exec_module, dataclass, sys.modules, scripts, study, test]
confidence: high
evidence: 043-S — tests/test_ocr_memory_calibration.py loaded a @dataclass script via importlib and crashed in dataclasses.py until the module was registered in sys.modules before exec_module
---

# A `@dataclass` in an importlib-loaded script needs the module in `sys.modules` before `exec_module`

## Problem

`scripts/` studies are unit-tested by loading them as modules via
`importlib.util.spec_from_file_location(...)` + `exec_module(...)` (they live
outside `src/docline`, so they are not importable as packages). This works for
scripts made of plain functions (e.g. `compare_merge_gap.py`).

But when the script defines a `@dataclass`, `exec_module` crashes:

```text
AttributeError: 'NoneType' object has no attribute '__dict__'
  File ".../dataclasses.py", line 749, in _process_class
    ns = sys.modules.get(cls.__module__).__dict__
```

`@dataclass` resolves field annotations (for `InitVar` / `ClassVar` detection)
by looking the defining module up in `sys.modules`. A module built with
`module_from_spec` is **not** auto-registered, so `sys.modules.get(cls.__module__)`
returns `None` and the attribute access explodes. `from __future__ import
annotations` does not help — the lookup still happens.

## Fix

Register the module in `sys.modules` under the spec name **before** calling
`exec_module`:

```python
def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ocr_memory_calibration", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module   # <-- required before exec so @dataclass resolves
    spec.loader.exec_module(module)
    return module
```

## Rule

- When a `scripts/` file loaded via `importlib.spec_from_file_location` defines
  any `@dataclass` (or anything that introspects `sys.modules[cls.__module__]`),
  the test loader **must** do `sys.modules[spec.name] = module` before
  `exec_module`. Plain-function scripts do not need this, which is why the
  existing `compare_merge_gap.py` loader omitted it.
