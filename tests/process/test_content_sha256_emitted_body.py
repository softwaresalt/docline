"""content_sha256 must hash the emitted body exactly (docline<->graphtor contract).

Regression tests for the stage-ordering bug where content_sha256 was computed
over the pre-anchor body while the anchored body was written to disk, so a
downstream re-hash of the emitted body never matched.
"""

from docline.process.assemble import assemble_markdown
from docline.process.hashing import compute_content_sha256
from docline.process.metadata import assemble_frontmatter_payload
from docline.schema.library import WikiFrontmatter


def _payload(content_sha256: str = "") -> dict:
    """Build a v1 frontmatter payload dict, optionally seeding content_sha256."""
    model = assemble_frontmatter_payload(
        WikiFrontmatter,
        {
            "title": "Doc",
            "source": "https://example.com",
            "ingested_at": "2024-01-01T00:00:00Z",
            "content_sha256": content_sha256,
        },
    )
    return model.model_dump(mode="json")


def _emitted_body(markdown: str) -> str:
    """Return the body exactly as graphtor sees it: everything after the frontmatter."""
    return markdown.split("---\n", 2)[2]


def test_content_sha256_matches_emitted_body_with_anchors() -> None:
    """The stored hash equals a re-hash of the emitted body AFTER anchor injection."""
    body = "# H1\n\n## H2\n\nSome text.\n"
    markdown = assemble_markdown(_payload(), body, emit_chunk_anchors=True)
    emitted = _emitted_body(markdown)

    assert '<a id="chunk-' in emitted  # anchors are actually present in the output
    import yaml

    fm = yaml.safe_load(markdown.split("---\n", 2)[1])
    assert fm["content_sha256"] == compute_content_sha256(emitted)


def test_content_sha256_matches_emitted_body_without_anchors() -> None:
    """The stored hash equals a re-hash of the emitted body when no anchors are added."""
    body = "# Title\n\nBody paragraph.\n"
    markdown = assemble_markdown(_payload(), body)
    emitted = _emitted_body(markdown)

    import yaml

    fm = yaml.safe_load(markdown.split("---\n", 2)[1])
    assert fm["content_sha256"] == compute_content_sha256(emitted)


def test_content_sha256_is_authoritative_over_supplied_value() -> None:
    """A stale/incorrect supplied content_sha256 is replaced by the emitted-body hash."""
    body = "# Title\n\nBody.\n"
    markdown = assemble_markdown(_payload(content_sha256="deadbeef"), body, emit_chunk_anchors=True)
    emitted = _emitted_body(markdown)

    import yaml

    fm = yaml.safe_load(markdown.split("---\n", 2)[1])
    assert fm["content_sha256"] != "deadbeef"
    assert fm["content_sha256"] == compute_content_sha256(emitted)


def test_content_sha256_handles_body_without_trailing_newline() -> None:
    """A body lacking a trailing newline hashes the normalized emitted body."""
    body = "# Title\n\nNo trailing newline."
    markdown = assemble_markdown(_payload(), body)
    emitted = _emitted_body(markdown)

    assert emitted.endswith("\n")
    import yaml

    fm = yaml.safe_load(markdown.split("---\n", 2)[1])
    assert fm["content_sha256"] == compute_content_sha256(emitted)
