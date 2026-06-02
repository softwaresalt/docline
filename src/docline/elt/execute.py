"""Real ELT fetch execution — copies local files and fetches remote sources.

This module provides :func:`execute_elt_fetch`, which discovers ELT source
configs and actually fetches content into the staging area (unlike
:func:`~docline.elt.orchestrate.orchestrate_fetch` which only plans jobs).

Staging layout
--------------
Each source produces a staging job under::

    {staging_dir}/{job_id[:2]}/{job_id}/
        metadata.json    # StagingJob JSON; complete=true on success
        files/
            {content files}

Stale-path compatibility heuristic
------------------------------------
Sample manifests use ``path: tmp`` or ``path: tmp/pbi``, but actual workspace
files live under ``.elt/`` or ``.elt/pbi/``.  The heuristic applies **only**
when:

1. The path starts with ``"tmp"`` **and**
2. ``workspace_root/tmp`` does **not** exist **and**
3. The ``.elt/``-relative candidate exists.

This is intentionally narrow to avoid silently remapping legitimate ``tmp``
directories in other workspaces.

Generated-artifact exclusion
------------------------------
When the stale-path heuristic resolves a ``path: tmp`` source to ``.elt/``,
prior pipeline runs will have created ``runtime-staging*`` and
``runtime-output*`` subdirectories inside ``.elt/``.  Those subtrees contain
pipeline-generated staging artifacts and processed markdown — not source
documents.  The :func:`_is_elt_generated_artifact` helper and its call site
in :func:`_fetch_manifest_local` ensure these paths are skipped during the
local glob scan so that re-runs do not re-ingest their own prior output.
"""

import asyncio
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from docline.elt.config import discover_configs
from docline.elt.manifest_models import ManifestGitSource, ManifestLocalSource, ManifestUrlSource
from docline.elt.models import GitHubRepoSource, LocalFileSource, SourceConfig, WebCrawlSource
from docline.fetch.crawl import CrawlConfig
from docline.fetch.models import SourceMetadata, StagingJob
from docline.fetch.staging import build_cache_path, make_job_id, sanitize_source
from docline.paths import PathContainmentError, safe_workspace_path
from docline.readers.github import fetch_github_files

# ---------------------------------------------------------------------------
# Compatibility: generated-artifact exclusion for .elt fallback root
# ---------------------------------------------------------------------------
# When the stale-path heuristic remaps "path: tmp" → ".elt/", prior pipeline
# runs create runtime-staging* and runtime-output* subdirectories inside .elt/.
# These are tool-generated outputs (staged files, processed markdown) and must
# not be re-ingested as source documents on subsequent runs.
_ELT_GENERATED_DIR_PREFIXES: tuple[str, ...] = ("runtime-staging", "runtime-output")
_STAGED_WEB_METADATA_SUFFIX = ".meta.json"
_CRAWL_MANIFEST_NAME = "crawl-manifest.json"


def _is_elt_generated_artifact(src: Path, base: Path) -> bool:
    """Return True when *src* lives inside a generated ELT artifact subtree.

    Compatibility shim for sample manifests that resolve ``path: tmp`` to
    ``.elt/`` via the stale-path heuristic.  Files whose first component
    relative to *base* starts with a generated-artifact prefix
    (``runtime-staging*``, ``runtime-output*``) are pipeline outputs and
    should not be re-ingested as source documents.

    Args:
        src: Absolute (or workspace-relative) path being evaluated.
        base: Resolved base directory used for the local glob.

    Returns:
        ``True`` when the first path component relative to *base* matches a
        known generated-artifact prefix; ``False`` otherwise (including when
        *src* is not inside *base*).
    """
    try:
        rel = src.relative_to(base)
    except ValueError:
        return False
    if rel.parts:
        return any(rel.parts[0].startswith(prefix) for prefix in _ELT_GENERATED_DIR_PREFIXES)
    return False


def execute_elt_fetch(
    config_dir: Path | str,
    staging_dir: str,
    workspace_root: Path | str | None = None,
) -> list[StagingJob]:
    """Fetch all configured ELT sources into the staging area.

    Discovers source configs in ``config_dir``, fetches content for each one,
    and writes staged files under ``staging_dir``.  Every job gets a
    ``metadata.json`` file with ``complete=true`` on success or
    ``complete=false`` if fetching fails.

    Args:
        config_dir: Directory containing ELT source configuration files.
        staging_dir: Workspace-relative staging root (e.g. ``".elt/staging"``).
        workspace_root: Workspace root for resolving relative paths.  Defaults
            to the current working directory when ``None``.

    Returns:
        A list of :class:`~docline.fetch.models.StagingJob` records, one per
        discovered source config.

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

    safe_workspace_path(staging_dir, root_resolved)

    configs = discover_configs(config_dir_resolved)
    return [_execute_single_source(config, staging_dir, root) for config in configs]


def _source_execution_key(config: SourceConfig) -> str:
    """Derive a deterministic cache key for a source config.

    Args:
        config: Typed source configuration.

    Returns:
        Deterministic string suitable for use as the source argument to
        :func:`~docline.fetch.staging.make_job_id`.
    """
    if isinstance(config, LocalFileSource):
        return f"local_file:{','.join(sorted(config.paths))}"
    if isinstance(config, WebCrawlSource):
        return f"web_crawl:{config.url}"
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


def _execute_single_source(config: SourceConfig, staging_dir: str, root: Path) -> StagingJob:
    """Fetch a single source config and write its content to staging.

    Args:
        config: Typed source configuration.
        staging_dir: Workspace-relative staging root.
        root: Resolved workspace root.

    Returns:
        A :class:`~docline.fetch.models.StagingJob` with ``complete=True`` on
        success or ``complete=False`` if the fetch fails.
    """
    source_key = _source_execution_key(config)
    job_id = make_job_id(source_key)
    cache_rel = build_cache_path(staging_dir, job_id)
    cache_abs = root / cache_rel
    files_dir = cache_abs / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    metadata = SourceMetadata(
        source=sanitize_source(source_key),
        fetch_timestamp=datetime.now(UTC),
    )

    complete = False
    try:
        if isinstance(config, LocalFileSource):
            _fetch_local_files(config, root, files_dir)
            complete = True
        elif isinstance(config, ManifestLocalSource):
            _fetch_manifest_local(config, root, files_dir)
            complete = True
        elif isinstance(config, (WebCrawlSource, ManifestUrlSource)):
            complete = _fetch_url(config, files_dir) > 0
        elif isinstance(config, (GitHubRepoSource, ManifestGitSource)):
            _fetch_github(config, files_dir)
            complete = True
    except (OSError, Exception):  # noqa: BLE001
        pass  # leave complete=False; metadata.json written below

    job = StagingJob(
        job_id=job_id,
        metadata=metadata,
        cache_path=cache_rel,
        complete=complete,
    )
    (cache_abs / "metadata.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return job


# ---------------------------------------------------------------------------
# Per-type fetch helpers
# ---------------------------------------------------------------------------


def _resolve_local_base(path: str, root: Path) -> Path:
    """Resolve a local source base directory, applying the stale-path heuristic.

    Manifests may use ``path: tmp`` when the actual workspace layout stores
    files under ``.elt/``.  This function remaps ``tmp``-prefixed paths to
    their ``.elt/``-rooted equivalents when the ``tmp`` directory does not
    exist but the ``.elt/`` candidate does.

    Args:
        path: Source-relative base directory from the manifest.
        root: Workspace root.

    Returns:
        Resolved :class:`~pathlib.Path` for the base directory.
    """
    candidate = root / path
    if candidate.exists():
        return candidate

    # Apply stale-path heuristic: tmp → .elt/[suffix]
    if path == "tmp" or path.startswith("tmp/") or path.startswith("tmp\\"):
        suffix = path[3:].lstrip("/\\")
        elt_candidate = (root / ".elt" / suffix) if suffix else (root / ".elt")
        if elt_candidate.exists():
            return elt_candidate

    return candidate  # Fall through (may not exist; callers handle empty globs)


def _fetch_local_files(config: LocalFileSource, root: Path, files_dir: Path) -> None:
    """Copy flat local_file source paths into the staging files directory.

    Args:
        config: LocalFileSource configuration.
        root: Workspace root.
        files_dir: Destination staging files directory.
    """
    for rel_path in config.paths:
        src = root / rel_path
        if not src.is_file():
            continue
        dest = files_dir / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))


def _sanitize_web_path_component(value: str) -> str:
    """Return a filesystem-safe path component for a crawled URL segment."""
    cleaned = "".join(ch if ch.isalnum() or ch in {".", "-", "_"} else "-" for ch in value)
    trimmed = cleaned.strip(" .-_")
    return trimmed or "page"


def _staged_web_relative_path(
    page_url: str,
    start_url: str,
    used_paths: dict[str, str],
) -> Path:
    """Derive a stable relative HTML path for a crawled page URL."""
    if page_url == start_url and "page.html" not in used_paths:
        used_paths["page.html"] = page_url
        return Path("page.html")

    parsed = urlparse(page_url)
    raw_path = unquote(parsed.path or "/")
    raw_parts = [part for part in raw_path.split("/") if part]
    if not raw_parts:
        raw_parts = ["index.html"]
    elif "." not in raw_parts[-1]:
        raw_parts.append("index.html")

    safe_parts = [_sanitize_web_path_component(part) for part in raw_parts]
    candidate = Path(*safe_parts)
    suffix = candidate.suffix or ".html"
    if suffix.lower() not in {".html", ".htm"}:
        candidate = candidate.parent / f"{candidate.name}.html"

    key = candidate.as_posix()
    needs_hash = bool(parsed.query) or (key in used_paths and used_paths[key] != page_url)
    if needs_hash:
        digest = hashlib.sha256(page_url.encode("utf-8")).hexdigest()[:10]
        candidate = candidate.parent / f"{candidate.stem}--{digest}{candidate.suffix}"
        key = candidate.as_posix()

    used_paths[key] = page_url
    return candidate


def _staged_web_metadata_path(html_path: Path) -> Path:
    """Return the metadata sidecar path for a staged HTML file."""
    return html_path.with_suffix(_STAGED_WEB_METADATA_SUFFIX)


def _crawl_manifest_path(files_dir: Path) -> Path:
    """Return the crawl-manifest path for a staged web job."""
    return files_dir.parent / _CRAWL_MANIFEST_NAME


def _crawl_config_from_source(config: WebCrawlSource | ManifestUrlSource) -> CrawlConfig:
    """Translate ELT source config fields into a crawl configuration."""
    max_depth = config.depth if isinstance(config, WebCrawlSource) else config.max_depth
    if config.max_pages is not None:
        return CrawlConfig(
            max_depth=max_depth,
            domain_lock=config.domain_lock,
            rate_limit_ms=config.rate_limit_ms,
            max_pages=config.max_pages,
        )
    return CrawlConfig(
        max_depth=max_depth,
        domain_lock=config.domain_lock,
        rate_limit_ms=config.rate_limit_ms,
    )


def _fetch_manifest_local(config: ManifestLocalSource, root: Path, files_dir: Path) -> None:
    """Glob and copy files for a manifest-format local source.

    Applies the stale-path heuristic to resolve the base directory, then
    expands each include pattern relative to that base.

    Args:
        config: ManifestLocalSource configuration.
        root: Workspace root.
        files_dir: Destination staging files directory.
    """
    base = _resolve_local_base(config.path, root)
    if not base.exists():
        return  # Nothing to copy; job still marked complete

    seen: set[Path] = set()
    for pattern in config.include:
        # Materialise the generator before copying to avoid the copied files
        # being discovered by the generator when files_dir is inside base.
        for src in list(base.glob(pattern)):
            if src.is_file() and src not in seen:
                # Compatibility: skip generated artifact subtrees created by
                # prior pipeline runs (runtime-staging*, runtime-output*) so
                # that re-running the ELT fetch does not re-ingest its own
                # previous outputs.
                if _is_elt_generated_artifact(src, base):
                    continue
                seen.add(src)
                # Preserve relative directory structure within base
                rel = src.relative_to(base)
                dest = files_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dest))


def _fetch_url(config: WebCrawlSource | ManifestUrlSource, files_dir: Path) -> int:
    """Fetch a URL source and stage every crawled HTML page.

    Args:
        config: WebCrawlSource or ManifestUrlSource configuration.
        files_dir: Destination staging files directory.

    Returns:
        Number of staged HTML pages.

    Raises:
        OSError: When no crawlable pages were staged.
    """
    from docline.fetch.crawl import crawl

    url = config.url
    results = asyncio.run(crawl(url, _crawl_config_from_source(config)))
    staged_count = 0
    used_paths: dict[str, str] = {}
    manifest_pages: list[dict[str, object]] = []
    for result in results:
        if result.response is not None and result.response.body:
            rel_path = _staged_web_relative_path(result.url, url, used_paths)
            dest = files_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(result.response.body, encoding="utf-8")
            page_metadata = {
                "page_url": result.url,
                "crawl_depth": result.depth,
                "crawl_order": staged_count,
            }
            _staged_web_metadata_path(dest).write_text(
                json.dumps(page_metadata, indent=2),
                encoding="utf-8",
            )
            manifest_pages.append(
                {
                    "crawl_order": staged_count,
                    "relative_path": rel_path.as_posix(),
                    **page_metadata,
                }
            )
            staged_count += 1
    if staged_count == 0:
        raise OSError(f"No crawlable HTML pages were staged for {url}")
    _crawl_manifest_path(files_dir).write_text(
        json.dumps(
            {
                "pages": manifest_pages,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return staged_count


def _fetch_github(config: GitHubRepoSource | ManifestGitSource, files_dir: Path) -> None:
    """Fetch files from a GitHub repository into the staging files directory.

    Args:
        config: GitHubRepoSource or ManifestGitSource configuration.
        files_dir: Destination staging files directory.
    """
    if isinstance(config, GitHubRepoSource):
        repo_url = config.repo_url
        branch = config.branch
        include_patterns = [config.path_glob]
    else:
        repo_url = config.url
        branch = config.branch
        include_patterns = config.include

    file_pairs = fetch_github_files(repo_url, branch, include_patterns)
    for rel_path, content in file_pairs:
        dest = files_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")


__all__ = [
    "execute_elt_fetch",
]
