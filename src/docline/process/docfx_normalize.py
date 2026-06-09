"""DocFx container syntax normalizer for source-MD ingestion (024.001-T / 026-S T1).

Translates the most common Microsoft DocFx container extensions into
standard CommonMark so downstream consumers (graph extraction, vector
embeddings, LLM context windows) see the structural intent rather than
opaque ``:::container:::`` syntax.

Supported transforms:

* ``:::image type="content" source="X" alt-text="Y":::`` →
  ``![Y](X)``. Also handles the self-closing form and the long-description
  block form (``:::image ... ::: ... :::image-end:::``). The long
  description is preserved as a paragraph immediately after the image.

* ``:::moniker range="...":::`` ... ``:::moniker-end:::`` →
  the inner content is preserved; the wrappers are stripped. The
  conditional-publishing semantics of moniker ranges are a publish-time
  concern; by the time docline sees the source, the operator has
  already chosen which moniker variant to ingest.

Unrecognized container syntax passes through unchanged so consumers
that DO understand the original DocFx syntax can still process it.
This is a conservative-by-default policy: docline adds value by
normalizing what it confidently can, without lossy reshaping of
unfamiliar constructs.

Public API:
    :func:`normalize_docfx_containers` — takes a markdown body string
    and returns a body with the supported containers translated.
"""

from __future__ import annotations

import re

# :::image type="..." source="..." alt-text="..." :::
# Two forms supported, matched by distinct regexes:
#
#   1. Self-closing form on a single conceptual unit:
#        :::image type="X" source="Y" alt-text="Z":::
#      Attributes may span multiple lines and contain colons (e.g.
#      ``alt-text="Figure 1: Overview"``), so the attribute group uses
#      ``.+?`` with ``re.DOTALL`` rather than ``[^:]+?``.
#
#   2. Block form with optional long description body:
#        :::image type="complex" source="X" alt-text="Y":::
#        Long description paragraph.
#        :::image-end:::
#      The block form has an explicit ``:::image-end:::`` terminator;
#      we match it greedily so the long description is captured.
#
# The block form is matched FIRST so its terminator is consumed before
# the self-closing form gets a chance to false-match ``:::image-end:::``
# as another opening tag.
_IMAGE_BLOCK_RE = re.compile(
    r":::image\b"
    r"(?P<attrs>.+?)"  # attribute text including colons in values
    r":::\s*\n"
    r"(?P<long_desc>.*?)"
    r":::image-end:::",
    re.DOTALL,
)
_IMAGE_SELF_CLOSING_RE = re.compile(
    r":::image\b"
    r"(?P<attrs>.+?)"  # attribute text including colons in values
    r":::",
    re.DOTALL,
)
_ATTR_RE = re.compile(r'([\w-]+)\s*=\s*["\']([^"\']*)["\']')

# :::moniker range="..." ... :::moniker-end:::
# Captures the body content between the wrappers and preserves it.
_MONIKER_RE = re.compile(
    r":::moniker\b[^\n]*\n?"  # opening line (may have attrs and trailing :::)
    r"(?P<body>.*?)"
    r":::moniker-end:::",
    re.DOTALL,
)


def _extract_attrs(attr_text: str) -> dict[str, str]:
    """Parse DocFx container attribute text (``key="value" other='val'``)."""
    return dict(_ATTR_RE.findall(attr_text or ""))


def _render_image_block(match: re.Match[str]) -> str:
    """Render the block form :::image:::...:::image-end::: with long description."""
    attrs = _extract_attrs(match.group("attrs"))
    source = attrs.get("source", "")
    alt_text = attrs.get("alt-text") or attrs.get("alt") or ""
    long_desc = (match.group("long_desc") or "").strip()
    image_md = f"![{alt_text}]({source})"
    if long_desc:
        return f"{image_md}\n\n{long_desc}"
    return image_md


def _render_image_self_closing(match: re.Match[str]) -> str:
    """Render the self-closing form :::image type=... :::."""
    attrs = _extract_attrs(match.group("attrs"))
    source = attrs.get("source", "")
    alt_text = attrs.get("alt-text") or attrs.get("alt") or ""
    return f"![{alt_text}]({source})"


def _render_moniker(match: re.Match[str]) -> str:
    body = match.group("body") or ""
    # Strip leading/trailing whitespace but preserve internal structure
    return body.strip("\n")


def normalize_docfx_containers(body: str) -> str:
    """Translate supported DocFx container syntax to standard CommonMark.

    Args:
        body: Markdown body content possibly containing DocFx ``:::``
            container syntax.

    Returns:
        Body with ``:::image:::`` translated to standard markdown image
        syntax and ``:::moniker:::``/``:::moniker-end:::`` wrappers
        stripped (content preserved). Unrecognized ``:::container:::``
        syntax passes through unchanged.

    Raises:
        Never raises on any string input. Malformed containers (e.g.
        unbalanced ``:::xxx:::``/``:::xxx-end:::`` pairs) pass through
        unchanged so consumers can surface them.
    """
    if not body:
        return body

    # Process moniker wrappers first so their content participates in
    # subsequent image transforms.
    out = _MONIKER_RE.sub(_render_moniker, body)
    # Process block form FIRST so its :::image-end::: terminator is
    # consumed before the self-closing pattern gets a chance to
    # false-match it as another opening tag.
    out = _IMAGE_BLOCK_RE.sub(_render_image_block, out)
    out = _IMAGE_SELF_CLOSING_RE.sub(_render_image_self_closing, out)
    return out


__all__ = ["normalize_docfx_containers"]
