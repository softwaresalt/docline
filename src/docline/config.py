"""Configuration scaffolding for processing-stage features."""

from collections.abc import Mapping

from pydantic import BaseModel


class CorrectionProviderConfig(BaseModel):
    """Stub configuration for an optional correction provider.

    Attributes:
        enabled: Whether the correction provider may be used.
        provider: External provider identifier.
        api_key_env_var: Environment-variable name containing provider credentials.
        model: Optional provider model identifier.
    """

    enabled: bool = False
    provider: str | None = None
    api_key_env_var: str | None = None
    model: str | None = None


def resolve_correction_provider_config(
    raw_config: Mapping[str, object] | None = None,
) -> CorrectionProviderConfig:
    """Resolve correction-provider settings from raw configuration data.

    Args:
        raw_config: Optional raw configuration mapping.

    Returns:
        Normalized correction-provider configuration.

    Raises:
        ValueError: If secret material or enablement policy is invalid.
    """
    if raw_config is None:
        return CorrectionProviderConfig()

    if "api_key" in raw_config:
        raise ValueError(
            "api_key must not be provided directly; use api_key_env_var to reference a secret"
        )

    if not raw_config.get("enabled", False):
        raise ValueError("Correction provider must be explicitly enabled with enabled=True")

    config = CorrectionProviderConfig.model_validate(raw_config)
    if not config.provider:
        raise ValueError("Correction provider must specify a provider when enabled")
    if not config.api_key_env_var:
        raise ValueError("Correction provider must use api_key_env_var when enabled")
    return config


__all__ = ["CorrectionProviderConfig", "resolve_correction_provider_config"]
