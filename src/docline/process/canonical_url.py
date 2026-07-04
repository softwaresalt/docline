"""Canonical Microsoft Learn URL derivation for local-dir ingestion (044.001-T).

Maps a repo-relative source file path to the canonical Learn URL path a document
publishes under, using the repo's ``.openpublishing.publish.config.json``
``docsets_to_publish`` entries. graphtor-docs uses this URL as a globally-unique
cross-source key to resolve cross-product links across separately-ingested repos
(see ``docs/decisions/2026-07-03-graphtor-cross-repo-link-resolution-spike.md``).

**v1 scope**: the docset whose ``build_source_folder`` is the longest path-prefix
of the source path supplies the ``url_path_prefix``; the URL is that prefix joined
with the path under ``build_source_folder``, with ``.md`` dropped, ``index.md``
collapsed to its directory, forward slashes, and lowercased. Returns ``None`` when
no docset matches or the matching docset declares no ``url_path_prefix``.

**Deferred** (feature 044-F): moniker ranges, redirect maps, documentId
path-depot mappings, and ``docfx.json`` ``base_path`` fallback when a docset omits
``url_path_prefix``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from docline.paths import posixify_path


def _normalize_folder(folder: str) -> str:
    """Normalize a ``build_source_folder`` to a clean posix prefix.

    Strips surrounding slashes; treats ``"."`` and ``""`` (repo root) as the
    empty prefix that matches every path.
    """
    posix = posixify_path(folder).strip("/")
    return "" if posix in (".", "") else posix


def _build_url(prefix: str, rel: str) -> str:
    """Join a docset ``url_path_prefix`` with the doc's path-under-folder.

    Drops the ``.md`` suffix, collapses ``index.md`` to its directory, and
    returns a lowercase, leading-slash Learn URL path.
    """
    rel = rel[:-3] if rel.endswith(".md") else rel
    if rel == "index" or rel.endswith("/index"):
        rel = rel[: -len("index")].rstrip("/")
    prefix_norm = "/" + posixify_path(prefix).strip("/")
    url = f"{prefix_norm}/{rel}" if rel else prefix_norm
    return url.lower()


def derive_canonical_url(
    publish_config: Mapping[str, Any],
    source_rel_path: str | Path,
) -> str | None:
    """Return the canonical Learn URL path for ``source_rel_path``, or ``None``.

    Args:
        publish_config: Parsed ``.openpublishing.publish.config.json`` mapping.
        source_rel_path: Repo-relative path of the source Markdown file.

    Returns:
        The canonical Learn URL path (leading ``/``, lowercase, no ``.md``), or
        ``None`` when no docset matches or the matching docset has no
        ``url_path_prefix``.
    """
    source = posixify_path(source_rel_path).lstrip("/")
    docsets = publish_config.get("docsets_to_publish")
    if not isinstance(docsets, list):
        return None

    best: tuple[int, str, str] | None = None  # (folder_len, rel_under_folder, prefix)
    for docset in docsets:
        if not isinstance(docset, Mapping):
            continue
        prefix = docset.get("url_path_prefix")
        if not isinstance(prefix, str) or not prefix:
            continue
        folder = _normalize_folder(str(docset.get("build_source_folder", "")))
        if folder:
            if source == folder or source.startswith(f"{folder}/"):
                rel = source[len(folder) :].lstrip("/")
            else:
                continue
        else:
            rel = source  # root docset matches every path
        if best is None or len(folder) > best[0]:
            best = (len(folder), rel, prefix)

    if best is None:
        return None
    return _build_url(best[2], best[1])
