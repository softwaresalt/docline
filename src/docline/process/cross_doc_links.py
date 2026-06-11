"""Cross-doc markdown link resolver (024.003-T / 026-S T3 / 028-S T3).

Scans markdown body content for ``[text](relative/path.md)`` cross-doc
links and ``[text](/absolute/cross-product-path)`` cross-product links,
collecting both as graph-edge metadata. The collected list is surfaced
via the application layer under ``docline.cross_doc_links`` so downstream
graph extraction can treat each link as a first-class edge
``{target_path, anchor, link_text, cross_product}`` without re-parsing.

Three link categories:

1. **In-corpus cross-doc** (relative ``.md`` paths) — resolved relative
   to the host file's directory. ``cross_product: False``.
2. **Cross-product** (absolute ``/path`` paths, e.g. ``/fabric/admin``,
   ``/dax/abs-function-dax``) — preserved verbatim with leading slash.
   ``cross_product: True``. Microsoft Learn uses these for cross-product
   references (Fabric, DAX, Azure, Power Platform) that target sibling
   docs sites not present in the local corpus.
3. **Skipped**: external schemes (``https://``, ``mailto:``, ``ftp://``
   etc.), media asset paths (``./media/x.png``, ``media/x.png``,
   ``/media/x.png``), and same-page anchor-only links (``#fragment``).
   Images (``![alt](path)``) are skipped at the regex level via a
   negative lookbehind.

Public API:
    :func:`resolve_cross_doc_links` — returns ``(body, links)`` tuple
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

# [link text](path)
# - link text: anything except a bare ] (DocFx escapes \] for nested brackets)
# - path: anything except a bare ) and not starting with ! (which is an image)
_LINK_RE = re.compile(r"(?<!\!)\[(?P<text>[^\]]*)\]\((?P<href>[^)]+)\)")

# Skip patterns: external schemes, media asset paths, anchor-only
_EXTERNAL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_MEDIA_PATH_RE = re.compile(r"(^|/)media/", re.IGNORECASE)


def _is_external(href: str) -> bool:
    """True when href uses a URL scheme (http/https/mailto/ftp/etc.)."""
    return bool(_EXTERNAL_SCHEME_RE.match(href))


def _is_media_asset(href: str) -> bool:
    """True when href points at a media asset path."""
    return bool(_MEDIA_PATH_RE.search(href))


def _is_anchor_only(href: str) -> bool:
    return href.startswith("#")


def _is_absolute_cross_product(href: str) -> bool:
    """True when href is an absolute path (``/...``) indicating a cross-product link.

    Microsoft Learn uses absolute paths like ``/fabric/admin``,
    ``/dax/abs-function-dax``, ``/azure/storage/blobs/overview`` to link
    across product documentation sites. These are not in the local
    corpus and must be flagged separately so graphtor can model them
    as external graph edges.
    """
    return href.startswith("/") and not _is_anchor_only(href) and not _is_media_asset(href)


def _split_anchor(href: str) -> tuple[str, str | None]:
    """Split ``path#anchor`` into ``(path, anchor)`` parts."""
    if "#" not in href:
        return href, None
    path, anchor = href.split("#", 1)
    return path, anchor


def _resolve_relative(current_rel_path: Path, target_rel: str) -> str:
    """Resolve a target path relative to the host file's location.

    Returns a posix-style path string. Uses PurePosixPath so behavior is
    consistent across Windows / POSIX hosts.
    """
    # Host file's containing directory (posix)
    host_dir = PurePosixPath(current_rel_path.as_posix()).parent
    target = PurePosixPath(target_rel)
    if target.is_absolute():
        return target.as_posix().lstrip("/")
    # Combine + normalize away ".." segments
    combined = host_dir / target
    # PurePosixPath doesn't have a resolve()-equivalent for relative paths;
    # walk the parts manually to collapse "..".
    parts: list[str] = []
    for part in combined.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part == "." or part == "":
            continue
        else:
            parts.append(part)
    return "/".join(parts)


def resolve_cross_doc_links(
    body: str,
    *,
    current_rel_path: Path,
    deduplicate: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    """Scan body for cross-doc / cross-product links and collect them as graph edges.

    Args:
        body: Markdown body content.
        current_rel_path: Path of the host file relative to the corpus root.
            Used to resolve relative link targets to corpus-relative posix
            paths.
        deduplicate: When ``True``, the returned link list contains at most
            one entry per ``(target_path, anchor)`` tuple. Default ``False``
            preserves order and duplicates so consumers can see all reference
            occurrences.

    Returns:
        A tuple of ``(body, links)``:

        * ``body``: Unchanged input body (this resolver does not rewrite
          link text; downstream tooling can use the link list to do that).
        * ``links``: List of ``dict`` entries with keys ``target_path``
          (posix; leading-slash retained for cross-product entries),
          ``anchor`` (str or None), ``link_text`` (str), and
          ``cross_product`` (bool). External / media / anchor-only links
          are excluded.
    """
    if not body:
        return body, []

    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()

    for match in _LINK_RE.finditer(body):
        href = match.group("href").strip()
        text = match.group("text")

        if _is_external(href) or _is_anchor_only(href) or _is_media_asset(href):
            continue

        path_part, anchor = _split_anchor(href)

        if _is_absolute_cross_product(href):
            # Cross-product link — preserve the leading slash so graphtor can
            # distinguish in-corpus targets from cross-product references.
            target_path = path_part
            cross_product = True
        elif path_part.endswith(".md"):
            target_path = _resolve_relative(current_rel_path, path_part)
            cross_product = False
        else:
            # Not a markdown cross-doc link and not a cross-product link; skip
            continue

        if deduplicate:
            key = (target_path, anchor)
            if key in seen:
                continue
            seen.add(key)
        links.append(
            {
                "target_path": target_path,
                "anchor": anchor,
                "link_text": text,
                "cross_product": cross_product,
            }
        )

    return body, links


__all__ = ["resolve_cross_doc_links"]
