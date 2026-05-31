"""Failing harness tests for the bounded correction loop."""

from docline.config import CorrectionProviderConfig
from docline.process.correction import CorrectionLoopResult, run_correction_loop


def _enabled_config() -> CorrectionProviderConfig:
    return CorrectionProviderConfig(
        enabled=True,
        provider="mock-provider",
        api_key_env_var="DOCLINE_CORRECTION_API_KEY",
        model="mock-model",
    )


def test_run_correction_loop_enforces_retry_bounds() -> None:
    result = run_correction_loop(
        "# Title\n\n## Summary\nDraft body\n",
        ["Missing required section: Decision"],
        _enabled_config(),
        max_attempts=2,
    )
    assert result.attempts == 0


def test_run_correction_loop_preserves_non_semantic_content() -> None:
    result = run_correction_loop(
        "# Title\n\n## Summary\nLine A\n",
        ["Heading depth exceeded schema limits"],
        _enabled_config(),
    )
    assert result.corrected_markdown is None


def test_run_correction_loop_returns_typed_failure_outcome() -> None:
    result = run_correction_loop(
        "# Title\n\n## Summary\nDraft body\n",
        ["Missing required section: Decision"],
        _enabled_config(),
        max_attempts=1,
    )
    assert isinstance(result, CorrectionLoopResult)
    assert result.status == "failed"
