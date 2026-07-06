"""Swagger 2.0 -> OpenAPI 3.0.x pre-conversion (051.001-T / T1).

Upgrades a Swagger 2.0 specification model to OpenAPI 3.0.3 so the existing 3.x
renderer (050-F) can ingest it without a parallel 2.0 code path. The transform
is a pure function over the parsed mapping; it walks the literal JSON tree and
never follows ``$ref`` values, so it is inherently cycle-safe.

Scope (v1): the 2.0 -> 3.x *model* upgrade only. External / split-file ``$ref``
values (e.g. ``./definitions.json#/definitions/X``) are preserved verbatim —
their resolution remains a separate, security-bounded follow-up (stash
``D9AC2CD6``).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch")

# Swagger 2.0 local pointer prefixes -> OpenAPI 3.x component pointer prefixes.
_REF_REWRITES = (
    ("#/definitions/", "#/components/schemas/"),
    ("#/parameters/", "#/components/parameters/"),
    ("#/responses/", "#/components/responses/"),
)

# Swagger 2.0 non-body parameter keys that describe the value's schema.
_PARAM_SCHEMA_KEYS = (
    "type",
    "format",
    "items",
    "enum",
    "default",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "multipleOf",
)

# Swagger 2.0 non-body parameter keys carried through to the OpenAPI parameter.
_PARAM_TOP_KEYS = ("name", "in", "description", "required", "deprecated", "allowEmptyValue")

# Swagger 2.0 oauth2 flow name -> OpenAPI 3.x flow name.
_OAUTH_FLOWS = {
    "implicit": "implicit",
    "password": "password",
    "application": "clientCredentials",
    "accessCode": "authorizationCode",
}


def swagger2_to_openapi3(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a Swagger 2.0 spec mapping into an OpenAPI 3.0.3 spec dict.

    Args:
        spec: The parsed Swagger 2.0 specification.

    Returns:
        A new OpenAPI 3.0.3 specification dict. The input is not mutated.
    """
    result: dict[str, Any] = {"openapi": "3.0.3"}
    if isinstance(spec.get("info"), Mapping):
        result["info"] = copy.deepcopy(dict(spec["info"]))

    servers = _build_servers(spec)
    if servers:
        result["servers"] = servers

    global_consumes = _as_str_list(spec.get("consumes")) or ["application/json"]
    global_produces = _as_str_list(spec.get("produces")) or ["application/json"]

    paths = spec.get("paths")
    result["paths"] = (
        _convert_paths(paths, global_consumes, global_produces)
        if isinstance(paths, Mapping)
        else {}
    )

    components: dict[str, Any] = {}
    if isinstance(spec.get("definitions"), Mapping):
        components["schemas"] = _rewrite_refs(spec["definitions"])
    if isinstance(spec.get("parameters"), Mapping):
        components["parameters"] = {
            key: _convert_parameter(value)
            for key, value in spec["parameters"].items()
            if isinstance(value, Mapping)
        }
    if isinstance(spec.get("responses"), Mapping):
        components["responses"] = {
            key: _convert_response(value, global_produces)
            for key, value in spec["responses"].items()
            if isinstance(value, Mapping)
        }
    if isinstance(spec.get("securityDefinitions"), Mapping):
        components["securitySchemes"] = _convert_security_schemes(spec["securityDefinitions"])
    if components:
        result["components"] = components

    if "security" in spec:
        result["security"] = _rewrite_refs(spec["security"])
    if isinstance(spec.get("tags"), list):
        result["tags"] = _rewrite_refs(spec["tags"])

    return result


def _as_str_list(value: Any) -> list[str] | None:
    """Return *value* as a list of strings, or ``None`` when not applicable."""
    if isinstance(value, list):
        strings = [item for item in value if isinstance(item, str)]
        return strings or None
    return None


def _build_servers(spec: Mapping[str, Any]) -> list[dict[str, str]]:
    """Build an OpenAPI ``servers`` list from 2.0 host/basePath/schemes."""
    base_path = spec.get("basePath") if isinstance(spec.get("basePath"), str) else ""
    host = spec.get("host")
    if not isinstance(host, str) or not host:
        return [{"url": base_path}] if base_path else []
    schemes = _as_str_list(spec.get("schemes")) or ["https"]
    return [{"url": f"{scheme}://{host}{base_path}"} for scheme in schemes]


def _rewrite_ref_value(ref: str) -> str:
    """Rewrite a local Swagger 2.0 ``$ref`` pointer to its 3.x equivalent.

    External / split-file refs (anything not starting with a known local
    prefix) are returned unchanged.
    """
    for old, new in _REF_REWRITES:
        if ref.startswith(old):
            return new + ref[len(old) :]
    return ref


def _rewrite_refs(node: Any) -> Any:
    """Deep-copy *node*, rewriting local ``$ref`` string values to 3.x pointers."""
    if isinstance(node, Mapping):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                out[key] = _rewrite_ref_value(value)
            else:
                out[key] = _rewrite_refs(value)
        return out
    if isinstance(node, list):
        return [_rewrite_refs(item) for item in node]
    return node


def _convert_paths(
    paths: Mapping[str, Any], consumes: list[str], produces: list[str]
) -> dict[str, Any]:
    """Convert the 2.0 ``paths`` object to 3.x."""
    out: dict[str, Any] = {}
    for path, item in paths.items():
        if not isinstance(item, Mapping):
            continue
        new_item: dict[str, Any] = {}
        for key, value in item.items():
            if key in _HTTP_METHODS and isinstance(value, Mapping):
                new_item[key] = _convert_operation(value, consumes, produces)
            elif key == "parameters" and isinstance(value, list):
                non_body, _ = _split_convert_params(value, consumes)
                if non_body:
                    new_item[key] = non_body
            elif key == "$ref" and isinstance(value, str):
                new_item[key] = _rewrite_ref_value(value)
            else:
                new_item[key] = _rewrite_refs(value)
        out[path] = new_item
    return out


def _convert_operation(
    op: Mapping[str, Any], consumes: list[str], produces: list[str]
) -> dict[str, Any]:
    """Convert a single 2.0 operation object to 3.x."""
    op_consumes = _as_str_list(op.get("consumes")) or consumes
    op_produces = _as_str_list(op.get("produces")) or produces

    new_op: dict[str, Any] = {}
    for key, value in op.items():
        if key == "parameters" and isinstance(value, list):
            non_body, request_body = _split_convert_params(value, op_consumes)
            if non_body:
                new_op["parameters"] = non_body
            if request_body is not None:
                new_op["requestBody"] = request_body
        elif key == "responses" and isinstance(value, Mapping):
            new_op["responses"] = {
                str(code): _convert_response(resp, op_produces) for code, resp in value.items()
            }
        elif key in ("consumes", "produces", "schemes"):
            continue  # folded into content / servers in 3.x
        else:
            new_op[key] = _rewrite_refs(value)
    return new_op


def _param_schema(param: Mapping[str, Any]) -> dict[str, Any]:
    """Extract a 3.x schema object from a 2.0 non-body parameter."""
    schema: dict[str, Any] = {}
    for key in _PARAM_SCHEMA_KEYS:
        if key in param:
            schema[key] = _rewrite_refs(param[key])
    return schema


def _convert_parameter(param: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a 2.0 non-body parameter to 3.x (type/format -> schema)."""
    ref = param.get("$ref")
    if isinstance(ref, str):
        return {"$ref": _rewrite_ref_value(ref)}

    new_param: dict[str, Any] = {}
    for key in _PARAM_TOP_KEYS:
        if key in param:
            new_param[key] = param[key]
    schema = _param_schema(param)
    if schema:
        new_param["schema"] = schema
    return new_param


def _split_convert_params(
    params: list[Any], consumes: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Split a 2.0 parameter list into 3.x (non-body params, requestBody).

    Body parameters become a ``requestBody``; ``formData`` parameters are
    aggregated into a form-encoded request body; everything else is converted
    in place.
    """
    non_body: list[dict[str, Any]] = []
    request_body: dict[str, Any] | None = None
    form_properties: dict[str, Any] = {}
    form_required: list[str] = []

    for param in params:
        if not isinstance(param, Mapping):
            continue
        if isinstance(param.get("$ref"), str):
            non_body.append({"$ref": _rewrite_ref_value(param["$ref"])})
            continue

        location = param.get("in")
        if location == "body":
            schema = _rewrite_refs(param.get("schema", {}))
            request_body = {"content": {ct: {"schema": schema} for ct in consumes}}
            if param.get("required"):
                request_body["required"] = True
            if isinstance(param.get("description"), str):
                request_body["description"] = param["description"]
        elif location == "formData":
            name = param.get("name", "")
            form_properties[name] = _param_schema(param)
            if param.get("required"):
                form_required.append(name)
        else:
            non_body.append(_convert_parameter(param))

    if form_properties and request_body is None:
        form_schema: dict[str, Any] = {"type": "object", "properties": form_properties}
        if form_required:
            form_schema["required"] = form_required
        request_body = {"content": {"application/x-www-form-urlencoded": {"schema": form_schema}}}

    return non_body, request_body


def _convert_response(resp: Mapping[str, Any], produces: list[str]) -> dict[str, Any]:
    """Convert a 2.0 response object to 3.x (schema -> content)."""
    ref = resp.get("$ref")
    if isinstance(ref, str):
        return {"$ref": _rewrite_ref_value(ref)}

    new_resp: dict[str, Any] = {}
    description = resp.get("description")
    new_resp["description"] = description if isinstance(description, str) else ""

    schema = resp.get("schema")
    if schema is not None:
        rewritten = _rewrite_refs(schema)
        new_resp["content"] = {ct: {"schema": rewritten} for ct in produces}
    if isinstance(resp.get("headers"), Mapping):
        new_resp["headers"] = _rewrite_refs(resp["headers"])
    return new_resp


def _convert_security_schemes(sec_defs: Mapping[str, Any]) -> dict[str, Any]:
    """Convert 2.0 ``securityDefinitions`` to 3.x ``securitySchemes``."""
    out: dict[str, Any] = {}
    for name, definition in sec_defs.items():
        if not isinstance(definition, Mapping):
            continue
        kind = definition.get("type")
        if kind == "basic":
            out[name] = {"type": "http", "scheme": "basic"}
        elif kind == "apiKey":
            scheme: dict[str, Any] = {"type": "apiKey"}
            if "name" in definition:
                scheme["name"] = definition["name"]
            if "in" in definition:
                scheme["in"] = definition["in"]
            out[name] = scheme
        elif kind == "oauth2":
            flow_name = _OAUTH_FLOWS.get(str(definition.get("flow")), "implicit")
            flow_obj: dict[str, Any] = {}
            if "authorizationUrl" in definition:
                flow_obj["authorizationUrl"] = definition["authorizationUrl"]
            if "tokenUrl" in definition:
                flow_obj["tokenUrl"] = definition["tokenUrl"]
            flow_obj["scopes"] = definition.get("scopes", {})
            out[name] = {"type": "oauth2", "flows": {flow_name: flow_obj}}
        else:
            out[name] = _rewrite_refs(definition)
    return out


__all__ = ["swagger2_to_openapi3"]
