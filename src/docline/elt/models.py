"""Typed source configuration models for the ELT pipeline."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from docline.elt.manifest_models import ManifestGitSource, ManifestLocalSource, ManifestUrlSource


class LocalFileSource(BaseModel):
    """Configuration for ingesting one or more local files.

    Attributes:
        type: Discriminator for the local file source kind.
        paths: Workspace-relative file paths to ingest.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["local_file"]
    paths: list[str]


class WebCrawlSource(BaseModel):
    """Configuration for ingesting content from a web crawl.

    Attributes:
        type: Discriminator for the web crawl source kind.
        url: Starting URL for the crawl.
        depth: Maximum crawl depth.
        max_pages: Optional maximum page count.
        domain_lock: Whether discovered links must stay on the start URL host.
        rate_limit_ms: Delay between page fetches in milliseconds.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["web_crawl"]
    url: str
    depth: int = 0
    max_pages: int | None = None
    domain_lock: bool = True
    rate_limit_ms: int = 0


class GitHubRepoSource(BaseModel):
    """Configuration for ingesting files from a GitHub repository.

    Attributes:
        type: Discriminator for the GitHub repository source kind.
        repo_url: Repository URL to inspect.
        path_glob: File glob to include.
        branch: Branch name to read from.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["github_repo"]
    repo_url: str
    path_glob: str = "**/*.md"
    branch: str = "main"


SourceConfig = Annotated[
    LocalFileSource
    | WebCrawlSource
    | GitHubRepoSource
    | ManifestLocalSource
    | ManifestUrlSource
    | ManifestGitSource,
    Field(discriminator="type"),
]

__all__ = [
    "GitHubRepoSource",
    "LocalFileSource",
    "ManifestGitSource",
    "ManifestLocalSource",
    "ManifestUrlSource",
    "SourceConfig",
    "WebCrawlSource",
]
