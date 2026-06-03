"""Red-first tests for chunk anchor emission in ``assemble_markdown``.

010-S F7.T3 — Chunk anchor emission

Per the graphtor-docs ingestion contract (chunk strategy ``h1-h2-h3``),
``assemble_markdown`` must optionally inject an HTML anchor tag immediately
before each chunk-boundary heading so downstream chunkers can address chunks
by stable identifier:

* anchors render as an ``a`` element with ``id`` attribute ``chunk-NNNN``
* IDs are 1-based, zero-padded to 4 digits, monotonically increasing
* one anchor per H1/H2/H3 heading; H4+ headings are not chunk boundaries
* emission is gated by ``emit_chunk_anchors=False`` (default off) so the
  existing baseline behavior is preserved without an opt-in

These tests are authored red-first per Constitution Principle II. The
``emit_chunk_anchors`` keyword is intentionally not yet supported by
``assemble_markdown``; the type stub silences pyright until the impl lands.
"""

from collections.abc import Mapping

from docline.process.assemble import assemble_markdown
from docline.process.metadata import assemble_frontmatter_payload
from docline.schema.library import WikiFrontmatter


def _frontmatter() -> Mapping[str, object]:
    payload = assemble_frontmatter_payload(
        WikiFrontmatter,
        {
            "title": "Doc",
            "source": "https://example.com",
            "ingested_at": "2024-01-01T00:00:00Z",
        },
    )
    return payload.model_dump(mode="json")


def _body_lines(markdown: str) -> list[str]:
    """Return body lines following the closing frontmatter ``---``."""
    parts = markdown.split("---\n", 2)
    assert len(parts) == 3, f"expected YAML frontmatter envelope, got: {markdown!r}"
    return parts[2].splitlines()


def test_chunk_anchors_default_off_preserves_baseline() -> None:
    """Without ``emit_chunk_anchors=True``, no anchors are injected."""
    body = "# Title\n\n## Section\n\nContent\n"
    markdown = assemble_markdown(_frontmatter(), body)
    assert "chunk-" not in markdown
    assert "<a id=" not in markdown


def test_chunk_anchors_injected_before_h1_h2_h3() -> None:
    """When opted in, each H1/H2/H3 gets a preceding anchor element."""
    body = "# Title\n\n## Section\n\n### Sub\n\nText\n"
    markdown = assemble_markdown(
        _frontmatter(),
        body,
        emit_chunk_anchors=True,  # type: ignore[call-arg]
    )
    lines = _body_lines(markdown)
    # Each heading is preceded by its anchor on its own line.
    expected = [
        '<a id="chunk-0001"></a>',
        "# Title",
        "",
        '<a id="chunk-0002"></a>',
        "## Section",
        "",
        '<a id="chunk-0003"></a>',
        "### Sub",
        "",
        "Text",
    ]
    # Allow trailing blank line tolerance.
    assert lines[: len(expected)] == expected


def test_chunk_anchors_are_zero_padded_four_digits() -> None:
    """Chunk IDs use 4-digit zero-padded numbering."""
    headings = "\n\n".join(f"# H{n}" for n in range(1, 12))
    markdown = assemble_markdown(
        _frontmatter(),
        headings + "\n",
        emit_chunk_anchors=True,  # type: ignore[call-arg]
    )
    assert '<a id="chunk-0001"></a>' in markdown
    assert '<a id="chunk-0009"></a>' in markdown
    assert '<a id="chunk-0010"></a>' in markdown
    assert '<a id="chunk-0011"></a>' in markdown
    # No 3-digit or unpadded variants leak through.
    assert '<a id="chunk-1"></a>' not in markdown
    assert '<a id="chunk-001"></a>' not in markdown


def test_chunk_anchors_ignore_h4_and_deeper() -> None:
    """H4+ headings are not chunk boundaries and receive no anchor."""
    body = "# Title\n\n## Section\n\n### Sub\n\n#### Detail\n\n##### Tiny\n"
    markdown = assemble_markdown(
        _frontmatter(),
        body,
        emit_chunk_anchors=True,  # type: ignore[call-arg]
    )
    # Three boundary headings → three anchors.
    assert markdown.count('<a id="chunk-') == 3
    # H4 and H5 lines are unmodified.
    assert "#### Detail" in markdown
    assert "##### Tiny" in markdown
    # No anchor immediately precedes H4 or H5.
    assert '<a id="chunk-0004"></a>\n#### Detail' not in markdown
    assert '<a id="chunk-0005"></a>\n##### Tiny' not in markdown


def test_chunk_anchors_skip_atx_headings_inside_fenced_code() -> None:
    """Hash lines inside fenced code blocks are not chunk boundaries."""
    body = (
        "# Real H1\n"
        "\n"
        "```python\n"
        "# This is a comment, not a heading\n"
        "## Also not a heading\n"
        "```\n"
        "\n"
        "## Real H2\n"
    )
    markdown = assemble_markdown(
        _frontmatter(),
        body,
        emit_chunk_anchors=True,  # type: ignore[call-arg]
    )
    # Exactly two chunk anchors — one per real heading.
    assert markdown.count('<a id="chunk-') == 2
    # The fenced contents survive verbatim.
    assert "# This is a comment, not a heading" in markdown
    assert "## Also not a heading" in markdown


def test_chunk_anchors_handle_empty_body() -> None:
    """Empty body with anchors enabled emits no anchors and assembles cleanly."""
    markdown = assemble_markdown(
        _frontmatter(),
        "",
        emit_chunk_anchors=True,  # type: ignore[call-arg]
    )
    assert "chunk-" not in markdown


def test_chunk_anchors_handle_body_without_boundary_headings() -> None:
    """Body with only H4+ or no headings emits no anchors."""
    body = "Plain paragraph.\n\n#### Detail-only\n\nMore text.\n"
    markdown = assemble_markdown(
        _frontmatter(),
        body,
        emit_chunk_anchors=True,  # type: ignore[call-arg]
    )
    assert "chunk-" not in markdown
    assert "Plain paragraph." in markdown
    assert "#### Detail-only" in markdown
