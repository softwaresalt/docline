"""Bounded correction-loop stubs."""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from docline.config import CorrectionProviderConfig


class CorrectionLoopResult(BaseModel):
    """Typed result returned by the bounded correction loop.

    Attributes:
        status: Final correction-loop status.
        attempts: Number of provider attempts performed.
        corrected_markdown: Corrected Markdown output, when available.
        failure_reason: Structured failure explanation, when applicable.
    """

    status: Literal["corrected", "failed"]
    attempts: int = Field(ge=0)
    corrected_markdown: str | None = None
    failure_reason: str | None = None


def run_correction_loop(
    markdown_text: str,
    lint_errors: Sequence[str],
    config: CorrectionProviderConfig,
    max_attempts: int = 3,
) -> CorrectionLoopResult:
    """Run a bounded correction loop for schema-lint failures.

    **Stub**: This function is intentionally unimplemented in v1. No provider
    calls are made, no correction attempts are performed, and ``corrected_markdown``
    is always ``None`` on the returned failure result. Callers MUST treat
    ``corrected_markdown is None`` as the signal that no correction was produced.
    The ``max_attempts`` and ``lint_errors`` parameters are accepted for API
    stability but are not used until a real correction provider is wired in.

    Args:
        markdown_text: Markdown document requiring correction.
        lint_errors: Structural lint errors to address.
        config: Resolved correction-provider configuration.
        max_attempts: Maximum number of correction retries.

    Returns:
        Typed correction-loop result with ``status="failed"``,
        ``attempts=0``, and ``corrected_markdown=None``.
    """
    del markdown_text, lint_errors, config, max_attempts

    return CorrectionLoopResult(
        status="failed",
        attempts=0,
        corrected_markdown=None,
        failure_reason="Correction provider not yet implemented",
    )


__all__ = ["CorrectionLoopResult", "run_correction_loop"]
