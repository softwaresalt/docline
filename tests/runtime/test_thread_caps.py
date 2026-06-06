"""Tests for probe-derived docling thread caps (018.001.004-T).

Verifies that ``_apply_docling_thread_caps`` consults the resource probe
and writes the recommended thread count into ``OMP_NUM_THREADS`` /
``MKL_NUM_THREADS`` / ``OPENBLAS_NUM_THREADS`` via ``setdefault`` so
operator-set values are respected. Also verifies ``TOKENIZERS_PARALLELISM``
is forced to ``"false"`` to silence the HuggingFace warning and avoid
spawning a second thread pool that competes with BLAS.
"""

from __future__ import annotations

from typing import Any

import pytest


def _make_budget(omp_thread_count: int) -> Any:
    """Build a minimal ResourceBudget that only varies omp_thread_count."""

    from docline.runtime.resource_probe import ResourceBudget

    return ResourceBudget(
        available_ram_gb=24.0,
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
        omp_thread_count=omp_thread_count,
    )


@pytest.fixture(autouse=True)
def _clear_thread_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip the relevant env vars so each test starts from a known state."""

    for var in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "TOKENIZERS_PARALLELISM",
    ):
        monkeypatch.delenv(var, raising=False)


def test_apply_docling_thread_caps_sets_omp_mkl_openblas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Probe-derived OMP thread count is written into all three BLAS env vars."""
    monkeypatch.setattr(
        "docline.runtime.resource_probe.probe", lambda: _make_budget(omp_thread_count=2)
    )

    from docline.readers.pdf import _apply_docling_thread_caps

    _apply_docling_thread_caps()

    import os

    assert os.environ["OMP_NUM_THREADS"] == "2"
    assert os.environ["MKL_NUM_THREADS"] == "2"
    assert os.environ["OPENBLAS_NUM_THREADS"] == "2"
    assert os.environ["TOKENIZERS_PARALLELISM"] == "false"


def test_apply_docling_thread_caps_respects_operator_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``setdefault`` semantics: operator-set values win over the probe recommendation."""

    monkeypatch.setenv("OMP_NUM_THREADS", "16")
    monkeypatch.setenv("TOKENIZERS_PARALLELISM", "true")
    monkeypatch.setattr(
        "docline.runtime.resource_probe.probe", lambda: _make_budget(omp_thread_count=2)
    )

    from docline.readers.pdf import _apply_docling_thread_caps

    _apply_docling_thread_caps()

    import os

    # Operator's OMP value preserved.
    assert os.environ["OMP_NUM_THREADS"] == "16"
    # Operator's tokenizers value preserved.
    assert os.environ["TOKENIZERS_PARALLELISM"] == "true"
    # Other vars get the probe default.
    assert os.environ["MKL_NUM_THREADS"] == "2"
    assert os.environ["OPENBLAS_NUM_THREADS"] == "2"


def test_apply_docling_thread_caps_floors_at_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """A budget with 0 threads still results in a sane value of 1."""

    monkeypatch.setattr(
        "docline.runtime.resource_probe.probe", lambda: _make_budget(omp_thread_count=0)
    )

    from docline.readers.pdf import _apply_docling_thread_caps

    _apply_docling_thread_caps()

    import os

    assert os.environ["OMP_NUM_THREADS"] == "1"


def test_apply_docling_thread_caps_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling twice in a row leaves the env vars stable."""

    monkeypatch.setattr(
        "docline.runtime.resource_probe.probe", lambda: _make_budget(omp_thread_count=4)
    )

    from docline.readers.pdf import _apply_docling_thread_caps

    _apply_docling_thread_caps()
    _apply_docling_thread_caps()

    import os

    assert os.environ["OMP_NUM_THREADS"] == "4"
