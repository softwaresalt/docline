"""Pydantic models for the graphtor-docs manifest source shape.

These models represent the ``type: local|url|git`` source entries that appear
in ``.sources.yaml`` files using the graphtor-docs manifest format (a top-level
``sources:`` list rather than a single flat ``type:`` mapping).

All models use ``extra="ignore"`` to tolerate pipeline-specific fields such as
``database``, ``domain_lock``, and ``rate_limit_ms`` that are irrelevant to
the docline fetch/process pipeline.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ManifestLocalSource(BaseModel):
    """Configuration for a local-file source in graphtor-docs manifest format.

    Attributes:
        type: Discriminator literal ``"local"``.
        id: Unique source identifier within the manifest.
        path: Workspace-relative (or stale-path) base directory.
        include: Glob patterns for files to include.  Defaults to ``["**/*"]``.
        formats: Optional list of format hints (e.g. ``["pdf"]``).  Informational
            only; unused by the fetch pipeline.
    """

    model_config = ConfigDict(extra="ignore")

    type: Literal["local"]
    id: str
    path: str
    include: list[str] = ["**/*"]
    formats: list[str] = []


class ManifestUrlSource(BaseModel):
    """Configuration for a web-crawl source in graphtor-docs manifest format.

    Attributes:
        type: Discriminator literal ``"url"``.
        id: Unique source identifier within the manifest.
        url: Starting URL for the crawl.
        max_depth: Maximum crawl depth.  Defaults to ``0`` (single page).
        max_pages: Optional maximum page count.
        domain_lock: Whether discovered links must stay on the start URL host.
        rate_limit_ms: Delay between page fetches in milliseconds.
        formats: Optional list of format hints.  Informational only.
    """

    model_config = ConfigDict(extra="ignore")

    type: Literal["url"]
    id: str
    url: str
    max_depth: int = 0
    max_pages: int | None = None
    domain_lock: bool = True
    rate_limit_ms: int = 0
    formats: list[str] = []


class ManifestGitSource(BaseModel):
    """Configuration for a Git-repository source in graphtor-docs manifest format.

    Attributes:
        type: Discriminator literal ``"git"``.
        id: Unique source identifier within the manifest.
        url: Repository URL (may include a ``.git`` suffix).
        branch: Branch to read from.  Defaults to ``"main"``.
        include: Glob patterns for files to include.  Defaults to ``["**/*"]``.
        formats: Optional list of format hints.  Informational only.
    """

    model_config = ConfigDict(extra="ignore")

    type: Literal["git"]
    id: str
    url: str
    branch: str = "main"
    include: list[str] = ["**/*"]
    formats: list[str] = []


__all__ = [
    "ManifestGitSource",
    "ManifestLocalSource",
    "ManifestUrlSource",
]
