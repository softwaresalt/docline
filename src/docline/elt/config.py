"""YAML configuration file discovery and parsing for the ELT pipeline."""

from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

from docline.elt.manifest_models import ManifestGitSource, ManifestLocalSource, ManifestUrlSource
from docline.elt.models import SourceConfig
from docline.schema.models import DoclineError

_SOURCE_CONFIG_ADAPTER: TypeAdapter[SourceConfig] = TypeAdapter(SourceConfig)

_MANIFEST_TYPE_MAP: dict[str, type] = {
    "local": ManifestLocalSource,
    "url": ManifestUrlSource,
    "git": ManifestGitSource,
}


class ConfigDiscoveryError(DoclineError):
    """Raised when ELT config discovery or parsing fails."""


def discover_configs(config_dir: Path) -> list[SourceConfig]:
    """Discover and parse YAML config files from a directory.

    Handles both flat-format configs (single mapping with a ``type:`` field)
    and graphtor-docs manifest-format configs (a mapping with a top-level
    ``sources:`` list).

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
    for path in _iter_config_paths(config_dir):
        raw_data = _load_yaml_file(path)
        if raw_data is None:
            continue
        if "sources" in raw_data and isinstance(raw_data["sources"], list):
            # Graphtor-docs manifest format: parse each entry in the sources list
            configs.extend(_parse_manifest_sources(raw_data["sources"], path))
        else:
            # Flat format: single source config mapping with a required ``type`` field
            configs.append(_parse_flat_source(raw_data, path))
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


def _load_yaml_file(path: Path) -> dict[str, object] | None:
    """Load a single YAML file and return its parsed content.

    Args:
        path: YAML file path.

    Returns:
        The parsed mapping, or ``None`` for empty files.

    Raises:
        ConfigDiscoveryError: If the file is unreadable or not a YAML mapping.
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
    return raw_data


def _parse_manifest_sources(sources: list[object], path: Path) -> list[SourceConfig]:
    """Parse a graphtor-docs manifest ``sources:`` list.

    Each entry must be a mapping with at least an ``id`` and a ``type`` field.
    Supported manifest types are ``local``, ``url``, and ``git``.

    Args:
        sources: Raw list of source entries from the YAML ``sources:`` key.
        path: Config file path (for error messages).

    Returns:
        Validated typed source configurations for each entry.

    Raises:
        ConfigDiscoveryError: If an entry is malformed or has an unknown type.
    """
    parsed: list[SourceConfig] = []
    for i, entry in enumerate(sources):
        if not isinstance(entry, dict):
            raise ConfigDiscoveryError(f"Config file {path.name}: sources[{i}] must be a mapping")
        entry_type = entry.get("type")
        if entry_type not in _MANIFEST_TYPE_MAP:
            raise ConfigDiscoveryError(
                f"Config file {path.name}: sources[{i}] has unknown manifest type {entry_type!r}; "
                f"expected one of {sorted(_MANIFEST_TYPE_MAP)}"
            )
        model_class = _MANIFEST_TYPE_MAP[entry_type]
        try:
            parsed.append(model_class(**entry))
        except (TypeError, ValueError) as err:
            raise ConfigDiscoveryError(
                f"Config file {path.name}: sources[{i}] is invalid: {err}"
            ) from err
    return parsed


def _parse_flat_source(raw_config: dict[str, object], path: Path) -> SourceConfig:
    """Parse a flat-format source config mapping.

    Requires a ``type`` field.  The type must be one of ``local_file``,
    ``web_crawl``, or ``github_repo``.

    Args:
        raw_config: Parsed YAML mapping.
        path: Config file path (for error messages).

    Returns:
        The validated typed source configuration.

    Raises:
        ConfigDiscoveryError: If the ``type`` field is missing or validation fails.
    """
    if "type" not in raw_config:
        raise ConfigDiscoveryError(f"Config file {path.name} is missing required field 'type'")
    return _validate_source_config(raw_config, path)


# ---------------------------------------------------------------------------
# Internal helpers (kept for backwards-compatibility with existing call sites)
# ---------------------------------------------------------------------------


def _load_config_file(path: Path) -> dict[str, object] | None:
    """Load a single YAML config file (flat format only).

    .. deprecated::
        Use :func:`_load_yaml_file` and :func:`_parse_flat_source` instead.
        This function is retained for backwards-compatibility.

    Args:
        path: Config file path.

    Returns:
        The parsed config mapping, or ``None`` for empty files.

    Raises:
        ConfigDiscoveryError: If the file is invalid or missing required fields.
    """
    raw_data = _load_yaml_file(path)
    if raw_data is None:
        return None
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
