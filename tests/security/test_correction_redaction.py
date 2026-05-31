"""Failing harness tests for correction payload redaction."""

import json

from docline.config import CorrectionProviderConfig
from docline.process.prompts import build_correction_payload, redact_correction_payload
from docline.process.quarantine import redact_quarantine_payload


def _enabled_config() -> CorrectionProviderConfig:
    return CorrectionProviderConfig(
        enabled=True,
        provider="mock-provider",
        api_key_env_var="DOCLINE_CORRECTION_API_KEY",
        model="mock-model",
    )


def test_build_correction_payload_minimizes_persisted_fields() -> None:
    payload = build_correction_payload(
        "# Title\n\n## Summary\nDraft body\n",
        ["Missing required section: Decision"],
        _enabled_config(),
    )
    assert sorted(payload) == ["document_excerpt", "lint_errors", "provider"]


def test_redact_correction_payload_omits_provider_secrets() -> None:
    payload = redact_correction_payload(
        {
            "provider": "mock-provider",
            "api_key": "secret-token",
            "authorization": "Bearer secret-token",
        }
    )
    serialized = json.dumps(payload)
    assert "secret-token" not in serialized
    assert "api_key" not in serialized


def test_redact_correction_payload_omits_nested_provider_secrets() -> None:
    payload = redact_correction_payload(
        {
            "provider": "mock-provider",
            "metadata": {
                "attempt": 1,
                "authorization": "Bearer secret-token",
                "nested": [{"token": "secret-token"}, {"status": "safe"}],
            },
        }
    )
    serialized = json.dumps(payload)
    assert "secret-token" not in serialized
    assert payload == {
        "provider": "mock-provider",
        "metadata": {"attempt": 1, "nested": [{}, {"status": "safe"}]},
    }


def test_redact_quarantine_payload_verifies_redaction() -> None:
    payload = redact_quarantine_payload(
        {
            "provider": "mock-provider",
            "api_key": "secret-token",
            "prompt": "Rewrite the markdown",
        }
    )
    serialized = json.dumps(payload)
    assert "secret-token" not in serialized
    assert "prompt" not in serialized
