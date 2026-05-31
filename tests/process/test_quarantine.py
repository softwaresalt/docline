"""Failing harness tests for safe quarantine artifacts."""

import json
from pathlib import Path

from docline.process.quarantine import persist_quarantine_artifact, redact_quarantine_payload


def test_persist_quarantine_artifact_routes_failed_documents(tmp_path: Path) -> None:
    artifact_path = persist_quarantine_artifact(
        tmp_path,
        "doc-001",
        {"reason": "ast-lint"},
        "# Broken\n\n## Missing Section\n",
    )
    assert artifact_path.parent == tmp_path
    assert artifact_path.name.startswith("doc-001")


def test_redact_quarantine_payload_removes_secrets() -> None:
    payload = redact_quarantine_payload(
        {"api_key": "secret-token", "authorization": "Bearer secret-token", "reason": "ast-lint"}
    )
    serialized = json.dumps(payload)
    assert "secret-token" not in serialized
    assert "api_key" not in serialized


def test_redact_quarantine_payload_removes_nested_secrets() -> None:
    payload = redact_quarantine_payload(
        {
            "reason": "ast-lint",
            "metadata": {
                "prompt": "Rewrite the markdown",
                "nested": [{"token": "secret-token"}, {"detail": "kept"}],
            },
        }
    )
    serialized = json.dumps(payload)
    assert "secret-token" not in serialized
    assert "Rewrite the markdown" not in serialized
    assert payload == {"reason": "ast-lint", "metadata": {"nested": [{}, {"detail": "kept"}]}}


def test_persist_quarantine_artifact_records_failed_document_context(tmp_path: Path) -> None:
    artifact_path = persist_quarantine_artifact(
        tmp_path,
        "doc-002",
        {"reason": "schema-validation"},
        "# Broken\n\n## Metadata\n",
    )
    assert "doc-002" in artifact_path.read_text(encoding="utf-8")
