"""Golden tests for the OpenAPI operation renderer (050.003-T / T3)."""

from docline.readers.openapi.render import render_operation

_ROOT = {
    "openapi": "3.1.0",
    "components": {"schemas": {"Widget": {"type": "object"}}},
}

_GET_OP = {
    "operationId": "getWidget",
    "summary": "Get a widget",
    "description": "Returns a single widget by id.",
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
            "description": "Widget id",
        },
        {"name": "verbose", "in": "query", "required": False, "schema": {"type": "boolean"}},
    ],
    "responses": {
        "200": {
            "description": "OK",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Widget"}}},
        },
        "404": {"description": "Not found"},
    },
    "security": [{"apiKey": []}],
}

_GET_EXPECTED = """# GET /widgets/{id}

Get a widget

Returns a single widget by id.

## Parameters

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string | yes | Widget id |
| `verbose` | query | boolean | no |  |

## Responses

| Status | Description | Schema |
| --- | --- | --- |
| `200` | OK | [Widget](../schemas/Widget.md) |
| `404` | Not found |  |

## Security

- `apiKey`"""

_POST_OP = {
    "operationId": "createWidget",
    "summary": "Create a widget",
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Widget"}}},
    },
    "responses": {
        "201": {
            "description": "Created",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Widget"}}},
        }
    },
}

_POST_EXPECTED = """# POST /widgets

Create a widget

## Request body

Required: yes

| Content type | Schema |
| --- | --- |
| `application/json` | [Widget](../schemas/Widget.md) |

## Responses

| Status | Description | Schema |
| --- | --- | --- |
| `201` | Created | [Widget](../schemas/Widget.md) |"""

_EMPTY_OP = {
    "operationId": "ping",
    "summary": "Health check",
    "responses": {"204": {"description": "No content"}},
}

_EMPTY_EXPECTED = """# GET /ping

Health check

## Responses

| Status | Description | Schema |
| --- | --- | --- |
| `204` | No content |  |"""


def test_render_get_operation_golden() -> None:
    """A GET operation renders byte-for-byte to the expected Markdown."""
    result = render_operation("get", "/widgets/{id}", _GET_OP, root=_ROOT)
    assert result == _GET_EXPECTED


def test_render_post_operation_with_request_body_golden() -> None:
    """A POST operation renders its request body section and schema links."""
    result = render_operation("post", "/widgets", _POST_OP, root=_ROOT)
    assert result == _POST_EXPECTED


def test_render_operation_no_params_no_body() -> None:
    """An operation without parameters or a body omits those sections cleanly."""
    result = render_operation("get", "/ping", _EMPTY_OP, root=_ROOT)
    assert result == _EMPTY_EXPECTED
    assert "## Parameters" not in result
    assert "## Request body" not in result


def test_render_operation_method_uppercased_in_h1() -> None:
    """The HTTP method is uppercased in the H1 regardless of input case."""
    result = render_operation("GeT", "/ping", _EMPTY_OP, root=_ROOT)
    assert result.startswith("# GET /ping\n")


def test_render_operation_escapes_pipe_in_description() -> None:
    """A pipe character in a description is escaped so the table stays valid."""
    op = {
        "responses": {"200": {"description": "a | b"}},
    }
    result = render_operation("get", "/x", op, root=_ROOT)
    assert r"a \| b" in result


def test_render_operation_custom_schema_href() -> None:
    """A custom schema_href callable controls the emitted link target."""
    result = render_operation(
        "post",
        "/widgets",
        _POST_OP,
        root=_ROOT,
        schema_href=lambda name: f"schemas/{name}.md",
    )
    assert "[Widget](schemas/Widget.md)" in result
