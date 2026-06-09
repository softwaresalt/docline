"""Tests for triage_report_only integration with quality_metrics (task 021.003-T / 023-S T3).

Verifies that ``triage_report_only`` emits per-page AST-aware quality
metrics in the TSV output and aggregate quality_metrics_summary in
the returned TriageResult.metadata.

Backward-compatibility tests are kept separate in
``test_pdf_triage_baseline_engine.py``; this file focuses on the new
qm_* columns and summary block.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pypdf


def _make_pdf(path: Path, page_count: int) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def _no_flag_scorer() -> Any:
    from docline.process.fidelity_scorer import PageScore

    def scorer(page_index: int, text: str, page_metadata: object | None) -> PageScore:
        return PageScore(
            page_index=page_index,
            signals={"density": 0.0},
            aggregate=0.0,
            needs_docling=False,
            reason="ok",
        )

    return scorer


def test_triage_report_only_tsv_includes_qm_columns(tmp_path: Path) -> None:
    """TSV from triage_report_only MUST include 7 qm_* columns.

    Required columns (suffixed onto the existing signal columns):
        qm_parse_ok, qm_heading_count, qm_section_count, qm_table_count,
        qm_table_cell_count, qm_structural_density_per_1k, qm_median_section_chars
    """
    from docline.process.pdf_triage import triage_report_only

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=3)
    tsv_path = tmp_path / "report.tsv"
    triage_report_only(
        pdf,
        output_dir=tmp_path / "out",
        report_tsv_path=tsv_path,
        scorer=_no_flag_scorer(),
    )
    with tsv_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    required_qm_cols = {
        "qm_parse_ok",
        "qm_heading_count",
        "qm_section_count",
        "qm_table_count",
        "qm_table_cell_count",
        "qm_structural_density_per_1k",
        "qm_median_section_chars",
    }
    missing = required_qm_cols - set(fieldnames)
    assert not missing, f"TSV missing qm_* columns: {missing}"
    assert len(rows) == 3, "expected 1 row per page"


def test_triage_report_only_metadata_includes_quality_metrics_summary(tmp_path: Path) -> None:
    """TriageResult.metadata from triage_report_only MUST include a
    quality_metrics_summary block with mean+median for the key metrics.
    """
    from docline.process.pdf_triage import triage_report_only

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=2)
    result = triage_report_only(
        pdf,
        output_dir=tmp_path / "out",
        report_tsv_path=tmp_path / "report.tsv",
        scorer=_no_flag_scorer(),
    )
    summary = result.metadata.get("quality_metrics_summary")
    assert isinstance(summary, dict), (
        f"missing quality_metrics_summary block; got {type(summary).__name__}"
    )
    # MUST report mean and median for at least these 4 key metrics
    for metric in (
        "structural_density_per_1k",
        "heading_count",
        "section_count",
        "table_cell_count",
    ):
        assert metric in summary, f"missing {metric} in summary"
        assert "mean" in summary[metric], f"missing mean for {metric}"
        assert "median" in summary[metric], f"missing median for {metric}"


def test_triage_report_only_qm_columns_appear_after_existing_signal_columns(tmp_path: Path) -> None:
    """qm_* columns MUST come after the existing signal/aggregate/needs_docling/reason
    columns for backward compatibility with TSV consumers that read positionally.
    """
    from docline.process.pdf_triage import triage_report_only

    pdf = _make_pdf(tmp_path / "doc.pdf", page_count=1)
    tsv_path = tmp_path / "report.tsv"
    triage_report_only(
        pdf,
        output_dir=tmp_path / "out",
        report_tsv_path=tsv_path,
        scorer=_no_flag_scorer(),
    )
    with tsv_path.open("r", encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")

    # page_index, signal..., aggregate, needs_docling, reason, qm_*
    assert header[0] == "page_index"
    # Find first qm_ index
    qm_indices = [i for i, h in enumerate(header) if h.startswith("qm_")]
    reason_idx = header.index("reason")
    assert all(i > reason_idx for i in qm_indices), (
        f"qm_* columns must come after 'reason' for backward compat; header={header}"
    )
