"""Tests for workspace path containment security enforcement."""

import pytest

from docline.paths import PathContainmentError, resolve_contained, safe_workspace_path
from docline.schema.models import DoclineError


def test_path_containment_error_is_docline_error() -> None:
    """PathContainmentError is a subclass of DoclineError."""
    err = PathContainmentError("escapes root")
    assert isinstance(err, DoclineError)


def test_resolve_contained_safe_nested_path(tmp_path) -> None:
    """resolve_contained accepts a path nested within the workspace root."""
    result = resolve_contained("docs/report.md", tmp_path)
    assert str(result).startswith(str(tmp_path))


def test_resolve_contained_same_dir(tmp_path) -> None:
    """resolve_contained accepts a file in the root itself."""
    result = resolve_contained("README.md", tmp_path)
    assert str(result).startswith(str(tmp_path))


def test_resolve_contained_traversal_escaping_root_raises(tmp_path) -> None:
    """resolve_contained raises PathContainmentError for .. traversal escaping root."""
    with pytest.raises(PathContainmentError):
        resolve_contained("../../etc/passwd", tmp_path)


def test_resolve_contained_absolute_path_outside_raises(tmp_path) -> None:
    """resolve_contained raises PathContainmentError for absolute paths outside root."""
    with pytest.raises(PathContainmentError):
        resolve_contained("/etc/passwd", tmp_path)


def test_safe_workspace_path_nested(tmp_path) -> None:
    """safe_workspace_path accepts a nested relative path."""
    result = safe_workspace_path("output/doc.md", tmp_path)
    assert str(result).startswith(str(tmp_path))


def test_safe_workspace_path_unix_absolute_raises(tmp_path) -> None:
    """safe_workspace_path raises PathContainmentError for Unix absolute path."""
    with pytest.raises(PathContainmentError):
        safe_workspace_path("/etc/passwd", tmp_path)


def test_safe_workspace_path_windows_absolute_raises(tmp_path) -> None:
    """safe_workspace_path raises PathContainmentError for Windows absolute path."""
    with pytest.raises(PathContainmentError):
        safe_workspace_path("C:\\Users\\alice\\secret.txt", tmp_path)


def test_safe_workspace_path_traversal_raises(tmp_path) -> None:
    """safe_workspace_path raises PathContainmentError for escaping traversal."""
    with pytest.raises(PathContainmentError):
        safe_workspace_path("../../outside.txt", tmp_path)


def test_safe_workspace_path_deep_nesting(tmp_path) -> None:
    """safe_workspace_path accepts deeply nested relative paths."""
    result = safe_workspace_path("a/b/c/d/file.txt", tmp_path)
    assert str(result).startswith(str(tmp_path))
