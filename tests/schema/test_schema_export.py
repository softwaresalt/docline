"""Regression tests for the JSON Schema export surface (010.005-T)."""

from __future__ import annotations

import json

from docline.schema.export import (
    BASE_FRONTMATTER_SCHEMA_ID,
    JSON_SCHEMA_DIALECT,
    export_base_frontmatter_schema,
    export_base_frontmatter_schema_json,
)


def test_exported_schema_declares_draft_2020_12_dialect() -> None:
    """Exported schema must declare the JSON Schema Draft 2020-12 dialect."""
    schema = export_base_frontmatter_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert JSON_SCHEMA_DIALECT == "https://json-schema.org/draft/2020-12/schema"


def test_exported_schema_declares_stable_id() -> None:
    """Exported schema must declare a stable $id URI for graphtor consumers."""
    schema = export_base_frontmatter_schema()
    assert schema["$id"] == BASE_FRONTMATTER_SCHEMA_ID
    assert BASE_FRONTMATTER_SCHEMA_ID.startswith("https://")
    assert "base-frontmatter" in BASE_FRONTMATTER_SCHEMA_ID
    assert "v1" in BASE_FRONTMATTER_SCHEMA_ID


def test_exported_schema_includes_v1_fields() -> None:
    """Exported schema must include all BaseFrontmatter v1 fields."""
    schema = export_base_frontmatter_schema()
    properties = schema["properties"]
    expected = {
        "title",
        "source",
        "ingested_at",
        "doc_type",
        "description",
        "content_sha256",
        "source_path",
        "chunk_strategy",
        "schema_version",
        "docline",
    }
    assert expected.issubset(set(properties.keys()))


def test_exported_schema_json_is_sort_keys_normalized() -> None:
    """Exported schema JSON string must be sort_keys normalized for determinism."""
    payload = export_base_frontmatter_schema_json()
    parsed = json.loads(payload)
    re_serialized = json.dumps(parsed, indent=2, sort_keys=True)
    assert payload == re_serialized


def test_exported_schema_json_is_deterministic() -> None:
    """Two successive exports must produce byte-identical JSON output."""
    first = export_base_frontmatter_schema_json()
    second = export_base_frontmatter_schema_json()
    assert first == second
