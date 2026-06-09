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

# :::image type="..." source="..." alt-text="..." ::: [optional long description] :::image-end:::
# Attributes use either single or double quotes. The trailing ::: may
# appear on the same line (self-closing) or paired with :::image-end:::
# on a later line (block form with optional long description).
_IMAGE_OPEN_RE = re.compile(
    r":::image\b"  # opening tag
    r"(?P<attrs>[^:]*?)"  # attribute text up to closing :::
    r":::"  # opening close
    r"(?P<long_desc>"  # capture optional long description
    r"(?:(?!:::image-end:::).)*?"
    r")"
    r"(?P<has_end>:::image-end:::)?",
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


def _render_image(match: re.Match[str]) -> str:
    attrs = _extract_attrs(match.group("attrs"))
    source = attrs.get("source", "")
    alt_text = attrs.get("alt-text") or attrs.get("alt") or ""
    long_desc = match.group("long_desc") or ""
    long_desc = long_desc.strip()
    image_md = f"![{alt_text}]({source})"
    if long_desc:
        return f"{image_md}\n\n{long_desc}"
    return image_md


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
    out = _IMAGE_OPEN_RE.sub(_render_image, out)
    return out


__all__ = ["normalize_docfx_containers"]
