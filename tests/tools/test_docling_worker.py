"""Tests for ``docline._tools.docling_worker`` (019.001.002-T)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def test_returns_2_on_wrong_argument_count(capsys) -> None:
    from docline._tools.docling_worker import main

    exit_code = main([])
    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())

    assert exit_code == 2
    assert payload["stage"] == "cli"


def test_returns_3_when_input_missing(tmp_path: Path, capsys) -> None:
    from docline._tools.docling_worker import main

    exit_code = main([str(tmp_path / "nope.pdf"), str(tmp_path / "out.md")])
    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())

    assert exit_code == 3
    assert payload["stage"] == "input"


def test_returns_4_when_docling_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """DependencyUnavailableError from the reader maps to exit 4."""

    from docline import dependencies
    from docline._tools import docling_worker

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def fake_read(path: Path, *, picture_sink: Any | None = None) -> list[str]:
        raise dependencies.DependencyUnavailableError("docling not installed")

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", fake_read)

    exit_code = docling_worker.main([str(pdf), str(tmp_path / "out.md")])
    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())

    assert exit_code == 4
    assert payload["stage"] == "docling-extras"


def test_returns_5_when_docling_raises_runtime_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """Any non-DependencyUnavailableError exception from docling becomes exit 5."""

    from docline._tools import docling_worker

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def boom(path: Path, *, picture_sink: Any | None = None) -> list[str]:
        raise RuntimeError("DefaultCPUAllocator: not enough memory")

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", boom)

    exit_code = docling_worker.main([str(pdf), str(tmp_path / "out.md")])
    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())

    assert exit_code == 5
    assert payload["stage"] == "docling-runtime"
    assert "RuntimeError" in payload["exception"]


def test_success_writes_markdown_and_returns_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: docling returns pages, worker writes joined markdown, exits 0."""

    from docline._tools import docling_worker

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    output = tmp_path / "out.md"

    def fake_read(path: Path, *, picture_sink: Any | None = None) -> list[str]:
        return ["# Page 1\nHello", "# Page 2\nWorld"]

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", fake_read)

    exit_code = docling_worker.main([str(pdf), str(output)])

    assert exit_code == 0
    assert output.exists()
    body = output.read_text(encoding="utf-8")
    assert "# Page 1" in body
    assert "# Page 2" in body
    assert "Hello\n\n# Page 2" in body


def test_creates_parent_directories_for_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Worker creates output_path.parent if it doesn't exist."""

    from docline._tools import docling_worker

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    output = tmp_path / "nested" / "subdir" / "out.md"

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", lambda path, picture_sink=None: ["x"])

    exit_code = docling_worker.main([str(pdf), str(output)])

    assert exit_code == 0
    assert output.exists()
