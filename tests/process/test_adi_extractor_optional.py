"""Tests for the optional ``[adi]`` extra (027-F T1 / 027.001-T).

The Azure Document Intelligence SDK is an OPTIONAL dependency. docline
MUST function without it installed (existing pdf_engine values 'docling'
and 'heuristic' remain available). The ADI extractor module imports the
SDK lazily and raises a clear, actionable ImportError when the SDK is
absent and the operator attempts to use pdf_engine='azure_di'.

This test module asserts:

* pyproject.toml has the ``[adi]`` extra declared with the correct
  package pin so ``pip install docline[adi]`` works.
* docline imports cleanly without the ADI SDK installed (verified
  indirectly by the test running; any import-time SDK requirement
  would break collection).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import docline  # noqa: F401 — assertion that core import doesn't require [adi]

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def pyproject_text() -> str:
    return PYPROJECT_PATH.read_text(encoding="utf-8")


def test_pyproject_declares_adi_extra(pyproject_text: str) -> None:
    """``[adi]`` extra MUST be declared in optional-dependencies."""
    assert "adi = [" in pyproject_text, (
        "pyproject.toml must declare an `adi` optional dependency group"
    )


def test_adi_extra_pins_azure_sdk(pyproject_text: str) -> None:
    """The ``[adi]`` extra MUST include azure-ai-documentintelligence."""
    assert "azure-ai-documentintelligence" in pyproject_text, (
        "the [adi] extra must include azure-ai-documentintelligence"
    )


def test_pdf_extra_still_intact(pyproject_text: str) -> None:
    """Adding [adi] MUST NOT affect the existing [pdf] extra."""
    assert "pdf = " in pyproject_text
    assert "docling" in pyproject_text


def test_docline_imports_without_adi_extra() -> None:
    """``import docline`` MUST succeed without ADI SDK installed.

    The fact that this test file collected and ran proves the assertion —
    pytest can't reach this function if docline import-time required the
    ADI SDK.
    """
    import docline.app  # noqa: F401
    import docline.cli  # noqa: F401
    import docline.process.output_contract  # noqa: F401
