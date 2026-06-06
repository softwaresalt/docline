"""Tests for ``docline.runtime.resource_probe`` (018.001.001-T).

Covers ``ResourceBudget`` and ``probe()`` per the contract documented in
``docs/plans/2026-06-05-shipment-a-runtime-safety-primitives.md`` and the
revised stash 1D945AB5.

Tests mock ``psutil`` and ``docline.runtime.resource_probe._import_torch``
so the suite runs deterministically on CPU-only contributor machines and
on hosts with stale NVIDIA drivers. The ``_import_torch`` indirection keeps
tests away from ``sys.modules['torch']`` manipulation, which crashes real
torch builds because of one-shot ``TORCH_LIBRARY`` registration.
"""

from __future__ import annotations

import types
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest


def _make_vmem(available_bytes: int, total_bytes: int) -> Any:
    return types.SimpleNamespace(available=available_bytes, total=total_bytes)


def _make_swap(percent: float) -> Any:
    return types.SimpleNamespace(percent=percent)


def _make_torch_module(cuda_namespace: Any) -> Any:
    torch_stub = types.SimpleNamespace(cuda=cuda_namespace)
    torch_stub.zeros = lambda *args, **kwargs: MagicMock()
    return torch_stub


@pytest.fixture
def probe_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """Patch psutil + os.cpu_count + _import_torch deterministically.

    Mutate the returned dict to control behavior:
      * available_gb, total_gb — RAM tier
      * swap_percent           — pagefile pressure
      * cpu_count              — logical processors
      * torch_cuda             — None to simulate torch not installed;
                                 otherwise a SimpleNamespace acting as torch.cuda
    """

    state: dict[str, Any] = {
        "available_gb": 32.0,
        "total_gb": 32.0,
        "swap_percent": 5.0,
        "cpu_count": 8,
        "torch_cuda": None,
    }

    def fake_vmem() -> Any:
        return _make_vmem(
            int(state["available_gb"] * 1_000_000_000),
            int(state["total_gb"] * 1_000_000_000),
        )

    def fake_swap() -> Any:
        return _make_swap(state["swap_percent"])

    def fake_cpu_count() -> int:
        return int(state["cpu_count"])

    def fake_import_torch() -> object | None:
        cuda = state["torch_cuda"]
        if cuda is None:
            return None
        return _make_torch_module(cuda)

    monkeypatch.setattr("psutil.virtual_memory", fake_vmem)
    monkeypatch.setattr("psutil.swap_memory", fake_swap)
    monkeypatch.setattr("os.cpu_count", fake_cpu_count)
    monkeypatch.setattr("docline.runtime.resource_probe._import_torch", fake_import_torch)
    monkeypatch.delenv("DOCLINE_GPU_FORCE", raising=False)

    yield state


def test_resource_budget_is_frozen_dataclass() -> None:
    """``ResourceBudget`` is a frozen dataclass — callers can hash / cache it."""

    from docline.runtime.resource_probe import ResourceBudget

    budget = ResourceBudget(
        available_ram_gb=32.0,
        total_ram_gb=32.0,
        logical_cpus=8,
        pagefile_pressure=False,
        accelerator_device="cpu",
        gpu_name=None,
        gpu_vram_gb=None,
        gpu_compute_capability=None,
        recommended_concurrency=2,
        recommended_docling_max_pages=75,
        recommended_docling_max_mb=30,
        serialize_docling=False,
        omp_thread_count=2,
    )

    with pytest.raises(AttributeError):
        budget.recommended_concurrency = 999  # type: ignore[misc]


@pytest.mark.parametrize(
    "available_gb,expected_pages,expected_mb,expected_serialize,expected_concurrency,expected_omp",
    [
        (2.0, 0, 0, True, 1, 1),
        (6.0, 25, 10, True, 1, 1),
        (12.0, 50, 20, True, 1, 2),
        (24.0, 75, 30, False, 2, 2),
        (48.0, 100, 40, False, 4, 2),
    ],
)
def test_cpu_ram_tier_threshold_table(
    probe_env: dict[str, Any],
    available_gb: float,
    expected_pages: int,
    expected_mb: int,
    expected_serialize: bool,
    expected_concurrency: int,
    expected_omp: int,
) -> None:
    """Probe returns the documented threshold table for each CPU RAM tier."""

    probe_env["available_gb"] = available_gb
    probe_env["total_gb"] = max(available_gb, 4.0)
    probe_env["cpu_count"] = 8

    from docline.runtime.resource_probe import probe

    budget = probe()

    assert budget.accelerator_device == "cpu"
    assert budget.recommended_docling_max_pages == expected_pages
    assert budget.recommended_docling_max_mb == expected_mb
    assert budget.serialize_docling is expected_serialize
    assert budget.recommended_concurrency == expected_concurrency
    assert budget.omp_thread_count == expected_omp


def test_pagefile_pressure_forces_serialize_and_halves_max_pages(probe_env: dict[str, Any]) -> None:
    """Swap usage > 50 % forces serialize and halves max pages regardless of free RAM."""

    probe_env["available_gb"] = 24.0
    probe_env["total_gb"] = 32.0
    probe_env["swap_percent"] = 75.0

    from docline.runtime.resource_probe import probe

    budget = probe()

    assert budget.pagefile_pressure is True
    assert budget.serialize_docling is True
    assert budget.recommended_docling_max_pages == 75 // 2


def test_pagefile_pressure_does_not_zero_pages_for_high_ram(probe_env: dict[str, Any]) -> None:
    """Halve operation never reduces a positive page budget to zero."""

    probe_env["available_gb"] = 48.0
    probe_env["swap_percent"] = 60.0

    from docline.runtime.resource_probe import probe

    budget = probe()

    assert budget.pagefile_pressure is True
    assert budget.recommended_docling_max_pages > 0


def test_gpu_not_available_returns_cpu(probe_env: dict[str, Any]) -> None:
    """When torch.cuda.is_available() is False, accelerator stays cpu."""

    probe_env["torch_cuda"] = types.SimpleNamespace(is_available=lambda: False)

    from docline.runtime.resource_probe import probe

    budget = probe()

    assert budget.accelerator_device == "cpu"
    assert budget.gpu_compute_capability is None


def test_gpu_capability_below_5_0_is_rejected(probe_env: dict[str, Any]) -> None:
    """sm_3x (Kepler) is rejected — PyTorch 2.x ships no kernels for it.

    Regression coverage for the 2026-06-04 host's GTX 770M (sm_30).
    """

    probe_env["torch_cuda"] = types.SimpleNamespace(
        is_available=lambda: True,
        get_device_capability=lambda device=0: (3, 0),
        get_device_name=lambda device=0: "GeForce GTX 770M",
        mem_get_info=lambda device=0: (3 * 1024**3, 3 * 1024**3),
    )

    from docline.runtime.resource_probe import probe

    budget = probe()

    assert budget.accelerator_device == "cpu"
    assert budget.gpu_name == "GeForce GTX 770M"
    assert budget.gpu_compute_capability == (3, 0)


def test_gpu_low_vram_is_rejected(probe_env: dict[str, Any]) -> None:
    """< 4 GB free VRAM is rejected — docling rt_detr-l4 working set is 4-6 GB."""

    probe_env["torch_cuda"] = types.SimpleNamespace(
        is_available=lambda: True,
        get_device_capability=lambda device=0: (8, 6),
        get_device_name=lambda device=0: "RTX 3050 Mobile 4GB",
        mem_get_info=lambda device=0: (int(2.5 * 1024**3), 4 * 1024**3),
    )

    from docline.runtime.resource_probe import probe

    budget = probe()

    assert budget.accelerator_device == "cpu"
    assert budget.gpu_vram_gb is not None
    assert budget.gpu_vram_gb < 4.0


def test_gpu_all_conditions_met_returns_cuda(probe_env: dict[str, Any]) -> None:
    """All four conditions pass → accelerator_device='cuda' with raised limits."""

    probe_env["torch_cuda"] = types.SimpleNamespace(
        is_available=lambda: True,
        get_device_capability=lambda device=0: (8, 6),
        get_device_name=lambda device=0: "RTX 3060",
        mem_get_info=lambda device=0: (8 * 1024**3, 12 * 1024**3),
    )

    from docline.runtime.resource_probe import probe

    budget = probe()

    assert budget.accelerator_device == "cuda"
    assert budget.gpu_name == "RTX 3060"
    assert budget.gpu_compute_capability == (8, 6)
    assert budget.recommended_docling_max_pages >= 100


def test_gpu_force_override_bypasses_capability_gate(
    probe_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """DOCLINE_GPU_FORCE=1 lets contributors test the cuda branch on weak GPUs."""

    monkeypatch.setenv("DOCLINE_GPU_FORCE", "1")
    probe_env["torch_cuda"] = types.SimpleNamespace(
        is_available=lambda: True,
        get_device_capability=lambda device=0: (3, 0),
        get_device_name=lambda device=0: "GTX 770M",
        mem_get_info=lambda device=0: (5 * 1024**3, 6 * 1024**3),
    )

    from docline.runtime.resource_probe import probe

    budget = probe()

    assert budget.accelerator_device == "cuda"


def test_probe_works_without_torch_installed(probe_env: dict[str, Any]) -> None:
    """Probe never raises ImportError when torch isn't present."""

    probe_env["torch_cuda"] = None

    from docline.runtime.resource_probe import probe

    budget = probe()

    assert budget.accelerator_device == "cpu"
    assert budget.gpu_name is None
    assert budget.gpu_vram_gb is None
    assert budget.gpu_compute_capability is None


def _budget(**overrides: Any) -> Any:
    from docline.runtime.resource_probe import ResourceBudget

    defaults: dict[str, Any] = {
        "available_ram_gb": 24.0,
        "total_ram_gb": 32.0,
        "logical_cpus": 8,
        "pagefile_pressure": False,
        "accelerator_device": "cpu",
        "gpu_name": None,
        "gpu_vram_gb": None,
        "gpu_compute_capability": None,
        "recommended_concurrency": 2,
        "recommended_docling_max_pages": 75,
        "recommended_docling_max_mb": 30,
        "serialize_docling": False,
        "omp_thread_count": 2,
    }
    defaults.update(overrides)
    return ResourceBudget(**defaults)


def test_should_use_docling_ok_within_budget() -> None:
    from docline.runtime.resource_probe import should_use_docling

    use, reason = should_use_docling(_budget(), file_size_mb=15.0, page_count=40)
    assert use is True
    assert reason == "ok"


def test_should_use_docling_rejects_oversize_file() -> None:
    from docline.runtime.resource_probe import should_use_docling

    use, reason = should_use_docling(_budget(), file_size_mb=109.0, page_count=40)
    assert use is False
    assert reason == "file_too_large"


def test_should_use_docling_rejects_excess_pages() -> None:
    from docline.runtime.resource_probe import should_use_docling

    use, reason = should_use_docling(_budget(), file_size_mb=5.0, page_count=500)
    assert use is False
    assert reason == "page_count_too_high"


def test_should_use_docling_rejects_when_max_pages_is_zero() -> None:
    from docline.runtime.resource_probe import should_use_docling

    budget = _budget(recommended_docling_max_pages=0, recommended_docling_max_mb=0)
    use, reason = should_use_docling(budget, file_size_mb=1.0, page_count=5)
    assert use is False
    assert reason == "insufficient_ram"


def test_should_use_docling_treats_unknown_page_count_optimistically() -> None:
    """When page_count is None we trust the file-size gate alone."""

    from docline.runtime.resource_probe import should_use_docling

    use, reason = should_use_docling(_budget(), file_size_mb=10.0, page_count=None)
    assert use is True
    assert reason == "ok"


def test_probe_returns_conservative_budget_on_psutil_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If psutil raises, probe returns the most conservative budget."""

    def boom() -> Any:
        raise RuntimeError("psutil unavailable")

    monkeypatch.setattr("psutil.virtual_memory", boom)
    monkeypatch.setattr("psutil.swap_memory", lambda: _make_swap(0.0))
    monkeypatch.setattr("os.cpu_count", lambda: 4)
    monkeypatch.setattr("docline.runtime.resource_probe._import_torch", lambda: None)

    from docline.runtime.resource_probe import probe

    budget = probe()

    assert budget.recommended_docling_max_pages == 0
    assert budget.recommended_docling_max_mb == 0
    assert budget.serialize_docling is True
    assert budget.omp_thread_count == 1
