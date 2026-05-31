"""Failing harness tests for validated frontmatter assembly."""

from datetime import datetime

import pytest

from docline.process.metadata import assemble_frontmatter_payload
from docline.schema.library import WikiFrontmatter
from docline.schema.models import SchemaValidationError


def _wiki_metadata() -> dict[str, object]:
    return {
        "title": "Architecture Overview",
        "source": "https://docs.example.com/wiki/architecture",
        "ingested_at": datetime(2026, 5, 30, 12, 0, 0),
        "doc_type": "wiki",
        "tags": ["architecture", "process"],
        "section": "platform",
    }


def test_assemble_frontmatter_payload_includes_required_metadata_fields() -> None:
    payload = assemble_frontmatter_payload(WikiFrontmatter, _wiki_metadata())
    assert payload.title == "Architecture Overview"
    assert payload.source == "https://docs.example.com/wiki/architecture"
    assert payload.doc_type == "wiki"


def test_assemble_frontmatter_payload_matches_schema_shape() -> None:
    payload = assemble_frontmatter_payload(WikiFrontmatter, _wiki_metadata())
    assert isinstance(payload, WikiFrontmatter)
    assert payload.model_dump(mode="json")["tags"] == ["architecture", "process"]


def test_assemble_frontmatter_payload_rejects_missing_required_fields() -> None:
    with pytest.raises(SchemaValidationError):
        assemble_frontmatter_payload(
            WikiFrontmatter,
            {
                "source": "https://docs.example.com/wiki/architecture",
                "ingested_at": datetime(2026, 5, 30, 12, 0, 0),
                "doc_type": "wiki",
            },
        )
