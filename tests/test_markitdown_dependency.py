"""Tests for markitdown[pdf] dependency declaration (task 020.001-T / U4)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _project_dependencies() -> list[str]:
    """Load the project.dependencies array from pyproject.toml."""
    raw = _PYPROJECT.read_text(encoding="utf-8")
    data = tomllib.loads(raw)
    return list(data.get("project", {}).get("dependencies", []))


def test_markitdown_pdf_listed_in_project_dependencies() -> None:
    """`markitdown[pdf]` MUST appear in project.dependencies."""
    deps = _project_dependencies()
    assert any("markitdown" in d for d in deps), (
        f"markitdown not found in project.dependencies; got: {deps}"
    )


def test_markitdown_pdf_pin_includes_pdf_extras_and_minor_range() -> None:
    """The markitdown pin MUST include [pdf] extras and a tight minor-version range.

    Per plan-review P3#6: pin >=0.1.6,<0.2 to insulate against backend swaps
    in future markitdown versions (e.g., pdfminer.six → Marker LLM).
    """
    deps = _project_dependencies()
    markitdown_entries = [d for d in deps if "markitdown" in d]
    assert markitdown_entries, "markitdown not found in deps"
    entry = markitdown_entries[0]
    assert "[pdf]" in entry, f"markitdown entry must include [pdf] extras; got: {entry!r}"
    # Tight minor-version cap: <0.2 (or equivalent like ~=0.1.6)
    assert re.search(r"<\s*0\.2", entry) or "~=" in entry, (
        f"markitdown entry must pin a minor-version cap (<0.2 or ~=0.1.x); got: {entry!r}"
    )
    # Lower bound at or above 0.1.6 (the bench-tested version)
    assert re.search(r">=\s*0\.1\.[6-9]|>=\s*0\.[2-9]|~=\s*0\.1\.[6-9]", entry), (
        f"markitdown entry must require >=0.1.6 or compatible; got: {entry!r}"
    )
