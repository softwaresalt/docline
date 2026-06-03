"""Tests for ELT YAML config discovery."""

from pathlib import Path

import pytest


def test_discover_configs_returns_empty_list_for_missing_directory(tmp_path: Path) -> None:
    """discover_configs returns an empty list when the config directory is absent."""
    from docline.elt.config import discover_configs

    assert discover_configs(tmp_path / "missing") == []


def test_discover_configs_returns_empty_list_for_empty_directory(tmp_path: Path) -> None:
    """discover_configs returns an empty list for an empty directory."""
    from docline.elt.config import discover_configs

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    assert discover_configs(config_dir) == []


def test_discover_configs_reads_yaml_and_yml_fixtures() -> None:
    """discover_configs loads both .yaml and .yml files."""
    from docline.elt.config import discover_configs
    from docline.elt.models import LocalFileSource, WebCrawlSource

    fixture_dir = Path(__file__).parent / "fixtures"

    configs = discover_configs(fixture_dir)

    assert len(configs) == 2
    assert [type(config) for config in configs] == [LocalFileSource, WebCrawlSource]
    assert [config.type for config in configs] == ["local_file", "web_crawl"]


def test_discover_configs_skips_empty_yaml_files(tmp_path: Path) -> None:
    """discover_configs skips YAML files that parse to no data."""
    from docline.elt.config import discover_configs

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "empty.yaml").write_text("", encoding="utf-8")

    assert discover_configs(config_dir) == []


def test_discover_configs_raises_for_invalid_yaml() -> None:
    """discover_configs raises a typed error when a YAML file is invalid."""
    from docline.elt.config import ConfigDiscoveryError, discover_configs

    fixture_dir = Path(__file__).parent / "fixtures" / "invalid_only"

    with pytest.raises(ConfigDiscoveryError, match="invalid.yaml"):
        discover_configs(fixture_dir)


def test_discover_configs_raises_for_missing_required_fields() -> None:
    """discover_configs raises a typed error when required fields are missing."""
    from docline.elt.config import ConfigDiscoveryError, discover_configs

    fixture_dir = Path(__file__).parent / "fixtures" / "missing_fields"

    with pytest.raises(ConfigDiscoveryError, match="missing_type.yaml"):
        discover_configs(fixture_dir)
