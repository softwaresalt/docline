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

    Args:
        markdown_text: Markdown document requiring correction.
        lint_errors: Structural lint errors to address.
        config: Resolved correction-provider configuration.
        max_attempts: Maximum number of correction retries.

    Returns:
        Typed correction-loop result.
    """
    del lint_errors, config

    attempts = max(max_attempts, 0)
    return CorrectionLoopResult(
        status="failed",
        attempts=attempts,
        corrected_markdown=markdown_text,
        failure_reason="Correction provider did not produce a valid revision",
    )


__all__ = ["CorrectionLoopResult", "run_correction_loop"]
