"""Quarantine persistence stubs for failed processing artifacts."""

import json
from collections.abc import Mapping
from pathlib import Path

_REDACTED_KEYS = frozenset({"api_key", "authorization", "password", "prompt", "secret", "token"})


def redact_quarantine_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Redact secrets from data destined for quarantine artifacts.

    Args:
        payload: Raw quarantine payload.

    Returns:
        Redacted quarantine payload.
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
            if key.lower() not in _REDACTED_KEYS
        }
    if isinstance(obj, list):
        return [_redact_recursive(item) for item in obj]
    return obj


def persist_quarantine_artifact(
    quarantine_root: Path | str,
    document_id: str,
    failure_payload: Mapping[str, object],
    markdown_text: str,
) -> Path:
    """Persist a safe quarantine artifact for a failed document.

    Args:
        quarantine_root: Workspace-contained quarantine root directory.
        document_id: Deterministic document identifier.
        failure_payload: Failure details to persist.
        markdown_text: Markdown content associated with the failure.

    Returns:
        Path to the written quarantine artifact.
    """
    root = Path(quarantine_root)
    root.mkdir(parents=True, exist_ok=True)
    artifact_path = root / f"{document_id}-quarantine.json"
    artifact = {
        "document_id": document_id,
        "failure_payload": redact_quarantine_payload(failure_payload),
        "markdown_excerpt": markdown_text[:500],
    }
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return artifact_path


__all__ = ["persist_quarantine_artifact", "redact_quarantine_payload"]
