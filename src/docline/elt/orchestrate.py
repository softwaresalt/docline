"""Config-driven multi-source fetch orchestration for the ELT pipeline."""

from pathlib import Path

from docline.elt.config import discover_configs
from docline.elt.source_keys import build_source_key
from docline.fetch.models import StagingJob
from docline.fetch.staging import create_staging_job
from docline.paths import PathContainmentError, safe_workspace_path


def orchestrate_fetch(
    config_dir: Path, staging_dir: str, workspace_root: str | Path | None = None
) -> list[StagingJob]:
    """Create staging jobs for every configured ELT source.

    Both ``config_dir`` and ``staging_dir`` are validated against
    ``workspace_root`` to enforce workspace containment.

    Args:
        config_dir: Directory containing ELT source configuration files.
            Must resolve within ``workspace_root`` when provided.
        staging_dir: Workspace-relative staging directory root.
        workspace_root: Optional workspace root for containment checks.
            Defaults to the current working directory.

    Returns:
        A staging job for each discovered source config.

    Raises:
        PathContainmentError: If ``config_dir`` or ``staging_dir`` resolves
            outside ``workspace_root``.
    """
    root = Path.cwd() if workspace_root is None else Path(workspace_root)
    root_resolved = root.resolve()

    config_dir_resolved = Path(config_dir).resolve()
    if not config_dir_resolved.is_relative_to(root_resolved):
        raise PathContainmentError(
            f"config_dir {config_dir!r} resolves to {config_dir_resolved!r} "
            f"which is outside workspace root {root_resolved!r}"
        )

    safe_workspace_path(staging_dir, root)

    configs = discover_configs(config_dir)
    return [create_staging_job(build_source_key(config), staging_dir) for config in configs]
