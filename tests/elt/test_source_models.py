"""Tests for typed ELT source configuration models."""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError


def test_local_file_source_validates_expected_fields() -> None:
    """LocalFileSource accepts valid input."""
    from docline.elt.models import LocalFileSource

    source = LocalFileSource(type="local_file", paths=["docs/sample.pdf"])

    assert source.type == "local_file"
    assert source.paths == ["docs/sample.pdf"]


def test_web_crawl_source_validates_expected_fields() -> None:
    """WebCrawlSource accepts valid input."""
    from docline.elt.models import WebCrawlSource

    source = WebCrawlSource(type="web_crawl", url="https://example.com")

    assert source.type == "web_crawl"
    assert source.url == "https://example.com"
    assert source.depth == 0
    assert source.domain_lock is True
    assert source.rate_limit_ms == 0


def test_github_repo_source_validates_expected_fields() -> None:
    """GitHubRepoSource accepts valid input."""
    from docline.elt.models import GitHubRepoSource

    source = GitHubRepoSource(type="github_repo", repo_url="https://github.com/org/repo")

    assert source.type == "github_repo"
    assert source.repo_url == "https://github.com/org/repo"
    assert source.branch == "main"


def test_source_config_rejects_unknown_type() -> None:
    """SourceConfig rejects unknown discriminator values."""
    from docline.elt.models import SourceConfig

    adapter = TypeAdapter(SourceConfig)

    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "ftp_source", "url": "https://example.com"})


def test_source_models_forbid_extra_fields() -> None:
    """Source models reject undeclared extra fields."""
    from docline.elt.models import LocalFileSource

    with pytest.raises(ValidationError):
        LocalFileSource(type="local_file", paths=["docs/sample.pdf"], extra_field=True)


def test_local_file_source_round_trips_through_pydantic_dump() -> None:
    """LocalFileSource supports dump and validate round-tripping."""
    from docline.elt.models import LocalFileSource

    source = LocalFileSource(type="local_file", paths=["docs/sample.pdf"])
    payload: dict[str, Any] = source.model_dump()

    restored = LocalFileSource.model_validate(payload)

    assert restored == source


def test_source_config_discriminates_on_type_field() -> None:
    """SourceConfig dispatches to the correct model by type."""
    from docline.elt.models import SourceConfig, WebCrawlSource

    adapter = TypeAdapter(SourceConfig)

    result = adapter.validate_python({"type": "web_crawl", "url": "https://example.com"})

    assert isinstance(result, WebCrawlSource)
