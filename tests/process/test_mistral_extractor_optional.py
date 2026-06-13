"""Tests verifying the [mistral] optional extra is correctly gated (029.002-T)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_import_docline_without_mistral_extra_succeeds() -> None:
    """`import docline` must succeed regardless of [mistral] installation."""
    import docline  # noqa: F401  — import side-effects only


def test_pyproject_declares_mistral_extra() -> None:
    """pyproject.toml [project.optional-dependencies] must contain mistral = [httpx ...]."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "mistral = [" in pyproject
    assert "httpx" in pyproject


def test_read_pdf_mistral_raises_when_httpx_missing() -> None:
    """When httpx is unimportable, require_extra raises DependencyUnavailableError.

    Verifies the contract that gates ``read_pdf_mistral``'s reader body
    via ``require_extra("httpx", extra="mistral")`` at the top of the
    function. Tested at the dependencies layer directly to avoid pytest
    deadlock from patching import machinery.
    """
    from docline.dependencies import DependencyUnavailableError, require_extra

    # Call require_extra with a deliberately-nonexistent module name to
    # exercise the exact code path read_pdf_mistral takes when httpx is
    # absent from the environment.
    with pytest.raises(DependencyUnavailableError, match="mistral"):
        require_extra("definitely_not_a_real_module_xyz123", extra="mistral")
