"""Tests for schema core models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from docline.schema.models import BaseDocument, BaseFrontmatter, DoclineError, SchemaValidationError


def _valid_frontmatter(**overrides: object) -> dict:
    base = {
        "title": "Test Doc",
        "source": "http://example.com",
        "ingested_at": datetime(2024, 1, 1, 12, 0, 0),
        "doc_type": "wiki",
    }
    base.update(overrides)
    return base


def test_docline_error_is_exception() -> None:
    """DoclineError is a subclass of Exception."""
    err = DoclineError("fail")
    assert isinstance(err, Exception)


def test_schema_validation_error_is_docline_error() -> None:
    """SchemaValidationError is a subclass of DoclineError."""
    err = SchemaValidationError("bad schema")
    assert isinstance(err, DoclineError)


def test_base_frontmatter_valid_construction() -> None:
    """BaseFrontmatter accepts valid fields."""
    fm = BaseFrontmatter(**_valid_frontmatter())
    assert fm.title == "Test Doc"
    assert fm.source == "http://example.com"
    assert fm.doc_type == "wiki"


def test_base_frontmatter_rejects_empty_title() -> None:
    """BaseFrontmatter raises ValidationError for empty title."""
    with pytest.raises(ValidationError):
        BaseFrontmatter(**_valid_frontmatter(title=""))


def test_base_frontmatter_rejects_empty_source() -> None:
    """BaseFrontmatter raises ValidationError for empty source."""
    with pytest.raises(ValidationError):
        BaseFrontmatter(**_valid_frontmatter(source=""))


def test_base_frontmatter_rejects_empty_doc_type() -> None:
    """BaseFrontmatter raises ValidationError for empty doc_type."""
    with pytest.raises(ValidationError):
        BaseFrontmatter(**_valid_frontmatter(doc_type=""))


def test_base_frontmatter_rejects_missing_title() -> None:
    """BaseFrontmatter raises ValidationError when title is missing."""
    data = _valid_frontmatter()
    del data["title"]
    with pytest.raises(ValidationError):
        BaseFrontmatter(**data)


def test_base_frontmatter_ingested_at_is_datetime() -> None:
    """ingested_at field stores a datetime."""
    fm = BaseFrontmatter(**_valid_frontmatter())
    assert isinstance(fm.ingested_at, datetime)


def test_base_document_valid_construction() -> None:
    """BaseDocument accepts valid frontmatter and body."""
    fm = BaseFrontmatter(**_valid_frontmatter())
    doc = BaseDocument(frontmatter=fm, body="Some content")
    assert doc.body == "Some content"
    assert doc.frontmatter.title == "Test Doc"


def test_base_document_rejects_missing_frontmatter() -> None:
    """BaseDocument raises ValidationError when frontmatter is missing."""
    with pytest.raises(ValidationError):
        BaseDocument(body="content")  # type: ignore[call-arg]


def test_base_document_accepts_empty_body() -> None:
    """BaseDocument allows empty body string."""
    fm = BaseFrontmatter(**_valid_frontmatter())
    doc = BaseDocument(frontmatter=fm, body="")
    assert doc.body == ""
