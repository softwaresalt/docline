"""Tests for ``scripts/study/ocr_memory_calibration.py`` (040.002-T)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "study" / "ocr_memory_calibration.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ocr_memory_calibration", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve the module for annotations.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(mod: ModuleType, mpx: float, scale: float, pages: int, base: float, k: float):
    """A synthetic OK measurement lying exactly on peak = base + k * (mpx*scale^2*pages)."""
    peak = base + k * mpx * scale * scale * pages
    return mod.Measurement(
        page_class="synthetic",
        page_megapixels=mpx,
        scale=scale,
        pages_per_group=pages,
        peak_rss_mb=peak,
        outcome="ok",
    )


def test_fit_cost_model_recovers_coefficients() -> None:
    mod = _load()
    base, k = 100.0, 5.0
    rows = [
        _row(mod, 1.0, 1.0, 1, base, k),
        _row(mod, 2.0, 1.0, 1, base, k),
        _row(mod, 1.0, 2.0, 1, base, k),
        _row(mod, 1.0, 1.0, 3, base, k),
        _row(mod, 3.0, 1.5, 2, base, k),
    ]
    model = mod.fit_cost_model(rows)
    assert model.base_mb == pytest.approx(base, abs=1e-6)
    assert model.k_mb_per_mpx == pytest.approx(k, abs=1e-6)


def test_fit_ignores_oom_rows() -> None:
    mod = _load()
    base, k = 50.0, 3.0
    rows = [
        _row(mod, 1.0, 1.0, 1, base, k),
        _row(mod, 2.0, 1.0, 1, base, k),
        _row(mod, 4.0, 1.0, 1, base, k),
        # An OOM row has no valid peak; it must not skew the fit.
        mod.Measurement("big", 100.0, 1.0, 1, peak_rss_mb=0.0, outcome="oom"),
    ]
    model = mod.fit_cost_model(rows)
    assert model.base_mb == pytest.approx(base, abs=1e-6)
    assert model.k_mb_per_mpx == pytest.approx(k, abs=1e-6)


def test_fit_requires_two_points() -> None:
    mod = _load()
    with pytest.raises(ValueError):
        mod.fit_cost_model([_row(mod, 1.0, 1.0, 1, 10.0, 1.0)])


def test_cost_model_predict() -> None:
    mod = _load()
    model = mod.CostModel(base_mb=100.0, k_mb_per_mpx=5.0)
    # 100 + 5 * (2 * 1^2 * 3) = 100 + 30 = 130
    assert model.predict(page_megapixels=2.0, scale=1.0, pages_per_group=3) == pytest.approx(130.0)


def test_recommend_max_pages_per_group() -> None:
    mod = _load()
    model = mod.CostModel(base_mb=100.0, k_mb_per_mpx=5.0)
    # budget = 1000 * 0.8 = 800; usable = 700; marginal = 5*2*1 = 10 -> 70 pages.
    cap = mod.recommend_max_pages(
        model, available_mb=1000.0, safe_fraction=0.8, page_megapixels=2.0, scale=1.0
    )
    assert cap == 70


def test_recommend_max_pages_never_below_one() -> None:
    mod = _load()
    model = mod.CostModel(base_mb=100.0, k_mb_per_mpx=5.0)
    # Tiny budget where even base overhead does not fit -> still 1 (downscale later).
    cap = mod.recommend_max_pages(
        model, available_mb=50.0, safe_fraction=0.8, page_megapixels=10.0, scale=2.0
    )
    assert cap == 1


def test_recommend_scale_schedule_descending_fit() -> None:
    mod = _load()
    model = mod.CostModel(base_mb=100.0, k_mb_per_mpx=5.0)
    # budget = 300*0.8 = 240; predict(10, s, 1) = 100 + 50*s^2.
    # s=2 -> 300 (no), s=1 -> 150 (yes), s=0.5 -> 112.5 (yes).
    schedule = mod.recommend_scale_schedule(
        model,
        available_mb=300.0,
        safe_fraction=0.8,
        page_megapixels=10.0,
        candidate_scales=(2.0, 1.0, 0.5),
    )
    assert schedule == (1.0, 0.5)


def test_measurements_tsv_round_trip(tmp_path: Path) -> None:
    mod = _load()
    rows = [
        _row(mod, 1.0, 1.0, 1, 100.0, 5.0),
        mod.Measurement("scan", 12.0, 2.0, 4, peak_rss_mb=0.0, outcome="oom"),
    ]
    tsv = tmp_path / "measurements.tsv"
    mod.write_measurements_tsv(rows, tsv)
    parsed = mod.parse_measurements_tsv(tsv.read_text(encoding="utf-8"))
    assert parsed == rows


def test_main_analyze_emits_model_and_recommendation(tmp_path: Path, capsys) -> None:
    mod = _load()
    rows = [
        _row(mod, 1.0, 1.0, 1, 100.0, 5.0),
        _row(mod, 2.0, 1.0, 1, 100.0, 5.0),
        _row(mod, 1.0, 2.0, 1, 100.0, 5.0),
        _row(mod, 4.0, 1.0, 2, 100.0, 5.0),
    ]
    tsv = tmp_path / "measurements.tsv"
    mod.write_measurements_tsv(rows, tsv)

    exit_code = mod.main(
        [
            "--analyze",
            str(tsv),
            "--available-mb",
            "1000",
            "--page-megapixels",
            "2.0",
            "--safe-fraction",
            "0.8",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "base_mb" in out
    assert "k_mb_per_mpx" in out
    assert "max_pages_per_group" in out


def test_main_analyze_missing_file_returns_2(tmp_path: Path, capsys) -> None:
    mod = _load()
    exit_code = mod.main(["--analyze", str(tmp_path / "nope.tsv"), "--available-mb", "1000"])
    assert exit_code == 2


class _FakeMemInfo:
    def __init__(self, rss: int) -> None:
        self.rss = rss


class _FakeProc:
    """A minimal psutil.Process stand-in for :func:`_tree_rss_mb` tests."""

    def __init__(self, rss: int, descendants=()):
        self._rss = rss
        self._descendants = list(descendants)

    def memory_info(self) -> _FakeMemInfo:
        return _FakeMemInfo(self._rss)

    def children(self, recursive: bool = False):
        # psutil returns the flattened descendant list when recursive=True.
        return list(self._descendants)


def test_tree_rss_mb_sums_process_tree() -> None:
    mod = _load()
    # Direct process is a tiny redirector shim (4 MB); the real docling work
    # lives in a child (1000 MB) alongside a grandchild (250 MB). psutil's
    # children(recursive=True) returns them flattened.
    grandchild = _FakeProc(250_000_000)
    child = _FakeProc(1_000_000_000)
    root = _FakeProc(4_000_000, descendants=[child, grandchild])
    assert mod._tree_rss_mb(root) == pytest.approx(1254.0)


def test_tree_rss_mb_no_children_is_direct_rss() -> None:
    mod = _load()
    root = _FakeProc(512_000_000)
    assert mod._tree_rss_mb(root) == pytest.approx(512.0)
