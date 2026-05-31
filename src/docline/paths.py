"""Workspace path containment enforcement for the docline pipeline."""

import re
from pathlib import Path

from docline.schema.models import DoclineError

_PATH_SEPARATOR_RE = re.compile(r"[\\/]+")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:", re.ASCII)


class PathContainmentError(DoclineError):
    """Raised when a path resolves outside the workspace root."""


def validate_workspace_relative_path(relative: str | Path) -> str:
    """Validate that a path is workspace-relative and non-traversing.

    Args:
        relative: Path text supplied at a CLI, MCP, or helper boundary.

    Returns:
        The validated path text.

    Raises:
        PathContainmentError: If the path is empty, absolute, or contains ``..`` traversal.
    """
    str_path = str(relative)
    if Path(str_path) == Path("."):
        raise PathContainmentError(
            "Empty or current-directory path text is not allowed; "
            "provide a non-empty path relative to the workspace"
        )
    if str_path.startswith(("/", "\\")) or _WINDOWS_DRIVE_RE.match(str_path):
        raise PathContainmentError(
            f"Absolute path {relative!r} is not allowed; provide a path relative to the workspace"
        )
    if ".." in _PATH_SEPARATOR_RE.split(str_path):
        raise PathContainmentError(f"Path {relative!r} must not contain parent-directory traversal")
    return str_path


def _contains_workspace_symlink(candidate: Path, workspace_root: Path) -> bool:
    """Return whether a candidate path traverses a symlink under the workspace root.

    Args:
        candidate: Absolute candidate path before canonical resolution.
        workspace_root: Canonical workspace root.

    Returns:
        ``True`` when any existing path segment under ``workspace_root`` is a symlink.
    """
    try:
        relative_candidate = candidate.relative_to(workspace_root)
    except ValueError:
        return False

    current = workspace_root
    for part in relative_candidate.parts:
        current /= part
        if current.is_symlink():
            return True
    return False


def resolve_contained(path: str | Path, workspace_root: str | Path) -> Path:
    """Resolve a path and verify it is contained within the workspace root.

    Uses ``Path.resolve(strict=False)`` to compute the canonical path without
    requiring the path to exist on disk, rejects symlink traversal within the
    workspace, then checks that the resolved path is a descendant of
    ``workspace_root``.

    Args:
        path: The path to resolve. May be relative or absolute.
        workspace_root: The workspace directory that must contain ``path``.

    Returns:
        The resolved :class:`~pathlib.Path` if it is inside ``workspace_root``.

    Raises:
        PathContainmentError: If the resolved path is not under ``workspace_root``
            or the path traverses a workspace symlink.
    """
    root = Path(workspace_root).resolve()
    candidate_text = str(path)
    if Path(candidate_text) == Path("."):
        raise PathContainmentError(
            "Empty or current-directory path text is not allowed; "
            "provide a non-empty path relative to the workspace"
        )
    if candidate_text.startswith(("/", "\\")) or _WINDOWS_DRIVE_RE.match(candidate_text):
        raise PathContainmentError(
            f"Absolute path {path!r} is not allowed; provide a path relative to the workspace"
        )
    candidate = Path(path)
    unresolved = candidate if candidate.is_absolute() else root / candidate

    if _contains_workspace_symlink(unresolved, root):
        raise PathContainmentError(
            f"Path {path!r} traverses a symlink under workspace root {root!r}"
        )

    resolved = unresolved.resolve(strict=False)

    if not resolved.is_relative_to(root):
        raise PathContainmentError(
            f"Path {path!r} resolves to {resolved!r} which is outside workspace root {root!r}"
        )
    return resolved


def safe_workspace_path(relative: str | Path, workspace_root: str | Path) -> Path:
    """Validate a relative path and resolve it within the workspace root.

    Rejects paths that are absolute (Unix ``/`` prefix or Windows drive letter
    ``C:``) before calling :func:`resolve_contained`.

    Args:
        relative: A path that must be relative. Must not be an absolute path.
        workspace_root: The workspace directory that must contain ``relative``.

    Returns:
        The resolved :class:`~pathlib.Path` within ``workspace_root``.

    Raises:
        PathContainmentError: If ``relative`` is absolute or escapes the root.
    """
    validated = validate_workspace_relative_path(relative)
    return resolve_contained(validated, workspace_root)
