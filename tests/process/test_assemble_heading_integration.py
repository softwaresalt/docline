"""Red-first integration tests for assemble + heading hierarchy enforcement (010-S F3.T3).

Validates that ``assemble_markdown`` enforces heading hierarchy by default
and that an explicit ``allow_heading_disorder=True`` opt-out flag bypasses
the check. Also covers the CLI/MCP parity surface (ProcessRequest field +
CLI flag) so escape hatch is reachable from both interfaces.
"""

from __future__ import annotations

import pytest

from docline.app_models import ProcessRequest
from docline.process.assemble import assemble_markdown
from docline.process.heading_validation import HeadingHierarchyError


def test_assemble_rejects_disordered_headings_by_default() -> None:
    """Default ``assemble_markdown`` raises on H3-before-H2 documents."""
    frontmatter = {"title": "Doc", "source": "test"}
    body = "# Top\n\n### Orphan Subsection\n\nBody\n"
    with pytest.raises(HeadingHierarchyError):
        assemble_markdown(frontmatter, body)


def test_assemble_accepts_disorder_with_override_flag() -> None:
    """``allow_heading_disorder=True`` bypasses validation."""
    frontmatter = {"title": "Doc", "source": "test"}
    body = "# Top\n\n### Orphan Subsection\n\nBody\n"
    output = assemble_markdown(frontmatter, body, allow_heading_disorder=True)
    assert "### Orphan Subsection" in output
    assert output.startswith("---\n")


def test_assemble_passes_valid_hierarchy_without_flag() -> None:
    """Canonical H1->H2->H3 body assembles without flag."""
    frontmatter = {"title": "Doc", "source": "test"}
    body = "# Top\n\n## Section\n\n### Sub\n\nBody\n"
    output = assemble_markdown(frontmatter, body)
    assert "### Sub" in output


def test_process_request_exposes_allow_heading_disorder_field() -> None:
    """``ProcessRequest`` carries the override flag for MCP parity."""
    req = ProcessRequest()
    assert req.allow_heading_disorder is False

    explicit = ProcessRequest(allow_heading_disorder=True)
    assert explicit.allow_heading_disorder is True


def test_process_request_schema_includes_allow_heading_disorder() -> None:
    """JSON schema surfaces the override flag for MCP clients."""
    schema = ProcessRequest.model_json_schema()
    assert "allow_heading_disorder" in schema["properties"]
    assert schema["properties"]["allow_heading_disorder"]["type"] == "boolean"


def test_cli_process_supports_allow_heading_disorder_flag(
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    """CLI ``process --allow-heading-disorder`` is accepted and parsed."""
    import json

    from docline.cli import main

    # Use an empty staging dir so process completes without errors.
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    # The CLI uses workspace-relative paths so chdir into tmp_path.
    import os

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        rc = main(
            [
                "process",
                "--staging-dir",
                "staging",
                "--output-dir",
                "out",
                "--allow-heading-disorder",
            ]
        )
    finally:
        os.chdir(cwd)
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["success"] is True
