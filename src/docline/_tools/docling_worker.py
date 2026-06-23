"""Subprocess CLI that runs docling on a single PDF or a batch of PDFs.

Invoked by :mod:`docline.process.pdf_batch` and
:mod:`docline.process.pdf_triage`.

Single-chunk mode (legacy)::

    python -m docline._tools.docling_worker INPUT_PDF OUTPUT_MD [--no-ocr]

Batched mode (030-F T3)::

    python -m docline._tools.docling_worker --batch MANIFEST_JSON

In batched mode the worker imports docling and loads its layout model
ONCE, then iterates the manifest writing one envelope per chunk to its
output path. This amortizes the ~5-10s docling cold-start cost across
N chunks instead of paying it per invocation. The manifest format is::

    {
        "chunks": [
            {"input": "/abs/path/chunk-1.pdf", "output": "/abs/path/chunk-1.md"},
            {"input": "/abs/path/chunk-2.pdf", "output": "/abs/path/chunk-2.md"}
        ]
    }

Each chunk may include an optional ``"do_ocr"`` boolean (default ``true``);
set it ``false`` to skip OCR for ranges whose pages already carry an
extractable text layer (034-F). The single-chunk CLI exposes the same
control via the optional ``--no-ocr`` flag.

Per-chunk failures during batched processing write an error envelope to
that chunk's output path (with the legacy schema_version=1 plus an
``error`` field) and the worker continues with the next chunk. The
process exit code is 0 if AT LEAST ONE chunk succeeded; non-zero only
if docling import or model load itself failed (so the parent decides
whether to retry single-chunk or fall back to heuristic for everything).

Writes a JSON envelope (see schema below) describing the docling-rendered
Markdown to the output path(s) and exits 0 on success. On failure (missing
input, docling import error, docling runtime error, or any other
exception), writes a structured JSON diagnostic line to stderr and
exits non-zero so the parent batch processor can route the chunk to
the heuristic fallback.

The exit codes are:

* ``0`` — success (at least one chunk succeeded in batched mode)
* ``2`` — bad CLI arguments or malformed manifest
* ``3`` — input PDF does not exist (single-chunk mode only;
  per-chunk in batched mode writes an error envelope instead)
* ``4`` — docling extras not installed
* ``5`` — docling raised an exception during conversion
  (single-chunk mode; or import / model load failure in batched mode)
* ``6`` — any other unexpected error (including envelope serialization
  or all-chunks-failed in batched mode)

Output envelope (schema_version 1)
----------------------------------

The output file is a JSON object with the following shape::

    {
        "schema_version": 1,
        "pages": ["page 1 markdown", "page 2 markdown", ...],
        "page_count": N,
        "text": "page 1 markdown\\n\\npage 2 markdown\\n\\n..."
    }

In batched mode, a chunk that failed mid-loop has the additional
``error`` field set to ``repr(exception)`` and ``pages``/``page_count``
empty/zero so consumers can detect the failure and route to heuristic
fallback for that chunk only.

Fields:

* ``schema_version`` — integer; bumped on any breaking envelope change.
* ``pages`` — list of per-page markdown strings, one entry per source
  PDF page.
* ``page_count`` — integer; redundancy check, equals ``len(pages)``.
* ``text`` — convenience field; equals ``"\\n\\n".join(pages)``.
* ``error`` — present only when this chunk failed in batched mode;
  consumers check ``"error" in envelope`` to detect.

Running each chunk in its own subprocess gives the OS a chance to
reclaim torch tensor working set between calls (PyTorch's CPU
allocator does not return memory to the OS reliably) and contains
C-level crashes (``c10::Error``, SIGABRT, etc.) that would otherwise
abort the parent. Batched mode trades that per-chunk isolation for
shared model-load cost — use it for chunk groups where the per-chunk
isolation is less critical than the model-load amortization.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ENVELOPE_SCHEMA_VERSION = 1


def _emit_diagnostic(stage: str, error: str, exception: str | None = None) -> None:
    """Write a one-line JSON diagnostic to stderr."""

    payload: dict[str, str] = {"stage": stage, "error": error}
    if exception:
        payload["exception"] = exception
    sys.stderr.write(json.dumps(payload) + "\n")
    sys.stderr.flush()


def _build_envelope(pages: list[str]) -> dict[str, object]:
    """Build the JSON envelope from a per-page markdown list.

    Args:
        pages: Per-page markdown strings as returned by
            :func:`docline.readers.pdf._read_pdf_docling_pages`.

    Returns:
        A dict with ``schema_version``, ``pages``, ``page_count``,
        and ``text`` keys. Safe to pass to :func:`json.dumps`.
    """

    return {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "pages": pages,
        "page_count": len(pages),
        "text": "\n\n".join(pages),
    }


def _build_error_envelope(exception: Exception) -> dict[str, object]:
    """Build an error envelope for a failed chunk in batched mode.

    Args:
        exception: The exception raised while processing the chunk.

    Returns:
        An envelope with empty ``pages`` and an ``error`` field
        containing ``repr(exception)`` for diagnostic surfacing.
    """

    return {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "pages": [],
        "page_count": 0,
        "text": "",
        "error": repr(exception),
    }


def _write_envelope(output_path: Path, envelope: dict[str, object]) -> None:
    """Serialize and write an envelope to ``output_path``."""

    body = json.dumps(envelope, ensure_ascii=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body, encoding="utf-8")


def _run_single(input_path: Path, output_path: Path, *, do_ocr: bool = True) -> int:
    """Single-chunk mode entry point.

    Args:
        input_path: Source PDF path.
        output_path: Envelope output path.
        do_ocr: When ``False`` the docling OCR engine is skipped (034-F).

    Returns the process exit code per the table in the module docstring.
    """

    if not input_path.exists():
        _emit_diagnostic("input", f"input PDF not found: {input_path}")
        return 3

    try:
        from docline.dependencies import DependencyUnavailableError
        from docline.readers.pdf import _read_pdf_docling_pages
    except ImportError as err:
        _emit_diagnostic("import", "could not import docline.readers.pdf", str(err))
        return 6

    # Forward do_ocr only when disabling OCR so the reader default and the
    # existing default-path call contract remain unchanged.
    read_kwargs: dict[str, bool] = {} if do_ocr else {"do_ocr": False}
    try:
        pages = _read_pdf_docling_pages(input_path, **read_kwargs)
    except DependencyUnavailableError as err:
        _emit_diagnostic("docling-extras", "docling extras not installed", str(err))
        return 4
    except Exception as err:  # noqa: BLE001 — surface to parent via exit code
        _emit_diagnostic("docling-runtime", "docling raised during conversion", repr(err))
        return 5

    try:
        envelope = _build_envelope(pages)
    except (TypeError, ValueError) as err:
        _emit_diagnostic("envelope", "could not serialize envelope to JSON", repr(err))
        return 6

    try:
        _write_envelope(output_path, envelope)
    except OSError as err:
        _emit_diagnostic("output", f"could not write {output_path}", str(err))
        return 6
    except (TypeError, ValueError) as err:
        _emit_diagnostic("envelope", "could not serialize envelope to JSON", repr(err))
        return 6

    return 0


def _run_batched(manifest_path: Path) -> int:
    """Batched mode entry point: shared docling model load across N chunks.

    Returns the process exit code per the table in the module docstring.
    """

    if not manifest_path.exists():
        _emit_diagnostic("batch-manifest", f"manifest file not found: {manifest_path}")
        return 2

    try:
        manifest_raw = manifest_path.read_text(encoding="utf-8")
        manifest: Any = json.loads(manifest_raw)
    except (OSError, json.JSONDecodeError) as err:
        _emit_diagnostic("batch-manifest", "could not read or parse manifest", str(err))
        return 2

    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("chunks"), list)
        or not manifest["chunks"]
    ):
        _emit_diagnostic("batch-manifest", "manifest must have non-empty 'chunks' list")
        return 2

    chunks: list[dict[str, Any]] = manifest["chunks"]
    for i, entry in enumerate(chunks):
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("input"), str)
            or not isinstance(entry.get("output"), str)
        ):
            _emit_diagnostic(
                "batch-manifest",
                f"chunk[{i}] must have string 'input' and 'output' fields",
            )
            return 2

    # Single import / model load — this is the perf win.
    try:
        from docline.dependencies import DependencyUnavailableError
        from docline.readers.pdf import _read_pdf_docling_pages
    except ImportError as err:
        _emit_diagnostic("import", "could not import docline.readers.pdf", str(err))
        return 6

    success_count = 0
    failure_count = 0

    for i, entry in enumerate(chunks):
        input_path = Path(entry["input"])
        output_path = Path(entry["output"])
        chunk_do_ocr = bool(entry.get("do_ocr", True))

        if not input_path.exists():
            err_env = _build_error_envelope(FileNotFoundError(f"input PDF not found: {input_path}"))
            try:
                _write_envelope(output_path, err_env)
            except OSError as werr:
                _emit_diagnostic(
                    "batch-output",
                    f"could not write error envelope for chunk[{i}] to {output_path}",
                    str(werr),
                )
                # Cannot record this failure to consumers; treat as critical.
                return 6
            failure_count += 1
            continue

        read_kwargs: dict[str, bool] = {} if chunk_do_ocr else {"do_ocr": False}
        try:
            pages = _read_pdf_docling_pages(input_path, **read_kwargs)
        except DependencyUnavailableError as err:
            # Extras missing affects ALL chunks identically; abort.
            _emit_diagnostic("docling-extras", "docling extras not installed", str(err))
            return 4
        except Exception as err:  # noqa: BLE001 — per-chunk isolation
            err_env = _build_error_envelope(err)
            try:
                _write_envelope(output_path, err_env)
            except OSError as werr:
                _emit_diagnostic(
                    "batch-output",
                    f"could not write error envelope for chunk[{i}] to {output_path}",
                    str(werr),
                )
                return 6
            failure_count += 1
            continue

        try:
            envelope = _build_envelope(pages)
            _write_envelope(output_path, envelope)
        except (OSError, TypeError, ValueError) as err:
            err_env = _build_error_envelope(err)
            try:
                _write_envelope(output_path, err_env)
            except OSError as werr:
                _emit_diagnostic(
                    "batch-output",
                    f"could not write error envelope for chunk[{i}] to {output_path}",
                    str(werr),
                )
                return 6
            failure_count += 1
            continue

        success_count += 1

    if success_count == 0:
        _emit_diagnostic(
            "batch-runtime",
            f"all {failure_count} chunks failed in batched mode",
        )
        return 6
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m docline._tools.docling_worker``.

    Args:
        argv: Command-line arguments (without the program name).
            Defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code per the table in the module docstring.
    """

    args = sys.argv[1:] if argv is None else argv

    if len(args) == 2 and args[0] == "--batch":
        return _run_batched(Path(args[1]))

    # Single-chunk mode: an optional --no-ocr flag may appear among the args.
    do_ocr = True
    positional: list[str] = []
    for arg in args:
        if arg == "--no-ocr":
            do_ocr = False
        elif arg.startswith("--"):
            _emit_diagnostic("cli", f"unknown flag: {arg}")
            return 2
        else:
            positional.append(arg)

    if len(positional) != 2:
        _emit_diagnostic(
            "cli",
            "expected: INPUT_PDF OUTPUT_MD [--no-ocr]  |  --batch MANIFEST_JSON",
        )
        return 2

    return _run_single(Path(positional[0]), Path(positional[1]), do_ocr=do_ocr)


if __name__ == "__main__":
    raise SystemExit(main())
