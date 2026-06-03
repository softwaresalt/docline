"""JSON Schema export surface for the docline frontmatter contract (010.005-T).

Exports the :class:`~docline.schema.models.BaseFrontmatter` Pydantic model as a
JSON Schema document conformant to Draft 2020-12 with a stable ``$id`` so that
graphtor-docs and other downstream consumers can validate document frontmatter
against the published docline contract.
"""

from __future__ import annotations

import json
from typing import Any

from docline.schema.models import BaseFrontmatter

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
"""JSON Schema dialect URI declared via ``$schema`` for the exported contract."""

BASE_FRONTMATTER_SCHEMA_ID = "https://docline.softwaresalt.dev/schema/base-frontmatter/v1.json"
"""Stable ``$id`` URI for the exported BaseFrontmatter v1 schema."""


def export_base_frontmatter_schema() -> dict[str, Any]:
    """Return the JSON Schema dict for :class:`BaseFrontmatter` with $schema and $id.

    Returns:
        A JSON Schema mapping with ``$schema`` set to the Draft 2020-12 dialect
        URI and ``$id`` set to the stable docline contract URI.
    """
    schema: dict[str, Any] = BaseFrontmatter.model_json_schema()
    schema["$schema"] = JSON_SCHEMA_DIALECT
    schema["$id"] = BASE_FRONTMATTER_SCHEMA_ID
    return schema


def export_base_frontmatter_schema_json() -> str:
    """Return a deterministic ``sort_keys`` normalized JSON string for the schema.

    Returns:
        JSON text with two-space indentation and sorted keys at every level so
        successive exports produce byte-identical output (P2-3 advisory).
    """
    return json.dumps(export_base_frontmatter_schema(), indent=2, sort_keys=True)
