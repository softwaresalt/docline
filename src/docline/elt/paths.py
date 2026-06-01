"""ELT staging area path constants and resolution utilities."""

from pathlib import Path

from docline.paths import PathContainmentError, resolve_contained, safe_workspace_path

ELT_DIR = ".elt"
ELT_CONFIG_DIR = ".elt/config"
ELT_STAGING_DIR = ".elt/staging"


def _validate_workspace_root(workspace_root: str | Path) -> Path:
    """Validate and normalize a workspace root path.

    Args:
        workspace_root: Candidate workspace root supplied by the caller.

    Returns:
        The resolved workspace root path.

    Raises:
        PathContainmentError: If the workspace root contains parent traversal.
    """
    root_path = Path(workspace_root)
    if ".." in root_path.parts:
        raise PathContainmentError(
            f"Workspace root {workspace_root!r} must not contain parent-directory traversal"
        )
    return root_path.resolve()


def get_elt_dir(workspace_root: str | Path) -> Path:
    """Return the .elt staging area root path within the workspace.

    Args:
        workspace_root: Workspace root directory.

    Returns:
        The resolved `.elt` directory path.

    Raises:
        PathContainmentError: If the workspace root or resulting path is unsafe.
    """
    return resolve_contained(ELT_DIR, _validate_workspace_root(workspace_root))


def get_elt_config_dir(workspace_root: str | Path) -> Path:
    """Return the .elt/config directory path within the workspace.

    Args:
        workspace_root: Workspace root directory.

    Returns:
        The resolved `.elt/config` directory path.

    Raises:
        PathContainmentError: If the workspace root or resulting path is unsafe.
    """
    return safe_workspace_path(ELT_CONFIG_DIR, _validate_workspace_root(workspace_root))


def get_elt_staging_dir(workspace_root: str | Path) -> Path:
    """Return the .elt/staging directory path within the workspace.

    Args:
        workspace_root: Workspace root directory.

    Returns:
        The resolved `.elt/staging` directory path.

    Raises:
        PathContainmentError: If the workspace root or resulting path is unsafe.
    """
    return safe_workspace_path(ELT_STAGING_DIR, _validate_workspace_root(workspace_root))
