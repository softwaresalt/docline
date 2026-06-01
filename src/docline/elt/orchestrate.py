"""Config-driven multi-source fetch orchestration for the ELT pipeline."""

from pathlib import Path

from docline.elt.config import discover_configs
from docline.elt.models import GitHubRepoSource, LocalFileSource, SourceConfig, WebCrawlSource
from docline.fetch.models import StagingJob
from docline.fetch.staging import create_staging_job
from docline.paths import safe_workspace_path


def orchestrate_fetch(
    config_dir: Path, staging_dir: str, workspace_root: str | Path | None = None
) -> list[StagingJob]:
    """Create staging jobs for every configured ELT source.

    Args:
        config_dir: Directory containing ELT source configuration files.
        staging_dir: Workspace-relative staging directory root.
        workspace_root: Optional workspace root for containment checks.

    Returns:
        A staging job for each discovered source config.
    """
    root = Path.cwd() if workspace_root is None else Path(workspace_root)
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
    raise TypeError(f"Unsupported source config type: {type(config)!r}")
