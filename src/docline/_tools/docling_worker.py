"""Subprocess CLI that runs docling on a single PDF.

Invoked by :mod:`docline.process.pdf_batch` as::

    python -m docline._tools.docling_worker INPUT_PDF OUTPUT_MD

Writes the docling-rendered Markdown to ``OUTPUT_MD`` and exits 0 on
success. On failure (missing input, docling import error, docling
runtime error, or any other exception), writes a structured JSON
diagnostic line to stderr and exits non-zero so the parent batch
processor can route the chunk to the heuristic fallback.

The exit codes are:

* ``0`` — success
* ``2`` — bad CLI arguments
* ``3`` — input PDF does not exist
* ``4`` — docling extras not installed
* ``5`` — docling raised an exception during conversion
* ``6`` — any other unexpected error

Running each chunk in its own subprocess gives the OS a chance to
reclaim torch tensor working set between calls (PyTorch's CPU
allocator does not return memory to the OS reliably) and contains
C-level crashes (``c10::Error``, SIGABRT, etc.) that would otherwise
abort the parent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _emit_diagnostic(stage: str, error: str, exception: str | None = None) -> None:
    """Write a one-line JSON diagnostic to stderr."""

    payload: dict[str, str] = {"stage": stage, "error": error}
    if exception:
        payload["exception"] = exception
    sys.stderr.write(json.dumps(payload) + "\n")
    sys.stderr.flush()


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m docline._tools.docling_worker``.

    Args:
        argv: Command-line arguments (without the program name).
            Defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code per the table in the module docstring.
    """

    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        _emit_diagnostic("cli", "expected exactly 2 args: INPUT_PDF OUTPUT_MD")
        return 2

    input_path = Path(args[0])
    output_path = Path(args[1])

    if not input_path.exists():
        _emit_diagnostic("input", f"input PDF not found: {input_path}")
        return 3

    try:
        from docline.dependencies import DependencyUnavailableError
        from docline.readers.pdf import _read_pdf_docling_pages
    except ImportError as err:
        _emit_diagnostic("import", "could not import docline.readers.pdf", str(err))
        return 6

    try:
        pages = _read_pdf_docling_pages(input_path)
    except DependencyUnavailableError as err:
        _emit_diagnostic("docling-extras", "docling extras not installed", str(err))
        return 4
    except Exception as err:  # noqa: BLE001 — surface to parent via exit code
        _emit_diagnostic("docling-runtime", "docling raised during conversion", repr(err))
        return 5

    markdown = "\n\n".join(pages)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    except OSError as err:
        _emit_diagnostic("output", f"could not write {output_path}", str(err))
        return 6

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
