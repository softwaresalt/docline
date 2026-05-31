"""Correction prompt stubs for optional external remediation flows."""

from collections.abc import Mapping, Sequence

from docline.config import CorrectionProviderConfig

_SECRET_KEYS = frozenset({"api_key", "authorization", "password", "secret", "token"})


def build_correction_payload(
    markdown_text: str, lint_errors: Sequence[str], config: CorrectionProviderConfig
) -> dict[str, object]:
    """Build the correction request payload for an enabled provider.

    Args:
        markdown_text: Markdown document requiring correction.
        lint_errors: Structural lint errors to address.
        config: Resolved correction-provider configuration.

    Returns:
        Provider request payload.
    """
    return {
        "document_excerpt": markdown_text[:500],
        "lint_errors": list(lint_errors),
        "provider": config.provider or "",
    }


def redact_correction_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Remove provider secrets from a persisted correction payload.

    Args:
        payload: Raw correction payload.

    Returns:
        Redacted correction payload.
    """
    result = _redact_recursive(dict(payload))
    assert isinstance(result, dict)
    return result


def _redact_recursive(obj: object) -> object:
    """Recursively remove secret-bearing keys from nested payload data."""
    if isinstance(obj, dict):
        return {
            key: _redact_recursive(value)
            for key, value in obj.items()
            if key.lower() not in _SECRET_KEYS
        }
    if isinstance(obj, list):
        return [_redact_recursive(item) for item in obj]
    return obj


__all__ = ["build_correction_payload", "redact_correction_payload"]
