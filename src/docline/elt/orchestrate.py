"""Config-driven multi-source fetch orchestration for the ELT pipeline."""

from pathlib import Path

from docline.elt.config import discover_configs
from docline.elt.manifest_models import ManifestGitSource, ManifestLocalSource, ManifestUrlSource
from docline.elt.models import GitHubRepoSource, LocalFileSource, SourceConfig, WebCrawlSource
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
    return [create_staging_job(_source_to_job_key(config), staging_dir) for config in configs]


def _source_to_job_key(config: SourceConfig) -> str:
    """Derive a deterministic staging key for a typed source config.

    All behavior-affecting fields are included so that two configs that
    differ only in crawl depth, max pages, or path glob produce distinct
    job IDs and cache paths.

    Args:
        config: Typed source configuration.

    Returns:
        Deterministic source text for job ID generation and metadata.
    """
    if isinstance(config, LocalFileSource):
        return f"local_file:{','.join(sorted(config.paths))}"
    if isinstance(config, WebCrawlSource):
        parts = [config.url]
        if config.depth != 0:
            parts.append(f"depth={config.depth}")
        if config.max_pages is not None:
            parts.append(f"max_pages={config.max_pages}")
        return f"web_crawl:{':'.join(parts)}"
    if isinstance(config, GitHubRepoSource):
        return f"github_repo:{config.repo_url}@{config.branch}:{config.path_glob}"
    if isinstance(config, ManifestLocalSource):
        includes = ",".join(sorted(config.include))
        return f"manifest_local:{config.id}:{config.path}:{includes}"
    if isinstance(config, ManifestUrlSource):
        return f"manifest_url:{config.id}:{config.url}"
    if isinstance(config, ManifestGitSource):
        return f"manifest_git:{config.id}:{config.url}@{config.branch}"
    raise TypeError(f"Unsupported source config type: {type(config)!r}")
