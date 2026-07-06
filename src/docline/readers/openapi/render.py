"""Markdown renderers for OpenAPI operations and schemas (050.003-T / 050.004-T).

Renders deterministic Markdown from an OpenAPI 3.x object model. Operations and
named component schemas each become their own document; references between them
are emitted as relative Markdown links so docline's existing cross-doc link
harvester (:func:`docline.process.cross_doc_links.resolve_cross_doc_links`)
turns each ``$ref`` into a typed graph edge without any new contract surface.

Rendering is pure (model in, Markdown ``str`` out) and order-stable so the
output is golden-testable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from docline.readers.openapi.loader import component_name_from_ref, deref

# Callable mapping a component-schema name to the relative href of its document.
SchemaHref = Callable[[str], str]
# Callable mapping a ``$ref`` string to a relative href, or ``None`` when the ref
# should not be linked (external-denied, non-schema, or unresolvable).
RefLink = Callable[[str], "str | None"]

_SCHEMAS_REF_PREFIX = "#/components/schemas/"


def _href_to_ref_link(schema_href: SchemaHref) -> RefLink:
    """Adapt a legacy per-name ``schema_href`` into a ``$ref``-string ``RefLink``.

    Only local component-schema refs are linked (the pre-053-F behavior); all
    other refs (external, non-schema) map to ``None``.
    """

    def ref_link(ref: str) -> str | None:
        if ref.startswith(_SCHEMAS_REF_PREFIX):
            return schema_href(component_name_from_ref(ref))
        return None

    return ref_link


def default_schema_href(name: str) -> str:
    """Default schema link target: a sibling ``schemas/`` document.

    Operation documents live under ``operations/`` and schema documents under
    ``schemas/``, so an operation links to a schema via ``../schemas/{name}.md``.

    Args:
        name: Component schema name.

    Returns:
        The relative href of the schema document.
    """
    return f"../schemas/{name}.md"


def sibling_schema_href(name: str) -> str:
    """Schema-to-schema link target for documents that share the ``schemas/`` dir.

    Args:
        name: Component schema name.

    Returns:
        The relative href of a sibling schema document (``{name}.md``).
    """
    return f"{name}.md"


def _cell(value: object) -> str:
    """Render a value as a safe single-line Markdown table cell."""
    text = "" if value is None else str(value)
    return text.replace("\r", " ").replace("\n", " ").replace("|", r"\|")


def _row(cells: list[str]) -> str:
    """Render one Markdown table row from pre-escaped cell strings."""
    return "| " + " | ".join(cells) + " |"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a Markdown table. Header/cell values are used verbatim."""
    lines = [_row(headers), _row(["---"] * len(headers))]
    lines.extend(_row(row) for row in rows)
    return "\n".join(lines)


def _schema_type_summary(schema: Any, root: Mapping[str, Any], ref_link: RefLink) -> str:
    """Summarize a schema node as a short type string or component link.

    A ``$ref`` that ``ref_link`` maps to an href becomes a Markdown link to that
    schema's document; everything else collapses to a compact type description
    (``string``, ``array of integer``, ``A | B`` for unions, etc.).
    """
    if not isinstance(schema, Mapping):
        return ""

    ref = schema.get("$ref")
    if isinstance(ref, str):
        href = ref_link(ref)
        if href:
            return f"[{component_name_from_ref(ref)}]({href})"

    for key, separator in (("allOf", " & "), ("oneOf", " | "), ("anyOf", " | ")):
        members = schema.get(key)
        if isinstance(members, list) and members:
            return separator.join(
                _schema_type_summary(member, root, ref_link) for member in members
            )

    type_value = schema.get("type")
    if type_value == "array":
        items = schema.get("items")
        inner = _schema_type_summary(items, root, ref_link) if items else "any"
        return f"array of {inner}"
    if isinstance(type_value, list):
        return " | ".join(str(member) for member in type_value)
    if isinstance(type_value, str):
        fmt = schema.get("format")
        return f"{type_value} ({fmt})" if isinstance(fmt, str) and fmt else type_value
    if "enum" in schema:
        return "enum"
    if "properties" in schema:
        return "object"
    return ""


def _pick_content_schema(content: Any) -> Any:
    """Pick the representative schema from a ``content`` map.

    Prefers ``application/json`` when present; otherwise the first media type in
    sorted order for determinism.
    """
    if not isinstance(content, Mapping) or not content:
        return None
    media_type = "application/json" if "application/json" in content else sorted(content)[0]
    media = content[media_type]
    if isinstance(media, Mapping):
        return media.get("schema")
    return None


def _status_sort_key(status: str) -> tuple[int, object]:
    """Order numeric statuses ascending, then non-numeric (e.g. ``default``)."""
    try:
        return (0, int(status))
    except ValueError:
        return (1, status)


def _render_parameters(parameters: Any, root: Mapping[str, Any], ref_link: RefLink) -> str:
    """Render the Parameters section, or ``""`` when there are none."""
    if not isinstance(parameters, list) or not parameters:
        return ""

    rows: list[list[str]] = []
    for raw in parameters:
        param = deref(raw, root)
        if not isinstance(param, Mapping):
            continue
        rows.append(
            [
                _cell(f"`{param.get('name', '')}`"),
                _cell(param.get("in", "")),
                _cell(_schema_type_summary(param.get("schema"), root, ref_link)),
                _cell("yes" if param.get("required", False) else "no"),
                _cell(param.get("description", "")),
            ]
        )
    if not rows:
        return ""
    table = _table(["Name", "In", "Type", "Required", "Description"], rows)
    return f"## Parameters\n\n{table}"


def _render_request_body(request_body: Any, root: Mapping[str, Any], ref_link: RefLink) -> str:
    """Render the Request body section, or ``""`` when there is none."""
    body = deref(request_body, root)
    if not isinstance(body, Mapping):
        return ""
    content = body.get("content")
    if not isinstance(content, Mapping) or not content:
        return ""

    rows: list[list[str]] = []
    for media_type in sorted(content):
        media = content[media_type]
        schema = media.get("schema") if isinstance(media, Mapping) else None
        rows.append([_cell(f"`{media_type}`"), _cell(_schema_type_summary(schema, root, ref_link))])
    required = "yes" if body.get("required", False) else "no"
    table = _table(["Content type", "Schema"], rows)
    return f"## Request body\n\nRequired: {required}\n\n{table}"


def _render_responses(responses: Any, root: Mapping[str, Any], ref_link: RefLink) -> str:
    """Render the Responses section, or ``""`` when there are none."""
    if not isinstance(responses, Mapping) or not responses:
        return ""

    # Response status codes parse as integers under YAML (``200:``) but as
    # strings under JSON; normalize to string keys before sorting/indexing so
    # both spec formats render identically.
    entries = {str(key): value for key, value in responses.items()}
    rows: list[list[str]] = []
    for status in sorted(entries, key=_status_sort_key):
        response = deref(entries[status], root)
        if isinstance(response, Mapping):
            description = response.get("description", "")
            schema = _pick_content_schema(response.get("content"))
        else:
            description = ""
            schema = None
        rows.append(
            [
                _cell(f"`{status}`"),
                _cell(description),
                _cell(_schema_type_summary(schema, root, ref_link)),
            ]
        )
    table = _table(["Status", "Description", "Schema"], rows)
    return f"## Responses\n\n{table}"


def _render_security(security: Any) -> str:
    """Render the Security section, or ``""`` when none is declared."""
    if not isinstance(security, list) or not security:
        return ""

    bullets: list[str] = []
    for requirement in security:
        if not isinstance(requirement, Mapping) or not requirement:
            continue
        for scheme, scopes in requirement.items():
            if isinstance(scopes, list) and scopes:
                joined = ", ".join(str(scope) for scope in scopes)
                bullets.append(f"- `{scheme}` ({joined})")
            else:
                bullets.append(f"- `{scheme}`")
    if not bullets:
        return ""
    return "## Security\n\n" + "\n".join(bullets)


def render_operation(
    method: str,
    path: str,
    operation: Mapping[str, Any],
    *,
    root: Mapping[str, Any],
    schema_href: SchemaHref = default_schema_href,
    ref_link: RefLink | None = None,
) -> str:
    """Render a single OpenAPI operation as a Markdown document body.

    Args:
        method: HTTP method (rendered uppercased in the H1).
        path: Templated request path (e.g. ``/widgets/{id}``).
        operation: The operation object from the spec ``paths`` map.
        root: The full parsed specification, used to resolve local refs.
        schema_href: Legacy per-name mapper for local component-schema links.
            Used only when ``ref_link`` is not supplied.
        ref_link: Maps a ``$ref`` string to a relative href (or ``None`` to skip
            linking). Supplied by the reader to enable cross-file links (053-F);
            when ``None``, a local-only link function is derived from
            ``schema_href`` (pre-053-F behavior).

    Returns:
        A Markdown body: an H1 ``METHOD path`` heading followed by
        Summary/Description, Parameters, Request body, Responses, and Security
        sections. Sections with no content are omitted.
    """
    link = ref_link if ref_link is not None else _href_to_ref_link(schema_href)
    op = deref(operation, root)
    if not isinstance(op, Mapping):
        op = operation

    sections: list[str] = [f"# {method.upper()} {path}"]

    summary = op.get("summary")
    if isinstance(summary, str) and summary.strip():
        sections.append(summary.strip())
    description = op.get("description")
    if isinstance(description, str) and description.strip():
        sections.append(description.strip())

    for block in (
        _render_parameters(op.get("parameters"), root, link),
        _render_request_body(op.get("requestBody"), root, link),
        _render_responses(op.get("responses"), root, link),
        _render_security(op.get("security")),
    ):
        if block:
            sections.append(block)

    return "\n\n".join(sections)


def render_schema(
    name: str,
    schema: Mapping[str, Any],
    *,
    root: Mapping[str, Any],
    schema_href: SchemaHref = sibling_schema_href,
    ref_link: RefLink | None = None,
) -> str:
    """Render a named component schema as a Markdown document body.

    Args:
        name: Component schema name (used as the H1 and node identity).
        schema: The schema object from ``components.schemas``.
        root: The full parsed specification, used to resolve local refs.
        schema_href: Legacy per-name mapper for local schema→schema links. Used
            only when ``ref_link`` is not supplied.
        ref_link: Maps a ``$ref`` string to a relative href (or ``None``).
            Supplied by the reader to enable cross-file links (053-F); when
            ``None``, a local-only link function is derived from ``schema_href``.

    Returns:
        A Markdown body: an H1 schema-name heading followed by an optional
        description, a ``Type`` line, a Properties table, Composition sections
        (``allOf`` / ``oneOf`` / ``anyOf``), and an enum Values list. Absent
        sections are omitted.
    """
    link = ref_link if ref_link is not None else _href_to_ref_link(schema_href)
    resolved = deref(schema, root)
    if not isinstance(resolved, Mapping):
        resolved = {}

    sections: list[str] = [f"# {name}"]

    description = resolved.get("description")
    if isinstance(description, str) and description.strip():
        sections.append(description.strip())

    type_value = resolved.get("type")
    if isinstance(type_value, str):
        sections.append(f"Type: {type_value}")
    elif isinstance(type_value, list):
        sections.append("Type: " + " | ".join(str(member) for member in type_value))

    properties = resolved.get("properties")
    if isinstance(properties, Mapping) and properties:
        required_raw = resolved.get("required")
        required = set(required_raw) if isinstance(required_raw, list) else set()
        rows: list[list[str]] = []
        for prop_name, prop_schema in properties.items():
            prop_description = (
                prop_schema.get("description", "") if isinstance(prop_schema, Mapping) else ""
            )
            rows.append(
                [
                    _cell(f"`{prop_name}`"),
                    _cell(_schema_type_summary(prop_schema, root, link)),
                    _cell("yes" if prop_name in required else "no"),
                    _cell(prop_description),
                ]
            )
        table = _table(["Name", "Type", "Required", "Description"], rows)
        sections.append(f"## Properties\n\n{table}")

    for key in ("allOf", "oneOf", "anyOf"):
        members = resolved.get(key)
        if isinstance(members, list) and members:
            bullets = "\n".join(
                f"- {_schema_type_summary(member, root, link)}" for member in members
            )
            sections.append(f"## Composition ({key})\n\n{bullets}")

    enum = resolved.get("enum")
    if isinstance(enum, list) and enum:
        bullets = "\n".join(f"- `{value}`" for value in enum)
        sections.append(f"## Values\n\n{bullets}")

    return "\n\n".join(sections)


__all__ = [
    "RefLink",
    "SchemaHref",
    "default_schema_href",
    "render_operation",
    "render_schema",
    "sibling_schema_href",
]
