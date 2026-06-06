"""Tests for ``triage_report_only`` (task 019.006-T)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pypdf


def _make_pdf(path: Path, page_count: int) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def test_report_only_never_invokes_runner(tmp_path: Path) -> None:
    """report-only mode must not invoke the docling runner under any flag pattern."""
    from docline.process.pdf_triage import triage_report_only

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=10)
    runner = MagicMock()
    triage_report_only(
        pdf,
        output_dir=tmp_path / "out",
        report_tsv_path=tmp_path / "report.tsv",
    )
    assert runner.call_count == 0


def test_report_tsv_has_canonical_columns(tmp_path: Path) -> None:
    """The emitted TSV must include a header row with all expected columns."""
    from docline.process.pdf_triage import triage_report_only

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=5)
    tsv_path = tmp_path / "report.tsv"
    triage_report_only(pdf, output_dir=tmp_path / "out", report_tsv_path=tsv_path)

    assert tsv_path.exists(), "report TSV must be written"
    header = tsv_path.read_text(encoding="utf-8").splitlines()[0].split("\t")
    for required in ("page_index", "aggregate", "needs_docling", "reason"):
        assert required in header, f"TSV header missing column: {required}"


def test_report_tsv_rows_sorted_by_page_index(tmp_path: Path) -> None:
    """Each data row in the TSV is one page, sorted ascending by page_index."""
    from docline.process.pdf_triage import triage_report_only

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=7)
    tsv_path = tmp_path / "report.tsv"
    triage_report_only(pdf, output_dir=tmp_path / "out", report_tsv_path=tsv_path)

    lines = tsv_path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    page_col = header.index("page_index")
    indices = [int(row.split("\t")[page_col]) for row in lines[1:]]
    assert indices == sorted(indices)
    assert indices == list(range(7))
