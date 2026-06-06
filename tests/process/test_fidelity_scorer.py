"""Tests for ``docline.process.fidelity_scorer`` (task 019.001-T)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_score_page_clean_prose_returns_not_flagged() -> None:
    """Clean prose text should produce a PageScore with needs_docling=False."""
    from docline.process.fidelity_scorer import score_page

    clean = (
        "Azure Cosmos DB is a fully managed NoSQL database service "
        "for modern app development with single-digit-millisecond response times."
    )
    result = score_page(0, clean, page_metadata=None)
    assert result.needs_docling is False
    assert result.reason == "ok"
    assert result.aggregate == 0.0


@pytest.mark.parametrize(
    "sample,expected_trigger",
    [
        ("\ue000\ue001\ue002\ue003\ue004 ABC \ue010\ue011\ue012", "non_ascii_ratio"),
        (
            "| col1 | col2 | col3 |\n|------|------|------|\n| a | b | c |\n" * 20,
            "table_char_density",
        ),
        (
            "\n".join(f"Left col row {i}            Right col row {i}" for i in range(20)),
            "column_gap",
        ),
        (
            "ThisIsAVeryLongLineWithNoWhitespaceProducedByABrokenSubsetFontDecoderThatPypdfFellThroughOn"
            * 3,
            "long_unbroken_line",
        ),
    ],
)
def test_score_page_flags_each_failure_mode(sample: str, expected_trigger: str) -> None:
    """Each POC failure-mode sample should be flagged with the right reason."""
    from docline.process.fidelity_scorer import score_page

    result = score_page(0, sample, page_metadata=None)
    assert result.needs_docling is True, f"sample should be flagged: {sample[:40]!r}"
    assert expected_trigger in result.reason


def test_score_page_with_no_metadata_does_not_fire_metadata_signals() -> None:
    """When page_metadata=None, metadata-dependent signals must return 0.0."""
    from docline.process.fidelity_scorer import score_page

    result = score_page(0, "ordinary paragraph text content here.", page_metadata=None)
    assert result.signals["image_heavy"] == 0.0
    assert result.signals["form_fields"] == 0.0


def test_score_page_applies_weight_override_from_json(tmp_path: Path) -> None:
    """Weight override JSON file must be loaded and applied."""
    from docline.process.fidelity_scorer import score_page

    weights_file = tmp_path / "weights.json"
    weights = {
        "char_density": 0.0,
        "non_ascii_ratio": 0.0,
        "long_unbroken_line": 0.0,
        "column_gap": 0.0,
        "table_char_density": 0.0,
        "image_heavy": 0.0,
        "form_fields": 0.0,
    }
    weights_file.write_text(json.dumps(weights), encoding="utf-8")

    table_sample = "| a | b |\n|---|---|\n| 1 | 2 |\n" * 30
    result = score_page(0, table_sample, page_metadata=None, weights_path=weights_file)
    assert result.needs_docling is False, "zero weights should disable the aggregate flag path"
