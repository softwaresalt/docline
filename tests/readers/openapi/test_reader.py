"""Tests for OpenAPI BaseDocument assembly (050.005-T / T5)."""

import json
from pathlib import Path

import pytest

from docline.readers.openapi.reader import read_openapi_spec
from docline.schema.models import BaseDocument

_SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "Demo", "version": "1.0.0"},
    "paths": {
        "/widgets/{id}": {
            "get": {
                "operationId": "getWidget",
                "summary": "Get a widget",
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Widget"}}
                        },
                    }
                },
            }
        },
        "/widgets": {
            "get": {
                "summary": "List widgets",
                "responses": {"200": {"description": "OK"}},
            }
        },
    },
    "components": {
        "schemas": {"Widget": {"type": "object", "properties": {"id": {"type": "string"}}}}
    },
}


def _write_spec(tmp_path: Path) -> Path:
    path = tmp_path / "demo.json"
    path.write_text(json.dumps(_SPEC), encoding="utf-8")
    return path


def test_read_openapi_spec_emits_operation_and_schema_docs(tmp_path: Path) -> None:
    """The reader emits one doc per operation and per named component schema."""
    docs = read_openapi_spec(_write_spec(tmp_path), source_uri="specs/demo.json")
    paths = {doc.relative_path for doc in docs}
    assert paths == {
        "operations/getWidget.md",
        "operations/get-widgets.md",
        "schemas/Widget.md",
    }


def test_documents_validate_as_base_document(tmp_path: Path) -> None:
    """Every emitted document round-trips through BaseDocument validation."""
    docs = read_openapi_spec(_write_spec(tmp_path), source_uri="specs/demo.json")
    for doc in docs:
        assert isinstance(doc.document, BaseDocument)
        # Re-validate from a serialized dump to prove contract conformance.
        BaseDocument.model_validate(doc.document.model_dump())


def test_operation_doc_type_and_source(tmp_path: Path) -> None:
    """Operation docs carry doc_type=openapi_operation and a spec-uri#operationId source."""
    docs = read_openapi_spec(_write_spec(tmp_path), source_uri="specs/demo.json")
    op = next(d for d in docs if d.relative_path == "operations/getWidget.md")
    assert op.document.frontmatter.doc_type == "openapi_operation"
    assert op.document.frontmatter.source == "specs/demo.json#getWidget"
    assert op.document.body.startswith("# GET /widgets/{id}")


def test_schema_doc_type_and_source(tmp_path: Path) -> None:
    """Schema docs carry doc_type=openapi_schema and a component-keyed source."""
    docs = read_openapi_spec(_write_spec(tmp_path), source_uri="specs/demo.json")
    schema = next(d for d in docs if d.relative_path == "schemas/Widget.md")
    assert schema.document.frontmatter.doc_type == "openapi_schema"
    assert schema.document.frontmatter.source == "specs/demo.json#/components/schemas/Widget"


def test_content_sha256_and_contract_defaults(tmp_path: Path) -> None:
    """content_sha256 is a 64-char digest and contract defaults are preserved."""
    docs = read_openapi_spec(_write_spec(tmp_path), source_uri="specs/demo.json")
    for doc in docs:
        fm = doc.document.frontmatter
        assert len(fm.content_sha256) == 64
        assert all(c in "0123456789abcdef" for c in fm.content_sha256)
        assert fm.chunk_strategy == "h1-h2-h3"
        assert fm.schema_version == "1.0"


def test_operation_without_operation_id_derives_slug(tmp_path: Path) -> None:
    """An operation lacking operationId gets a deterministic derived id."""
    docs = read_openapi_spec(_write_spec(tmp_path), source_uri="specs/demo.json")
    derived = next(d for d in docs if d.relative_path == "operations/get-widgets.md")
    assert derived.document.frontmatter.doc_type == "openapi_operation"
    # The derived id is reflected in the source fragment.
    assert derived.document.frontmatter.source == "specs/demo.json#get-widgets"


def test_no_dangling_links_across_all_docs(tmp_path: Path) -> None:
    """Every cross-doc link target maps to a produced document path."""
    docs = read_openapi_spec(_write_spec(tmp_path), source_uri="specs/demo.json")
    produced = {doc.relative_path for doc in docs}
    for doc in docs:
        namespace = doc.document.frontmatter.docline or {}
        for link in namespace.get("cross_doc_links", []):
            assert link["target_path"] in produced


def test_source_uri_defaults_to_path(tmp_path: Path) -> None:
    """When source_uri is omitted, the spec path is used as the source base."""
    spec_path = _write_spec(tmp_path)
    docs = read_openapi_spec(spec_path)
    op = next(d for d in docs if d.relative_path == "operations/getWidget.md")
    assert op.document.frontmatter.source == f"{spec_path.as_posix()}#getWidget"


def test_read_yaml_spec_with_integer_status_codes(tmp_path: Path) -> None:
    """A YAML spec (integer status codes) renders end-to-end without error."""
    spec_path = tmp_path / "demo.yaml"
    spec_path.write_text(
        "openapi: 3.1.0\n"
        "info:\n  title: Demo\n  version: 1.0.0\n"
        "paths:\n"
        "  /ping:\n"
        "    get:\n"
        "      operationId: ping\n"
        "      responses:\n"
        "        200:\n"
        "          description: OK\n",
        encoding="utf-8",
    )
    docs = read_openapi_spec(spec_path, source_uri="specs/demo.yaml")
    op = next(d for d in docs if d.relative_path == "operations/ping.md")
    assert op.document.frontmatter.doc_type == "openapi_operation"
    assert "| `200` | OK |  |" in op.document.body


def test_read_swagger_2_cross_file_link(tmp_path: Path) -> None:
    """A corpus ingest cross-links an operation to an external file's schema doc (053-F)."""
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "types.json").write_text(
        json.dumps(
            {
                "swagger": "2.0",
                "info": {"title": "T", "version": "1"},
                "definitions": {
                    "Widget": {"type": "object", "properties": {"id": {"type": "string"}}}
                },
            }
        ),
        encoding="utf-8",
    )
    swagger = {
        "swagger": "2.0",
        "info": {"title": "S", "version": "1"},
        "paths": {
            "/w": {
                "get": {
                    "operationId": "getW",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "schema": {"$ref": "./types.json#/definitions/Widget"},
                        }
                    },
                }
            }
        },
    }
    (tmp_path / "svc" / "swagger.json").write_text(json.dumps(swagger), encoding="utf-8")

    docs = read_openapi_spec(
        tmp_path / "svc" / "swagger.json",
        source_uri="svc/swagger.json",
        source_path="svc/swagger.json",
        corpus_root=tmp_path,
    )
    op = next(d for d in docs if d.relative_path == "operations/getW.md")
    # The external ref becomes a cross-file Markdown link...
    assert "[Widget](../../types/schemas/Widget.md)" in op.document.body
    # ...harvested as a corpus-relative graph edge to the target file's schema doc.
    links = (op.document.frontmatter.docline or {}).get("cross_doc_links", [])
    targets = {link["target_path"] for link in links}
    assert "svc/types/schemas/Widget.md" in targets


def test_read_openapi_spec_without_corpus_no_external_links(tmp_path: Path) -> None:
    """Without corpus_root, external refs are not linked (single-file behavior)."""
    swagger = {
        "swagger": "2.0",
        "info": {"title": "S", "version": "1"},
        "paths": {
            "/w": {
                "get": {
                    "operationId": "getW",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "schema": {"$ref": "./types.json#/definitions/Widget"},
                        }
                    },
                }
            }
        },
    }
    spec_path = tmp_path / "swagger.json"
    spec_path.write_text(json.dumps(swagger), encoding="utf-8")
    docs = read_openapi_spec(spec_path, source_uri="s.json")
    op = next(d for d in docs if d.relative_path == "operations/getW.md")
    assert "](" not in op.document.body  # no link emitted for the external ref


def test_read_openapi_spec_rejects_unknown_root(tmp_path: Path) -> None:
    """A spec that is neither OpenAPI 3.x nor Swagger 2.0 is rejected."""
    from docline.readers.openapi.errors import OpenApiError

    spec_path = tmp_path / "bad.json"
    spec_path.write_text(
        json.dumps({"info": {"title": "L", "version": "1"}, "paths": {}}),
        encoding="utf-8",
    )
    with pytest.raises(OpenApiError):
        read_openapi_spec(spec_path)


def test_read_swagger_2_spec_converts_and_renders(tmp_path: Path) -> None:
    """A self-contained Swagger 2.0 spec is converted and rendered end-to-end (051-F)."""
    spec = {
        "swagger": "2.0",
        "info": {"title": "W", "version": "1"},
        "paths": {
            "/w/{id}": {
                "get": {
                    "operationId": "getW",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "type": "string"}
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "schema": {"$ref": "#/definitions/W"},
                        }
                    },
                }
            }
        },
        "definitions": {"W": {"type": "object", "properties": {"id": {"type": "string"}}}},
    }
    spec_path = tmp_path / "s2.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    docs = read_openapi_spec(spec_path, source_uri="specs/s2.json")
    paths = {d.relative_path for d in docs}
    assert "operations/getW.md" in paths
    assert "schemas/W.md" in paths

    op = next(d for d in docs if d.relative_path == "operations/getW.md")
    assert op.document.frontmatter.doc_type == "openapi_operation"
    # the 2.0 #/definitions/W ref was rewritten and links to the schema doc
    assert "[W](../schemas/W.md)" in op.document.body
