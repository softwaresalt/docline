"""Deterministic source-key builders for ELT staging jobs."""

from docline.elt.manifest_models import ManifestGitSource, ManifestLocalSource, ManifestUrlSource
from docline.elt.models import GitHubRepoSource, LocalFileSource, SourceConfig, WebCrawlSource


def build_source_key(config: SourceConfig) -> str:
    """Derive a deterministic staging key for a typed source config.

    Args:
        config: Typed source configuration.

    Returns:
        Deterministic source text for job ID generation and metadata.
    """
    if isinstance(config, LocalFileSource):
        return f"local_file:{','.join(sorted(config.paths))}"
    if isinstance(config, WebCrawlSource):
        return _build_crawl_source_key(
            "web_crawl",
            config.url,
            max_depth=config.depth,
            max_pages=config.max_pages,
            domain_lock=config.domain_lock,
            rate_limit_ms=config.rate_limit_ms,
        )
    if isinstance(config, GitHubRepoSource):
        return f"github_repo:{config.repo_url}@{config.branch}:{config.path_glob}"
    if isinstance(config, ManifestLocalSource):
        includes = ",".join(sorted(config.include))
        return f"manifest_local:{config.id}:{config.path}:{includes}"
    if isinstance(config, ManifestUrlSource):
        return _build_crawl_source_key(
            f"manifest_url:{config.id}",
            config.url,
            max_depth=config.max_depth,
            max_pages=config.max_pages,
            domain_lock=config.domain_lock,
            rate_limit_ms=config.rate_limit_ms,
        )
    if isinstance(config, ManifestGitSource):
        return f"manifest_git:{config.id}:{config.url}@{config.branch}"
    raise TypeError(f"Unsupported source config type: {type(config)!r}")


def _build_crawl_source_key(
    prefix: str,
    url: str,
    *,
    max_depth: int,
    max_pages: int | None,
    domain_lock: bool,
    rate_limit_ms: int,
) -> str:
    """Build a canonical crawl-source key."""
    parts = [prefix, url, *_crawl_option_parts(max_depth, max_pages, domain_lock, rate_limit_ms)]
    return ":".join(parts)


def _crawl_option_parts(
    max_depth: int,
    max_pages: int | None,
    domain_lock: bool,
    rate_limit_ms: int,
) -> list[str]:
    """Return canonical crawl-option suffixes for non-default values."""
    parts: list[str] = []
    if max_depth != 0:
        parts.append(f"depth={max_depth}")
    if max_pages is not None:
        parts.append(f"max_pages={max_pages}")
    if not domain_lock:
        parts.append(f"domain_lock={str(domain_lock).lower()}")
    if rate_limit_ms != 0:
        parts.append(f"rate_limit_ms={rate_limit_ms}")
    return parts


__all__ = ["build_source_key"]
