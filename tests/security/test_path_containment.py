"""Tests for workspace path containment security enforcement."""

import pytest

from docline.paths import (
    PathContainmentError,
    resolve_contained,
    safe_workspace_path,
    validate_workspace_relative_path,
)
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


def test_resolve_contained_internal_parent_segment_raises(tmp_path) -> None:
    """resolve_contained rejects internal .. segments even when the final path stays inside root."""
    with pytest.raises(PathContainmentError):
        resolve_contained("docs/../secret.md", tmp_path)


def test_resolve_contained_absolute_path_outside_raises(tmp_path) -> None:
    """resolve_contained raises PathContainmentError for absolute paths outside root."""
    with pytest.raises(PathContainmentError):
        resolve_contained("/etc/passwd", tmp_path)


def test_resolve_contained_windows_absolute_raises(tmp_path) -> None:
    """resolve_contained rejects Windows drive-letter absolute paths."""
    with pytest.raises(PathContainmentError, match="Absolute path"):
        resolve_contained("C:\\Users\\alice\\secret.txt", tmp_path)


def test_resolve_contained_windows_rooted_raises(tmp_path) -> None:
    """resolve_contained rejects rooted Windows paths for direct callers."""
    with pytest.raises(PathContainmentError, match="Absolute path"):
        resolve_contained("\\Windows\\system32\\config", tmp_path)


def test_resolve_contained_unc_raises(tmp_path) -> None:
    """resolve_contained rejects UNC paths for direct callers."""
    with pytest.raises(PathContainmentError, match="Absolute path"):
        resolve_contained("\\\\server\\share\\secret.txt", tmp_path)


def test_resolve_contained_empty_string_raises(tmp_path) -> None:
    """resolve_contained rejects an empty string instead of returning the workspace root."""
    with pytest.raises(PathContainmentError, match="[Ee]mpty"):
        resolve_contained("", tmp_path)


def test_resolve_contained_dot_path_raises(tmp_path) -> None:
    """resolve_contained rejects dot paths instead of resolving them to the workspace root."""
    with pytest.raises(PathContainmentError, match="[Ee]mpty"):
        resolve_contained(".", tmp_path)


def test_resolve_contained_dot_slash_path_raises(tmp_path) -> None:
    """resolve_contained rejects dot-slash paths instead of resolving them to the workspace root."""
    with pytest.raises(PathContainmentError, match="[Ee]mpty"):
        resolve_contained("./", tmp_path)


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


def test_safe_workspace_path_windows_rooted_raises(tmp_path) -> None:
    """safe_workspace_path raises PathContainmentError for rooted Windows paths."""
    with pytest.raises(PathContainmentError, match="Absolute path"):
        safe_workspace_path("\\Windows\\system32\\config", tmp_path)


def test_safe_workspace_path_unc_raises(tmp_path) -> None:
    """safe_workspace_path raises PathContainmentError for UNC paths."""
    with pytest.raises(PathContainmentError, match="Absolute path"):
        safe_workspace_path("\\\\server\\share\\secret.txt", tmp_path)


def test_safe_workspace_path_traversal_raises(tmp_path) -> None:
    """safe_workspace_path raises PathContainmentError for escaping traversal."""
    with pytest.raises(PathContainmentError):
        safe_workspace_path("../../outside.txt", tmp_path)


def test_safe_workspace_path_deep_nesting(tmp_path) -> None:
    """safe_workspace_path accepts deeply nested relative paths."""
    result = safe_workspace_path("a/b/c/d/file.txt", tmp_path)
    assert str(result).startswith(str(tmp_path))


def test_resolve_contained_sibling_prefix_bypass(tmp_path) -> None:
    """resolve_contained raises PathContainmentError for sibling paths sharing a prefix.

    Regression: startswith("root") incorrectly accepted "root2/secret.txt"
    because "root2" starts with "root".
    """
    root = tmp_path / "root"
    # ../root2/secret.txt resolves to tmp_path/root2/secret.txt, which is
    # outside root but shares its string prefix.
    with pytest.raises(PathContainmentError):
        resolve_contained("../root2/secret.txt", root)


def test_resolve_contained_rejects_symlink_within_workspace(tmp_path) -> None:
    """resolve_contained rejects paths that traverse a workspace symlink."""
    target_dir = tmp_path / "real"
    target_dir.mkdir()
    symlink_dir = tmp_path / "linked"

    try:
        symlink_dir.symlink_to(target_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(PathContainmentError, match="symlink"):
        resolve_contained("linked/report.md", tmp_path)


# ---------------------------------------------------------------------------
# Regression: empty path text must not resolve to workspace root (Copilot blocker)
# ---------------------------------------------------------------------------


def test_validate_workspace_relative_path_empty_string_raises() -> None:
    """validate_workspace_relative_path rejects an empty string.

    Regression: an empty string passed through without a guard would resolve to
    the workspace root via ``root / ""``, allowing callers to treat the root
    itself as a valid artifact path and produce escaped cache paths.
    """
    with pytest.raises(PathContainmentError, match="[Ee]mpty"):
        validate_workspace_relative_path("")


def test_validate_workspace_relative_path_empty_path_raises() -> None:
    """validate_workspace_relative_path rejects a Path constructed from an empty string.

    In Python, ``Path("")`` is canonicalised to ``"."`` (current directory) by
    ``str()``.  ``"."`` resolves to the workspace root under
    ``root / "."`` == ``root``, so it carries the same vulnerability as a bare
    empty string and must be rejected with the same guard.
    """
    from pathlib import Path

    with pytest.raises(PathContainmentError, match="[Ee]mpty"):
        validate_workspace_relative_path(Path(""))


def test_validate_workspace_relative_path_dot_slash_raises() -> None:
    """validate_workspace_relative_path rejects dot-slash root aliases."""
    with pytest.raises(PathContainmentError, match="[Ee]mpty"):
        validate_workspace_relative_path("./")


def test_safe_workspace_path_empty_string_raises(tmp_path) -> None:
    """safe_workspace_path rejects an empty string end-to-end.

    Regression: ``safe_workspace_path("", root)`` must not silently return the
    workspace root and allow downstream code to build cache paths from it.
    """
    with pytest.raises(PathContainmentError, match="[Ee]mpty"):
        safe_workspace_path("", tmp_path)
