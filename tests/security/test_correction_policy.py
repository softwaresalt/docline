"""Failing harness tests for correction-provider policy enforcement."""

import pytest

from docline.config import resolve_correction_provider_config


def test_resolve_correction_provider_config_defaults_to_disabled() -> None:
    config = resolve_correction_provider_config()
    assert config.enabled is False


def test_resolve_correction_provider_config_requires_explicit_enablement() -> None:
    with pytest.raises(ValueError):
        resolve_correction_provider_config(
            {"provider": "mock-provider", "api_key_env_var": "DOCLINE_CORRECTION_API_KEY"}
        )


def test_resolve_correction_provider_config_requires_secret_source_reference() -> None:
    with pytest.raises(ValueError):
        resolve_correction_provider_config(
            {"enabled": True, "provider": "mock-provider", "api_key": "plain-text-secret"}
        )
