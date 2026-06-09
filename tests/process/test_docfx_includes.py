"""Tests for DocFx [!INCLUDE] directive resolver (024.002-T / 026-S T2)."""

from __future__ import annotations

import logging
from pathlib import Path


def test_resolve_includes_inlines_referenced_file(tmp_path: Path) -> None:
    """A simple [!INCLUDE [name](path.md)] directive replaces with file contents."""
    from docline.process.docfx_includes import resolve_docfx_includes

    inc = tmp_path / "includes" / "shared.md"
    inc.parent.mkdir(parents=True)
    inc.write_text("Shared snippet text.\n", encoding="utf-8")

    body = "Para 1.\n\n[!INCLUDE [shared](includes/shared.md)]\n\nPara 2.\n"
    out = resolve_docfx_includes(body, base_dir=tmp_path)

    assert "Shared snippet text." in out
    assert "[!INCLUDE" not in out
    assert "Para 1." in out
    assert "Para 2." in out


def test_resolve_includes_uses_relative_path(tmp_path: Path) -> None:
    """Include paths are resolved relative to the host file's directory (base_dir)."""
    from docline.process.docfx_includes import resolve_docfx_includes

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "includes").mkdir()
    (tmp_path / "docs" / "includes" / "note.md").write_text("Note body.\n", encoding="utf-8")

    body = "[!INCLUDE [note](includes/note.md)]"
    out = resolve_docfx_includes(body, base_dir=tmp_path / "docs")
    assert "Note body." in out


def test_resolve_includes_handles_parent_relative_paths(tmp_path: Path) -> None:
    """Includes can reference parent directories via ../path/."""
    from docline.process.docfx_includes import resolve_docfx_includes

    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "common.md").write_text("Common.\n", encoding="utf-8")
    (tmp_path / "subdir").mkdir()

    body = "[!INCLUDE [common](../shared/common.md)]"
    out = resolve_docfx_includes(body, base_dir=tmp_path / "subdir")
    assert "Common." in out


def test_resolve_includes_recursive(tmp_path: Path) -> None:
    """Includes inside includes are resolved recursively."""
    from docline.process.docfx_includes import resolve_docfx_includes

    (tmp_path / "includes").mkdir()
    (tmp_path / "includes" / "inner.md").write_text("Inner.\n", encoding="utf-8")
    (tmp_path / "includes" / "outer.md").write_text(
        "Outer top.\n\n[!INCLUDE [i](inner.md)]\n\nOuter bottom.\n",
        encoding="utf-8",
    )

    body = "[!INCLUDE [o](includes/outer.md)]"
    out = resolve_docfx_includes(body, base_dir=tmp_path)
    assert "Outer top." in out
    assert "Inner." in out
    assert "Outer bottom." in out


def test_resolve_includes_cycle_detection(tmp_path: Path) -> None:
    """A cycle (A → B → A) MUST NOT recurse forever; the cycle is broken
    with a comment and a warning is logged.
    """
    from docline.process.docfx_includes import resolve_docfx_includes

    (tmp_path / "includes").mkdir()
    (tmp_path / "includes" / "a.md").write_text(
        "A content.\n[!INCLUDE [b](b.md)]\n", encoding="utf-8"
    )
    (tmp_path / "includes" / "b.md").write_text(
        "B content.\n[!INCLUDE [a](a.md)]\n", encoding="utf-8"
    )

    body = "[!INCLUDE [a](includes/a.md)]"
    out = resolve_docfx_includes(body, base_dir=tmp_path)
    assert "A content." in out
    assert "B content." in out
    # Cycle marker must appear; should not infinite-loop
    assert "cycle" in out.lower() or "<!-- include cycle" in out


def test_resolve_includes_missing_file_is_nonfatal(tmp_path: Path, caplog) -> None:
    """A missing include MUST emit a markdown comment placeholder and log warning,
    NOT raise.
    """
    from docline.process.docfx_includes import resolve_docfx_includes

    body = "Before.\n[!INCLUDE [missing](nonexistent.md)]\nAfter.\n"
    with caplog.at_level(logging.WARNING):
        out = resolve_docfx_includes(body, base_dir=tmp_path)

    assert "Before." in out
    assert "After." in out
    assert "missing include" in out.lower() or "<!-- missing include" in out
    assert any(
        "missing" in r.message.lower() or "not found" in r.message.lower() for r in caplog.records
    )


def test_resolve_includes_max_depth_circuit_break(tmp_path: Path) -> None:
    """Deeply nested includes (beyond max_depth=5) MUST stop expanding."""
    from docline.process.docfx_includes import resolve_docfx_includes

    (tmp_path / "incs").mkdir()
    # Build a chain 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7
    for i in range(8):
        nxt = f"[!INCLUDE [n](next-{i + 1}.md)]" if i < 7 else "deepest content"
        (tmp_path / "incs" / f"next-{i}.md").write_text(f"Level {i}.\n{nxt}\n", encoding="utf-8")

    body = "[!INCLUDE [start](incs/next-0.md)]"
    out = resolve_docfx_includes(body, base_dir=tmp_path)
    # We should see at least levels 0-4 expanded, then a max-depth marker
    assert "Level 0." in out
    assert "Level 4." in out
    # Should NOT see the "deepest content" (would mean depth exceeded)
    assert "deepest content" not in out
    assert "max depth" in out.lower() or "<!-- include max depth" in out


def test_resolve_includes_handles_empty_body(tmp_path: Path) -> None:
    from docline.process.docfx_includes import resolve_docfx_includes

    assert resolve_docfx_includes("", base_dir=tmp_path) == ""


def test_resolve_includes_passes_plain_markdown_unchanged(tmp_path: Path) -> None:
    from docline.process.docfx_includes import resolve_docfx_includes

    body = "# Heading\n\nPlain paragraph.\n\n- item 1\n- item 2\n"
    out = resolve_docfx_includes(body, base_dir=tmp_path)
    assert out == body


def test_resolve_includes_collects_resolution_telemetry(tmp_path: Path) -> None:
    """Optional return shape: when callers pass collect_stats=True, the
    function returns (body, stats) instead of just body.
    """
    from docline.process.docfx_includes import resolve_docfx_includes_with_stats

    (tmp_path / "includes").mkdir()
    (tmp_path / "includes" / "a.md").write_text("A.\n", encoding="utf-8")
    body = "[!INCLUDE [a](includes/a.md)]\n[!INCLUDE [missing](nope.md)]\n"
    out, stats = resolve_docfx_includes_with_stats(body, base_dir=tmp_path)
    assert "A." in out
    assert stats["resolved_count"] == 1
    assert stats["missing_count"] == 1
