"""Tests for the Swagger 2.0 -> OpenAPI 3.x converter (051.001-T / T1)."""

from docline.readers.openapi.convert import swagger2_to_openapi3

_SWAGGER_2 = {
    "swagger": "2.0",
    "info": {"title": "Widget API", "version": "1.0"},
    "host": "api.example.com",
    "basePath": "/v1",
    "schemes": ["https"],
    "consumes": ["application/json"],
    "produces": ["application/json"],
    "securityDefinitions": {
        "key": {"type": "apiKey", "name": "api-key", "in": "header"},
        "oauth": {
            "type": "oauth2",
            "flow": "accessCode",
            "authorizationUrl": "https://auth",
            "tokenUrl": "https://token",
            "scopes": {"read": "read access"},
        },
    },
    "paths": {
        "/widgets/{id}": {
            "get": {
                "operationId": "getWidget",
                "summary": "Get a widget",
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "type": "string"},
                    {"name": "verbose", "in": "query", "type": "boolean"},
                ],
                "responses": {
                    "200": {
                        "description": "OK",
                        "schema": {"$ref": "#/definitions/Widget"},
                    }
                },
            },
            "post": {
                "operationId": "createWidget",
                "consumes": ["application/json"],
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {"$ref": "#/definitions/Widget"},
                    }
                ],
                "responses": {"201": {"description": "Created"}},
            },
        }
    },
    "definitions": {
        "Widget": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "parent": {"$ref": "#/definitions/Widget"},
            },
        }
    },
}


def test_root_version_becomes_openapi_3x() -> None:
    out = swagger2_to_openapi3(_SWAGGER_2)
    assert out["openapi"].startswith("3.")
    assert "swagger" not in out


def test_definitions_move_to_components_schemas() -> None:
    out = swagger2_to_openapi3(_SWAGGER_2)
    assert "Widget" in out["components"]["schemas"]
    assert "definitions" not in out


def test_local_definition_refs_are_rewritten() -> None:
    out = swagger2_to_openapi3(_SWAGGER_2)
    # schema self-ref rewritten to components pointer
    parent = out["components"]["schemas"]["Widget"]["properties"]["parent"]
    assert parent == {"$ref": "#/components/schemas/Widget"}
    # response schema ref rewritten
    resp = out["paths"]["/widgets/{id}"]["get"]["responses"]["200"]
    assert resp["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/Widget"}


def test_servers_built_from_host_basepath_schemes() -> None:
    out = swagger2_to_openapi3(_SWAGGER_2)
    assert out["servers"] == [{"url": "https://api.example.com/v1"}]


def test_non_body_param_type_wrapped_in_schema() -> None:
    out = swagger2_to_openapi3(_SWAGGER_2)
    params = out["paths"]["/widgets/{id}"]["get"]["parameters"]
    id_param = next(p for p in params if p["name"] == "id")
    assert id_param["in"] == "path"
    assert id_param["required"] is True
    assert id_param["schema"] == {"type": "string"}
    assert "type" not in id_param


def test_body_param_becomes_request_body() -> None:
    out = swagger2_to_openapi3(_SWAGGER_2)
    post = out["paths"]["/widgets/{id}"]["post"]
    assert "requestBody" in post
    assert post["requestBody"]["required"] is True
    schema = post["requestBody"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/Widget"}
    # the body param is removed from the parameters list
    assert all(p.get("in") != "body" for p in post.get("parameters", []))


def test_response_schema_moves_to_content() -> None:
    out = swagger2_to_openapi3(_SWAGGER_2)
    resp = out["paths"]["/widgets/{id}"]["get"]["responses"]["200"]
    assert "schema" not in resp
    assert "application/json" in resp["content"]
    assert resp["description"] == "OK"


def test_response_without_schema_keeps_description() -> None:
    out = swagger2_to_openapi3(_SWAGGER_2)
    resp = out["paths"]["/widgets/{id}"]["post"]["responses"]["201"]
    assert resp["description"] == "Created"
    assert "content" not in resp


def test_security_definitions_become_security_schemes() -> None:
    out = swagger2_to_openapi3(_SWAGGER_2)
    schemes = out["components"]["securitySchemes"]
    assert schemes["key"] == {"type": "apiKey", "name": "api-key", "in": "header"}
    assert schemes["oauth"]["type"] == "oauth2"
    assert "authorizationCode" in schemes["oauth"]["flows"]
    assert schemes["oauth"]["flows"]["authorizationCode"]["scopes"] == {"read": "read access"}


def test_external_refs_are_left_untouched() -> None:
    spec = {
        "swagger": "2.0",
        "info": {"title": "X", "version": "1"},
        "paths": {
            "/x": {
                "get": {
                    "operationId": "x",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "schema": {"$ref": "./definitions.json#/definitions/Ext"},
                        }
                    },
                }
            }
        },
    }
    out = swagger2_to_openapi3(spec)
    resp = out["paths"]["/x"]["get"]["responses"]["200"]
    # external/split-file ref is preserved verbatim (resolution deferred, D9AC2CD6)
    assert (
        resp["content"]["application/json"]["schema"]["$ref"]
        == "./definitions.json#/definitions/Ext"
    )


def test_definitions_only_spec_converts_schemas() -> None:
    """A definitions-only file (fabric layout) converts to components.schemas."""
    spec = {
        "swagger": "2.0",
        "info": {"title": "defs", "version": "1"},
        "definitions": {"A": {"type": "object"}, "B": {"$ref": "#/definitions/A"}},
    }
    out = swagger2_to_openapi3(spec)
    assert set(out["components"]["schemas"]) == {"A", "B"}
    assert out["components"]["schemas"]["B"] == {"$ref": "#/components/schemas/A"}
    assert out["paths"] == {}


def test_malformed_non_mapping_response_does_not_crash() -> None:
    """A non-mapping response value (malformed 2.0) is coerced, never raised (Copilot #139)."""
    spec = {
        "swagger": "2.0",
        "info": {"title": "X", "version": "1"},
        "paths": {"/x": {"get": {"operationId": "x", "responses": {"200": "OK"}}}},
    }
    out = swagger2_to_openapi3(spec)
    resp = out["paths"]["/x"]["get"]["responses"]["200"]
    assert resp == {"description": ""}


def test_form_data_params_become_form_request_body() -> None:
    """formData parameters aggregate into a form-encoded request body."""
    spec = {
        "swagger": "2.0",
        "info": {"title": "X", "version": "1"},
        "paths": {
            "/upload": {
                "post": {
                    "operationId": "upload",
                    "parameters": [
                        {"name": "name", "in": "formData", "required": True, "type": "string"},
                        {"name": "size", "in": "formData", "type": "integer"},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    out = swagger2_to_openapi3(spec)
    post = out["paths"]["/upload"]["post"]
    schema = post["requestBody"]["content"]["application/x-www-form-urlencoded"]["schema"]
    assert schema["type"] == "object"
    assert schema["properties"]["name"] == {"type": "string"}
    assert schema["properties"]["size"] == {"type": "integer"}
    assert schema["required"] == ["name"]
    # formData params are not left in the operation parameters list
    assert all(p.get("in") != "formData" for p in post.get("parameters", []))


def test_basic_auth_security_scheme() -> None:
    """A 2.0 ``basic`` securityDefinition converts to a 3.x http/basic scheme."""
    spec = {
        "swagger": "2.0",
        "info": {"title": "X", "version": "1"},
        "securityDefinitions": {"b": {"type": "basic"}},
        "paths": {},
    }
    out = swagger2_to_openapi3(spec)
    assert out["components"]["securitySchemes"]["b"] == {"type": "http", "scheme": "basic"}
