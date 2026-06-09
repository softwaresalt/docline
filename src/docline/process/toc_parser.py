"""DocFx TOC.yml parser → topological ingest order (024.004-T / 026-S T4).

Walks Microsoft DocFx ``TOC.yml`` files to produce an ordered list of
markdown file references. The DocFx convention: each TOC entry is a
``{name, href, items[]}`` dict. ``href`` references a file (markdown,
yml, or external URL); ``items`` is an optional nested list of more
entries. Multiple TOC.yml files (one per major subdir, plus a root
TOC.yml) merge in lexicographic subdir order.

The returned ordered list lets the staging / ingestion pipeline process
docs in their authorial sequence so graph parent nodes are ingested
before children — improving graph density and stabilizing chunk
identifiers across re-runs.

Public API:
    :func:`parse_toc` — single TOC.yml → ordered entry list
    :func:`merge_toc_files` — multiple TOC.yml files → merged ordered list
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

_log = logging.getLogger(__name__)


def _walk_entries(
    entries: Iterable[Any],
    *,
    toc_dir: Path,
    base_dir: Path,
    depth: int,
) -> list[dict[str, Any]]:
    """Recursively walk a TOC entry list and yield ordered dicts."""
    out: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        href = entry.get("href")
        if isinstance(href, str) and href.endswith(".md"):
            # Resolve relative to TOC file's directory
            full = (toc_dir / href).resolve()
            try:
                rel = full.relative_to(base_dir.resolve())
                target_path = rel.as_posix()
            except ValueError:
                target_path = PurePosixPath(href).as_posix()
            out.append(
                {
                    "name": entry.get("name", ""),
                    "href": href,
                    "target_path": target_path,
                    "depth": depth,
                }
            )
        # Walk nested items even when the parent has no href
        nested = entry.get("items")
        if isinstance(nested, list):
            out.extend(_walk_entries(nested, toc_dir=toc_dir, base_dir=base_dir, depth=depth + 1))
    return out


def parse_toc(toc_yml_path: Path, *, base_dir: Path) -> list[dict[str, Any]]:
    """Parse a single TOC.yml file → ordered list of markdown entries.

    Args:
        toc_yml_path: Path to a TOC.yml file.
        base_dir: Corpus root directory; resolved ``target_path`` values
            are corpus-relative posix strings.

    Returns:
        List of ``{name, href, target_path, depth}`` dicts in TOC order.
        Empty list for empty / malformed TOC files (logged as warning).
    """
    if not toc_yml_path.exists():
        return []
    try:
        text = toc_yml_path.read_text(encoding="utf-8")
    except OSError as exc:
        _log.warning("Could not read TOC.yml at %s: %s", toc_yml_path, exc)
        return []
    if not text.strip():
        return []
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        _log.warning("Could not parse TOC.yml at %s: %s", toc_yml_path, exc)
        return []
    if not isinstance(parsed, list):
        _log.warning(
            "TOC.yml at %s did not parse to a list; got %s", toc_yml_path, type(parsed).__name__
        )
        return []
    return _walk_entries(parsed, toc_dir=toc_yml_path.parent, base_dir=base_dir, depth=0)


def merge_toc_files(toc_yml_paths: list[Path], *, base_dir: Path) -> list[dict[str, Any]]:
    """Merge multiple TOC.yml files into a single ordered list.

    Args:
        toc_yml_paths: Iterable of TOC.yml file paths. Order in this
            list defines the merge order — callers should typically pass
            them sorted lexicographically by their containing
            subdirectory (root TOC first, then alpha subdir, then beta).
        base_dir: Corpus root for relative path resolution.

    Returns:
        Concatenated ordered list of entries. Duplicate ``target_path``
        entries from later TOC files are kept (caller may dedupe).
    """
    merged: list[dict[str, Any]] = []
    for toc_path in toc_yml_paths:
        merged.extend(parse_toc(toc_path, base_dir=base_dir))
    return merged


__all__ = ["parse_toc", "merge_toc_files"]
