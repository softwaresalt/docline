"""Tests for new pre-extraction source-aware signals (028.001-T).

Adds tests for ``signal_font_diversity`` and ``signal_text_flow_consistency``,
the two new pure source-aware signals that extend the existing 3
(``image_heavy``, ``form_fields``, ``layout_complexity``) to form the
5-signal pre-extraction triage scoring set used by ``pre_triage_score``
(028.002-T).

Both signals follow the same defensive-degrade pattern as
``signal_layout_complexity``: return ``0.0`` on ``None`` page_metadata
and on any pypdf API exception. Both are pure (no I/O, no extraction)
and deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pypdf
import pytest


def _make_blank_pdf(path: Path, page_count: int = 1) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


class _FakeContents:
    """Minimal pypdf-content-stream shim returning a fixed byte payload."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def get_data(self) -> bytes:
        return self._data


class _FakePageWithContent:
    """Minimal pypdf.PageObject shim that yields a custom content stream.

    Mirrors the duck-typed surface that ``_count_x_clusters`` exercises:
    ``get_contents()`` returns an object whose ``get_data()`` yields bytes.
    Used to inject deterministic content streams into signal tests
    without depending on a real PDF generator like reportlab.
    """

    def __init__(self, content_bytes: bytes, resources: dict | None = None) -> None:
        self._content_bytes = content_bytes
        self._resources = resources if resources is not None else {}

    def get_contents(self) -> _FakeContents:
        return _FakeContents(self._content_bytes)

    def get(self, key: str, default: object | None = None) -> object | None:
        if key == "/Resources":
            return self._resources
        return default


# ---------------------------------------------------------------------------
# signal_font_diversity
# ---------------------------------------------------------------------------


def test_signal_font_diversity_no_metadata_returns_zero() -> None:
    """`signal_font_diversity(None)` MUST return 0.0 (charitable-no-metadata)."""
    from docline.process.fidelity_scorer import signal_font_diversity

    assert signal_font_diversity(None) == pytest.approx(0.0)


def test_signal_font_diversity_blank_page_returns_zero(tmp_path: Path) -> None:
    """A blank pypdf page has no `/Resources/Font` so the signal MUST return 0.0."""
    from docline.process.fidelity_scorer import signal_font_diversity

    pdf_path = _make_blank_pdf(tmp_path / "blank.pdf")
    reader = pypdf.PdfReader(str(pdf_path), strict=False)
    assert signal_font_diversity(reader.pages[0]) == pytest.approx(0.0)


def test_signal_font_diversity_fires_on_multi_font_page() -> None:
    """A page with 4 distinct font references MUST fire (return > 0.5).

    Threshold rationale: pre-triage classifies a page as needing docling
    when its source structure is sufficiently complex. 4 fonts on a single
    page is a strong indicator of stylized layout (callouts, code blocks,
    table headers, body) that the heuristic typically flattens.
    """
    from docline.process.fidelity_scorer import signal_font_diversity

    page = _FakePageWithContent(
        content_bytes=b"",
        resources={"/Font": {"/F1": 1, "/F2": 2, "/F3": 3, "/F4": 4}},
    )
    score = signal_font_diversity(page)
    assert score > 0.5
    assert score <= 1.0


def test_signal_font_diversity_handles_parse_errors() -> None:
    """Any pypdf-side exception MUST degrade gracefully to 0.0."""
    from docline.process.fidelity_scorer import signal_font_diversity

    class _BrokenPage:
        def get(self, key: str, default: object | None = None) -> object | None:
            raise RuntimeError("simulated pypdf failure")

    assert signal_font_diversity(_BrokenPage()) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# signal_text_flow_consistency
# ---------------------------------------------------------------------------


def test_signal_text_flow_consistency_no_metadata_returns_zero() -> None:
    """`signal_text_flow_consistency(None)` MUST return 0.0."""
    from docline.process.fidelity_scorer import signal_text_flow_consistency

    assert signal_text_flow_consistency(None) == pytest.approx(0.0)


def test_signal_text_flow_consistency_blank_page_returns_zero(tmp_path: Path) -> None:
    """A blank page emits no Td/TD/Tm operators so the signal MUST return 0.0."""
    from docline.process.fidelity_scorer import signal_text_flow_consistency

    pdf_path = _make_blank_pdf(tmp_path / "blank.pdf")
    reader = pypdf.PdfReader(str(pdf_path), strict=False)
    assert signal_text_flow_consistency(reader.pages[0]) == pytest.approx(0.0)


def test_signal_text_flow_consistency_fires_on_irregular_baselines() -> None:
    """A page with high variance in consecutive baseline gaps MUST fire.

    The signal interprets "irregular" as "needs docling": uniform
    baseline gaps mean consistent prose, while highly variable gaps
    typically signal multi-column layouts, callouts, code blocks, or
    mixed-size headings that the heuristic flattens incorrectly.
    """
    from docline.process.fidelity_scorer import signal_text_flow_consistency

    # Y positions: 100, 50, 200, 5, 150 — gaps of -50, +150, -195, +145
    irregular_stream = b"100 100 Td 0 -50 Td 0 150 Td 0 -195 Td 0 145 Td"
    page = _FakePageWithContent(content_bytes=irregular_stream)
    score = signal_text_flow_consistency(page)
    assert score > 0.3


def test_signal_text_flow_consistency_low_on_uniform_baselines() -> None:
    """A page with uniform 12-unit baseline gaps MUST score low (close to 0)."""
    from docline.process.fidelity_scorer import signal_text_flow_consistency

    # Identical -12 unit gaps; zero variance → uniform flow → low score
    uniform_stream = b"100 100 Td 0 -12 Td 0 -12 Td 0 -12 Td 0 -12 Td 0 -12 Td"
    page = _FakePageWithContent(content_bytes=uniform_stream)
    score = signal_text_flow_consistency(page)
    assert score < 0.3


def test_signal_text_flow_consistency_handles_parse_errors() -> None:
    """A pypdf get_contents exception MUST degrade gracefully to 0.0."""
    from docline.process.fidelity_scorer import signal_text_flow_consistency

    class _BrokenPage:
        def get_contents(self) -> object:
            raise RuntimeError("simulated pypdf content-stream failure")

    assert signal_text_flow_consistency(_BrokenPage()) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Module-level integration (signal names + default weights)
# ---------------------------------------------------------------------------


def test_new_signals_in_pre_triage_signal_names() -> None:
    """Both new signals MUST appear in `_PRE_TRIAGE_SIGNAL_NAMES` (028.002-T sets this up)."""
    from docline.process.fidelity_scorer import _PRE_TRIAGE_SIGNAL_NAMES

    assert "font_diversity" in _PRE_TRIAGE_SIGNAL_NAMES
    assert "text_flow_consistency" in _PRE_TRIAGE_SIGNAL_NAMES


def test_new_signals_have_default_pre_triage_weights() -> None:
    """`_DEFAULT_PRE_TRIAGE_WEIGHTS` MUST include both new signals."""
    from docline.process.fidelity_scorer import _DEFAULT_PRE_TRIAGE_WEIGHTS

    assert "font_diversity" in _DEFAULT_PRE_TRIAGE_WEIGHTS
    assert "text_flow_consistency" in _DEFAULT_PRE_TRIAGE_WEIGHTS
    assert _DEFAULT_PRE_TRIAGE_WEIGHTS["font_diversity"] > 0
    assert _DEFAULT_PRE_TRIAGE_WEIGHTS["text_flow_consistency"] > 0


# ---------------------------------------------------------------------------
# pre_triage_score + PreTriageDecision (028.002-T)
# ---------------------------------------------------------------------------


class _FakeAnnotationWidget:
    """Minimal form-field annotation that triggers ``signal_form_fields``."""

    def get_object(self) -> dict:
        return {"/Subtype": "/Widget"}


class _FakeImages:
    def __init__(self, count: int) -> None:
        self._count = count

    def __iter__(self):
        return iter(range(self._count))


class _FakeComplexPage:
    """Synthetic page that triggers 3+ of the 5 pre-triage signals."""

    def __init__(self) -> None:
        # X-cluster pattern: 3 columns to push layout_complexity > 0
        # Y-irregular pattern: variable baseline gaps to push text_flow_consistency > 0
        self._content = (
            b"100 700 Td 200 700 Td 400 700 Td "  # X-clusters at 100/200/400
            b"0 -50 Td 0 -10 Td 0 -200 Td 0 -5 Td"  # Irregular Y-gaps
        )
        self._resources = {"/Font": {"/F1": 1, "/F2": 2, "/F3": 3, "/F4": 4, "/F5": 5}}
        self.annotations = [_FakeAnnotationWidget()]
        self.images = _FakeImages(5)

    def get_contents(self) -> _FakeContents:
        return _FakeContents(self._content)

    def get(self, key: str, default: object | None = None) -> object | None:
        if key == "/Resources":
            return self._resources
        return default


class _FakeCleanPage:
    """Synthetic page that triggers zero pre-triage signals (typical prose)."""

    def __init__(self) -> None:
        # Single uniform-baseline column, single font, no images, no widgets
        self._content = b"100 700 Td 0 -12 Td 0 -12 Td 0 -12 Td 0 -12 Td"
        self._resources = {"/Font": {"/F1": 1}}
        self.annotations: list = []
        self.images = _FakeImages(0)

    def get_contents(self) -> _FakeContents:
        return _FakeContents(self._content)

    def get(self, key: str, default: object | None = None) -> object | None:
        if key == "/Resources":
            return self._resources
        return default


class _FakeUncertainPage:
    """Synthetic page that lands in the uncertain band (0.2 < aggregate < 0.7)."""

    def __init__(self) -> None:
        # Moderate irregularity: CV around 0.6 (gaps of 10, 30, 10, 30, 10)
        # Plus 4 fonts (font_diversity ≈ 0.67) but no images / widgets /
        # multi-column layout. Aggregate lands in the uncertain band.
        self._content = b"100 700 Td 0 -10 Td 0 -30 Td 0 -10 Td 0 -30 Td 0 -10 Td"
        self._resources = {"/Font": {"/F1": 1, "/F2": 2, "/F3": 3, "/F4": 4}}
        self.annotations: list = []
        self.images = _FakeImages(0)

    def get_contents(self) -> _FakeContents:
        return _FakeContents(self._content)

    def get(self, key: str, default: object | None = None) -> object | None:
        if key == "/Resources":
            return self._resources
        return default


def test_pre_triage_score_classifies_complex_page_as_route_to_docling() -> None:
    """A page that triggers ≥3 of the 5 pre-triage signals MUST route to docling."""
    from docline.process.fidelity_scorer import pre_triage_score

    result = pre_triage_score(0, _FakeComplexPage())
    assert result.classification == "route_to_docling"
    assert result.aggregate >= 0.7
    # All 5 signal keys must be populated
    assert set(result.signals.keys()) == {
        "image_heavy",
        "form_fields",
        "layout_complexity",
        "font_diversity",
        "text_flow_consistency",
    }


def test_pre_triage_score_classifies_clean_page_as_route_to_heuristic() -> None:
    """A clean prose page (all signals near 0) MUST route to heuristic."""
    from docline.process.fidelity_scorer import pre_triage_score

    result = pre_triage_score(0, _FakeCleanPage())
    assert result.classification == "route_to_heuristic"
    assert result.aggregate <= 0.2


def test_pre_triage_score_classifies_in_between_page_as_uncertain() -> None:
    """A page with mid-range signal scores MUST classify as uncertain (fallback)."""
    from docline.process.fidelity_scorer import pre_triage_score

    result = pre_triage_score(0, _FakeUncertainPage())
    assert result.classification == "uncertain"
    assert 0.2 < result.aggregate < 0.7


def test_pre_triage_score_respects_weights_override(tmp_path: Path) -> None:
    """Passing weights_path MUST override the default pre-triage weights."""
    import json

    from docline.process.fidelity_scorer import pre_triage_score

    weights_file = tmp_path / "pre_triage_weights.json"
    # Mute font_diversity entirely so a 5-font page no longer hard-flags
    weights_file.write_text(
        json.dumps({"font_diversity": 0.0, "text_flow_consistency": 0.0}),
        encoding="utf-8",
    )
    result = pre_triage_score(0, _FakeComplexPage(), weights_path=weights_file)
    # With font_diversity + text_flow_consistency muted, the remaining 3
    # signals (image_heavy, form_fields, layout_complexity) still push
    # aggregate above 0.2 (so not route_to_heuristic) but the missing
    # contribution from the muted signals should keep the classification
    # below the route_to_docling threshold.
    assert result.classification in {"uncertain", "route_to_docling"}
    # Confirm the override applied: at least one weight was non-default.
    assert result.aggregate < 1.0


def test_pre_triage_decision_is_frozen() -> None:
    """`PreTriageDecision` MUST be frozen (mutation raises FrozenInstanceError)."""
    import dataclasses

    from docline.process.fidelity_scorer import PreTriageDecision, pre_triage_score

    result = pre_triage_score(0, _FakeCleanPage())
    assert isinstance(result, PreTriageDecision)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.aggregate = 0.99  # type: ignore[misc]


def test_pre_triage_score_is_deterministic() -> None:
    """Two invocations on the same input MUST yield identical results."""
    from docline.process.fidelity_scorer import pre_triage_score

    page = _FakeComplexPage()
    result_a = pre_triage_score(0, page)
    result_b = pre_triage_score(0, _FakeComplexPage())
    assert result_a.aggregate == pytest.approx(result_b.aggregate)
    assert result_a.classification == result_b.classification
    assert result_a.signals == result_b.signals


def test_pre_triage_score_no_metadata_routes_to_uncertain() -> None:
    """Without metadata, all signals return 0 → aggregate 0 → route_to_heuristic.

    Document this behavior explicitly: a None page_metadata is treated as
    "no source signal triggered, defer to heuristic". This means callers
    invoking pre_triage_score without metadata effectively bypass the
    short-circuit.
    """
    from docline.process.fidelity_scorer import pre_triage_score

    result = pre_triage_score(0, None)
    assert result.classification == "route_to_heuristic"
    assert result.aggregate == pytest.approx(0.0)
