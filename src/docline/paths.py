"""Workspace path containment enforcement for the docline pipeline."""

import re
from pathlib import Path

from docline.schema.models import DoclineError

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:", re.ASCII)


class PathContainmentError(DoclineError):
    """Raised when a path resolves outside the workspace root."""


def resolve_contained(path: str | Path, workspace_root: str | Path) -> Path:
    """Resolve a path and verify it is contained within the workspace root.

    Uses ``Path.resolve(strict=False)`` to compute the canonical path without
    requiring the path to exist on disk, then checks that the resolved path is
    a descendant of ``workspace_root``.

    Args:
        path: The path to resolve. May be relative or absolute.
        workspace_root: The workspace directory that must contain ``path``.

    Returns:
        The resolved :class:`~pathlib.Path` if it is inside ``workspace_root``.

    Raises:
        PathContainmentError: If the resolved path is not under ``workspace_root``.
    """
    root = Path(workspace_root).resolve()
    resolved = (root / path).resolve()

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
    str_path = str(relative)
    if str_path.startswith("/") or _WINDOWS_DRIVE_RE.match(str_path):
        raise PathContainmentError(
            f"Absolute path {relative!r} is not allowed; provide a path relative to the workspace"
        )
    return resolve_contained(relative, workspace_root)
