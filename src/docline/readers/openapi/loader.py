"""OpenAPI specification loader and local ``$ref`` resolver (050.002-T / T2).

Loads a specification from JSON or YAML into an in-memory mapping and resolves
**local** (``#/...``) JSON-pointer references. External / split-file refs are a
deliberate v1 non-goal: they are a security boundary (file refs must stay inside
the workspace root; URL-valued refs are an SSRF vector) and are therefore left
unresolved rather than fetched.

Reference following is cycle-guarded: a chain of ref-to-ref nodes that loops
back on itself raises :class:`OpenApiRefError` instead of recursing forever.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from docline.readers.openapi.errors import OpenApiParseError, OpenApiRefError

_LOCAL_REF_PREFIX = "#/"
_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def slug(text: str) -> str:
    """Return a filesystem/link-safe slug for *text* (shared doc-naming helper)."""
    result = _SLUG_RE.sub("-", text).strip("-")
    return result or "item"


def load_spec(source: str | Path) -> dict[str, Any]:
    """Load an OpenAPI/Swagger specification into a mapping.

    Args:
        source: Either a :class:`~pathlib.Path` to a spec file or the raw spec
            content as a ``str``. YAML parsing is used for both, since JSON is a
            strict subset of YAML.

    Returns:
        The parsed specification as a ``dict``.

    Raises:
        OpenApiParseError: If the file cannot be read, the content cannot be
            parsed, or the parsed root is not a mapping.
    """
    if isinstance(source, Path):
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as err:
            raise OpenApiParseError(f"cannot read OpenAPI spec {source}: {err}") from err
    else:
        text = source

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise OpenApiParseError(f"cannot parse OpenAPI spec: {err}") from err

    if not isinstance(data, dict):
        raise OpenApiParseError(f"OpenAPI spec root must be a mapping, got {type(data).__name__}")
    return data


def is_local_ref(ref: str) -> bool:
    """Return ``True`` when *ref* is a local (``#/...``) JSON pointer.

    Args:
        ref: A raw ``$ref`` string.

    Returns:
        ``True`` for in-document refs; ``False`` for external/split-file refs
        (which carry a file or URL component before the ``#``).
    """
    return ref.startswith(_LOCAL_REF_PREFIX)


def _unescape_token(token: str) -> str:
    """Decode a JSON-pointer token (``~1`` -> ``/``, ``~0`` -> ``~``)."""
    return token.replace("~1", "/").replace("~0", "~")


def component_name_from_ref(ref: str) -> str:
    """Return the final segment of a ``$ref`` (the component name).

    Args:
        ref: A ``$ref`` string such as ``#/components/schemas/Widget``.

    Returns:
        The decoded final pointer segment (e.g. ``Widget``).
    """
    return _unescape_token(ref.rstrip("/").split("/")[-1])


def resolve_pointer(root: Mapping[str, Any], ref: str) -> Any:
    """Resolve a single local JSON-pointer ``$ref`` against *root*.

    Args:
        root: The full parsed specification mapping.
        ref: A local (``#/...``) ``$ref`` string.

    Returns:
        The node the pointer targets.

    Raises:
        OpenApiRefError: If *ref* is external/split-file, or if the pointer
            cannot be resolved against *root*.
    """
    if not is_local_ref(ref):
        raise OpenApiRefError(f"external/split-file $ref is not supported in v1: {ref!r}")

    pointer = ref[len(_LOCAL_REF_PREFIX) :]
    node: Any = root
    for token in pointer.split("/") if pointer else []:
        key = _unescape_token(token)
        if isinstance(node, Mapping) and key in node:
            node = node[key]
        elif isinstance(node, list):
            try:
                index = int(key)
            except ValueError:
                raise OpenApiRefError(
                    f"unresolvable $ref {ref!r}: non-integer list index {key!r}"
                ) from None
            if index < 0 or index >= len(node):
                raise OpenApiRefError(f"unresolvable $ref {ref!r}: index {index} out of range")
            node = node[index]
        else:
            raise OpenApiRefError(f"unresolvable $ref {ref!r}: missing segment {key!r}")
    return node


def deref(node: Any, root: Mapping[str, Any]) -> Any:
    """Follow a chain of local ``$ref`` nodes to the first concrete target.

    A ``$ref`` may point at another ``$ref`` (ref-to-ref); this follows the
    chain until a non-ref node is reached. External refs terminate the chain and
    are returned unchanged (left unresolved, never fetched). Non-mapping and
    non-ref nodes are returned unchanged.

    Args:
        node: The node to dereference. Often ``{"$ref": "#/..."}`` but may be any
            value.
        root: The full parsed specification mapping.

    Returns:
        The concrete (non-local-ref) node, or *node* itself when it is not a
        local ref.

    Raises:
        OpenApiRefError: If a local ref in the chain is unresolvable or the chain
            forms a cycle.
    """
    seen: set[str] = set()
    current = node
    while isinstance(current, Mapping):
        ref = current.get("$ref")
        if not isinstance(ref, str) or not is_local_ref(ref):
            return current
        if ref in seen:
            raise OpenApiRefError(f"circular $ref chain detected at {ref!r}")
        seen.add(ref)
        current = resolve_pointer(root, ref)
    return current


__all__ = [
    "component_name_from_ref",
    "deref",
    "is_local_ref",
    "load_spec",
    "resolve_pointer",
    "slug",
]
