"""Failing harness tests for schema-driven AST lint."""

from docline.process.ast_lint import lint_markdown_ast


def test_lint_markdown_ast_enforces_heading_depth() -> None:
    errors = lint_markdown_ast("# Title\n#### Too Deep\n", "wiki")
    assert errors == ["Heading depth exceeded schema limits"]


def test_lint_markdown_ast_checks_required_sections() -> None:
    errors = lint_markdown_ast("# Title\n## Context\nBackground\n", "adr")
    assert errors == ["Missing required section: Decision"]


def test_lint_markdown_ast_applies_schema_assertions() -> None:
    errors = lint_markdown_ast("# Title\n## Decision\nAdopt the change.\n", "adr")
    assert errors == []


def test_lint_markdown_ast_accepts_decorated_required_headings() -> None:
    errors = lint_markdown_ast("# Title\n## *Decision*\nAdopt the change.\n", "adr")
    assert errors == []
