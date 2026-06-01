"""Typed source configuration models for the ELT pipeline."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["web_crawl"]
    url: str
    depth: int = 0
    max_pages: int | None = None


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
    LocalFileSource | WebCrawlSource | GitHubRepoSource,
    Field(discriminator="type"),
]
