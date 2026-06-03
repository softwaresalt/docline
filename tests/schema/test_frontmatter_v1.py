"""Red-first contract tests for the v1 frontmatter schema (F1.T1).

These tests pin the graphtor-docs ingestion contract for shared frontmatter:

* required new fields: ``description``, ``content_sha256``, ``source_path``,
  ``chunk_strategy``, ``schema_version``;
* ``docline:`` namespace for docline-only metadata;
* backward-compat: existing minimal frontmatter (without v1 fields) still parses
  because all v1 additions are optional with documented defaults.

These tests are authored red-first per Constitution Principle II. They MUST
fail against the pre-F1.T2 ``BaseFrontmatter`` implementation and pass after
the schema extension lands.
"""

from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from docline.schema.models import BaseFrontmatter


def _v1_frontmatter(**overrides: Any) -> dict[str, Any]:
    """Build a v1-shaped frontmatter dict with all new fields populated."""
    base: dict[str, Any] = {
        "title": "Test Doc",
        "source": "http://example.com",
        "ingested_at": datetime(2024, 1, 1, 12, 0, 0),
        "doc_type": "wiki",
        "description": "Short human-readable description of the document.",
        "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "source_path": "docs/example.md",
        "chunk_strategy": "h1-h2-h3",
        "schema_version": "1.0",
    }
    base.update(overrides)
    return base


def _legacy_frontmatter(**overrides: Any) -> dict[str, Any]:
    """Build a pre-v1 (minimal) frontmatter dict — no new fields."""
    base: dict[str, Any] = {
        "title": "Legacy Doc",
        "source": "http://example.com/legacy",
        "ingested_at": datetime(2023, 6, 1, 0, 0, 0),
        "doc_type": "wiki",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# New required-or-defaulted fields accepted on the model
# ---------------------------------------------------------------------------


def test_frontmatter_accepts_description() -> None:
    """v1 frontmatter accepts a non-empty ``description``."""
    fm = BaseFrontmatter(**_v1_frontmatter())
    assert fm.description == "Short human-readable description of the document."


def test_frontmatter_accepts_content_sha256() -> None:
    """v1 frontmatter accepts a 64-char hex ``content_sha256``."""
    fm = BaseFrontmatter(**_v1_frontmatter())
    assert fm.content_sha256 == ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_frontmatter_accepts_source_path() -> None:
    """v1 frontmatter accepts a POSIX-style ``source_path``."""
    fm = BaseFrontmatter(**_v1_frontmatter())
    assert fm.source_path == "docs/example.md"


def test_frontmatter_accepts_chunk_strategy() -> None:
    """v1 frontmatter accepts a ``chunk_strategy`` string."""
    fm = BaseFrontmatter(**_v1_frontmatter())
    assert fm.chunk_strategy == "h1-h2-h3"


def test_frontmatter_accepts_schema_version() -> None:
    """v1 frontmatter accepts a ``schema_version`` string."""
    fm = BaseFrontmatter(**_v1_frontmatter())
    assert fm.schema_version == "1.0"


# ---------------------------------------------------------------------------
# Defaults when omitted
# ---------------------------------------------------------------------------


def test_chunk_strategy_default_is_h1_h2_h3() -> None:
    """``chunk_strategy`` defaults to ``"h1-h2-h3"`` when omitted."""
    data = _v1_frontmatter()
    del data["chunk_strategy"]
    fm = BaseFrontmatter(**data)
    assert fm.chunk_strategy == "h1-h2-h3"


def test_schema_version_default_is_1_0() -> None:
    """``schema_version`` defaults to ``"1.0"`` when omitted."""
    data = _v1_frontmatter()
    del data["schema_version"]
    fm = BaseFrontmatter(**data)
    assert fm.schema_version == "1.0"


def test_description_default_is_empty_string() -> None:
    """``description`` defaults to ``""`` when omitted (optional field)."""
    data = _v1_frontmatter()
    del data["description"]
    fm = BaseFrontmatter(**data)
    assert fm.description == ""


def test_content_sha256_default_is_empty_string() -> None:
    """``content_sha256`` defaults to ``""`` when omitted (filled at assemble time)."""
    data = _v1_frontmatter()
    del data["content_sha256"]
    fm = BaseFrontmatter(**data)
    assert fm.content_sha256 == ""


def test_source_path_default_is_empty_string() -> None:
    """``source_path`` defaults to ``""`` when omitted (filled at assemble time)."""
    data = _v1_frontmatter()
    del data["source_path"]
    fm = BaseFrontmatter(**data)
    assert fm.source_path == ""


# ---------------------------------------------------------------------------
# Type-rejection cases for the new fields
# ---------------------------------------------------------------------------


def test_description_rejects_non_string() -> None:
    """``description`` rejects non-string values."""
    with pytest.raises(ValidationError):
        BaseFrontmatter(**_v1_frontmatter(description=123))


def test_content_sha256_rejects_non_string() -> None:
    """``content_sha256`` rejects non-string values."""
    with pytest.raises(ValidationError):
        BaseFrontmatter(**_v1_frontmatter(content_sha256=[]))


def test_source_path_rejects_non_string() -> None:
    """``source_path`` rejects non-string values."""
    with pytest.raises(ValidationError):
        BaseFrontmatter(**_v1_frontmatter(source_path=42))


def test_chunk_strategy_rejects_non_string() -> None:
    """``chunk_strategy`` rejects non-string values."""
    with pytest.raises(ValidationError):
        BaseFrontmatter(**_v1_frontmatter(chunk_strategy=None))


def test_schema_version_rejects_non_string() -> None:
    """``schema_version`` rejects non-string values."""
    with pytest.raises(ValidationError):
        BaseFrontmatter(**_v1_frontmatter(schema_version=1.0))


# ---------------------------------------------------------------------------
# docline: namespace
# ---------------------------------------------------------------------------


def test_frontmatter_accepts_docline_namespace() -> None:
    """The ``docline`` namespace accepts an arbitrary dict of docline-only keys."""
    fm = BaseFrontmatter(
        **_v1_frontmatter(
            docline={"internal_flag": True, "reader_version": "0.4.2"},
        )
    )
    assert fm.docline == {"internal_flag": True, "reader_version": "0.4.2"}


def test_docline_namespace_defaults_to_none() -> None:
    """The ``docline`` namespace defaults to ``None`` when omitted."""
    fm = BaseFrontmatter(**_v1_frontmatter())
    assert fm.docline is None


def test_docline_namespace_rejects_non_dict() -> None:
    """The ``docline`` namespace rejects non-dict values."""
    with pytest.raises(ValidationError):
        BaseFrontmatter(**_v1_frontmatter(docline="not-a-dict"))


def test_docline_namespace_keys_do_not_leak_to_top_level() -> None:
    """Keys placed under the ``docline`` namespace are NOT promoted to top-level fields.

    This protects against accidental contract drift where docline-only metadata
    is mistaken for a graphtor-contract field.
    """
    fm = BaseFrontmatter(
        **_v1_frontmatter(
            docline={"internal_flag": True},
        )
    )
    # internal_flag must live under .docline and NOT be a top-level attribute.
    assert getattr(fm, "internal_flag", None) is None
    assert fm.docline is not None
    assert fm.docline["internal_flag"] is True


# ---------------------------------------------------------------------------
# Backward compatibility — legacy frontmatter still parses
# ---------------------------------------------------------------------------


def test_legacy_frontmatter_still_parses() -> None:
    """A pre-v1 frontmatter dict (no new fields) still constructs successfully.

    All v1 additions MUST be optional with documented defaults so existing
    fixtures and consumer payloads continue to work.
    """
    fm = BaseFrontmatter(**_legacy_frontmatter())
    # Defaults apply silently.
    assert fm.description == ""
    assert fm.content_sha256 == ""
    assert fm.source_path == ""
    assert fm.chunk_strategy == "h1-h2-h3"
    assert fm.schema_version == "1.0"
    assert fm.docline is None


def test_legacy_frontmatter_round_trips_through_model_dump() -> None:
    """Legacy data round-trips: model_dump → BaseFrontmatter is stable."""
    fm = BaseFrontmatter(**_legacy_frontmatter())
    dumped = fm.model_dump()
    rebuilt = BaseFrontmatter(**dumped)
    assert rebuilt.title == fm.title
    assert rebuilt.schema_version == fm.schema_version
    assert rebuilt.docline is None
