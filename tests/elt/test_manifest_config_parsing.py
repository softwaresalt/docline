"""Tests for manifest-format ELT source config parsing.

These tests verify that .sources.yaml files using the graphtor-docs manifest
shape (top-level ``sources:`` list with ``type: local|url|git`` entries) are
parsed correctly by the ELT config discovery layer.
"""

from pathlib import Path

import pytest


def _write_sources_yaml(config_dir: Path, name: str, content: str) -> None:
    """Write a YAML sources file into the config directory.

    Args:
        config_dir: Directory to write into.
        name: File name.
        content: YAML text.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / name).write_text(content, encoding="utf-8")


class TestManifestLocalSourceParsing:
    """Config parsing for manifest local sources."""

    def test_manifest_local_source_is_parsed(self, tmp_path: Path) -> None:
        """discover_configs parses a manifest-format local source entry."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestLocalSource

        config_dir = tmp_path / "config"
        _write_sources_yaml(
            config_dir,
            "local.sources.yaml",
            (
                "sources:\n"
                "  - id: my-docs\n"
                "    type: local\n"
                "    path: tmp\n"
                "    include:\n"
                '      - "**/*.pdf"\n'
                "    formats: [pdf]\n"
            ),
        )

        configs = discover_configs(config_dir)

        assert len(configs) == 1
        assert isinstance(configs[0], ManifestLocalSource)
        assert configs[0].id == "my-docs"
        assert configs[0].path == "tmp"
        assert configs[0].include == ["**/*.pdf"]

    def test_manifest_local_source_ignores_database_field(self, tmp_path: Path) -> None:
        """discover_configs ignores extra fields like database."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestLocalSource

        config_dir = tmp_path / "config"
        _write_sources_yaml(
            config_dir,
            "local.sources.yaml",
            (
                "sources:\n"
                "  - id: cosmos-db\n"
                "    type: local\n"
                "    path: tmp\n"
                "    include:\n"
                '      - "azure-cosmos-db.pdf"\n'
                "    formats: [pdf]\n"
                '    database: "cosmos.db"\n'
            ),
        )

        configs = discover_configs(config_dir)

        assert len(configs) == 1
        assert isinstance(configs[0], ManifestLocalSource)
        assert configs[0].id == "cosmos-db"

    def test_manifest_local_source_defaults(self, tmp_path: Path) -> None:
        """ManifestLocalSource applies sensible defaults for optional fields."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestLocalSource

        config_dir = tmp_path / "config"
        _write_sources_yaml(
            config_dir,
            "minimal.sources.yaml",
            "sources:\n  - id: minimal\n    type: local\n    path: tmp\n",
        )

        configs = discover_configs(config_dir)

        assert isinstance(configs[0], ManifestLocalSource)
        assert configs[0].include == ["**/*"]
        assert configs[0].formats == []


class TestManifestUrlSourceParsing:
    """Config parsing for manifest URL sources."""

    def test_manifest_url_source_is_parsed(self, tmp_path: Path) -> None:
        """discover_configs parses a manifest-format URL source entry."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestUrlSource

        config_dir = tmp_path / "config"
        _write_sources_yaml(
            config_dir,
            "url.sources.yaml",
            (
                "sources:\n"
                "  - id: bicep-avm\n"
                "    type: url\n"
                "    url: https://azure.github.io/Azure-Verified-Modules/overview/\n"
                "    max_depth: 3\n"
                "    max_pages: 200\n"
                "    domain_lock: true\n"
                "    rate_limit_ms: 500\n"
                "    formats: [md]\n"
                '    database: "bicep-avm.db"\n'
            ),
        )

        configs = discover_configs(config_dir)

        assert len(configs) == 1
        assert isinstance(configs[0], ManifestUrlSource)
        assert configs[0].url == "https://azure.github.io/Azure-Verified-Modules/overview/"
        assert configs[0].max_depth == 3
        assert configs[0].max_pages == 200
        assert configs[0].domain_lock is True
        assert configs[0].rate_limit_ms == 500

    def test_manifest_url_source_parses_domain_lock(self, tmp_path: Path) -> None:
        """ManifestUrlSource preserves the domain_lock flag from the manifest."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestUrlSource

        config_dir = tmp_path / "config"
        _write_sources_yaml(
            config_dir,
            "url.sources.yaml",
            (
                "sources:\n"
                "  - id: rust-book\n"
                "    type: url\n"
                "    url: https://doc.rust-lang.org/book/\n"
                "    max_depth: 3\n"
                "    max_pages: 350\n"
                "    domain_lock: true\n"
                "    rate_limit_ms: 500\n"
            ),
        )

        configs = discover_configs(config_dir)

        assert isinstance(configs[0], ManifestUrlSource)
        assert configs[0].id == "rust-book"
        assert configs[0].domain_lock is True


class TestManifestGitSourceParsing:
    """Config parsing for manifest git sources."""

    def test_manifest_git_source_is_parsed(self, tmp_path: Path) -> None:
        """discover_configs parses a manifest-format git source entry."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestGitSource

        config_dir = tmp_path / "config"
        _write_sources_yaml(
            config_dir,
            "git.sources.yaml",
            (
                "sources:\n"
                "  - id: fabric-rest-api-specs\n"
                "    type: git\n"
                "    url: https://github.com/microsoft/fabric-rest-api-specs.git\n"
                "    branch: main\n"
                "    include:\n"
                '      - "**/*.md"\n'
                "    formats: [md]\n"
                '    database: "fabric-apispec.db"\n'
            ),
        )

        configs = discover_configs(config_dir)

        assert len(configs) == 1
        assert isinstance(configs[0], ManifestGitSource)
        assert configs[0].url == "https://github.com/microsoft/fabric-rest-api-specs.git"
        assert configs[0].branch == "main"
        assert configs[0].include == ["**/*.md"]

    def test_manifest_git_source_branch_defaults_to_main(self, tmp_path: Path) -> None:
        """ManifestGitSource defaults branch to 'main' when unspecified."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestGitSource

        config_dir = tmp_path / "config"
        _write_sources_yaml(
            config_dir,
            "git.sources.yaml",
            (
                "sources:\n"
                "  - id: some-repo\n"
                "    type: git\n"
                "    url: https://github.com/org/repo.git\n"
            ),
        )

        configs = discover_configs(config_dir)

        assert isinstance(configs[0], ManifestGitSource)
        assert configs[0].branch == "main"


class TestManifestMultiSourceParsing:
    """Config parsing for manifest files with multiple sources."""

    def test_multi_source_manifest_returns_all_entries(self, tmp_path: Path) -> None:
        """discover_configs returns all source entries from a multi-source manifest."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestLocalSource, ManifestUrlSource

        config_dir = tmp_path / "config"
        _write_sources_yaml(
            config_dir,
            "mixed.sources.yaml",
            (
                "sources:\n"
                "  - id: local-docs\n"
                "    type: local\n"
                "    path: tmp\n"
                "    include:\n"
                '      - "**/*.pdf"\n'
                "  - id: web-docs\n"
                "    type: url\n"
                "    url: https://example.com\n"
            ),
        )

        configs = discover_configs(config_dir)

        assert len(configs) == 2
        assert isinstance(configs[0], ManifestLocalSource)
        assert isinstance(configs[1], ManifestUrlSource)

    def test_flat_and_manifest_format_in_same_directory(self, tmp_path: Path) -> None:
        """discover_configs handles a directory with both flat and manifest format files."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestLocalSource
        from docline.elt.models import WebCrawlSource

        config_dir = tmp_path / "config"
        _write_sources_yaml(
            config_dir,
            "a_flat.yaml",
            "type: web_crawl\nurl: https://example.com\n",
        )
        _write_sources_yaml(
            config_dir,
            "b_manifest.sources.yaml",
            (
                "sources:\n"
                "  - id: local-docs\n"
                "    type: local\n"
                "    path: tmp\n"
                "    include:\n"
                '      - "**/*.pdf"\n'
            ),
        )

        configs = discover_configs(config_dir)

        assert len(configs) == 2
        assert isinstance(configs[0], WebCrawlSource)
        assert isinstance(configs[1], ManifestLocalSource)


class TestRealEltConfigFiles:
    """Tests that parse the actual .elt/config/*.sources.yaml files."""

    @pytest.mark.integration
    def test_cosmosdb_sources_yaml_parses_as_local_manifest(self) -> None:
        """The real cosmosdb.sources.yaml parses as a ManifestLocalSource."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestLocalSource

        config_dir = Path(__file__).parents[2] / ".elt" / "config"
        cosmosdb_path = config_dir / "cosmosdb.sources.yaml"
        if not cosmosdb_path.exists():
            pytest.skip("cosmosdb.sources.yaml not found in .elt/config")

        # Use a temp dir with just the cosmosdb file to isolate the test
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            shutil.copy(cosmosdb_path, tmp_dir / cosmosdb_path.name)
            configs = discover_configs(tmp_dir)

        assert len(configs) >= 1
        assert isinstance(configs[0], ManifestLocalSource)
        assert configs[0].path == "tmp"

    @pytest.mark.integration
    def test_fabric_apispec_sources_yaml_parses_as_git_manifest(self) -> None:
        """The real fabric-apispec.sources.yaml parses as a ManifestGitSource."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestGitSource

        config_dir = Path(__file__).parents[2] / ".elt" / "config"
        path = config_dir / "fabric-apispec.sources.yaml"
        if not path.exists():
            pytest.skip("fabric-apispec.sources.yaml not found in .elt/config")

        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            shutil.copy(path, tmp_dir / path.name)
            configs = discover_configs(tmp_dir)

        assert len(configs) >= 1
        assert isinstance(configs[0], ManifestGitSource)

    @pytest.mark.integration
    def test_bicep_avm_sources_yaml_parses_as_url_manifest(self) -> None:
        """The real bicep.avm.sources.yaml parses as a ManifestUrlSource."""
        from docline.elt.config import discover_configs
        from docline.elt.manifest_models import ManifestUrlSource

        config_dir = Path(__file__).parents[2] / ".elt" / "config"
        path = config_dir / "bicep.avm.sources.yaml"
        if not path.exists():
            pytest.skip("bicep.avm.sources.yaml not found in .elt/config")

        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            shutil.copy(path, tmp_dir / path.name)
            configs = discover_configs(tmp_dir)

        assert len(configs) >= 1
        assert isinstance(configs[0], ManifestUrlSource)
