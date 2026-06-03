"""Red-first contract tests for WebFrontmatter staging metadata (010.032-T).

Adds the four staging-metadata fields surfaced by the graphtor-docs ingestion
contract for crawled web pages:

* ``http_status`` — final HTTP status code observed on fetch (int >= 100).
* ``content_type`` — final Content-Type header from the responding origin.
* ``final_url`` — post-redirect URL the body was fetched from (http(s)).
* ``fetched_at`` — ISO-8601 timestamp of the final fetch attempt.

All four fields are docline-only metadata: they MUST serialize inside the
``docline:`` namespace and MUST NOT appear as top-level keys of the
serialized frontmatter contract surface.

These tests are authored red-first per Constitution Principle II.
"""

from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from docline.schema.library import WebFrontmatter

# The graphtor-docs ingestion contract surface — top-level frontmatter keys
# permitted on any docline frontmatter variant in serialized form.
GRAPHTOR_CONTRACT_KEYS: frozenset[str] = frozenset(
    {
        "title",
        "source",
        "ingested_at",
        "doc_type",
        "description",
        "content_sha256",
        "source_path",
        "chunk_strategy",
        "schema_version",
    }
)


def _base_fields() -> dict[str, Any]:
    return {
        "title": "My Page",
        "source": "https://example.com",
        "ingested_at": datetime(2024, 1, 1),
    }


def _staging_fields() -> dict[str, Any]:
    return {
        "http_status": 200,
        "content_type": "text/html; charset=utf-8",
        "final_url": "https://example.com/post-redirect",
        "fetched_at": datetime(2024, 1, 1, 12, 30, 0),
    }


# ---------------------------------------------------------------------------
# Construction and attribute access
# ---------------------------------------------------------------------------


def test_web_frontmatter_accepts_staging_metadata_fields() -> None:
    """WebFrontmatter accepts the four staging-metadata fields at construction."""
    fm = WebFrontmatter(
        **_base_fields(),
        source_url="https://example.com",
        **_staging_fields(),
    )
    assert fm.http_status == 200
    assert fm.content_type == "text/html; charset=utf-8"
    assert fm.final_url == "https://example.com/post-redirect"
    assert fm.fetched_at == datetime(2024, 1, 1, 12, 30, 0)


def test_web_frontmatter_staging_fields_default_to_none() -> None:
    """All four staging-metadata fields default to ``None`` when omitted."""
    fm = WebFrontmatter(
        **_base_fields(),
        source_url="https://example.com",
    )
    assert fm.http_status is None
    assert fm.content_type is None
    assert fm.final_url is None
    assert fm.fetched_at is None


# ---------------------------------------------------------------------------
# Serialization: staging fields live under docline namespace
# ---------------------------------------------------------------------------


def test_web_staging_fields_serialize_under_docline_namespace() -> None:
    """Staging-metadata fields MUST appear inside ``docline:``."""
    fm = WebFrontmatter(
        **_base_fields(),
        source_url="https://example.com",
        crawl_depth=1,
        **_staging_fields(),
    )
    dumped = fm.model_dump()
    docline_ns = dumped["docline"]
    assert docline_ns["http_status"] == 200
    assert docline_ns["content_type"] == "text/html; charset=utf-8"
    assert docline_ns["final_url"] == "https://example.com/post-redirect"
    # Pydantic emits datetime as datetime; serialization to YAML later may stringify.
    assert docline_ns["fetched_at"] == datetime(2024, 1, 1, 12, 30, 0)


def test_web_staging_fields_not_at_top_level() -> None:
    """Staging-metadata fields MUST NOT appear as top-level dump keys."""
    fm = WebFrontmatter(
        **_base_fields(),
        source_url="https://example.com",
        **_staging_fields(),
    )
    dumped = fm.model_dump()
    for key in ("http_status", "content_type", "final_url", "fetched_at"):
        assert key not in dumped, f"{key} leaked to top-level frontmatter"


def test_web_dump_top_level_remains_contract_subset_with_staging_fields() -> None:
    """Top-level keys remain ⊆ contract ∪ {docline} when staging fields are set."""
    fm = WebFrontmatter(
        **_base_fields(),
        source_url="https://example.com",
        crawl_depth=0,
        **_staging_fields(),
    )
    dumped = fm.model_dump()
    allowed = GRAPHTOR_CONTRACT_KEYS | {"docline"}
    extras = set(dumped.keys()) - allowed
    assert extras == set(), f"unexpected top-level keys: {extras}"


# ---------------------------------------------------------------------------
# Validation: HTTP status range and URL scheme
# ---------------------------------------------------------------------------


def test_web_http_status_rejects_sub_minimum_value() -> None:
    """``http_status`` MUST be a valid HTTP status code (>= 100)."""
    with pytest.raises(ValidationError):
        WebFrontmatter(
            **_base_fields(),
            source_url="https://example.com",
            http_status=42,
        )


def test_web_final_url_rejects_non_http_scheme() -> None:
    """``final_url`` MUST start with ``http://`` or ``https://``."""
    with pytest.raises(ValidationError):
        WebFrontmatter(
            **_base_fields(),
            source_url="https://example.com",
            final_url="ftp://example.com/file",
        )


def test_web_final_url_accepts_mixed_case_scheme() -> None:
    """``final_url`` scheme check is case-insensitive."""
    fm = WebFrontmatter(
        **_base_fields(),
        source_url="https://example.com",
        final_url="HTTPS://example.com/elsewhere",
    )
    assert fm.final_url == "HTTPS://example.com/elsewhere"


# ---------------------------------------------------------------------------
# Merging with caller-supplied docline namespace
# ---------------------------------------------------------------------------


def test_web_staging_fields_merge_with_explicit_docline_namespace() -> None:
    """Staging fields coexist with caller-supplied ``docline`` entries."""
    fm = WebFrontmatter(
        **_base_fields(),
        source_url="https://example.com",
        crawl_depth=2,
        docline={"reader_version": "0.4.2"},
        **_staging_fields(),
    )
    dumped = fm.model_dump()
    ns = dumped["docline"]
    assert ns["reader_version"] == "0.4.2"
    assert ns["http_status"] == 200
    assert ns["content_type"] == "text/html; charset=utf-8"
    assert ns["final_url"] == "https://example.com/post-redirect"
    assert ns["crawl_depth"] == 2
