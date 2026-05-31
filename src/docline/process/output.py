"""Contained Markdown output stubs."""

from pathlib import Path

from docline.paths import safe_workspace_path


def write_markdown_output(output_root: Path | str, relative_path: str, markdown_text: str) -> Path:
    """Write a validated Markdown document beneath a contained output root.

    Args:
        output_root: Workspace-contained output root directory.
        relative_path: Relative output path beneath the configured root.
        markdown_text: Validated Markdown document text.

    Returns:
        Path to the written Markdown document.
    """
    output_path = safe_workspace_path(relative_path, output_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown_text, encoding="utf-8")
    return output_path


__all__ = ["write_markdown_output"]
