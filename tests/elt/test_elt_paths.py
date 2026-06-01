"""Tests for ELT workspace path helpers."""

from pathlib import Path

import pytest

from docline.paths import PathContainmentError


def test_get_elt_dir_returns_workspace_local_path(tmp_path: Path) -> None:
    """get_elt_dir returns the workspace-local ELT root."""
    from docline.elt.paths import get_elt_dir

    result = get_elt_dir(tmp_path)

    assert result == tmp_path / ".elt"
    assert result.is_relative_to(tmp_path)


def test_get_elt_config_dir_returns_workspace_local_path(tmp_path: Path) -> None:
    """get_elt_config_dir returns the workspace-local config directory."""
    from docline.elt.paths import get_elt_config_dir

    result = get_elt_config_dir(tmp_path)

    assert result == tmp_path / ".elt" / "config"
    assert result.is_relative_to(tmp_path)


def test_get_elt_staging_dir_returns_workspace_local_path(tmp_path: Path) -> None:
    """get_elt_staging_dir returns the workspace-local staging directory."""
    from docline.elt.paths import get_elt_staging_dir

    result = get_elt_staging_dir(tmp_path)

    assert result == tmp_path / ".elt" / "staging"
    assert result.is_relative_to(tmp_path)


def test_get_elt_paths_reject_workspace_root_with_parent_traversal(tmp_path: Path) -> None:
    """ELT helpers reject workspace roots containing parent-directory traversal."""
    from docline.elt.paths import get_elt_dir

    with pytest.raises(PathContainmentError):
        get_elt_dir(tmp_path / "..")


def test_gitignore_includes_elt_entry() -> None:
    """Repository gitignore lists the local ELT staging directory."""
    gitignore = Path(__file__).resolve().parents[2] / ".gitignore"

    assert ".elt/" in gitignore.read_text(encoding="utf-8").splitlines()
