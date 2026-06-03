"""Markdown assembly stubs for YAML-prepended document composition."""

import json
import re
from collections.abc import Mapping

from docline.process.heading_validation import validate_heading_hierarchy

_CHUNK_ANCHOR_HEADING_RE = re.compile(r"^(#{1,3})\s+\S")
_CHUNK_ANCHOR_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")


def _inject_chunk_anchors(body: str) -> str:
    r"""Insert ``<a id="chunk-NNNN"></a>`` before each H1/H2/H3 heading.

    Headings inside fenced code blocks (``\`\`\``` or ``~~~``) are skipped.
    IDs are 1-based, zero-padded to four digits, monotonically increasing
    across the body. H4+ headings are not chunk boundaries and are left
    unmodified.
    """
    if not body:
        return body
    lines = body.splitlines(keepends=True)
    out: list[str] = []
    counter = 0
    in_fence = False
    for line in lines:
        stripped = line.rstrip("\r\n")
        if _CHUNK_ANCHOR_FENCE_RE.match(stripped):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence and _CHUNK_ANCHOR_HEADING_RE.match(stripped):
            counter += 1
            out.append(f'<a id="chunk-{counter:04d}"></a>\n')
        out.append(line)
    return "".join(out)


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


def assemble_markdown(
    frontmatter: Mapping[str, object],
    body: str,
    *,
    allow_heading_disorder: bool = False,
    emit_chunk_anchors: bool = False,
) -> str:
    """Assemble validated frontmatter and Markdown body into a document string.

    Args:
        frontmatter: Validated frontmatter payload values.
        body: Markdown body content.
        allow_heading_disorder: When ``True``, skip the H1->H2->H3 heading
            hierarchy validation. Default ``False`` enforces graphtor-docs
            chunk-boundary parentage rules.
        emit_chunk_anchors: When ``True``, inject an HTML anchor element
            (``<a id="chunk-NNNN"></a>``) immediately before each H1/H2/H3
            heading so downstream chunkers can address chunks by stable
            identifier. Headings inside fenced code blocks are skipped.
            Default ``False`` preserves baseline output.

    Returns:
        Assembled Markdown document with YAML frontmatter.

    Raises:
        HeadingHierarchyError: If ``allow_heading_disorder`` is ``False`` and
            ``body`` contains an H2 or H3 heading without a required ancestor.
    """
    if not allow_heading_disorder:
        validate_heading_hierarchy(body)
    if emit_chunk_anchors:
        body = _inject_chunk_anchors(body)
    yaml_text = "\n".join(_serialize_yaml(frontmatter))
    markdown = f"---\n{yaml_text}\n---\n{body}"
    if not markdown.endswith("\n"):
        return f"{markdown}\n"
    return markdown


__all__ = ["assemble_markdown"]
