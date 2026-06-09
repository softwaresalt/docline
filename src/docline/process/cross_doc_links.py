"""Cross-doc markdown link resolver (024.003-T / 026-S T3).

Scans markdown body content for ``[text](relative/path.md)`` cross-doc
links and collects them as graph-edge metadata. The collected list is
surfaced via the application layer under ``docline.cross_doc_links``
so downstream graph extraction can treat each link as a first-class
edge {source, target, anchor, link_text} without re-parsing.

External links (``https://``, ``mailto:``, ``ftp://`` etc.), media
asset links (``./media/x.png``, ``media/x.png``), and same-page
anchor-only links (``#fragment``) pass through unchanged and are NOT
collected as cross-doc edges.

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
    """Scan body for cross-doc markdown links and collect them as graph edges.

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
          (posix), ``anchor`` (str or None), ``link_text`` (str).
          External / media / anchor-only links are excluded.
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
        if not path_part.endswith(".md"):
            # Not a markdown cross-doc link; skip
            continue

        target_path = _resolve_relative(current_rel_path, path_part)
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
            }
        )

    return body, links


__all__ = ["resolve_cross_doc_links"]
