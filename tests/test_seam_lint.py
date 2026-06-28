"""Tests for ``scripts/study/seam_lint.py`` (037.001-T)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "study" / "seam_lint.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seam_lint", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_strip_frontmatter_removes_leading_yaml_block() -> None:
    mod = _load()
    text = "---\ntitle: X\nkind: doc\n---\n# Body\n\ntext\n"
    assert mod.strip_frontmatter(text) == "# Body\n\ntext\n"


def test_strip_frontmatter_passthrough_without_frontmatter() -> None:
    mod = _load()
    text = "# Body\n\ntext\n"
    assert mod.strip_frontmatter(text) == text


def test_strip_frontmatter_unterminated_block_is_body() -> None:
    mod = _load()
    text = "---\ntitle: X\n# Body\n"
    # No closing fence — treat the whole document as body rather than eat it.
    assert mod.strip_frontmatter(text) == text


def test_valid_hierarchy_passes() -> None:
    mod = _load()
    result = mod.check_document("# Title\n\n## Section\n\n### Sub\n")
    assert result["hierarchy"] == "pass"
    assert result["hierarchy_ok"] is True
    assert result["ast_errors"] == []


def test_h2_before_h1_fails_hierarchy() -> None:
    mod = _load()
    # H2 before any H1 is the real, non-tolerated ingestion defect.
    result = mod.check_document("## Orphan\n\n# Title\n")
    assert result["hierarchy"] == "fail"
    assert result["hierarchy_ok"] is False
    assert "H2" in (result["hierarchy_error"] or "")


def test_sparse_hierarchy_is_tolerated() -> None:
    mod = _load()
    # H1 + H3 with no H2 is an intentional sparse pattern (028-S tolerance).
    result = mod.check_document("# Title\n\n### Item\n")
    assert result["hierarchy"] == "skipped"
    assert result["hierarchy_ok"] is True


def test_deep_heading_flagged_as_ast_but_hierarchy_passes() -> None:
    mod = _load()
    # H4 is below the chunk-boundary horizon: hierarchy tolerates it, but the
    # AST depth lint reports it. The two signals are reported independently.
    result = mod.check_document("# Title\n\n## Section\n\n#### Deep\n")
    assert result["hierarchy_ok"] is True
    assert result["ast_errors"]  # non-empty: depth exceeded


def test_frontmatter_is_stripped_before_validation() -> None:
    mod = _load()
    # The leading YAML must not be parsed as content; body starts at the H1.
    text = "---\ntitle: T\n---\n# Title\n\n## Section\n\n### Sub\n"
    result = mod.check_document(text)
    assert result["hierarchy_ok"] is True


def test_check_path_reads_file(tmp_path: Path) -> None:
    mod = _load()
    doc = tmp_path / "doc.md"
    doc.write_text("# Title\n\n## Section\n", encoding="utf-8")
    result = mod.check_path(doc)
    assert result["path"] == doc
    assert result["hierarchy_ok"] is True


def test_main_returns_zero_when_all_ok(tmp_path: Path, capsys) -> None:
    mod = _load()
    (tmp_path / "a.md").write_text("# A\n\n## S\n### Sub\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n\n### Item\n", encoding="utf-8")
    rc = mod.main(["--paths", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "a.md" in out and "b.md" in out


def test_main_returns_one_on_hierarchy_failure(tmp_path: Path, capsys) -> None:
    mod = _load()
    (tmp_path / "bad.md").write_text("## Orphan\n\n# Title\n", encoding="utf-8")
    rc = mod.main(["--paths", str(tmp_path / "bad.md")])
    assert rc == 1
    out = capsys.readouterr().out
    assert "FAIL" in out


def test_main_reports_ast_depth_notes(tmp_path: Path, capsys) -> None:
    mod = _load()
    # Not sparse-tolerated (H1+H2, no H3) so hierarchy passes, and H4 triggers
    # an AST depth note — exercises the main() report + SUMMARY ast_notes path.
    (tmp_path / "deep.md").write_text("# T\n\n## S\n\n#### Deep\n", encoding="utf-8")
    rc = mod.main(["--paths", str(tmp_path / "deep.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "note(s)" in out
    assert "ast:" in out
    assert "AST depth note(s)" in out


def test_main_errors_on_missing_path(capsys) -> None:
    mod = _load()
    rc = mod.main(["--paths", "does-not-exist-xyz.md"])
    assert rc == 2
