"""Tests for ELT multi-source fetch orchestration."""

from pathlib import Path

import pytest

from docline.elt.config import ConfigDiscoveryError
from docline.elt.models import GitHubRepoSource, LocalFileSource, WebCrawlSource


def test_orchestrate_fetch_creates_one_staging_job_per_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """orchestrate_fetch creates one staging job for each source config."""
    from docline.elt.orchestrate import orchestrate_fetch

    configs = [
        LocalFileSource(type="local_file", paths=["docs/a.pdf", "docs/b.pdf"]),
        WebCrawlSource(type="web_crawl", url="https://example.com"),
        GitHubRepoSource(type="github_repo", repo_url="https://github.com/org/repo"),
    ]
    monkeypatch.setattr("docline.elt.orchestrate.discover_configs", lambda _: configs)

    jobs = orchestrate_fetch(tmp_path / "config", ".elt/staging", workspace_root=tmp_path)

    assert len(jobs) == 3
    assert [job.metadata.source for job in jobs] == [
        "local_file:docs/a.pdf,docs/b.pdf",
        "web_crawl:https://example.com",
        "github_repo:https://github.com/org/repo@main:**/*.md",
    ]


def test_orchestrate_fetch_job_ids_are_deterministic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """orchestrate_fetch produces deterministic staging job identifiers."""
    from docline.elt.orchestrate import orchestrate_fetch

    configs = [WebCrawlSource(type="web_crawl", url="https://example.com")]
    monkeypatch.setattr("docline.elt.orchestrate.discover_configs", lambda _: configs)

    first_jobs = orchestrate_fetch(tmp_path / "config", ".elt/staging", workspace_root=tmp_path)
    second_jobs = orchestrate_fetch(tmp_path / "config", ".elt/staging", workspace_root=tmp_path)

    assert [job.job_id for job in first_jobs] == [job.job_id for job in second_jobs]


def test_orchestrate_fetch_validates_staging_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """orchestrate_fetch validates the staging directory within the workspace."""
    from docline.elt.orchestrate import orchestrate_fetch

    recorded: dict[str, object] = {}
    monkeypatch.setattr(
        "docline.elt.orchestrate.discover_configs",
        lambda _: [WebCrawlSource(type="web_crawl", url="https://example.com")],
    )

    def fake_safe_workspace_path(relative: str, workspace_root: str | Path) -> Path:
        recorded["relative"] = relative
        recorded["workspace_root"] = workspace_root
        return Path(workspace_root) / relative

    monkeypatch.setattr("docline.elt.orchestrate.safe_workspace_path", fake_safe_workspace_path)

    orchestrate_fetch(tmp_path / "config", ".elt/staging", workspace_root=tmp_path)

    assert recorded == {"relative": ".elt/staging", "workspace_root": tmp_path}


def test_orchestrate_fetch_rejects_config_dir_outside_workspace(tmp_path: Path) -> None:
    """orchestrate_fetch raises PathContainmentError for out-of-workspace config_dir."""
    from docline.elt.orchestrate import orchestrate_fetch
    from docline.paths import PathContainmentError

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    with pytest.raises(PathContainmentError, match="outside workspace root"):
        orchestrate_fetch(outside_dir, ".elt/staging", workspace_root=workspace)


def test_orchestrate_fetch_returns_empty_list_when_no_configs(tmp_path: Path) -> None:
    """orchestrate_fetch returns an empty list for an empty config directory."""
    from docline.elt.orchestrate import orchestrate_fetch

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    assert orchestrate_fetch(config_dir, ".elt/staging", workspace_root=tmp_path) == []


def test_orchestrate_fetch_propagates_config_discovery_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """orchestrate_fetch lets config discovery errors bubble up."""
    from docline.elt.orchestrate import orchestrate_fetch

    def raise_error(config_dir: Path) -> list[object]:
        raise ConfigDiscoveryError(f"boom: {config_dir}")

    monkeypatch.setattr("docline.elt.orchestrate.discover_configs", raise_error)

    with pytest.raises(ConfigDiscoveryError, match="boom"):
        orchestrate_fetch(tmp_path / "config", ".elt/staging", workspace_root=tmp_path)


def test_orchestrate_fetch_distinct_depth_produces_distinct_job_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Different WebCrawlSource depth values produce distinct job IDs."""
    from docline.elt.orchestrate import orchestrate_fetch

    configs_shallow = [WebCrawlSource(type="web_crawl", url="https://example.com", depth=0)]
    configs_deep = [WebCrawlSource(type="web_crawl", url="https://example.com", depth=3)]

    monkeypatch.setattr("docline.elt.orchestrate.discover_configs", lambda _: configs_shallow)
    jobs_shallow = orchestrate_fetch(tmp_path / "config", ".elt/staging", workspace_root=tmp_path)

    monkeypatch.setattr("docline.elt.orchestrate.discover_configs", lambda _: configs_deep)
    jobs_deep = orchestrate_fetch(tmp_path / "config", ".elt/staging", workspace_root=tmp_path)

    assert jobs_shallow[0].job_id != jobs_deep[0].job_id


def test_orchestrate_fetch_distinct_path_glob_produces_distinct_job_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Different GitHubRepoSource path_glob values produce distinct job IDs."""
    from docline.elt.orchestrate import orchestrate_fetch

    configs_docs = [
        GitHubRepoSource(
            type="github_repo",
            repo_url="https://github.com/org/repo",
            path_glob="docs/**/*.md",
        )
    ]
    configs_src = [
        GitHubRepoSource(
            type="github_repo",
            repo_url="https://github.com/org/repo",
            path_glob="src/**/*.py",
        )
    ]

    monkeypatch.setattr("docline.elt.orchestrate.discover_configs", lambda _: configs_docs)
    jobs_docs = orchestrate_fetch(tmp_path / "config", ".elt/staging", workspace_root=tmp_path)

    monkeypatch.setattr("docline.elt.orchestrate.discover_configs", lambda _: configs_src)
    jobs_src = orchestrate_fetch(tmp_path / "config", ".elt/staging", workspace_root=tmp_path)

    assert jobs_docs[0].job_id != jobs_src[0].job_id
