"""DocFx ``[!INCLUDE]`` directive resolver (024.002-T / 026-S T2).

Expands ``[!INCLUDE [name](relative/path.md)]`` directives by inlining
the referenced file's body content at the directive location. Recursive
with cycle detection (max depth 5) and missing-file tolerance.

The Microsoft DocFx convention places shared snippets under
``includes/`` subdirectories at every level of the docs tree
(``includes/<topic>/foo.md``) and references them via relative-path
``[!INCLUDE [Note name](includes/path.md)]`` directives. Empirically
~45% of Power BI docs reference at least one include; expanding them
turns short reference docs into self-contained graphable content.

Public API:
    :func:`resolve_docfx_includes` — recursive resolve; returns body
    :func:`resolve_docfx_includes_with_stats` — same, plus stats dict
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

_log = logging.getLogger(__name__)

# [!INCLUDE [Display name](relative/path.md)]
# Display name is optional in some DocFx variants but we require it
# for consistency (real Power BI corpus always has it).
_INCLUDE_RE = re.compile(r"\[!INCLUDE\s*\[(?P<name>[^\]]*)\]\((?P<path>[^)]+)\)\]")

_MAX_DEPTH = 5


def _resolve_recursive(
    body: str,
    base_dir: Path,
    visited: frozenset[Path],
    depth: int,
    stats: dict[str, int],
) -> str:
    """Recursively expand [!INCLUDE] directives in ``body``."""
    if not body:
        return body

    def _replace(match: re.Match[str]) -> str:
        rel_path = match.group("path").strip()
        target = (base_dir / rel_path).resolve()

        if depth >= _MAX_DEPTH:
            stats["max_depth_hits"] = stats.get("max_depth_hits", 0) + 1
            return f"<!-- include max depth reached at {rel_path} -->"

        if target in visited:
            stats["cycle_hits"] = stats.get("cycle_hits", 0) + 1
            _log.warning("Include cycle detected: %s", target)
            return f"<!-- include cycle: {rel_path} -->"

        if not target.exists():
            stats["missing_count"] = stats.get("missing_count", 0) + 1
            _log.warning("Missing include file: %s (referenced from %s)", target, base_dir)
            return f"<!-- missing include: {rel_path} -->"

        try:
            inner = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            stats["missing_count"] = stats.get("missing_count", 0) + 1
            _log.warning("Could not read include %s: %s", target, exc)
            return f"<!-- include read failed: {rel_path} -->"

        stats["resolved_count"] = stats.get("resolved_count", 0) + 1
        # Recurse with the include's directory as the new base + visited+self
        expanded = _resolve_recursive(
            inner,
            base_dir=target.parent,
            visited=visited | {target},
            depth=depth + 1,
            stats=stats,
        )
        return expanded.rstrip("\n")

    return _INCLUDE_RE.sub(_replace, body)


def resolve_docfx_includes(body: str, *, base_dir: Path) -> str:
    """Expand DocFx ``[!INCLUDE]`` directives in ``body``.

    Args:
        body: Markdown body content possibly containing ``[!INCLUDE]``
            directives.
        base_dir: Directory the include paths are resolved relative to
            (typically the host file's parent directory).

    Returns:
        Body with includes inlined. Missing includes are replaced with
        a ``<!-- missing include: path -->`` comment and a warning is
        logged. Cycles are broken with a ``<!-- include cycle: path -->``
        comment. Includes exceeding depth 5 are stopped with a max-depth
        marker.

    Raises:
        Never raises on missing files or read errors — these degrade
        to inline markdown comments + warnings.
    """
    stats: dict[str, int] = {}
    return _resolve_recursive(body, base_dir, frozenset(), 0, stats)


def resolve_docfx_includes_with_stats(body: str, *, base_dir: Path) -> tuple[str, dict[str, int]]:
    """Like :func:`resolve_docfx_includes` but also returns a stats dict.

    The stats dict has keys ``resolved_count``, ``missing_count``,
    ``cycle_hits``, ``max_depth_hits`` (all default 0 if absent).
    Useful for telemetry / observability.
    """
    stats: dict[str, int] = {
        "resolved_count": 0,
        "missing_count": 0,
        "cycle_hits": 0,
        "max_depth_hits": 0,
    }
    out = _resolve_recursive(body, base_dir, frozenset(), 0, stats)
    return out, stats


__all__ = ["resolve_docfx_includes", "resolve_docfx_includes_with_stats"]
