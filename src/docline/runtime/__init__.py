"""Runtime safety primitives — resource probe, thread caps, and accelerator gating.

This subpackage exposes the runtime-environment introspection that the
docline pipeline uses to decide:

* whether to invoke docling on a given PDF (or downgrade to heuristic /
  route through the PDF splitter)
* how many docling workers to run concurrently
* whether to force serial processing under pagefile pressure
* which accelerator device to request from docling (cpu / cuda / mps)
* what thread caps to apply to PyTorch / BLAS before docling loads

See ``docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md``
for the failure that motivated this module and the design pivot from
"detect OOM and fall back" to "split and throttle proactively".
"""

from docline.runtime.resource_probe import (
    AcceleratorDevice,
    ResourceBudget,
    probe,
    should_use_docling,
)

__all__ = [
    "AcceleratorDevice",
    "ResourceBudget",
    "probe",
    "should_use_docling",
]
