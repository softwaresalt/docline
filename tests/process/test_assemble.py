"""Failing harness tests for Markdown assembly."""

from datetime import datetime

from docline.process.assemble import assemble_markdown
from docline.schema.library import WikiFrontmatter


def _frontmatter() -> dict[str, object]:
    return WikiFrontmatter(
        title="Architecture Overview",
        source="https://docs.example.com/wiki/architecture",
        ingested_at=datetime(2026, 5, 30, 12, 0, 0),
        tags=["architecture", "process"],
        section="platform",
    ).model_dump(mode="json")


def test_assemble_markdown_places_yaml_before_body() -> None:
    markdown = assemble_markdown(_frontmatter(), "# Body\n\nContent\n")
    assert markdown.startswith("---\n")
    assert markdown.index("---\n") < markdown.index("# Body")


def test_assemble_markdown_is_stable_for_identical_inputs() -> None:
    first = assemble_markdown(_frontmatter(), "# Body\n\nContent\n")
    second = assemble_markdown(_frontmatter(), "# Body\n\nContent\n")
    assert first == second


def test_assemble_markdown_handles_empty_body() -> None:
    markdown = assemble_markdown(_frontmatter(), "")
    assert markdown.endswith("\n")
