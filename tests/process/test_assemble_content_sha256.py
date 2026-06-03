"""Integration test for content_sha256 wiring through assemble pipeline (F1.T4)."""

import yaml

from docline.process.assemble import assemble_markdown
from docline.process.hashing import compute_content_sha256
from docline.process.metadata import assemble_frontmatter_payload
from docline.schema.library import WikiFrontmatter


def _extract_frontmatter(markdown: str) -> dict:
    """Parse YAML frontmatter from an assembled Markdown document."""
    parts = markdown.split("---\n", 2)
    assert len(parts) >= 3, "expected ---\\n YAML ---\\n body"
    return yaml.safe_load(parts[1])


def test_assemble_pipeline_populates_content_sha256_when_supplied() -> None:
    """When content_sha256 is set on the payload, it appears in the YAML frontmatter."""
    body = "# Heading\n\nBody text.\n"
    digest = compute_content_sha256(body)

    payload = assemble_frontmatter_payload(
        WikiFrontmatter,
        {
            "title": "Doc",
            "source": "https://example.com",
            "ingested_at": "2024-01-01T00:00:00Z",
            "content_sha256": digest,
        },
    )

    markdown = assemble_markdown(payload.model_dump(mode="json"), body)
    fm = _extract_frontmatter(markdown)
    assert fm["content_sha256"] == digest
    # SHA-256 hex digest length sanity check.
    assert len(fm["content_sha256"]) == 64


def test_content_sha256_matches_helper_for_assembled_body() -> None:
    """The digest computed by the helper matches the documented body bytes."""
    body = "# Title\n\nSome paragraph.\n"
    expected = compute_content_sha256(body)
    assert len(expected) == 64
    # Re-computing on the exact same body yields the same digest.
    assert compute_content_sha256(body) == expected
