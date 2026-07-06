"""Tests for source-MD YAML frontmatter strip + preservation (023.001-T / 025-S).

Verifies that:
- The MD/TXT reader strips YAML frontmatter before segmenting
- Parsed frontmatter is preserved on OutputDocumentPart.source_frontmatter
- _build_markdown_with_frontmatter uses source title as override
- Source frontmatter is nested under docline:source_frontmatter
- No frontmatter and malformed frontmatter are handled gracefully
- The end-to-end docline process flow on a sample Microsoft Learn MD
  file no longer fails frontmatter assembly (regression test for the
  bug identified in docs/decisions/2026-06-09-powerbi-source-md-gap-analysis.md)
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

MS_LEARN_SAMPLE = """---
title: Sample doc title
description: Sample description with detail.
author: testauthor
ms.author: testauthor
ms.topic: how-to
ms.date: 2026-06-09
LocalizationGroup: Test group
---
# Sample H1 heading

Body paragraph one.

## Sample H2 heading

Body paragraph two.
"""

NO_FRONTMATTER_SAMPLE = """# Plain H1

This document has no YAML frontmatter at all.

## Sub-section

Body content.
"""

MALFORMED_FRONTMATTER_SAMPLE = """---
title: Missing closing fence
description: This frontmatter has no closing --- line
# Looks like a heading but is actually inside un-closed YAML
"""


def test_build_output_document_parts_strips_md_frontmatter(tmp_path: Path) -> None:
    """build_output_document_parts MUST strip YAML frontmatter from .md body."""
    from docline.process.output_contract import build_output_document_parts

    f = tmp_path / "sample.md"
    f.write_text(MS_LEARN_SAMPLE, encoding="utf-8")

    parts = build_output_document_parts(f, Path("sample.md"))

    assert len(parts) == 1
    body = parts[0].body
    # Body MUST NOT contain the YAML frontmatter
    assert "title: Sample doc title" not in body
    assert "ms.author: testauthor" not in body
    # Body MUST contain the actual markdown content
    assert "# Sample H1 heading" in body
    assert "Body paragraph one." in body


def test_build_output_document_parts_preserves_source_frontmatter(tmp_path: Path) -> None:
    """OutputDocumentPart MUST expose parsed source_frontmatter when present."""
    from docline.process.output_contract import build_output_document_parts

    f = tmp_path / "sample.md"
    f.write_text(MS_LEARN_SAMPLE, encoding="utf-8")

    parts = build_output_document_parts(f, Path("sample.md"))

    assert parts[0].source_frontmatter is not None
    fm = parts[0].source_frontmatter
    assert fm["title"] == "Sample doc title"
    assert fm["description"] == "Sample description with detail."
    assert fm["author"] == "testauthor"
    assert fm["ms.topic"] == "how-to"


def test_build_output_document_parts_no_frontmatter(tmp_path: Path) -> None:
    """A bare MD file with no frontmatter MUST pass through cleanly."""
    from docline.process.output_contract import build_output_document_parts

    f = tmp_path / "bare.md"
    f.write_text(NO_FRONTMATTER_SAMPLE, encoding="utf-8")

    parts = build_output_document_parts(f, Path("bare.md"))

    assert len(parts) == 1
    assert parts[0].source_frontmatter is None
    assert "# Plain H1" in parts[0].body
    assert "Body content." in parts[0].body


def test_parse_md_frontmatter_handles_multiline_yaml_values() -> None:
    """YAML block scalar values that span multiple lines parse correctly.

    Microsoft Learn / Hugo frontmatter sometimes uses YAML block scalars
    (``|`` literal or ``>`` folded) for multi-line description fields.
    The fence-finder must not be tripped by the indented continuation
    lines that follow the block-scalar marker.
    """
    from docline.process.output_contract import _parse_md_frontmatter

    text = (
        "---\n"
        "title: Doc title\n"
        "description: |\n"
        "  Multi-line description that\n"
        "  spans several lines.\n"
        "---\n"
        "# Body\n\n"
        "Real body text.\n"
    )
    fm, body = _parse_md_frontmatter(text)
    assert fm is not None
    assert fm["title"] == "Doc title"
    assert "spans several lines" in str(fm.get("description", ""))
    assert body.startswith("# Body")


def test_parse_md_frontmatter_strips_leading_bom() -> None:
    """A UTF-8 BOM before the frontmatter fence must not defeat parsing (052-F)."""
    from docline.process.output_contract import _parse_md_frontmatter

    fm, body = _parse_md_frontmatter("\ufeff" + MS_LEARN_SAMPLE)
    assert fm is not None
    assert fm["title"] == "Sample doc title"
    assert body.startswith("# Sample H1 heading")
    assert "\ufeff" not in body


def test_parse_md_frontmatter_strips_bom_without_frontmatter() -> None:
    """A BOM on a file with no frontmatter is stripped from the returned body."""
    from docline.process.output_contract import _parse_md_frontmatter

    fm, body = _parse_md_frontmatter("\ufeff" + NO_FRONTMATTER_SAMPLE)
    assert fm is None
    assert body.startswith("# Plain H1")
    assert "\ufeff" not in body


def test_build_output_document_parts_handles_bom_prefixed_md(tmp_path: Path) -> None:
    """A staged BOM-prefixed .md file assembles frontmatter like a non-BOM file (052-F)."""
    from docline.process.output_contract import build_output_document_parts

    f = tmp_path / "bom.md"
    # Real UTF-8 BOM bytes (EF BB BF) ahead of the YAML frontmatter.
    f.write_bytes(b"\xef\xbb\xbf" + MS_LEARN_SAMPLE.encode("utf-8"))

    parts = build_output_document_parts(f, Path("bom.md"))

    assert len(parts) == 1
    assert parts[0].source_frontmatter is not None
    assert parts[0].source_frontmatter["title"] == "Sample doc title"
    body = parts[0].body
    assert body.lstrip().startswith("# Sample H1 heading")
    assert "title: Sample doc title" not in body
    assert "\ufeff" not in body


def test_parse_md_frontmatter_handles_triple_dash_inside_value() -> None:
    """A quoted YAML value containing ``---`` MUST NOT be mistaken for the
    closing fence. The fence-finder requires ``---`` to be on its own line
    (followed by newline or EOF), so embedded ``---`` in a string value
    should be preserved as part of the parsed value, not split the document.
    """
    from docline.process.output_contract import _parse_md_frontmatter

    text = (
        "---\n"
        "title: Doc with separator in description\n"
        "description: 'Has --- in value but inline only'\n"
        "notes: 'Another --- inline'\n"
        "---\n"
        "# Body\n\n"
        "Real body text.\n"
    )
    fm, body = _parse_md_frontmatter(text)
    assert fm is not None
    assert fm["title"] == "Doc with separator in description"
    assert fm["description"] == "Has --- in value but inline only"
    assert fm["notes"] == "Another --- inline"
    assert body.startswith("# Body")


def test_parse_md_frontmatter_returns_none_on_empty_input() -> None:
    from docline.process.output_contract import _parse_md_frontmatter

    fm, body = _parse_md_frontmatter("")
    assert fm is None
    assert body == ""


def test_build_output_document_parts_malformed_frontmatter(tmp_path: Path) -> None:
    """A file with malformed frontmatter (no closing fence) MUST not raise.

    Behavior: treat as no frontmatter — pass through the full content as
    body and leave source_frontmatter None. The downstream segmenter or
    heading validator will surface any structural issue.
    """
    from docline.process.output_contract import build_output_document_parts

    f = tmp_path / "malformed.md"
    f.write_text(MALFORMED_FRONTMATTER_SAMPLE, encoding="utf-8")

    parts = build_output_document_parts(f, Path("malformed.md"))

    assert len(parts) == 1
    # source_frontmatter should be None because we couldn't parse it safely
    assert parts[0].source_frontmatter is None
    # Content passes through (with the YAML-looking opening intact)
    assert "title: Missing closing fence" in parts[0].body


def test_build_output_document_parts_strips_txt_frontmatter_too(tmp_path: Path) -> None:
    """The same strip behavior applies to .txt inputs for consistency."""
    from docline.process.output_contract import build_output_document_parts

    f = tmp_path / "sample.txt"
    f.write_text(MS_LEARN_SAMPLE, encoding="utf-8")

    parts = build_output_document_parts(f, Path("sample.txt"))

    assert "title: Sample doc title" not in parts[0].body
    assert "# Sample H1 heading" in parts[0].body
    assert parts[0].source_frontmatter is not None
    assert parts[0].source_frontmatter["title"] == "Sample doc title"


def test_output_document_part_source_frontmatter_default_is_none() -> None:
    """OutputDocumentPart.source_frontmatter MUST default to None for backward compat
    with existing PDF/DOCX/HTML callers that don't supply it.
    """
    from docline.process.output_contract import OutputDocumentPart

    part = OutputDocumentPart(body="x", relative_output_path=Path("x.md"))
    assert part.source_frontmatter is None


def test_output_document_part_is_frozen() -> None:
    """OutputDocumentPart MUST remain a frozen dataclass after the field addition."""
    from dataclasses import FrozenInstanceError

    import pytest

    from docline.process.output_contract import OutputDocumentPart

    part = OutputDocumentPart(body="x", relative_output_path=Path("x.md"))
    with pytest.raises(FrozenInstanceError):
        part.body = "y"  # type: ignore[misc]


def test_execute_process_no_longer_fails_frontmatter_assembly_on_ms_learn_md(
    tmp_path: Path,
) -> None:
    """End-to-end regression test for the bug from PowerBI gap analysis.

    Before 025-S: docline process on a Microsoft Learn MD file produced
    'Failed to build frontmatter: H2 heading title: ... appeared before any H1'.

    After 025-S: the run succeeds with the source title preserved as the
    docline title, and the source frontmatter fields nested under
    docline:source_frontmatter.
    """
    import json

    from docline.app import execute_process
    from docline.app_models import ProcessRequest

    # Build minimal staging layout
    staging = tmp_path / "staging"
    job_dir = staging / "ab" / "abcdef1234567890"
    files_dir = job_dir / "files"
    files_dir.mkdir(parents=True)
    (files_dir / "sample.md").write_text(MS_LEARN_SAMPLE, encoding="utf-8")
    (job_dir / "metadata.json").write_text(
        json.dumps(
            {
                "job_id": "abcdef1234567890",
                "metadata": {
                    "source": "local:test:abcdef",
                    "fetch_timestamp": "2026-06-09T00:00:00Z",
                    "http_status": None,
                    "content_type": "text/markdown",
                },
                "cache_path": str(job_dir),
                "complete": True,
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "output"
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        rel_staging = staging.relative_to(tmp_path).as_posix()
        rel_output = output.relative_to(tmp_path).as_posix()
        result = execute_process(ProcessRequest(staging_dir=rel_staging, output_dir=rel_output))
    finally:
        os.chdir(old_cwd)

    assert result.success is True
    # Output file must exist
    produced = output / "abcdef1234567890" / "sample.md"
    assert produced.exists(), f"expected output at {produced}"
    body = produced.read_text(encoding="utf-8")
    # Output MUST be valid docline frontmatter + segmented body
    assert body.startswith("---\n"), "must have YAML frontmatter fence"
    # Source title MUST be preserved in the docline frontmatter
    assert "Sample doc title" in body
    # Source frontmatter MUST be nested under docline:source_frontmatter
    assert "source_frontmatter:" in body
    assert "ms.topic" in body or "ms_topic" in body or "ms.author" in body or "ms_author" in body


# ---------------------------------------------------------------------------
# T3 (027-S / 025.001-T) — robustness against Microsoft Learn include
# fragments whose YAML frontmatter has uniform leading whitespace or mixed
# indentation. The Power BI corpus evaluation
# (docs/decisions/2026-06-09-powerbi-corpus-coverage.md, Category B failure
# analysis) identified 8 of 1,340 files in includes/ that fail to parse
# because yaml.safe_load rejects the indentation style. Microsoft Learn's
# build pipeline accepts these forms; docline must too.
# ---------------------------------------------------------------------------


def test_parse_md_frontmatter_handles_uniform_leading_space() -> None:
    """YAML frontmatter where every key line has the same N>0 leading spaces
    MUST parse correctly. This is the Microsoft Learn include-fragment
    pattern (see includes/copilot-notes.md in the Power BI corpus).
    """
    from docline.process.output_contract import _parse_md_frontmatter

    text = (
        "---\n"
        " title: include file\n"
        " description: include file\n"
        " services: powerbi\n"
        " author: julcsc\n"
        " ms.service: powerbi\n"
        " ms.topic: include\n"
        " ms.date: 05/15/2025\n"
        " ms.author: juliacawthra\n"
        "---\n"
        "Body content here.\n"
    )
    fm, body = _parse_md_frontmatter(text)
    assert fm is not None
    assert fm["title"] == "include file"
    assert fm["ms.topic"] == "include"
    assert fm["author"] == "julcsc"
    assert body.startswith("Body content")


def test_parse_md_frontmatter_handles_mixed_indentation() -> None:
    """YAML frontmatter where SOME key lines are indented and others are not
    MUST fall back to regex-based key extraction (yaml.safe_load fails on
    this form). This is the includes/yes-paginated.md pattern.
    """
    from docline.process.output_contract import _parse_md_frontmatter

    text = (
        "---\n"
        " title: include file\n"
        " description: include file\n"
        " services: powerbi\n"
        " author: JulCsc\n"
        " ms.service: powerbi\n"
        "ms.topic: include\n"
        "ms.date: 12/01/2025\n"
        "ms.author: juliacawthra\n"
        " ms.custom: include file\n"
        "---\n"
        ":::image type=icon source=foo.svg::: Body\n"
    )
    fm, body = _parse_md_frontmatter(text)
    assert fm is not None, "mixed indentation should fall back to regex extraction"
    assert fm["title"] == "include file"
    assert fm["ms.topic"] == "include"
    assert fm["ms.author"] == "juliacawthra"
    assert body.startswith(":::image")


def test_parse_md_frontmatter_handles_no_loc_brackets_and_indented_keys() -> None:
    """Real-world Power BI corpus regression: copilot-notes.md has uniform
    leading-space keys AND a YAML list value with brackets. Both must work.
    """
    from docline.process.output_contract import _parse_md_frontmatter

    text = (
        "---\n"
        " title: include file\n"
        " description: include file\n"
        " services: powerbi\n"
        " author: julcsc\n"
        " ms.service: powerbi\n"
        " ms.topic: include\n"
        " ms.date: 05/15/2025\n"
        " ms.author: juliacawthra\n"
        " ms.custom: include file\n"
        "no-loc: [Copilot]\n"
        "ms.collection: ce-skilling-ai-copilot\n"
        "---\n"
        "> [!NOTE]\n"
        "> Keep the following requirements in mind:\n"
    )
    fm, body = _parse_md_frontmatter(text)
    assert fm is not None
    assert fm["title"] == "include file"
    # Either parser path is acceptable; both should preserve the key value.
    # Regex fallback returns the raw "[Copilot]" string; yaml.safe_load on
    # whitespace-stripped form returns the list ["Copilot"].
    no_loc_value = fm["no-loc"]
    assert "Copilot" in str(no_loc_value)
    assert body.startswith("> [!NOTE]")


def test_parse_md_frontmatter_truly_malformed_returns_none() -> None:
    """When NEITHER yaml.safe_load NOR the regex fallback can extract any
    key/value pair, _parse_md_frontmatter MUST return (None, original_text)
    so the caller's existing no-frontmatter path is preserved.
    """
    from docline.process.output_contract import _parse_md_frontmatter

    text = "---\n: : :\n@@@ not yaml at all\n---\nBody.\n"
    fm, _body = _parse_md_frontmatter(text)
    # Either None (truly unparseable) or an empty Mapping (regex found
    # nothing) is acceptable; the strict requirement is "no crash".
    assert fm is None or (isinstance(fm, Mapping) and len(fm) == 0)


def test_parse_md_frontmatter_clean_yaml_unaffected_by_fallback() -> None:
    """Regression: well-formed YAML MUST take the yaml.safe_load path and
    return native types (not strings stringified by the regex fallback).
    """
    from docline.process.output_contract import _parse_md_frontmatter

    text = (
        "---\ntitle: Doc\nms.date: 2026-06-10\ndraft: true\ntags:\n  - one\n  - two\n---\nBody.\n"
    )
    fm, _body = _parse_md_frontmatter(text)
    assert fm is not None
    assert fm["title"] == "Doc"
    # yaml.safe_load parses booleans and lists natively; regex fallback would
    # not. Use this to verify the canonical path was taken.
    assert fm["draft"] is True
    assert fm["tags"] == ["one", "two"]
