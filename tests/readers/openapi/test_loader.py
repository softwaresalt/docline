"""Tests for the OpenAPI loader and local ``$ref`` resolver (050.002-T / T2)."""

import json
from pathlib import Path

import pytest

from docline.readers.openapi.errors import OpenApiParseError, OpenApiRefError
from docline.readers.openapi.loader import (
    component_name_from_ref,
    deref,
    is_local_ref,
    load_spec,
    resolve_pointer,
)

_SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "Demo", "version": "1.0.0"},
    "paths": {},
    "components": {
        "schemas": {
            "Node": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "child": {"$ref": "#/components/schemas/Node"},
                },
            },
            "Leaf": {"type": "object", "properties": {"value": {"type": "integer"}}},
        },
        "parameters": {
            "RealParam": {"name": "id", "in": "query", "schema": {"type": "string"}},
            "ChainTop": {"$ref": "#/components/parameters/RealParam"},
            "AliasA": {"$ref": "#/components/parameters/AliasB"},
            "AliasB": {"$ref": "#/components/parameters/AliasA"},
        },
    },
}


def test_load_spec_from_json_file(tmp_path: Path) -> None:
    """A JSON spec file loads into a mapping."""
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(_SPEC), encoding="utf-8")
    loaded = load_spec(path)
    assert loaded["openapi"] == "3.1.0"
    assert "components" in loaded


def test_load_spec_from_yaml_file_matches_json(tmp_path: Path) -> None:
    """JSON and YAML inputs load into equivalent mappings."""
    json_path = tmp_path / "spec.json"
    json_path.write_text(json.dumps(_SPEC), encoding="utf-8")
    yaml_path = tmp_path / "spec.yaml"
    yaml_path.write_text(
        "openapi: 3.1.0\ninfo:\n  title: Demo\n  version: 1.0.0\npaths: {}\n",
        encoding="utf-8",
    )
    from_json = load_spec(json_path)
    from_yaml = load_spec(yaml_path)
    assert from_json["openapi"] == from_yaml["openapi"]
    assert from_json["info"] == from_yaml["info"]


def test_load_spec_from_text() -> None:
    """load_spec accepts raw text as well as a path."""
    loaded = load_spec(json.dumps(_SPEC))
    assert loaded["info"]["title"] == "Demo"


def test_load_spec_malformed_raises(tmp_path: Path) -> None:
    """Unparseable content raises a typed OpenApiParseError."""
    path = tmp_path / "bad.json"
    path.write_text("{ not: valid: json: ]", encoding="utf-8")
    with pytest.raises(OpenApiParseError):
        load_spec(path)


def test_load_spec_non_mapping_raises() -> None:
    """A non-mapping root (list/scalar) raises OpenApiParseError."""
    with pytest.raises(OpenApiParseError):
        load_spec(json.dumps([1, 2, 3]))


def test_load_spec_missing_file_raises(tmp_path: Path) -> None:
    """A missing file raises OpenApiParseError (not a bare OSError leak)."""
    with pytest.raises(OpenApiParseError):
        load_spec(tmp_path / "nope.json")


def test_resolve_pointer_nested() -> None:
    """A nested JSON pointer resolves to the target node."""
    target = resolve_pointer(_SPEC, "#/components/schemas/Leaf/properties/value")
    assert target == {"type": "integer"}


def test_resolve_pointer_component() -> None:
    """A component-schema pointer resolves to the schema object."""
    target = resolve_pointer(_SPEC, "#/components/schemas/Leaf")
    assert target["type"] == "object"


def test_resolve_pointer_external_raises() -> None:
    """An external/split-file ref raises OpenApiRefError (not fetched)."""
    with pytest.raises(OpenApiRefError):
        resolve_pointer(_SPEC, "common.json#/components/schemas/Foo")


def test_resolve_pointer_unresolvable_raises() -> None:
    """A local ref to a missing target raises OpenApiRefError."""
    with pytest.raises(OpenApiRefError):
        resolve_pointer(_SPEC, "#/components/schemas/DoesNotExist")


def test_is_local_ref() -> None:
    """Local refs start with ``#/``; everything else is non-local."""
    assert is_local_ref("#/components/schemas/Leaf") is True
    assert is_local_ref("common.json#/x") is False
    assert is_local_ref("https://example.com/s.json#/x") is False


def test_component_name_from_ref() -> None:
    """The component name is the last pointer segment."""
    assert component_name_from_ref("#/components/schemas/Leaf") == "Leaf"
    assert component_name_from_ref("#/components/schemas/My.Type") == "My.Type"


def test_deref_one_hop() -> None:
    """deref follows a single local ref node to its target object."""
    resolved = deref({"$ref": "#/components/schemas/Leaf"}, _SPEC)
    assert resolved["type"] == "object"


def test_deref_passthrough_non_ref() -> None:
    """deref returns non-ref nodes unchanged (identity)."""
    node = {"type": "string"}
    assert deref(node, _SPEC) is node


def test_deref_chain_resolves() -> None:
    """deref follows a chain of ref-to-ref nodes to the concrete target."""
    resolved = deref({"$ref": "#/components/parameters/ChainTop"}, _SPEC)
    assert resolved["name"] == "id"
    assert resolved["in"] == "query"


def test_deref_circular_chain_raises() -> None:
    """A circular ref chain (A -> B -> A) raises rather than looping forever."""
    with pytest.raises(OpenApiRefError):
        deref({"$ref": "#/components/parameters/AliasA"}, _SPEC)


def test_deref_external_ref_left_unresolved() -> None:
    """deref leaves an external ref unresolved (not fetched)."""
    node = {"$ref": "other.json#/components/schemas/Y"}
    assert deref(node, _SPEC) == {"$ref": "other.json#/components/schemas/Y"}


def test_deref_unresolvable_local_raises() -> None:
    """deref surfaces OpenApiRefError for an unresolvable local ref."""
    with pytest.raises(OpenApiRefError):
        deref({"$ref": "#/components/schemas/Missing"}, _SPEC)
