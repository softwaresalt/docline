"""Integration tests pinning the docline → graphtor-docs ingestion contract.

These tests assert the v1 contract surface documented in
``docs/design-docs/graphtor-docs-ingestion-contract.md``. They cover:

* Frontmatter v1 field set and defaults
* Chunk-boundary rules (H1/H2/H3) and ``emit_chunk_anchors`` opt-in
* ``content_sha256`` algorithm (SHA-256 over UTF-8 body bytes)
* ``source_path`` POSIX normalization
* ``schema_version`` default and SemVer-additive policy
* ``docline`` namespace isolation

The suite is marked with ``pytest.mark.graphtor_integration`` so it can be
selected or excluded by downstream consumers running compatibility checks.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from docline.paths import posixify_path
from docline.process.assemble import assemble_markdown
from docline.process.hashing import compute_content_sha256
from docline.schema.models import BaseFrontmatter


def _v1_frontmatter(**overrides: object) -> dict[str, object]:
    """Build a minimal v1-conformant frontmatter mapping for assembly."""
    base: dict[str, object] = {
        "title": "Example",
        "source": "https://example.com/source",
        "ingested_at": "2026-06-03T00:00:00Z",
        "doc_type": "html",
        "description": "",
        "content_sha256": "",
        "source_path": "",
        "chunk_strategy": "h1-h2-h3",
        "schema_version": "1.0",
    }
    base.update(overrides)
    return base


@pytest.mark.graphtor_integration
class TestGraphtorIngestionContract:
    """Pin the docline → graphtor-docs v1 contract surface."""

    def test_graphtor_integration_marker_is_registered(self, pytestconfig: pytest.Config) -> None:
        """The graphtor_integration pytest marker is registered in project config."""
        assert any(
            marker.startswith("graphtor_integration") for marker in pytestconfig.getini("markers")
        )

    def test_frontmatter_v1_field_set_matches_contract(self) -> None:
        """BaseFrontmatter exposes the full v1 field set with documented defaults."""
        model = BaseFrontmatter(
            title="Example",
            source="https://example.com/source",
            ingested_at=datetime(2026, 6, 3, tzinfo=UTC),
            doc_type="html",
        )
        fields = set(BaseFrontmatter.model_fields.keys())
        assert fields == {
            "title",
            "source",
            "ingested_at",
            "doc_type",
            "description",
            "content_sha256",
            "source_path",
            "chunk_strategy",
            "schema_version",
            "docline",
        }
        assert model.description == ""
        assert model.content_sha256 == ""
        assert model.source_path == ""
        assert model.chunk_strategy == "h1-h2-h3"
        assert model.schema_version == "1.0"
        assert model.docline is None

    def test_docline_namespace_isolated_from_contract_fields(self) -> None:
        """Keys placed in the docline namespace stay inside that object."""
        model = BaseFrontmatter(
            title="Example",
            source="https://example.com/source",
            ingested_at=datetime(2026, 6, 3, tzinfo=UTC),
            doc_type="html",
            docline={"internal_run_id": "abc-123"},
        )
        dumped = model.model_dump()
        assert dumped["docline"] == {"internal_run_id": "abc-123"}
        assert "internal_run_id" not in dumped

    def test_content_sha256_is_sha256_over_utf8_body(self) -> None:
        """compute_content_sha256 matches SHA-256 of body.encode('utf-8')."""
        body = "# Heading\n\nExample body with unicode: café.\n"
        expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert compute_content_sha256(body) == expected
        assert len(compute_content_sha256(body)) == 64

    def test_source_path_normalizes_to_posix(self) -> None:
        """posixify_path produces forward-slash repo-relative paths."""
        windows_path = PureWindowsPath("docs") / "design-docs" / "spec.md"
        assert posixify_path(windows_path) == "docs/design-docs/spec.md"
        posix_path = PurePosixPath("docs/design-docs/spec.md")
        assert posixify_path(posix_path) == "docs/design-docs/spec.md"
        assert posixify_path(posixify_path(windows_path)) == posixify_path(windows_path)

    def test_assembled_document_emits_v1_frontmatter_block(self) -> None:
        """Assembled documents wrap the v1 frontmatter in YAML delimiters."""
        body = "# Title\n\nBody.\n"
        out = assemble_markdown(_v1_frontmatter(), body)
        assert out.startswith("---\n")
        assert "\n---\n" in out
        assert out.endswith("\n")
        assert 'chunk_strategy: "h1-h2-h3"' in out or "chunk_strategy: h1-h2-h3" in out
        assert 'schema_version: "1.0"' in out or "schema_version: 1.0" in out

    def test_chunk_anchors_default_off_preserves_body(self) -> None:
        """Default assemble output contains no chunk anchor injection."""
        body = "# H1\n\n## H2\n\n### H3\n\nText.\n"
        out = assemble_markdown(_v1_frontmatter(), body)
        assert '<a id="chunk-' not in out

    def test_chunk_anchors_opt_in_injects_for_h1_h2_h3_only(self) -> None:
        """emit_chunk_anchors=True injects 1-based, zero-padded anchors for H1/H2/H3."""
        body = "# H1\n\n## H2\n\n### H3\n\n#### H4\n\nText.\n"
        out = assemble_markdown(_v1_frontmatter(), body, emit_chunk_anchors=True)
        assert '<a id="chunk-0001"></a>\n# H1' in out
        assert '<a id="chunk-0002"></a>\n## H2' in out
        assert '<a id="chunk-0003"></a>\n### H3' in out
        assert '<a id="chunk-0004"></a>' not in out
        assert "#### H4" in out

    def test_chunk_anchors_skip_headings_in_fenced_code(self) -> None:
        """Headings inside fenced code blocks are not chunk boundaries."""
        body = "# Real H1\n\n```markdown\n# Fake H1 inside code\n```\n\n## Real H2\n"
        out = assemble_markdown(_v1_frontmatter(), body, emit_chunk_anchors=True)
        assert '<a id="chunk-0001"></a>\n# Real H1' in out
        assert '<a id="chunk-0002"></a>\n## Real H2' in out
        assert '<a id="chunk-0003"></a>' not in out

    def test_schema_version_default_is_v1_zero(self) -> None:
        """Default schema_version stays on the 1.0 contract line."""
        model = BaseFrontmatter(
            title="Example",
            source="https://example.com/source",
            ingested_at=datetime(2026, 6, 3, tzinfo=UTC),
            doc_type="html",
        )
        assert model.schema_version.startswith("1.")
