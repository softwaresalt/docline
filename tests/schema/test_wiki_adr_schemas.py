"""Tests for wiki and ADR document schemas."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from docline.schema.library import AdrDocument, AdrFrontmatter, WikiDocument, WikiFrontmatter


def _base_fields() -> dict:
    return {"title": "My Doc", "source": "http://example.com", "ingested_at": datetime(2024, 1, 1)}


def test_wiki_frontmatter_default_tags() -> None:
    """WikiFrontmatter initialises tags as empty list by default."""
    fm = WikiFrontmatter(**_base_fields())
    assert fm.tags == []


def test_wiki_frontmatter_default_section() -> None:
    """WikiFrontmatter initialises section as empty string by default."""
    fm = WikiFrontmatter(**_base_fields())
    assert fm.section == ""


def test_wiki_frontmatter_doc_type_literal() -> None:
    """WikiFrontmatter doc_type is always 'wiki'."""
    fm = WikiFrontmatter(**_base_fields())
    assert fm.doc_type == "wiki"


def test_wiki_frontmatter_accepts_tags() -> None:
    """WikiFrontmatter accepts a list of tags."""
    fm = WikiFrontmatter(**_base_fields(), tags=["python", "docs"])
    assert fm.tags == ["python", "docs"]


def test_wiki_document_valid_construction() -> None:
    """WikiDocument accepts valid WikiFrontmatter and body."""
    fm = WikiFrontmatter(**_base_fields())
    doc = WikiDocument(frontmatter=fm, body="Wiki content")
    assert doc.frontmatter.doc_type == "wiki"
    assert doc.body == "Wiki content"


def test_adr_frontmatter_valid_status_proposed() -> None:
    """AdrFrontmatter accepts 'proposed' status."""
    fm = AdrFrontmatter(**_base_fields(), status="proposed")
    assert fm.status == "proposed"


def test_adr_frontmatter_valid_status_accepted() -> None:
    """AdrFrontmatter accepts 'accepted' status."""
    fm = AdrFrontmatter(**_base_fields(), status="accepted")
    assert fm.status == "accepted"


def test_adr_frontmatter_valid_status_deprecated() -> None:
    """AdrFrontmatter accepts 'deprecated' status."""
    fm = AdrFrontmatter(**_base_fields(), status="deprecated")
    assert fm.status == "deprecated"


def test_adr_frontmatter_valid_status_superseded() -> None:
    """AdrFrontmatter accepts 'superseded' status."""
    fm = AdrFrontmatter(**_base_fields(), status="superseded")
    assert fm.status == "superseded"


def test_adr_frontmatter_invalid_status_raises() -> None:
    """AdrFrontmatter raises ValidationError for unsupported status."""
    with pytest.raises(ValidationError):
        AdrFrontmatter(**_base_fields(), status="pending")


def test_adr_frontmatter_doc_type_literal() -> None:
    """AdrFrontmatter doc_type is always 'adr'."""
    fm = AdrFrontmatter(**_base_fields(), status="accepted")
    assert fm.doc_type == "adr"


def test_adr_frontmatter_default_decision_date() -> None:
    """AdrFrontmatter decision_date defaults to empty string."""
    fm = AdrFrontmatter(**_base_fields(), status="proposed")
    assert fm.decision_date == ""


def test_adr_document_valid_construction() -> None:
    """AdrDocument accepts valid AdrFrontmatter and body."""
    fm = AdrFrontmatter(**_base_fields(), status="accepted", decision_date="2024-01-15")
    doc = AdrDocument(frontmatter=fm, body="Decision rationale")
    assert doc.frontmatter.doc_type == "adr"
    assert doc.frontmatter.decision_date == "2024-01-15"
