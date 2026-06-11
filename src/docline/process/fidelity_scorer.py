"""Per-page fidelity scorer for the triage-then-repair PDF pipeline.

Provides eight pure-function fidelity signals
(``char_density``, ``non_ascii_ratio``, ``long_unbroken_line``,
``column_gap``, ``table_char_density``, ``image_heavy``, ``form_fields``,
``layout_complexity``), a weighted combiner :func:`score_page`, and a
frozen :class:`PageScore` result. Signal weights are externalized via
JSON so they can be tuned without code changes.

Weights are importance multipliers applied to BOTH the hard-flag path
(any single weighted signal at or above ``_HARD_FLAG_THRESHOLD``) and
the aggregate path (weighted mean at or above ``_AGGREGATE_FLAG_THRESHOLD``).
Setting a weight to ``0.0`` fully mutes that signal across both paths.

POC reference: ``docs/scratch/2026-06-06-fidelity-scorer-poc.py``.
Plan: ``docs/plans/2026-06-06-triage-then-repair-plan.md`` § U1.
``layout_complexity`` added in 020.004-T (plan
``docs/plans/2026-06-07-pa4-calibration-closure-plan.md`` § U3).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from docline.schema.models import DoclineError

_log = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Tunable thresholds. These start as reasonable defaults; calibrate against
# a corpus via ``--triage-report-only`` (task 019.006-T) before locking.
# -------------------------------------------------------------------------

_MIN_CHARS_PER_PAGE = 200
_NON_ASCII_RATIO_THRESHOLD = 0.05
_LONG_LINE_MIN_CHARS = 200
_LONG_LINE_MAX_WORDS = 20
_COLUMN_GAP_MIN_SPACES = 6
_COLUMN_GAP_LINE_RATIO = 0.30
_TABLE_CHAR_DENSITY_THRESHOLD = 0.02
_IMAGE_COUNT_HEAVY = 3

_HARD_FLAG_THRESHOLD = 0.7
_AGGREGATE_FLAG_THRESHOLD = 0.5

_DEFAULT_SIGNAL_WEIGHTS: dict[str, float] = {
    "char_density": 1.0,
    "non_ascii_ratio": 1.2,
    "long_unbroken_line": 0.8,
    "column_gap": 1.0,
    "table_char_density": 1.0,
    "image_heavy": 0.9,
    "form_fields": 1.2,
    "layout_complexity": 1.1,
}

_SIGNAL_NAMES: tuple[str, ...] = (
    "char_density",
    "non_ascii_ratio",
    "long_unbroken_line",
    "column_gap",
    "table_char_density",
    "image_heavy",
    "form_fields",
    "layout_complexity",
)

# -------------------------------------------------------------------------
# Pre-triage signal set (028.001-T / 028.002-T): the 5 source-aware signals
# usable BEFORE running heuristic extraction. Used by ``pre_triage_score``
# (added in 028.002-T) to short-circuit obviously-complex pages directly
# to docling without first wasting a heuristic extraction pass.
# -------------------------------------------------------------------------

_PRE_TRIAGE_SIGNAL_NAMES: tuple[str, ...] = (
    "image_heavy",
    "form_fields",
    "layout_complexity",
    "font_diversity",
    "text_flow_consistency",
)

_DEFAULT_PRE_TRIAGE_WEIGHTS: dict[str, float] = {
    "image_heavy": 0.9,
    "form_fields": 1.2,
    "layout_complexity": 1.1,
    "font_diversity": 1.0,
    "text_flow_consistency": 1.0,
}


class FidelityScorerError(DoclineError):
    """Raised on scorer input-validation failures."""


@dataclass(frozen=True)
class PageScore:
    """Per-page fidelity assessment.

    Attributes:
        page_index: Zero-based page index in the source PDF.
        signals: Map of signal name to raw score in ``[0.0, 1.0]``.
        aggregate: Weighted mean across all signals in ``[0.0, 1.0]``.
        needs_docling: True when the page should be routed through docling.
        reason: Comma-separated triggered signal names or ``"ok"``.
    """

    page_index: int
    signals: dict[str, float] = field(default_factory=dict)
    aggregate: float = 0.0
    needs_docling: bool = False
    reason: str = ""


# -------------------------------------------------------------------------
# Individual signal functions. Each is pure, deterministic, and cheap.
# Each returns a float in [0, 1] where 1.0 means "definitely broken".
# -------------------------------------------------------------------------


def signal_char_density(text: str, page_metadata: object | None = None) -> float:
    """Flag pages whose extracted text is suspiciously sparse.

    Without page metadata we cannot distinguish a legitimately short
    page from an image-heavy page where the heuristic missed content,
    so the charitable default is to return 0.0. When metadata is
    available, return a positive signal only if the page is sparse AND
    has embedded images (the heuristic clearly missed content).
    """
    char_count = len(text.strip())
    if char_count >= _MIN_CHARS_PER_PAGE:
        return 0.0
    if page_metadata is None:
        return 0.0
    if _page_image_count(page_metadata) == 0:
        return 0.0
    return 1.0 - (char_count / _MIN_CHARS_PER_PAGE)


def signal_non_ascii_ratio(text: str) -> float:
    """Flag pages with high non-printable / private-use codepoint ratio."""
    if not text:
        return 0.0
    suspicious = sum(
        1
        for c in text
        if (unicodedata.category(c) in ("Co", "Cn") or (not c.isprintable() and c not in "\n\r\t "))
    )
    ratio = suspicious / len(text)
    if ratio <= _NON_ASCII_RATIO_THRESHOLD:
        return 0.0
    return min(1.0, (ratio - _NON_ASCII_RATIO_THRESHOLD) / 0.15)


def signal_long_unbroken_line(text: str) -> float:
    """Flag pages with very long lines that have almost no whitespace."""
    max_chars = 0
    min_word_count_for_long_line = _LONG_LINE_MAX_WORDS + 1
    for line in text.splitlines():
        if len(line) >= _LONG_LINE_MIN_CHARS:
            max_chars = max(max_chars, len(line))
            min_word_count_for_long_line = min(min_word_count_for_long_line, len(line.split()))
    if max_chars == 0:
        return 0.0
    if min_word_count_for_long_line <= _LONG_LINE_MAX_WORDS:
        return 1.0
    return 0.0


def signal_column_gap(text: str) -> float:
    """Flag pages whose lines show consistent multi-space gutters."""
    gap_pattern = re.compile(r"\S {" + str(_COLUMN_GAP_MIN_SPACES) + r",}\S")
    non_blank_lines = [line for line in text.splitlines() if line.strip()]
    if not non_blank_lines:
        return 0.0
    matches = sum(1 for line in non_blank_lines if gap_pattern.search(line))
    ratio = matches / len(non_blank_lines)
    if ratio < _COLUMN_GAP_LINE_RATIO:
        return 0.0
    return min(1.0, ratio / 0.5)


def signal_table_char_density(text: str) -> float:
    """Flag pages with a high density of table-grid characters."""
    if not text:
        return 0.0
    grid_chars = sum(1 for c in text if c in "|│─━═")
    density = grid_chars / len(text)
    if density < _TABLE_CHAR_DENSITY_THRESHOLD:
        return 0.0
    return min(1.0, (density - _TABLE_CHAR_DENSITY_THRESHOLD) / 0.04)


def signal_image_heavy(page_metadata: object | None) -> float:
    """Flag pages whose pypdf metadata reports many embedded images."""
    if page_metadata is None:
        return 0.0
    count = _page_image_count(page_metadata)
    if count >= _IMAGE_COUNT_HEAVY:
        return 1.0
    return 0.0


def signal_font_diversity(page_metadata: object | None) -> float:
    """Flag pages with multiple distinct font references (028.001-T).

    Inspects ``page_metadata['/Resources']['/Font']`` for the count of
    distinct font keys. A page with many font references typically has
    stylized layout (callouts, code blocks, table headers, body) that
    the heuristic extractor flattens into ordinary prose.

    Charitable when no metadata: returns ``0.0`` for ``None`` input or
    any pypdf API error so the signal degrades gracefully.

    Scoring scale:
        * 0-2 fonts → 0.0 (single typography, typical clean prose)
        * 3 fonts   → 0.4 (mild styling)
        * 4 fonts   → 0.7 (multi-section page)
        * 5+ fonts  → 1.0 (high-complexity page)

    Args:
        page_metadata: ``pypdf.PageObject`` for the source page.

    Returns:
        Score in ``[0.0, 1.0]``. Higher means more font diversity was
        detected in the source.
    """
    if page_metadata is None:
        return 0.0
    try:
        resources = page_metadata.get("/Resources", None)
        if resources is None:
            return 0.0
        # Resources may be a pypdf IndirectObject or a dict; both expose .get().
        if hasattr(resources, "get_object"):
            resources = resources.get_object()
        font_dict = resources.get("/Font", None) if hasattr(resources, "get") else None
        if font_dict is None:
            return 0.0
        if hasattr(font_dict, "get_object"):
            font_dict = font_dict.get_object()
        font_count = len(list(font_dict.keys())) if hasattr(font_dict, "keys") else 0
    except (AttributeError, KeyError, TypeError):
        return 0.0
    except Exception:  # noqa: BLE001 — pypdf API surface varies; degrade gracefully
        _log.debug("font_diversity: resource lookup failed", exc_info=True)
        return 0.0
    if font_count <= 2:
        return 0.0
    return min(1.0, (font_count - 2) / 3.0)


def signal_text_flow_consistency(page_metadata: object | None) -> float:
    """Flag pages with irregular baseline spacing in the content stream (028.001-T).

    Parses the page content stream for ``Td``/``TD``/``Tm`` text-position
    operators, extracts the consecutive Y-coordinate deltas (baseline
    gaps), and computes a normalized variance score. Pages with uniform
    baseline gaps (consistent prose) score near 0; pages with highly
    variable gaps (multi-column callouts, code blocks, mixed-size
    headings, table cells) score near 1.

    The name ``text_flow_consistency`` reflects the signal's purpose
    (gauging consistency), but the score follows the codebase convention
    that signals FIRE when problematic: high return value = LOW
    consistency = page needs docling.

    Charitable when no metadata: returns ``0.0`` for ``None`` input,
    empty content stream, or any pypdf API error.

    Args:
        page_metadata: ``pypdf.PageObject`` for the source page.

    Returns:
        Score in ``[0.0, 1.0]``. Higher means more irregular baseline
        flow was detected.
    """
    if page_metadata is None:
        return 0.0
    try:
        contents = getattr(page_metadata, "get_contents", lambda: None)()
        if contents is None:
            return 0.0
        get_data = getattr(contents, "get_data", None)
        if get_data is None:
            return 0.0
        raw = get_data()
    except (AttributeError, KeyError, TypeError):
        return 0.0
    except Exception:  # noqa: BLE001 — pypdf API surface varies; degrade gracefully
        _log.debug("text_flow_consistency: content stream extraction failed", exc_info=True)
        return 0.0

    if not isinstance(raw, bytes):
        return 0.0

    try:
        stream = raw.decode("latin-1", errors="ignore")
    except (UnicodeDecodeError, AttributeError):
        return 0.0

    # Walk Td/TD/Tm operators, tracking current Y position. Each Td/TD
    # offset advances Y by the ty parameter; Tm sets Y to the f parameter.
    y_positions: list[float] = []
    current_y = 0.0
    pattern = re.compile(
        r"((?:-?\d+\.?\d*\s+){5}-?\d+\.?\d*)\s+Tm|"
        r"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+Td|"
        r"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+TD"
    )
    for match in pattern.finditer(stream):
        tm_group, _td_x, td_y, _td_cap_x, td_cap_y = match.groups()
        try:
            if tm_group is not None:
                parts = tm_group.split()
                current_y = float(parts[5])
            elif td_y is not None:
                current_y += float(td_y)
            elif td_cap_y is not None:
                current_y += float(td_cap_y)
        except (ValueError, IndexError):
            continue
        y_positions.append(current_y)

    # Need at least 3 positions to compute 2 gaps and a variance.
    if len(y_positions) < 3:
        return 0.0

    gaps = [abs(y_positions[i + 1] - y_positions[i]) for i in range(len(y_positions) - 1)]
    mean_gap = sum(gaps) / len(gaps)
    if mean_gap == 0:
        return 0.0

    # Coefficient of variation (stddev / mean) as a scale-free irregularity
    # metric. CV > 1.0 saturates to 1.0 (highly irregular).
    variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
    stddev = variance**0.5
    cv = stddev / mean_gap
    return min(1.0, cv)


def signal_form_fields(page_metadata: object | None) -> float:
    """Flag pages that contain form-field annotations."""
    if page_metadata is None:
        return 0.0
    try:
        annotations = getattr(page_metadata, "annotations", None)
        if annotations is None:
            return 0.0
        for annot in annotations:
            obj = annot.get_object() if hasattr(annot, "get_object") else annot
            if obj.get("/Subtype") == "/Widget":
                return 1.0
    except (AttributeError, KeyError, TypeError):
        return 0.0
    return 0.0


def _page_image_count(page_metadata: object) -> int:
    """Best-effort image count for a ``pypdf.PageObject``."""
    try:
        images = getattr(page_metadata, "images", None)
        if images is None:
            return 0
        return len(list(images))
    except (AttributeError, KeyError, TypeError):
        return 0


def signal_layout_complexity(text: str, page_metadata: object | None = None) -> float:
    """Flag pages whose source PDF layout has structural complexity (020.004-T / U3).

    Inspects the source ``pypdf.PageObject`` for text-run X-coordinate
    clustering and compares the column count against the heuristic-text
    line count. Fires (returns positive value in ``[0, 1]``) when the
    source PDF has multiple distinct X-positioned text runs but the
    extracted text reads as a small number of lines — the canonical
    signature of a table or multi-column layout that pypdf flattened
    into ordinary-looking prose.

    Returns ``0.0`` when ``page_metadata`` is ``None`` (charitable-
    when-no-metadata; matches the pattern from ``signal_char_density``).

    Args:
        text: Heuristic-extracted page text.
        page_metadata: ``pypdf.PageObject`` for the source page.

    Returns:
        Score in ``[0.0, 1.0]``. Higher means more layout structure
        was detected in the source that the heuristic failed to surface.
    """
    if page_metadata is None:
        return 0.0
    x_clusters = _count_x_clusters(page_metadata)
    if x_clusters == 0:
        return 0.0
    line_count = max(1, len([ln for ln in text.splitlines() if ln.strip()]))
    excess = x_clusters - line_count
    if excess <= 0:
        return 0.0
    return min(1.0, excess / 4.0)


def _count_x_clusters(page_metadata: object, tolerance: float = 10.0) -> int:
    """Count distinct X-coordinate clusters of text runs on a pypdf page.

    Walks the page content stream and extracts the X-coordinate of each
    ``Tm`` (text matrix), ``Td`` / ``TD`` (text-position offset) operator.
    Clusters positions within ``tolerance`` PDF units into a single column.

    Defensive: returns ``0`` on any pypdf API error so the signal degrades
    gracefully when the content stream cannot be parsed.

    Args:
        page_metadata: ``pypdf.PageObject``.
        tolerance: Cluster-merge tolerance in PDF units (default 10 ≈ 1/7.2 inch).

    Returns:
        Count of distinct X-coordinate clusters.
    """
    try:
        contents = getattr(page_metadata, "get_contents", lambda: None)()
        if contents is None:
            return 0
        get_data = getattr(contents, "get_data", None)
        if get_data is None:
            return 0
        raw = get_data()
    except (AttributeError, KeyError, TypeError):
        return 0
    except Exception:  # noqa: BLE001 — pypdf content-stream APIs vary; degrade gracefully
        _log.warning("layout_complexity: content stream extraction failed", exc_info=True)
        return 0

    if not isinstance(raw, bytes):
        return 0

    x_positions: list[float] = []
    current_x = 0.0
    try:
        text = raw.decode("latin-1", errors="ignore")
    except (UnicodeDecodeError, AttributeError):
        return 0

    # Parse Tm (text matrix), Td/TD (text position) operators.
    # Tm: a b c d e f Tm  → e is X
    # Td: tx ty Td  → tx adjusts current X
    # TD: tx ty TD  → tx adjusts current X + leading
    pattern = re.compile(
        r"((?:-?\d+\.?\d*\s+){5}-?\d+\.?\d*)\s+Tm|"
        r"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+Td|"
        r"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+TD"
    )
    for match in pattern.finditer(text):
        tm_group, td_x, _td_y, td_cap_x, _td_cap_y = match.groups()
        try:
            if tm_group is not None:
                parts = tm_group.split()
                current_x = float(parts[4])
            elif td_x is not None:
                current_x += float(td_x)
            elif td_cap_x is not None:
                current_x += float(td_cap_x)
        except (ValueError, IndexError):
            continue
        x_positions.append(current_x)

    if not x_positions:
        return 0

    # Cluster positions within tolerance.
    sorted_xs = sorted(x_positions)
    clusters = 1
    last_x = sorted_xs[0]
    for x in sorted_xs[1:]:
        if x - last_x > tolerance:
            clusters += 1
            last_x = x
    return clusters


# -------------------------------------------------------------------------
# Weight loading.
# -------------------------------------------------------------------------


_weights_cache: dict[str, dict[str, float]] = {}


def load_weights(weights_path: Path | None = None) -> dict[str, float]:
    """Load signal weights from JSON file or return module defaults.

    Args:
        weights_path: Optional path to a JSON weights file. When ``None``,
            module defaults are returned.

    Returns:
        Mapping of signal name to weight in ``[0.0, infinity)``.

    Raises:
        FidelityScorerError: If the weights file is malformed.
    """
    if weights_path is None:
        return dict(_DEFAULT_SIGNAL_WEIGHTS)
    cache_key = str(weights_path.resolve())
    if cache_key in _weights_cache:
        return dict(_weights_cache[cache_key])
    try:
        raw = json.loads(weights_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise FidelityScorerError(f"could not load weights from {weights_path}: {err}") from err
    if not isinstance(raw, dict):
        raise FidelityScorerError(
            f"weights file must contain a JSON object, got {type(raw).__name__}"
        )
    weights = dict(_DEFAULT_SIGNAL_WEIGHTS)
    for name, value in raw.items():
        if not isinstance(value, int | float):
            raise FidelityScorerError(
                f"weight for {name!r} must be numeric, got {type(value).__name__}"
            )
        if value < 0:
            raise FidelityScorerError(f"weight for {name!r} must be non-negative, got {value}")
        weights[name] = float(value)
    _weights_cache[cache_key] = dict(weights)
    return weights


# -------------------------------------------------------------------------
# Pre-triage scoring (028.002-T): runs BEFORE heuristic extraction.
# -------------------------------------------------------------------------


_PRE_TRIAGE_ROUTE_DOCLING_THRESHOLD = 0.7
_PRE_TRIAGE_ROUTE_HEURISTIC_THRESHOLD = 0.2

_PreTriageClassification = Literal["route_to_docling", "route_to_heuristic", "uncertain"]


@dataclass(frozen=True)
class PreTriageDecision:
    """Pre-extraction routing decision for one page.

    Attributes:
        page_index: Zero-based page index in the source PDF.
        signals: Map of pre-triage signal name to raw score in ``[0.0, 1.0]``.
        aggregate: Weighted mean across the 5 pre-triage signals in ``[0.0, 1.0]``.
        classification: One of ``"route_to_docling"`` (skip heuristic, route
            directly to docling), ``"route_to_heuristic"`` (accept heuristic
            output without post-extraction scoring), or ``"uncertain"``
            (fall back to the existing heuristic-then-score path).
        reason: Comma-separated triggered signal names, or ``"clean"`` for
            heuristic routing, or ``"borderline"`` for uncertain pages.
    """

    page_index: int
    signals: dict[str, float] = field(default_factory=dict)
    aggregate: float = 0.0
    classification: _PreTriageClassification = "uncertain"
    reason: str = ""


def load_pre_triage_weights(weights_path: Path | None = None) -> dict[str, float]:
    """Load pre-triage signal weights from JSON or return module defaults.

    Mirrors :func:`load_weights` but uses ``_DEFAULT_PRE_TRIAGE_WEIGHTS``
    as the baseline so operators can override pre-triage weights
    independently of the existing post-extraction weights.

    Args:
        weights_path: Optional path to a JSON weights file. When ``None``,
            module defaults are returned.

    Returns:
        Mapping of pre-triage signal name to weight in ``[0.0, infinity)``.

    Raises:
        FidelityScorerError: If the weights file is malformed.
    """
    if weights_path is None:
        return dict(_DEFAULT_PRE_TRIAGE_WEIGHTS)
    try:
        raw = json.loads(weights_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise FidelityScorerError(
            f"could not load pre-triage weights from {weights_path}: {err}"
        ) from err
    if not isinstance(raw, dict):
        raise FidelityScorerError(
            f"pre-triage weights file must contain a JSON object, got {type(raw).__name__}"
        )
    weights = dict(_DEFAULT_PRE_TRIAGE_WEIGHTS)
    for name, value in raw.items():
        if not isinstance(value, int | float):
            raise FidelityScorerError(
                f"pre-triage weight for {name!r} must be numeric, got {type(value).__name__}"
            )
        if value < 0:
            raise FidelityScorerError(
                f"pre-triage weight for {name!r} must be non-negative, got {value}"
            )
        weights[name] = float(value)
    return weights


def pre_triage_score(
    page_index: int,
    page_metadata: object | None,
    weights_path: Path | None = None,
) -> PreTriageDecision:
    """Score a page using only source-aware signals (no heuristic extraction).

    Runs the 5 pre-triage signals (``image_heavy``, ``form_fields``,
    ``layout_complexity``, ``font_diversity``, ``text_flow_consistency``)
    against the source ``pypdf.PageObject`` and returns a routing decision.
    Used by the ``--triage-pre-score`` opt-in path to short-circuit
    obviously-complex pages directly to docling without first running
    heuristic extraction.

    The decision rule applies the weighted aggregate against two thresholds:

    * ``aggregate >= 0.7`` → ``route_to_docling`` (skip heuristic entirely)
    * ``aggregate <= 0.2`` → ``route_to_heuristic`` (accept heuristic output)
    * else → ``uncertain`` (fall back to the existing heuristic + post-score path)

    Args:
        page_index: Zero-based page index in the source PDF.
        page_metadata: ``pypdf.PageObject`` for the source page. ``None``
            yields a ``route_to_heuristic`` classification (no source
            structure detected, defer to text-based scoring).
        weights_path: Optional path to a JSON pre-triage weights override.

    Returns:
        Populated :class:`PreTriageDecision`.

    Raises:
        FidelityScorerError: On input-validation failure.
    """
    if page_index < 0:
        raise FidelityScorerError(f"page_index must be >= 0, got {page_index}")

    weights = load_pre_triage_weights(weights_path)

    # signal_layout_complexity takes (text, page_metadata); the rest take
    # just page_metadata. We pass empty text since pre-triage has not yet
    # run heuristic extraction.
    signals: dict[str, float] = {
        "image_heavy": signal_image_heavy(page_metadata),
        "form_fields": signal_form_fields(page_metadata),
        "layout_complexity": signal_layout_complexity("", page_metadata),
        "font_diversity": signal_font_diversity(page_metadata),
        "text_flow_consistency": signal_text_flow_consistency(page_metadata),
    }

    weighted: dict[str, float] = {
        name: signals[name] * weights.get(name, 0.0) for name in _PRE_TRIAGE_SIGNAL_NAMES
    }

    total_weight = sum(weights.get(name, 0.0) for name in _PRE_TRIAGE_SIGNAL_NAMES)
    if total_weight > 0:
        aggregate = sum(weighted.values()) / total_weight
    else:
        aggregate = 0.0

    classification: _PreTriageClassification
    reason: str
    if aggregate >= _PRE_TRIAGE_ROUTE_DOCLING_THRESHOLD:
        classification = "route_to_docling"
        triggered = [name for name in _PRE_TRIAGE_SIGNAL_NAMES if weighted[name] > 0.3]
        reason = ",".join(triggered) if triggered else "aggregate"
    elif aggregate <= _PRE_TRIAGE_ROUTE_HEURISTIC_THRESHOLD:
        classification = "route_to_heuristic"
        reason = "clean"
    else:
        classification = "uncertain"
        reason = "borderline"

    return PreTriageDecision(
        page_index=page_index,
        signals=signals,
        aggregate=aggregate,
        classification=classification,
        reason=reason,
    )


# -------------------------------------------------------------------------
# Combiner.
# -------------------------------------------------------------------------


def score_page(
    page_index: int,
    text: str,
    page_metadata: object | None = None,
    weights_path: Path | None = None,
) -> PageScore:
    """Compute a :class:`PageScore` for one page.

    Weights are importance multipliers applied to both flag paths:

    * **Hard flag**: any single signal whose ``raw * weight >= _HARD_FLAG_THRESHOLD``
    * **Aggregate flag**: weighted mean of all signals ``>= _AGGREGATE_FLAG_THRESHOLD``

    Setting a weight to ``0.0`` fully mutes that signal in both paths.

    Args:
        page_index: Zero-based page index. Must be ``>= 0``.
        text: Heuristic-extracted page text.
        page_metadata: Optional ``pypdf.PageObject`` for metadata signals.
        weights_path: Optional path to a JSON weights override file.

    Returns:
        Populated :class:`PageScore` with all signals + aggregate + decision.

    Raises:
        FidelityScorerError: On input-validation failure.
    """
    if page_index < 0:
        raise FidelityScorerError(f"page_index must be >= 0, got {page_index}")

    weights = load_weights(weights_path)

    signals: dict[str, float] = {
        "char_density": signal_char_density(text, page_metadata),
        "non_ascii_ratio": signal_non_ascii_ratio(text),
        "long_unbroken_line": signal_long_unbroken_line(text),
        "column_gap": signal_column_gap(text),
        "table_char_density": signal_table_char_density(text),
        "image_heavy": signal_image_heavy(page_metadata),
        "form_fields": signal_form_fields(page_metadata),
        "layout_complexity": signal_layout_complexity(text, page_metadata),
    }

    weighted: dict[str, float] = {
        name: signals[name] * weights.get(name, 0.0) for name in _SIGNAL_NAMES
    }

    hard_flag = any(value >= _HARD_FLAG_THRESHOLD for value in weighted.values())

    total_weight = sum(weights.get(name, 0.0) for name in _SIGNAL_NAMES)
    if total_weight > 0:
        aggregate = sum(weighted.values()) / total_weight
    else:
        aggregate = 0.0
    aggregate_flag = aggregate >= _AGGREGATE_FLAG_THRESHOLD

    needs_docling = hard_flag or aggregate_flag

    if needs_docling:
        triggered = [
            name
            for name in _SIGNAL_NAMES
            if weighted[name] >= _HARD_FLAG_THRESHOLD or weighted[name] > 0.3
        ]
        reason = ",".join(triggered) if triggered else "aggregate"
    else:
        reason = "ok"

    return PageScore(
        page_index=page_index,
        signals=signals,
        aggregate=aggregate,
        needs_docling=needs_docling,
        reason=reason,
    )
