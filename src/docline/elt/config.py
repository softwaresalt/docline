"""YAML configuration file discovery and parsing for the ELT pipeline."""

from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

from docline.elt.models import SourceConfig
from docline.schema.models import DoclineError

_SOURCE_CONFIG_ADAPTER: TypeAdapter[SourceConfig] = TypeAdapter(SourceConfig)


class ConfigDiscoveryError(DoclineError):
    """Raised when ELT config discovery or parsing fails."""


def discover_configs(config_dir: Path) -> list[SourceConfig]:
    """Discover and parse YAML config files from a directory.

    Args:
        config_dir: Directory containing `.yaml` and `.yml` source configs.

    Returns:
        A sorted list of parsed config mappings. Missing or empty directories
        return an empty list.

    Raises:
        ConfigDiscoveryError: If a YAML file cannot be parsed or is missing
            required fields.
    """
    if not config_dir.exists() or not config_dir.is_dir():
        return []

    configs: list[SourceConfig] = []
    for path in sorted(_iter_config_paths(config_dir)):
        raw_config = _load_config_file(path)
        if raw_config is None:
            continue
        configs.append(_validate_source_config(raw_config, path))
    return configs


def _iter_config_paths(config_dir: Path) -> list[Path]:
    """Return ELT config file paths under a directory.

    Args:
        config_dir: Directory to scan.

    Returns:
        Sorted YAML file paths.
    """
    return sorted(
        path for path in config_dir.iterdir() if path.is_file() and path.suffix in {".yaml", ".yml"}
    )


def _load_config_file(path: Path) -> dict[str, object] | None:
    """Load a single YAML config file.

    Args:
        path: Config file path.

    Returns:
        The parsed config mapping, or ``None`` for empty files.

    Raises:
        ConfigDiscoveryError: If the file is invalid or missing required fields.
    """
    try:
        raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as err:
        raise ConfigDiscoveryError(f"Invalid YAML in {path.name}: {err}") from err
    except OSError as err:
        raise ConfigDiscoveryError(f"Unable to read config file {path.name}: {err}") from err

    if raw_data is None:
        return None
    if not isinstance(raw_data, dict):
        raise ConfigDiscoveryError(f"Config file {path.name} must contain a YAML mapping")
    if "type" not in raw_data:
        raise ConfigDiscoveryError(f"Config file {path.name} is missing required field 'type'")
    return raw_data


def _validate_source_config(raw_config: dict[str, object], path: Path) -> SourceConfig:
    """Validate raw config data against the typed source schema.

    Args:
        raw_config: Parsed YAML mapping.
        path: Source config file path.

    Returns:
        The validated typed source configuration.

    Raises:
        ConfigDiscoveryError: If typed validation fails.
    """
    try:
        return _SOURCE_CONFIG_ADAPTER.validate_python(raw_config)
    except ValidationError as err:
        raise ConfigDiscoveryError(f"Invalid source config in {path.name}: {err}") from err
