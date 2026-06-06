"""Adaptive resource probe — single source of truth for docline throttling.

This module exposes :class:`ResourceBudget`, a frozen dataclass that captures
the runtime environment's resource situation, and :func:`probe`, which
constructs one by sampling :mod:`psutil`, :func:`os.cpu_count`, and optionally
:mod:`torch.cuda`.

The probe drives every throttling decision in the docline PDF pipeline:

* whether ``layout_engine='auto'`` resolves to ``docling``
* the maximum PDF size / page count handed to docling in one call
* whether docling chunks process serially (one at a time) or concurrently
* which thread caps the docling subprocess inherits via ``OMP_NUM_THREADS``
* which accelerator device (``cpu`` / ``cuda``) docling targets

The probe is intentionally cheap (microseconds) so it can be called once
per batch run without measurable overhead. Failures in any introspection
path (psutil errors, torch import errors, CUDA driver errors) degrade
gracefully to the most conservative budget rather than propagating
exceptions to the caller — the pipeline must remain operational even
when the introspection itself is broken.

Decision tables and the motivating root-cause analysis are documented in
``docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal

import psutil

_log = logging.getLogger(__name__)

AcceleratorDevice = Literal["cpu", "cuda", "mps"]

_BYTES_PER_GB = 1_000_000_000  # decimal GB, matches psutil reporting convention
_GIB = 1024**3  # binary GiB, matches torch.cuda.mem_get_info convention

# Minimum GPU criteria for docling acceleration.
_MIN_GPU_COMPUTE_CAPABILITY: tuple[int, int] = (5, 0)  # Maxwell+; rejects Kepler sm_3x
_MIN_GPU_FREE_VRAM_GB: float = 4.0  # docling rt_detr-l4 working set is ~4-6 GB


@dataclass(frozen=True)
class ResourceBudget:
    """Snapshot of host resources + derived docling throttling parameters.

    Fields are computed once by :func:`probe` and frozen so callers can hash
    or cache the result safely.

    Attributes:
        available_ram_gb: Free physical RAM in decimal GB at probe time.
        total_ram_gb: Total physical RAM in decimal GB.
        logical_cpus: Number of logical CPUs from :func:`os.cpu_count`.
        pagefile_pressure: True when the swap / pagefile is more than
            half full. Independently of free RAM, this forces serial
            docling and halves the max page budget because the OS is
            already paging and adding more pressure risks a thrashing
            spiral (the 2026-06-04 incident pattern).
        accelerator_device: ``"cpu"``, ``"cuda"``, or ``"mps"``. Only
            ``"cpu"`` is currently selected automatically; ``"cuda"`` is
            selected when the four-condition GPU gate (see
            :func:`_detect_gpu`) passes.
        gpu_name: Device name reported by ``torch.cuda``, or ``None`` if
            no CUDA-capable GPU was detected.
        gpu_vram_gb: Free VRAM in decimal GB, or ``None``.
        gpu_compute_capability: ``(major, minor)`` per ``torch.cuda``,
            or ``None``.
        recommended_concurrency: Maximum number of docling workers that
            can safely run in parallel under this budget. Always ``1``
            under low-RAM or pagefile-pressured conditions.
        recommended_docling_max_pages: Per-call page-count ceiling for
            docling. ``0`` means docling is not safe on this host —
            callers should route to the heuristic engine.
        recommended_docling_max_mb: Per-call file-size ceiling (decimal
            megabytes) for docling. ``0`` means docling is not safe.
        serialize_docling: When True, callers MUST process docling
            chunks one at a time and SHOULD insert a small reclaim
            pause between calls so the OS can release torch tensor
            pages.
        omp_thread_count: Value to set into ``OMP_NUM_THREADS`` /
            ``MKL_NUM_THREADS`` / ``OPENBLAS_NUM_THREADS`` before the
            first docling import. Conservative for low-RAM hosts.
    """

    available_ram_gb: float
    total_ram_gb: float
    logical_cpus: int
    pagefile_pressure: bool
    accelerator_device: AcceleratorDevice
    gpu_name: str | None
    gpu_vram_gb: float | None
    gpu_compute_capability: tuple[int, int] | None
    recommended_concurrency: int
    recommended_docling_max_pages: int
    recommended_docling_max_mb: int
    serialize_docling: bool
    omp_thread_count: int


def _ram_tier_cpu_defaults(available_ram_gb: float, logical_cpus: int) -> dict[str, object]:
    """Return CPU-mode docling parameters for the given RAM tier.

    The table is the canonical decision matrix documented in the plan
    and the RCA. Hosts under 4 GB get zero docling budget — they should
    use the heuristic engine exclusively. Hosts over 32 GB get the
    highest budget that empirical measurement on the i7-4700MQ class
    has shown to be safe.
    """

    if available_ram_gb < 4.0:
        return {
            "max_pages": 0,
            "max_mb": 0,
            "serialize": True,
            "concurrency": 1,
            "omp_threads": 1,
        }
    if available_ram_gb < 8.0:
        return {
            "max_pages": 25,
            "max_mb": 10,
            "serialize": True,
            "concurrency": 1,
            "omp_threads": 1,
        }
    if available_ram_gb < 16.0:
        return {
            "max_pages": 50,
            "max_mb": 20,
            "serialize": True,
            "concurrency": 1,
            "omp_threads": 2,
        }
    if available_ram_gb < 32.0:
        return {
            "max_pages": 75,
            "max_mb": 30,
            "serialize": False,
            "concurrency": 2,
            "omp_threads": 2,
        }
    return {
        "max_pages": 100,
        "max_mb": 40,
        "serialize": False,
        "concurrency": min(max(logical_cpus // 2, 1), 4),
        "omp_threads": max(2, logical_cpus // 4),
    }


def _import_torch() -> object | None:
    """Lazily import torch and return the module, or None if not importable.

    Isolated as a helper so tests can monkeypatch it without manipulating
    ``sys.modules`` directly — real torch (when installed as a transitive
    docling dependency) is fragile against re-imports because of its
    one-shot ``TORCH_LIBRARY`` registration.
    """

    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        return None
    return torch


def _detect_gpu() -> tuple[AcceleratorDevice, str | None, float | None, tuple[int, int] | None]:
    """Probe for a docling-capable CUDA GPU.

    Returns a tuple of ``(accelerator_device, gpu_name, gpu_free_vram_gb,
    gpu_compute_capability)``. All four conditions must pass for
    ``accelerator_device == "cuda"``:

    1. ``torch`` is importable and ``torch.cuda.is_available()`` is True
    2. Compute capability is at least ``(5, 0)`` (Maxwell+) — Kepler
       ``sm_3x`` (e.g. the 2026-06-04 host's GTX 770M) is rejected
       because PyTorch 2.x ships no kernels for it
    3. Free VRAM is at least 4 GB — docling rt_detr-l4 working set is
       4-6 GB; below the threshold we OOM immediately
    4. A trivial ``torch.zeros(1, device='cuda')`` succeeds, confirming
       the driver can actually launch kernels

    The environment variable ``DOCLINE_GPU_FORCE=1`` bypasses gate 2
    for contributors who want to test the CUDA branch on weak GPUs.

    Any failure in the probe path returns CPU defaults — the caller
    must never see an exception bubble out of the GPU detector.
    """

    torch = _import_torch()
    if torch is None:
        return "cpu", None, None, None

    try:
        cuda = torch.cuda  # type: ignore[attr-defined]
        if not cuda.is_available():
            return "cpu", None, None, None

        gpu_name: str | None = None
        capability: tuple[int, int] | None = None
        free_vram_gb: float | None = None

        try:
            gpu_name = cuda.get_device_name(0)
        except Exception:  # noqa: BLE001 — defensive: torch APIs can drift
            gpu_name = None

        try:
            capability = cuda.get_device_capability(0)
        except Exception:  # noqa: BLE001
            capability = None

        try:
            free_bytes, _total_bytes = cuda.mem_get_info(0)
            free_vram_gb = free_bytes / _BYTES_PER_GB
        except Exception:  # noqa: BLE001
            free_vram_gb = None

        force_override = os.environ.get("DOCLINE_GPU_FORCE", "") == "1"

        if not force_override and capability is not None and capability < _MIN_GPU_COMPUTE_CAPABILITY:
            return "cpu", gpu_name, free_vram_gb, capability

        if free_vram_gb is not None and free_vram_gb < _MIN_GPU_FREE_VRAM_GB:
            return "cpu", gpu_name, free_vram_gb, capability

        # Confirm kernel launchability with a trivial allocation.
        try:
            torch.zeros(1, device="cuda")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            _log.warning("CUDA available but trivial allocation failed; falling back to CPU")
            return "cpu", gpu_name, free_vram_gb, capability

        return "cuda", gpu_name, free_vram_gb, capability
    except Exception:  # noqa: BLE001 — final guard around all torch.cuda calls
        return "cpu", None, None, None


def _conservative_budget(logical_cpus: int) -> ResourceBudget:
    """Construct the most-conservative budget for when introspection fails."""

    return ResourceBudget(
        available_ram_gb=0.0,
        total_ram_gb=0.0,
        logical_cpus=logical_cpus,
        pagefile_pressure=True,
        accelerator_device="cpu",
        gpu_name=None,
        gpu_vram_gb=None,
        gpu_compute_capability=None,
        recommended_concurrency=1,
        recommended_docling_max_pages=0,
        recommended_docling_max_mb=0,
        serialize_docling=True,
        omp_thread_count=1,
    )


def probe() -> ResourceBudget:
    """Sample host resources and compute a docling throttling budget.

    Returns a fresh :class:`ResourceBudget`. Any failure in psutil,
    os.cpu_count, or the GPU detection path causes the probe to return
    the conservative fallback budget rather than raising — the pipeline
    must remain operational even when the introspection itself is broken.

    Returns:
        A populated :class:`ResourceBudget`.
    """

    try:
        cpu_count = os.cpu_count() or 1
    except Exception:  # noqa: BLE001
        cpu_count = 1

    try:
        vmem = psutil.virtual_memory()
        available_ram_gb = vmem.available / _BYTES_PER_GB
        total_ram_gb = vmem.total / _BYTES_PER_GB
    except Exception as err:  # noqa: BLE001
        _log.warning("psutil.virtual_memory failed (%s); returning conservative budget", err)
        return _conservative_budget(cpu_count)

    try:
        swap = psutil.swap_memory()
        pagefile_pressure = float(swap.percent) > 50.0
    except Exception:  # noqa: BLE001
        pagefile_pressure = False

    accelerator_device, gpu_name, gpu_vram_gb, gpu_capability = _detect_gpu()

    if accelerator_device == "cuda" and gpu_vram_gb is not None:
        max_pages = min(200, int(gpu_vram_gb * 25))
        max_mb = 80
        serialize = False
        concurrency = 1  # CUDA contexts don't multi-tenant cleanly inside one process
        omp_threads = max(2, cpu_count // 4)
    else:
        tier = _ram_tier_cpu_defaults(available_ram_gb, cpu_count)
        max_pages = int(tier["max_pages"])  # type: ignore[arg-type]
        max_mb = int(tier["max_mb"])  # type: ignore[arg-type]
        serialize = bool(tier["serialize"])
        concurrency = int(tier["concurrency"])  # type: ignore[arg-type]
        omp_threads = int(tier["omp_threads"])  # type: ignore[arg-type]

    if pagefile_pressure:
        serialize = True
        if max_pages > 1:
            max_pages = max(max_pages // 2, 1)

    return ResourceBudget(
        available_ram_gb=available_ram_gb,
        total_ram_gb=total_ram_gb,
        logical_cpus=cpu_count,
        pagefile_pressure=pagefile_pressure,
        accelerator_device=accelerator_device,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram_gb,
        gpu_compute_capability=gpu_capability,
        recommended_concurrency=concurrency,
        recommended_docling_max_pages=max_pages,
        recommended_docling_max_mb=max_mb,
        serialize_docling=serialize,
        omp_thread_count=omp_threads,
    )


def should_use_docling(
    budget: ResourceBudget,
    *,
    file_size_mb: float,
    page_count: int | None,
) -> tuple[bool, str]:
    """Decide whether docling is safe for a single PDF under the given budget.

    Pure function — does no I/O and never raises. Callers use this to
    decide between docling, heuristic, or routing through the PDF
    splitter for chunked processing.

    Args:
        budget: The :class:`ResourceBudget` snapshot from :func:`probe`.
        file_size_mb: PDF file size in decimal megabytes.
        page_count: PDF page count, or ``None`` when the count is not
            yet known (e.g. before pypdf has parsed the file). In the
            ``None`` case the function trusts the file-size gate alone.

    Returns:
        A tuple of ``(use_docling, reason)`` where ``use_docling`` is
        ``True`` when all gates pass, ``False`` otherwise. ``reason`` is
        one of ``"ok"`` (use docling), ``"insufficient_ram"`` (host
        too small for docling at all), ``"file_too_large"``, or
        ``"page_count_too_high"``.
    """

    if budget.recommended_docling_max_pages <= 0 or budget.recommended_docling_max_mb <= 0:
        return False, "insufficient_ram"
    if file_size_mb > budget.recommended_docling_max_mb:
        return False, "file_too_large"
    if page_count is not None and page_count > budget.recommended_docling_max_pages:
        return False, "page_count_too_high"
    return True, "ok"
