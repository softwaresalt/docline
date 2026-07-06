"""Tests for the OpenAPI schema renderer and operation->schema edges (050.004-T / T4)."""

from pathlib import Path

from docline.process.cross_doc_links import resolve_cross_doc_links
from docline.readers.openapi.render import render_operation, render_schema

_ROOT = {
    "openapi": "3.1.0",
    "components": {
        "schemas": {
            "Widget": {
                "type": "object",
                "description": "A widget.",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string", "description": "Identifier"},
                    "parent": {"$ref": "#/components/schemas/Widget"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
            "Color": {"type": "string", "enum": ["red", "green", "blue"]},
        }
    },
}

_WIDGET_EXPECTED = """# Widget

A widget.

Type: object

## Properties

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | yes | Identifier |
| `parent` | [Widget](Widget.md) | no |  |
| `tags` | array of string | no |  |"""

_COLOR_EXPECTED = """# Color

Type: string

## Values

- `red`
- `green`
- `blue`"""


def test_render_object_schema_golden() -> None:
    """An object schema renders a properties table with nested schema links."""
    result = render_schema("Widget", _ROOT["components"]["schemas"]["Widget"], root=_ROOT)
    assert result == _WIDGET_EXPECTED


def test_render_enum_schema_golden() -> None:
    """A string enum schema renders a Values list."""
    result = render_schema("Color", _ROOT["components"]["schemas"]["Color"], root=_ROOT)
    assert result == _COLOR_EXPECTED


def test_schema_self_reference_links_to_sibling_doc() -> None:
    """A schema->schema self reference links to a sibling schema document."""
    result = render_schema("Widget", _ROOT["components"]["schemas"]["Widget"], root=_ROOT)
    _, links = resolve_cross_doc_links(result, current_rel_path=Path("schemas/Widget.md"))
    targets = {link["target_path"] for link in links}
    assert "schemas/Widget.md" in targets


def test_operation_to_schema_edge_shape() -> None:
    """An operation->schema $ref harvests as a cross-doc edge with the expected shape."""
    operation = {
        "operationId": "getWidget",
        "responses": {
            "200": {
                "description": "OK",
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/Widget"}}
                },
            }
        },
    }
    body = render_operation("get", "/widgets/{id}", operation, root=_ROOT)
    _, links = resolve_cross_doc_links(body, current_rel_path=Path("operations/getWidget.md"))
    assert links == [
        {
            "target_path": "schemas/Widget.md",
            "anchor": None,
            "link_text": "Widget",
            "cross_product": False,
        }
    ]


def test_operation_schema_links_are_not_dangling() -> None:
    """Every operation->schema link target maps to a rendered schema document."""
    operation = {
        "operationId": "getWidget",
        "responses": {
            "200": {
                "description": "OK",
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/Widget"}}
                },
            }
        },
    }
    body = render_operation("get", "/widgets", operation, root=_ROOT)
    _, links = resolve_cross_doc_links(body, current_rel_path=Path("operations/x.md"))
    schema_docs = {f"schemas/{name}.md" for name in _ROOT["components"]["schemas"]}
    for link in links:
        assert link["target_path"] in schema_docs


def test_render_schema_composition() -> None:
    """A schema built from allOf lists its members (links + inline types)."""
    root = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Base": {"type": "object"},
                "Derived": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Base"},
                        {"type": "object", "properties": {"extra": {"type": "string"}}},
                    ]
                },
            }
        },
    }
    result = render_schema("Derived", root["components"]["schemas"]["Derived"], root=root)
    assert "## Composition (allOf)" in result
    assert "- [Base](Base.md)" in result
