"""Tests for new flags in ``scripts/pa3_triage_cosmos.py`` (task 020.005-T / U5)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pypdf

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "pa3_triage_cosmos.py"


def _load_script_module() -> ModuleType:
    """Import ``scripts/pa3_triage_cosmos.py`` as a module for in-process tests."""
    spec = importlib.util.spec_from_file_location("pa3_triage_cosmos", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_blank_pdf(path: Path, page_count: int = 1) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def test_script_help_includes_baseline_engine_flag() -> None:
    """`scripts/pa3_triage_cosmos.py --help` MUST list `--baseline-engine`."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--baseline-engine" in result.stdout, (
        f"--baseline-engine not in --help output; got:\n{result.stdout}"
    )


def test_script_help_lists_markitdown_as_default_baseline() -> None:
    """`--help` MUST document markitdown as the default baseline engine."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    # The help text should say markitdown is the default for --baseline-engine.
    lowered = result.stdout.lower()
    assert "markitdown" in lowered, (
        f"--help must mention markitdown as the default baseline; got:\n{result.stdout}"
    )


def test_script_help_includes_similarity_threshold_flag() -> None:
    """`--help` MUST surface the new Jaccard similarity threshold control."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--similarity-threshold" in result.stdout, (
        f"--similarity-threshold not in --help output; got:\n{result.stdout}"
    )


def test_script_help_includes_use_batched_worker_flag() -> None:
    """`--help` MUST surface the new --use-batched-worker control (037-S)."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--use-batched-worker" in result.stdout, (
        f"--use-batched-worker not in --help output; got:\n{result.stdout}"
    )


def test_use_batched_worker_flag_forwarded_to_process(tmp_path: Path) -> None:
    """The --use-batched-worker flag must reach ``process_pdf_triaged``."""
    module = _load_script_module()
    pdf = _make_blank_pdf(tmp_path / "doc.pdf")

    captured: dict[str, Any] = {}

    def fake_process(path: Path, **kwargs: Any) -> Any:
        captured.update(kwargs)
        from docline.process.pdf_triage import TriageResult

        return TriageResult(
            source=path,
            pages=("",),
            engine_per_page=("heuristic",),
            flagged_ranges=(),
            metadata={},
        )

    module.process_pdf_triaged = fake_process  # type: ignore[attr-defined]

    exit_code = module.main(
        [
            "--pdf",
            str(pdf),
            "--output-dir",
            str(tmp_path / "out"),
            "--log-path",
            str(tmp_path / "run.log"),
            "--use-batched-worker",
        ]
    )

    assert exit_code == 0
    assert captured.get("use_batched_worker") is True


def test_omitting_flag_uses_library_default(tmp_path: Path) -> None:
    """Omitting the flag must NOT force a value — the library default applies."""
    module = _load_script_module()
    pdf = _make_blank_pdf(tmp_path / "doc.pdf")

    captured: dict[str, Any] = {}

    def fake_process(path: Path, **kwargs: Any) -> Any:
        captured.update(kwargs)
        from docline.process.pdf_triage import TriageResult

        return TriageResult(
            source=path,
            pages=("",),
            engine_per_page=("heuristic",),
            flagged_ranges=(),
            metadata={},
        )

    module.process_pdf_triaged = fake_process  # type: ignore[attr-defined]

    exit_code = module.main(
        [
            "--pdf",
            str(pdf),
            "--output-dir",
            str(tmp_path / "out"),
            "--log-path",
            str(tmp_path / "run.log"),
        ]
    )

    assert exit_code == 0
    # No explicit flag -> the script must not pass use_batched_worker at all,
    # so the library default (batched since 037-S) governs.
    assert "use_batched_worker" not in captured


def test_no_use_batched_worker_forces_per_chunk(tmp_path: Path) -> None:
    """`--no-use-batched-worker` must forward ``use_batched_worker=False``."""
    module = _load_script_module()
    pdf = _make_blank_pdf(tmp_path / "doc.pdf")

    captured: dict[str, Any] = {}

    def fake_process(path: Path, **kwargs: Any) -> Any:
        captured.update(kwargs)
        from docline.process.pdf_triage import TriageResult

        return TriageResult(
            source=path,
            pages=("",),
            engine_per_page=("heuristic",),
            flagged_ranges=(),
            metadata={},
        )

    module.process_pdf_triaged = fake_process  # type: ignore[attr-defined]

    exit_code = module.main(
        [
            "--pdf",
            str(pdf),
            "--output-dir",
            str(tmp_path / "out"),
            "--log-path",
            str(tmp_path / "run.log"),
            "--no-use-batched-worker",
        ]
    )

    assert exit_code == 0
    assert captured.get("use_batched_worker") is False
