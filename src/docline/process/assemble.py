"""Markdown assembly stubs for YAML-prepended document composition."""

import json
import re
from collections.abc import Mapping

from docline.process.hashing import compute_content_sha256
from docline.process.heading_validation import (
    body_should_skip_heading_validation,
    validate_heading_hierarchy,
)

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
        Assembled Markdown document with YAML frontmatter. The frontmatter's
        ``content_sha256`` is computed here over the final emitted body (after
        any anchor injection and trailing-newline normalization), overwriting
        any value supplied by an upstream stage, so a downstream re-hash of the
        emitted body matches the stored digest.

    Raises:
        HeadingHierarchyError: If ``allow_heading_disorder`` is ``False`` and
            ``body`` contains an H2 or H3 heading without a required ancestor.
    """
    if not allow_heading_disorder:
        # 028-S T1 / 026.001-T: auto-tolerate Microsoft Learn sparse-hierarchy
        # patterns where H1->H2->H3 enforcement is moot:
        #   * include fragments (no H1 anywhere) — embedded under a host H1
        #   * sparse hierarchies (no H2 anywhere) — common in changelogs,
        #     reference pages, tutorial steps that go H1 + H3 directly
        # Documents containing an H2 still get strict validation, preserving
        # the quality-signal feedback loop on real H3-before-H2 bugs.
        if not body_should_skip_heading_validation(body):
            validate_heading_hierarchy(body)
    if emit_chunk_anchors:
        body = _inject_chunk_anchors(body)
    # Normalize the body's trailing newline to exactly what is written to disk,
    # then hash those emitted bytes. content_sha256 must cover the FINAL body
    # (post anchor injection) so a downstream re-hash of the emitted body matches
    # the stored digest (docline<->graphtor ingestion contract). This is the sole
    # authoritative content_sha256 computation; upstream stages leave it empty.
    if body and not body.endswith("\n"):
        body = f"{body}\n"
    frontmatter = {**frontmatter, "content_sha256": compute_content_sha256(body)}
    yaml_text = "\n".join(_serialize_yaml(frontmatter))
    return f"---\n{yaml_text}\n---\n{body}"


__all__ = ["assemble_markdown"]
