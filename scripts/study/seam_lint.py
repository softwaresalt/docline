"""Seam-integrity lint for assembled triage markdown (037.001-T).

Verifies that assembled docline output — which interleaves heuristic pages
(markitdown/pypdf) with docling ranges — preserves a coherent, ingestible
document structure across those engine seams. This is the concern that gates
graphtor-docs ingestion (whole-document AST + proper heading hierarchy), as
distinct from per-page fidelity, which the assembled output discards anyway
(see ``docs/decisions/2026-06-28-merge-gap-tuning-verdict.md``).

Two independent signals are reported per document:

* **Heading hierarchy** (the ingestion gate) — reuses
  :func:`docline.process.heading_validation.validate_heading_hierarchy`, with
  the same sparse-hierarchy auto-tolerance the assembler applies
  (:func:`body_should_skip_heading_validation`, 028-S). A document FAILS only
  on real disorder (e.g. an H2 before any H1) — the case that produces
  incoherent chunk parentage downstream.
* **AST depth** (informational) — reuses
  :func:`docline.process.ast_lint.lint_markdown_ast`. It flags headings deeper
  than H3. H4-H6 are intentionally tolerated by the ingestion contract (they
  sit below the chunk-boundary horizon), so these findings are surfaced for
  visibility but do **not** fail a document.

This script does not run docling — it only reads already-assembled markdown,
so it is agent-safe and fully unit-testable.

Usage::

    python scripts/study/seam_lint.py \\
        --paths .elt/output/azure-cosmos-db

Exit codes: ``0`` all documents pass the heading-hierarchy gate; ``1`` at least
one document fails the gate; ``2`` bad arguments (no markdown found).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from docline.process.ast_lint import lint_markdown_ast
from docline.process.heading_validation import (
    HeadingHierarchyError,
    body_should_skip_heading_validation,
    validate_heading_hierarchy,
)

_FRONTMATTER_FENCE = "---"


def strip_frontmatter(text: str) -> str:
    """Return the document body with a leading YAML frontmatter block removed.

    The assembler emits ``---\\n<yaml>\\n---\\n<body>``. Heading validation
    expects the body, so the frontmatter is stripped first. A document without
    a leading fence, or with an unterminated one, is returned unchanged.

    Args:
        text: Full assembled document text.

    Returns:
        The body text with any leading frontmatter block removed.
    """
    if not text.startswith(_FRONTMATTER_FENCE):
        return text
    lines = text.splitlines(keepends=True)
    for index in range(1, len(lines)):
        if lines[index].rstrip("\n") == _FRONTMATTER_FENCE:
            return "".join(lines[index + 1 :])
    return text


def check_document(text: str, *, doc_type: str = "pdf") -> dict[str, Any]:
    """Run the AST depth lint and heading-hierarchy gate on one document.

    Args:
        text: Full assembled document text (frontmatter allowed).
        doc_type: Document type passed to :func:`lint_markdown_ast` for
            schema lookup. Defaults to ``"pdf"`` (no required sections), so
            only the heading-depth rule applies.

    Returns:
        A dict with ``ast_errors`` (list of AST lint strings),
        ``hierarchy`` (``"pass"`` / ``"fail"`` / ``"skipped"``),
        ``hierarchy_error`` (message or ``None``), and ``hierarchy_ok`` (bool;
        the ingestion-gate verdict — ``True`` unless hierarchy is ``"fail"``).
    """
    body = strip_frontmatter(text)
    ast_errors = lint_markdown_ast(body, doc_type)

    if body_should_skip_heading_validation(body):
        hierarchy = "skipped"
        hierarchy_error: str | None = None
    else:
        try:
            validate_heading_hierarchy(body)
            hierarchy = "pass"
            hierarchy_error = None
        except HeadingHierarchyError as err:
            hierarchy = "fail"
            hierarchy_error = str(err)

    return {
        "ast_errors": ast_errors,
        "hierarchy": hierarchy,
        "hierarchy_error": hierarchy_error,
        "hierarchy_ok": hierarchy != "fail",
    }


def check_path(path: Path, *, doc_type: str = "pdf") -> dict[str, Any]:
    """Check a single markdown file and tag the result with its path.

    Args:
        path: Path to an assembled markdown document.
        doc_type: Document type forwarded to :func:`check_document`.

    Returns:
        The :func:`check_document` result with an added ``path`` key.
    """
    result = check_document(path.read_text(encoding="utf-8"), doc_type=doc_type)
    result["path"] = path
    return result


def _collect_markdown(paths: list[Path]) -> list[Path]:
    """Expand the requested paths into a sorted list of markdown files.

    Directories are expanded to their ``*.md`` children (non-recursive);
    files are taken as-is.
    """
    collected: list[Path] = []
    for path in paths:
        if path.is_dir():
            collected.extend(sorted(path.glob("*.md")))
        elif path.exists():
            collected.append(path)
    return collected


def _format_report(results: list[dict[str, Any]]) -> str:
    """Render per-document results as a fixed-width text table."""
    header = f"{'document':<40}  {'hierarchy':>9}  {'ast_depth':>9}"
    lines = [header, "-" * len(header)]
    for result in results:
        name = Path(result["path"]).name
        verdict = "PASS" if result["hierarchy_ok"] else "FAIL"
        hierarchy = f"{verdict}/{result['hierarchy']}"
        ast = "clean" if not result["ast_errors"] else f"{len(result['ast_errors'])} note(s)"
        lines.append(f"{name:<40}  {hierarchy:>9}  {ast:>9}")
        if not result["hierarchy_ok"]:
            lines.append(f"    hierarchy: {result['hierarchy_error']}")
        for err in result["ast_errors"]:
            lines.append(f"    ast: {err}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python scripts/study/seam_lint.py``."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate assembled triage markdown for a coherent heading "
            "hierarchy (the graphtor-docs ingestion gate) across engine seams."
        ),
    )
    parser.add_argument(
        "--paths",
        type=Path,
        nargs="+",
        required=True,
        help="Assembled .md files or directories (directories expand to *.md).",
    )
    parser.add_argument(
        "--doc-type",
        default="pdf",
        help="Document type for the AST schema lookup (default 'pdf').",
    )
    args = parser.parse_args(argv)

    files = _collect_markdown(args.paths)
    if not files:
        print("ERROR: no markdown files found at the requested --paths")
        return 2

    results = [check_path(path, doc_type=args.doc_type) for path in files]

    print(_format_report(results))
    print()

    failures = [r for r in results if not r["hierarchy_ok"]]
    skipped = sum(1 for r in results if r["hierarchy"] == "skipped")
    ast_notes = sum(len(r["ast_errors"]) for r in results)
    print(
        f"SUMMARY: {len(results)} document(s), {len(failures)} hierarchy "
        f"failure(s), {skipped} tolerated (sparse), {ast_notes} AST depth note(s)."
    )
    if failures:
        print("VERDICT: FAIL — heading-hierarchy disorder at one or more documents")
        return 1
    print("VERDICT: PASS — all documents satisfy the heading-hierarchy gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
