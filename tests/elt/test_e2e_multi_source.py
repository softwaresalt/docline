"""End-to-end integration tests for ELT multi-source staging."""

import json
from pathlib import Path

import pytest

from docline.elt.orchestrate import orchestrate_fetch
from docline.fetch.staging import make_job_id


def _write_config(config_dir: Path, name: str, content: str) -> None:
    """Write an ELT source config file for integration tests.

    Args:
        config_dir: Directory that holds config files.
        name: File name to create.
        content: YAML payload to write.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / name).write_text(content, encoding="utf-8")


@pytest.mark.integration
class TestELTMultiSourcePipeline:
    """Integration coverage for config-driven multi-source staging."""

    def test_integration_marker_is_registered(self, pytestconfig: pytest.Config) -> None:
        """The integration pytest marker is registered in project config."""
        assert any(marker.startswith("integration") for marker in pytestconfig.getini("markers"))

    def test_local_file_source_produces_staging_job(self, tmp_path: Path) -> None:
        """Local file configs produce a deterministic staging job."""
        config_dir = tmp_path / "config"
        _write_config(
            config_dir,
            "local.yaml",
            "type: local_file\npaths:\n  - docs/sample.pdf\n  - docs/second.docx\n",
        )

        jobs = orchestrate_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

        assert len(jobs) == 1
        assert jobs[0].job_id == make_job_id("local_file:docs/sample.pdf,docs/second.docx")
        assert jobs[0].cache_path == f".elt/staging/{jobs[0].job_id[:2]}/{jobs[0].job_id}"
        assert jobs[0].metadata.source == "local_file:docs/sample.pdf,docs/second.docx"

    def test_web_crawl_source_produces_staging_job(self, tmp_path: Path) -> None:
        """Web crawl configs produce a deterministic staging job."""
        config_dir = tmp_path / "config"
        _write_config(
            config_dir,
            "web.yaml",
            "type: web_crawl\nurl: https://example.com\n",
        )

        jobs = orchestrate_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

        assert len(jobs) == 1
        assert jobs[0].job_id == make_job_id("web_crawl:https://example.com")
        assert jobs[0].cache_path == f".elt/staging/{jobs[0].job_id[:2]}/{jobs[0].job_id}"
        assert jobs[0].metadata.source == "web_crawl:https://example.com"

    def test_github_repo_source_produces_staging_job(self, tmp_path: Path) -> None:
        """GitHub repo configs produce a deterministic staging job."""
        config_dir = tmp_path / "config"
        _write_config(
            config_dir,
            "github.yaml",
            "type: github_repo\nrepo_url: https://github.com/org/repo\nbranch: trunk\n",
        )

        jobs = orchestrate_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

        assert len(jobs) == 1
        assert jobs[0].job_id == make_job_id(
            "github_repo:https://github.com/org/repo@trunk:**/*.md"
        )
        assert jobs[0].cache_path == f".elt/staging/{jobs[0].job_id[:2]}/{jobs[0].job_id}"
        assert jobs[0].metadata.source == "github_repo:https://github.com/org/repo@trunk:**/*.md"

    def test_mixed_sources_produce_one_job_per_config(self, tmp_path: Path) -> None:
        """Mixed configs produce one staging job for each config file."""
        config_dir = tmp_path / "config"
        _write_config(config_dir, "local.yaml", "type: local_file\npaths:\n  - docs/sample.pdf\n")
        _write_config(config_dir, "web.yaml", "type: web_crawl\nurl: https://example.com\n")
        _write_config(
            config_dir,
            "github.yaml",
            "type: github_repo\nrepo_url: https://github.com/org/repo\n",
        )

        jobs = orchestrate_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)

        assert len(jobs) == 3
        assert [job.metadata.source for job in jobs] == [
            "github_repo:https://github.com/org/repo@main:**/*.md",
            "local_file:docs/sample.pdf",
            "web_crawl:https://example.com",
        ]

    def test_staging_jobs_serialize_to_json(self, tmp_path: Path) -> None:
        """Produced staging jobs serialize cleanly to JSON."""
        config_dir = tmp_path / "config"
        _write_config(config_dir, "web.yaml", "type: web_crawl\nurl: https://example.com\n")

        jobs = orchestrate_fetch(config_dir, ".elt/staging", workspace_root=tmp_path)
        payload = [job.model_dump(mode="json") for job in jobs]

        assert json.loads(json.dumps(payload))[0]["job_id"] == jobs[0].job_id
