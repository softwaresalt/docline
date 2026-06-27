"""Tests for ``scripts/study/compare_merge_gap.py`` (036.001-T)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "study" / "compare_merge_gap.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compare_merge_gap", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _summary(
    *,
    merge_gap: int,
    wall: float,
    ranges: int,
    content: int,
    collapsed: int,
    chars: int,
    qa_disagreements: int = 0,
    qa_sampled: int = 6,
    flagged_pages: int = 1818,
) -> dict[str, Any]:
    return {
        "wall_clock_seconds": wall,
        "merge_gap": merge_gap,
        "engine_distribution": {"docling-collapsed": content + collapsed, "heuristic": 1},
        "docling_attribution": {
            "ranges": ranges,
            "content_pages": content,
            "collapsed_placeholder_pages": collapsed,
            "total_docling_chars": chars,
        },
        "metadata": {
            "qa_disagreements": qa_disagreements,
            "qa_sampled_count": qa_sampled,
            "flagged_pages_count": flagged_pages,
        },
    }


def _write(tmp_path: Path, name: str, summary: dict[str, Any]) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(summary), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _extract_row
# ---------------------------------------------------------------------------


def test_extract_row_pulls_fields() -> None:
    module = _load()
    row = module._extract_row(
        _summary(merge_gap=2, wall=4767.3, ranges=86, content=86, collapsed=2713, chars=3438001)
    )
    assert row["merge_gap"] == 2
    assert row["wall_clock_seconds"] == 4767.3
    assert row["docling_ranges"] == 86
    assert row["docling_source_pages"] == 86 + 2713
    assert row["qa_disagreements"] == 0


def test_extract_row_missing_docling_attribution_raises() -> None:
    module = _load()
    pre_038 = _summary(merge_gap=2, wall=1.0, ranges=1, content=1, collapsed=0, chars=1)
    del pre_038["docling_attribution"]
    with pytest.raises(ValueError) as exc:
        module._extract_row(pre_038)
    assert "docling_attribution" in str(exc.value)


# ---------------------------------------------------------------------------
# _verdict
# ---------------------------------------------------------------------------


def test_verdict_lower_wins_on_wallclock_without_qa_regression() -> None:
    module = _load()
    rows = [
        module._extract_row(
            _summary(merge_gap=2, wall=4767.0, ranges=86, content=86, collapsed=2713, chars=3438001)
        ),
        module._extract_row(
            _summary(
                merge_gap=0, wall=4000.0, ranges=120, content=120, collapsed=1800, chars=2_400_000
            )
        ),
    ]
    v = module._verdict(rows, win_threshold=0.05, qa_tolerance=0)
    assert v["verdict"] == "LOWER-DEFAULT"
    assert v["winner_merge_gap"] == 0


def test_verdict_keep_when_no_meaningful_wallclock_gain() -> None:
    module = _load()
    rows = [
        module._extract_row(
            _summary(merge_gap=2, wall=4767.0, ranges=86, content=86, collapsed=2713, chars=3438001)
        ),
        module._extract_row(
            _summary(
                merge_gap=0, wall=4720.0, ranges=120, content=120, collapsed=2600, chars=3_300_000
            )
        ),
    ]
    v = module._verdict(rows, win_threshold=0.05, qa_tolerance=0)
    assert v["verdict"] == "KEEP-DEFAULT"


def test_verdict_inconclusive_when_qa_regresses() -> None:
    module = _load()
    rows = [
        module._extract_row(
            _summary(
                merge_gap=2,
                wall=4767.0,
                ranges=86,
                content=86,
                collapsed=2713,
                chars=3438001,
                qa_disagreements=0,
            )
        ),
        module._extract_row(
            _summary(
                merge_gap=0,
                wall=4000.0,
                ranges=120,
                content=120,
                collapsed=1800,
                chars=2_400_000,
                qa_disagreements=3,
            )
        ),
    ]
    v = module._verdict(rows, win_threshold=0.05, qa_tolerance=0)
    # Faster but QA regressed beyond tolerance -> not a clean win.
    assert v["verdict"] in {"INCONCLUSIVE", "KEEP-DEFAULT"}
    assert v["verdict"] != "LOWER-DEFAULT"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_over_synthetic_summaries_exit_0(tmp_path: Path, capsys) -> None:
    module = _load()
    a = _write(
        tmp_path,
        "mg2.json",
        _summary(merge_gap=2, wall=4767.0, ranges=86, content=86, collapsed=2713, chars=3438001),
    )
    b = _write(
        tmp_path,
        "mg0.json",
        _summary(
            merge_gap=0, wall=4000.0, ranges=120, content=120, collapsed=1800, chars=2_400_000
        ),
    )
    exit_code = module.main(["--summaries", str(a), str(b)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "merge_gap" in out
    assert "LOWER-DEFAULT" in out


def test_main_requires_two_summaries(tmp_path: Path) -> None:
    module = _load()
    a = _write(
        tmp_path,
        "mg2.json",
        _summary(merge_gap=2, wall=1.0, ranges=1, content=1, collapsed=0, chars=1),
    )
    exit_code = module.main(["--summaries", str(a)])
    assert exit_code == 2
