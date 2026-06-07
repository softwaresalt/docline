"""Tests for Jaccard-similarity diff metric in QA tripwire (task 020.003-T / U2)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pypdf
import pytest


def _make_pdf(path: Path, page_count: int) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def _ok_runner(markdown: str = "# docling output") -> Any:
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        out = Path(args[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def _no_flag_scorer() -> Any:
    from docline.process.fidelity_scorer import PageScore

    def scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
        return PageScore(
            page_index=page_index,
            signals={},
            aggregate=0.0,
            needs_docling=False,
            reason="ok",
        )

    return scorer


def test_content_similarity_identical_strings_returns_one() -> None:
    """`_content_similarity('hello world', 'hello world')` MUST return 1.0."""
    from docline.process.pdf_triage import _content_similarity

    assert _content_similarity("hello world", "hello world") == pytest.approx(1.0)


def test_content_similarity_disjoint_strings_returns_zero() -> None:
    """`_content_similarity('foo bar', 'completely different')` MUST return 0.0."""
    from docline.process.pdf_triage import _content_similarity

    assert _content_similarity("foo bar baz", "completely unrelated text") == pytest.approx(0.0)


def test_content_similarity_both_empty_returns_one() -> None:
    """Empty inputs both empty MUST return 1.0 (vacuously identical)."""
    from docline.process.pdf_triage import _content_similarity

    assert _content_similarity("", "") == pytest.approx(1.0)


def test_content_similarity_one_empty_returns_zero() -> None:
    """One empty + one non-empty MUST return 0.0."""
    from docline.process.pdf_triage import _content_similarity

    assert _content_similarity("", "hello world") == pytest.approx(0.0)
    assert _content_similarity("hello world", "") == pytest.approx(0.0)


def test_content_similarity_whitespace_and_case_invariant() -> None:
    """Tokenization MUST normalize case and whitespace differences."""
    from docline.process.pdf_triage import _content_similarity

    assert _content_similarity("Hello World", "hello   world") == pytest.approx(1.0)
    assert _content_similarity("Hello, World!", "hello world") == pytest.approx(1.0)


def test_content_similarity_code_fence_vs_no_fence_high_similarity() -> None:
    """Same content with/without code fence (PA4 page 107 case) MUST score >= 0.9.

    The fix that motivated this work: the old `_normalize_markdown` flagged
    these as 100% disagreement. Token-set Jaccard should see them as ~identical.
    """
    from docline.process.pdf_triage import _content_similarity

    plain = (
        '"defaultConsistencyLevel": "ConsistentPrefix"\n'
        '      },\n'
        '      "Session": {\n'
        '        "defaultConsistencyLevel": "Session"\n'
        '      }'
    )
    fenced = (
        '```\n'
        '"defaultConsistencyLevel": "ConsistentPrefix" }, '
        '"Session": { "defaultConsistencyLevel": "Session" }\n'
        '```'
    )
    score = _content_similarity(plain, fenced)
    assert score >= 0.9, f"code-fence formatting variant must score >=0.9; got {score!r}"


def test_qa_tripwire_similarity_histogram_populated(tmp_path: Path) -> None:
    """metadata['qa_similarity_histogram'] MUST be populated and sum to sampled count."""
    from docline.process.pdf_triage import QASampling, process_pdf_triaged

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=5)
    result = process_pdf_triaged(
        pdf,
        output_dir=tmp_path / "out",
        runner=MagicMock(side_effect=_ok_runner()),
        scorer=_no_flag_scorer(),
        qa_sampling=QASampling(sample_rate=1.0, random_seed=42),
    )
    histogram = result.metadata.get("qa_similarity_histogram")
    assert isinstance(histogram, dict), (
        f"qa_similarity_histogram must be a dict; got {type(histogram)}"
    )
    expected_buckets = {">=0.9", "0.7-0.9", "0.5-0.7", "<0.5"}
    assert set(histogram.keys()) == expected_buckets, (
        f"histogram buckets must be exactly {expected_buckets}; got {set(histogram.keys())}"
    )
    sampled = result.metadata.get("qa_sampled_count", 0)
    assert sum(histogram.values()) == sampled
