"""Red-first contract tests for library frontmatter v1 reconciliation (F1.T3).

These tests pin the v1 contract for library subclasses of ``BaseFrontmatter``:

* Subclass-specific fields (e.g. ``tags``, ``section``, ``status``,
  ``decision_date``, ``speaker_count``, ``duration_seconds``, ``source_url``,
  ``crawl_depth``) are docline-only metadata. They MUST NOT appear as
  top-level keys in the serialized frontmatter contract surface.
* On ``model_dump()``, the top-level keys of any subclass MUST be a subset of
  the graphtor-contract field set plus the ``docline`` namespace.
* Subclass-specific values MUST appear inside the ``docline:`` namespace in
  ``model_dump()``.
* Direct attribute access on the subclass instance still works for ergonomics
  (``fm.crawl_depth``).
* Round-trip: dump → reconstruct via subclass constructor → equivalent.

These tests are authored red-first per Constitution Principle II. They MUST
fail against the pre-F1.T3 ``library.py`` implementation and pass after the
reconciliation lands.
"""

from datetime import datetime
from typing import Any

from docline.schema.library import (
    AdrFrontmatter,
    TranscriptFrontmatter,
    WebFrontmatter,
    WikiFrontmatter,
)

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
        "title": "My Doc",
        "source": "http://example.com",
        "ingested_at": datetime(2024, 1, 1),
    }


# ---------------------------------------------------------------------------
# Wiki: tags + section are docline-only
# ---------------------------------------------------------------------------


def test_wiki_dump_top_level_is_contract_subset() -> None:
    """``WikiFrontmatter.model_dump()`` top-level keys ⊆ contract ∪ {docline}."""
    fm = WikiFrontmatter(**_base_fields(), tags=["a", "b"], section="overview")
    dumped = fm.model_dump()
    allowed = GRAPHTOR_CONTRACT_KEYS | {"docline"}
    extras = set(dumped.keys()) - allowed
    assert extras == set(), f"unexpected top-level keys: {extras}"


def test_wiki_tags_and_section_live_under_docline_namespace() -> None:
    """Wiki-specific ``tags`` and ``section`` serialize under ``docline:``."""
    fm = WikiFrontmatter(**_base_fields(), tags=["a", "b"], section="overview")
    dumped = fm.model_dump()
    assert "tags" not in dumped
    assert "section" not in dumped
    assert dumped["docline"] == {"tags": ["a", "b"], "section": "overview"}


def test_wiki_attribute_access_still_works() -> None:
    """Direct Python attribute access on the subclass remains ergonomic."""
    fm = WikiFrontmatter(**_base_fields(), tags=["a"], section="s")
    assert fm.tags == ["a"]
    assert fm.section == "s"


# ---------------------------------------------------------------------------
# ADR: status + decision_date are docline-only
# ---------------------------------------------------------------------------


def test_adr_dump_top_level_is_contract_subset() -> None:
    """``AdrFrontmatter.model_dump()`` top-level keys ⊆ contract ∪ {docline}."""
    fm = AdrFrontmatter(
        **_base_fields(),
        doc_type="adr",
        status="accepted",
        decision_date="2024-01-01",
    )
    dumped = fm.model_dump()
    allowed = GRAPHTOR_CONTRACT_KEYS | {"docline"}
    extras = set(dumped.keys()) - allowed
    assert extras == set(), f"unexpected top-level keys: {extras}"


def test_adr_status_and_decision_date_live_under_docline_namespace() -> None:
    """ADR-specific ``status`` and ``decision_date`` serialize under ``docline:``."""
    fm = AdrFrontmatter(
        **_base_fields(),
        doc_type="adr",
        status="accepted",
        decision_date="2024-01-01",
    )
    dumped = fm.model_dump()
    assert "status" not in dumped
    assert "decision_date" not in dumped
    assert dumped["docline"] == {"status": "accepted", "decision_date": "2024-01-01"}


def test_adr_attribute_access_still_works() -> None:
    """Direct Python attribute access on the subclass remains ergonomic."""
    fm = AdrFrontmatter(
        **_base_fields(),
        doc_type="adr",
        status="accepted",
        decision_date="2024-01-01",
    )
    assert fm.status == "accepted"
    assert fm.decision_date == "2024-01-01"


# ---------------------------------------------------------------------------
# Transcript: speaker_count + duration_seconds are docline-only
# ---------------------------------------------------------------------------


def test_transcript_dump_top_level_is_contract_subset() -> None:
    """``TranscriptFrontmatter.model_dump()`` top-level keys ⊆ contract ∪ {docline}."""
    fm = TranscriptFrontmatter(
        **_base_fields(),
        doc_type="transcript",
        speaker_count=3,
        duration_seconds=120.5,
    )
    dumped = fm.model_dump()
    allowed = GRAPHTOR_CONTRACT_KEYS | {"docline"}
    extras = set(dumped.keys()) - allowed
    assert extras == set(), f"unexpected top-level keys: {extras}"


def test_transcript_fields_live_under_docline_namespace() -> None:
    """Transcript-specific fields serialize under ``docline:``."""
    fm = TranscriptFrontmatter(
        **_base_fields(),
        doc_type="transcript",
        speaker_count=3,
        duration_seconds=120.5,
    )
    dumped = fm.model_dump()
    assert "speaker_count" not in dumped
    assert "duration_seconds" not in dumped
    assert dumped["docline"] == {"speaker_count": 3, "duration_seconds": 120.5}


def test_transcript_attribute_access_still_works() -> None:
    """Direct Python attribute access on the subclass remains ergonomic."""
    fm = TranscriptFrontmatter(
        **_base_fields(),
        doc_type="transcript",
        speaker_count=2,
        duration_seconds=60.0,
    )
    assert fm.speaker_count == 2
    assert fm.duration_seconds == 60.0


# ---------------------------------------------------------------------------
# Web: source_url + crawl_depth are docline-only
# ---------------------------------------------------------------------------


def test_web_dump_top_level_is_contract_subset() -> None:
    """``WebFrontmatter.model_dump()`` top-level keys ⊆ contract ∪ {docline}."""
    fm = WebFrontmatter(
        **_base_fields(),
        doc_type="web",
        source_url="https://example.com/page",
        crawl_depth=2,
    )
    dumped = fm.model_dump()
    allowed = GRAPHTOR_CONTRACT_KEYS | {"docline"}
    extras = set(dumped.keys()) - allowed
    assert extras == set(), f"unexpected top-level keys: {extras}"


def test_web_fields_live_under_docline_namespace() -> None:
    """Web-specific ``source_url`` and ``crawl_depth`` serialize under ``docline:``."""
    fm = WebFrontmatter(
        **_base_fields(),
        doc_type="web",
        source_url="https://example.com/page",
        crawl_depth=2,
    )
    dumped = fm.model_dump()
    assert "source_url" not in dumped
    assert "crawl_depth" not in dumped
    assert dumped["docline"] == {
        "source_url": "https://example.com/page",
        "crawl_depth": 2,
    }


def test_web_attribute_access_still_works() -> None:
    """Direct Python attribute access on the subclass remains ergonomic."""
    fm = WebFrontmatter(
        **_base_fields(),
        doc_type="web",
        source_url="https://example.com/page",
        crawl_depth=1,
    )
    assert fm.source_url == "https://example.com/page"
    assert fm.crawl_depth == 1


# ---------------------------------------------------------------------------
# Docline namespace omission and merging
# ---------------------------------------------------------------------------


def test_wiki_dump_omits_docline_when_no_subclass_fields_set() -> None:
    """Subclass with only default empty subclass fields still emits a ``docline`` key.

    Subclass-specific fields always live under ``docline:``, even when they hold
    their default values, so consumers can rely on the namespace shape being
    stable.
    """
    fm = WikiFrontmatter(**_base_fields())
    dumped = fm.model_dump()
    # tags=[] and section="" defaults still serialize under docline namespace.
    assert dumped["docline"] == {"tags": [], "section": ""}


def test_existing_user_docline_namespace_keys_are_merged() -> None:
    """User-provided ``docline`` dict merges with subclass-derived fields.

    If the caller passes ``docline={"reader_version": "0.4.2"}`` explicitly,
    it MUST coexist with subclass-derived entries like ``crawl_depth`` rather
    than being overwritten.
    """
    fm = WebFrontmatter(
        **_base_fields(),
        doc_type="web",
        source_url="https://example.com",
        crawl_depth=3,
        docline={"reader_version": "0.4.2"},
    )
    dumped = fm.model_dump()
    assert dumped["docline"]["reader_version"] == "0.4.2"
    assert dumped["docline"]["source_url"] == "https://example.com"
    assert dumped["docline"]["crawl_depth"] == 3
