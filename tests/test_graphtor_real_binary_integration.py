"""Opt-in real-binary round-trip suite for the docline → graphtor-docs contract.

These tests exercise the v1 ingestion contract against real-world document
binaries (PDF, DOCX) instead of synthetic inputs. They are gated by:

* the ``graphtor_integration`` pytest marker (opt-in),
* the presence of fixtures under ``tests/fixtures/real_binary/`` (skip on
  missing fixture).

See ``tests/fixtures/real_binary/README.md`` for fixture setup.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from docline.paths import posixify_path
from docline.process.assemble import assemble_markdown
from docline.process.hashing import compute_content_sha256
from docline.readers.docx import read_docx
from docline.readers.pdf import read_pdf
from docline.schema.models import BaseFrontmatter

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "real_binary"
PDF_FIXTURE = FIXTURE_DIR / "sample.pdf"
DOCX_FIXTURE = FIXTURE_DIR / "sample.docx"

_MISSING_FIXTURE_REASON = (
    "Real-binary fixtures not present. See tests/fixtures/real_binary/README.md for setup."
)


def _v1_frontmatter(source_path: str, body: str) -> dict[str, object]:
    """Build a v1-conformant frontmatter mapping for the given body."""
    return {
        "title": "Real Binary Sample",
        "source": "file://local",
        "ingested_at": datetime(2026, 6, 3, tzinfo=UTC).isoformat(),
        "doc_type": "binary",
        "description": "",
        "content_sha256": compute_content_sha256(body),
        "source_path": posixify_path(source_path),
        "chunk_strategy": "h1-h2-h3",
        "schema_version": "1.0",
    }


def _assert_v1_round_trip(source: Path, body: str) -> None:
    """Assert a real-binary body round-trips through the v1 contract surface."""
    assert isinstance(body, str)
    assert body.strip(), "reader returned empty Markdown"
    frontmatter = _v1_frontmatter(str(source), body)
    document = assemble_markdown(frontmatter, body, allow_heading_disorder=True)
    assert document.startswith("---\n")
    assert "\n---\n" in document
    assert document.endswith("\n")

    digest = compute_content_sha256(body)
    assert digest == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert len(digest) == 64

    posix_source = posixify_path(str(source))
    assert "\\" not in posix_source
    # BaseFrontmatter validates the v1 field set with our computed values.
    model = BaseFrontmatter(
        title="Real Binary Sample",
        source="file://local",
        ingested_at=datetime(2026, 6, 3, tzinfo=UTC),
        doc_type="binary",
        content_sha256=digest,
        source_path=posix_source,
    )
    assert model.schema_version.startswith("1.")
    assert model.chunk_strategy == "h1-h2-h3"


@pytest.mark.graphtor_integration
@pytest.mark.skipif(not PDF_FIXTURE.exists(), reason=_MISSING_FIXTURE_REASON)
def test_pdf_real_binary_round_trip() -> None:
    """A real PDF fixture round-trips through the v1 ingestion contract."""
    body = read_pdf(PDF_FIXTURE)
    _assert_v1_round_trip(PDF_FIXTURE, body)


@pytest.mark.graphtor_integration
@pytest.mark.skipif(not DOCX_FIXTURE.exists(), reason=_MISSING_FIXTURE_REASON)
def test_docx_real_binary_round_trip() -> None:
    """A real DOCX fixture round-trips through the v1 ingestion contract."""
    body = read_docx(DOCX_FIXTURE)
    _assert_v1_round_trip(DOCX_FIXTURE, body)
