"""Per-page fidelity scorer for the triage-then-repair PDF pipeline.

Stub module — implementation lands in task 019.001-T (U1).

Provides seven pure-function fidelity signals
(``char_density``, ``non_ascii_ratio``, ``long_unbroken_line``,
``column_gap``, ``table_char_density``, ``image_heavy``, ``form_fields``),
a weighted combiner :func:`score_page`, and a frozen :class:`PageScore`
result. Signal weights are externalized via JSON so they can be tuned
without code changes.

POC reference: ``docs/scratch/2026-06-06-fidelity-scorer-poc.py``.
Plan: ``docs/plans/2026-06-06-triage-then-repair-plan.md`` § U1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docline.schema.models import DoclineError


class FidelityScorerError(DoclineError):
    """Raised on scorer input-validation failures."""


@dataclass(frozen=True)
class PageScore:
    """Per-page fidelity assessment.

    Attributes:
        page_index: Zero-based page index in the source PDF.
        signals: Map of signal name to raw score in ``[0.0, 1.0]``.
        aggregate: Combined weighted score in ``[0.0, 1.0]``.
        needs_docling: True when the page should be routed through docling.
        reason: Comma-separated triggered signal names or ``"ok"``.
    """

    page_index: int
    signals: dict[str, float] = field(default_factory=dict)
    aggregate: float = 0.0
    needs_docling: bool = False
    reason: str = ""


def signal_char_density(text: str, page_metadata: object | None = None) -> float:
    """Flag pages whose extracted text is suspiciously sparse."""
    raise NotImplementedError("019.001-T: signal_char_density")


def signal_non_ascii_ratio(text: str) -> float:
    """Flag pages with high non-printable / private-use codepoint ratio."""
    raise NotImplementedError("019.001-T: signal_non_ascii_ratio")


def signal_long_unbroken_line(text: str) -> float:
    """Flag pages with very long lines that have almost no whitespace."""
    raise NotImplementedError("019.001-T: signal_long_unbroken_line")


def signal_column_gap(text: str) -> float:
    """Flag pages whose lines show consistent multi-space gutters."""
    raise NotImplementedError("019.001-T: signal_column_gap")


def signal_table_char_density(text: str) -> float:
    """Flag pages with a high density of table-grid characters."""
    raise NotImplementedError("019.001-T: signal_table_char_density")


def signal_image_heavy(page_metadata: object | None) -> float:
    """Flag pages whose pypdf metadata reports many embedded images."""
    raise NotImplementedError("019.001-T: signal_image_heavy")


def signal_form_fields(page_metadata: object | None) -> float:
    """Flag pages that contain form-field annotations."""
    raise NotImplementedError("019.001-T: signal_form_fields")


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
    raise NotImplementedError("019.001-T: load_weights")


def score_page(
    page_index: int,
    text: str,
    page_metadata: object | None = None,
    weights_path: Path | None = None,
) -> PageScore:
    """Compute a :class:`PageScore` for one page.

    Args:
        page_index: Zero-based page index.
        text: Heuristic-extracted page text.
        page_metadata: Optional ``pypdf.PageObject`` for metadata signals.
        weights_path: Optional path to a JSON weights override file.

    Returns:
        Populated :class:`PageScore` with all signals + aggregate + decision.

    Raises:
        FidelityScorerError: On input-validation failure.
    """
    raise NotImplementedError("019.001-T: score_page")
