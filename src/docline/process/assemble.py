"""Markdown assembly stubs for YAML-prepended document composition."""

import json
from collections.abc import Mapping


def _yaml_scalar(value: object) -> str:
    """Serialize a scalar value into a YAML-safe string.

    Args:
        value: Scalar value to serialize.

    Returns:
        YAML-safe scalar text.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _serialize_yaml(value: object, indent: int = 0) -> list[str]:
    """Serialize a limited JSON-compatible value as YAML lines.

    Args:
        value: Value to serialize.
        indent: Current indentation width.

    Returns:
        Serialized YAML lines.
    """
    prefix = " " * indent
    if isinstance(value, Mapping):
        lines: list[str] = []
        for key in sorted(value):
            item = value[key]
            if isinstance(item, Mapping):
                if not item:
                    lines.append(f"{prefix}{key}: {{}}")
                    continue
                lines.append(f"{prefix}{key}:")
                lines.extend(_serialize_yaml(item, indent + 2))
            elif isinstance(item, list):
                if not item:
                    lines.append(f"{prefix}{key}: []")
                    continue
                lines.append(f"{prefix}{key}:")
                lines.extend(_serialize_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, Mapping | list):
                lines.append(f"{prefix}-")
                lines.extend(_serialize_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
        if not lines:
            return [f"{prefix}[]"]
        return lines
    return [f"{prefix}{_yaml_scalar(value)}"]


def assemble_markdown(frontmatter: Mapping[str, object], body: str) -> str:
    """Assemble validated frontmatter and Markdown body into a document string.

    Args:
        frontmatter: Validated frontmatter payload values.
        body: Markdown body content.

    Returns:
        Assembled Markdown document with YAML frontmatter.
    """
    yaml_text = "\n".join(_serialize_yaml(frontmatter))
    markdown = f"---\n{yaml_text}\n---\n{body}"
    if not markdown.endswith("\n"):
        return f"{markdown}\n"
    return markdown


__all__ = ["assemble_markdown"]
