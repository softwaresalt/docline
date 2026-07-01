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


def test_returns_4_when_docling_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
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


def test_returns_5_when_docling_raises_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
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


def test_success_writes_envelope_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: docling returns pages, worker writes JSON envelope, exits 0.

    Contract refresh (030-F T1): worker output is now a JSON envelope
    with shape ``{schema_version, pages, page_count, text}``. Per-page
    fidelity is preserved in the ``pages`` field; the ``text`` field
    keeps the legacy joined-markdown for stitching consumers.
    """

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
    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert envelope["schema_version"] == 1
    assert envelope["pages"] == ["# Page 1\nHello", "# Page 2\nWorld"]
    assert envelope["page_count"] == 2
    assert envelope["text"] == "# Page 1\nHello\n\n# Page 2\nWorld"


def test_envelope_page_count_matches_pages_length(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Integrity check: ``len(pages) == page_count`` for any page count."""

    from docline._tools import docling_worker

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    output = tmp_path / "out.md"

    monkeypatch.setattr(
        "docline.readers.pdf._read_pdf_docling_pages",
        lambda path, picture_sink=None: ["a", "b", "c", "d", "e"],
    )

    exit_code = docling_worker.main([str(pdf), str(output)])

    assert exit_code == 0
    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert len(envelope["pages"]) == envelope["page_count"] == 5


def test_envelope_preserves_non_ascii_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ensure_ascii=False keeps unicode characters intact in the envelope."""

    from docline._tools import docling_worker

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    output = tmp_path / "out.md"

    pages = ["# Δοκιμή", "# 日本語ページ", "# Página español — ☕"]
    monkeypatch.setattr(
        "docline.readers.pdf._read_pdf_docling_pages",
        lambda path, picture_sink=None: list(pages),
    )

    exit_code = docling_worker.main([str(pdf), str(output)])

    assert exit_code == 0
    raw = output.read_text(encoding="utf-8")
    # ensure_ascii=False means the raw bytes contain the actual unicode
    # characters, not \uXXXX escapes.
    assert "Δοκιμή" in raw
    assert "日本語ページ" in raw
    assert "☕" in raw
    envelope = json.loads(raw)
    assert envelope["pages"] == pages


def test_envelope_empty_pages_list_for_zero_page_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A zero-page result still produces a well-formed envelope."""

    from docline._tools import docling_worker

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    output = tmp_path / "out.md"

    monkeypatch.setattr(
        "docline.readers.pdf._read_pdf_docling_pages",
        lambda path, picture_sink=None: [],
    )

    exit_code = docling_worker.main([str(pdf), str(output)])

    assert exit_code == 0
    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert envelope["schema_version"] == 1
    assert envelope["pages"] == []
    assert envelope["page_count"] == 0
    assert envelope["text"] == ""


def test_creates_parent_directories_for_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Worker creates output_path.parent if it doesn't exist."""

    from docline._tools import docling_worker

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    output = tmp_path / "nested" / "subdir" / "out.md"

    monkeypatch.setattr(
        "docline.readers.pdf._read_pdf_docling_pages", lambda path, picture_sink=None: ["x"]
    )

    exit_code = docling_worker.main([str(pdf), str(output)])

    assert exit_code == 0
    assert output.exists()
    # Still emits an envelope at the nested path
    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert envelope["pages"] == ["x"]


# ---------------------------------------------------------------------------
# 030.003-T: batched mode (--batch MANIFEST_JSON)
# ---------------------------------------------------------------------------


def _write_manifest(path: Path, chunks: list[tuple[Path, Path]]) -> Path:
    payload = {"chunks": [{"input": str(inp), "output": str(out)} for inp, out in chunks]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_batched_mode_processes_multiple_chunks_in_one_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 3-chunk manifest produces 3 envelope files from a single subprocess call.

    The shared docling import / model load is the perf win. Verify each
    chunk's output path has its own valid envelope with the expected
    pages payload.
    """

    from docline._tools import docling_worker

    chunks: list[tuple[Path, Path]] = []
    for i in range(3):
        inp = tmp_path / f"chunk-{i}.pdf"
        inp.write_bytes(b"%PDF-1.4\n")
        out = tmp_path / f"chunk-{i}.md"
        chunks.append((inp, out))

    manifest_path = _write_manifest(tmp_path / "manifest.json", chunks)

    call_counts: dict[str, int] = {"reads": 0}

    def fake_read(path: Path, *, picture_sink: Any | None = None) -> list[str]:
        call_counts["reads"] += 1
        idx = int(path.stem.split("-")[1])
        return [f"# Chunk {idx} Page 1", f"# Chunk {idx} Page 2"]

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", fake_read)

    exit_code = docling_worker.main(["--batch", str(manifest_path)])

    assert exit_code == 0
    assert call_counts["reads"] == 3
    for i, (_inp, out) in enumerate(chunks):
        assert out.exists()
        envelope = json.loads(out.read_text(encoding="utf-8"))
        assert envelope["schema_version"] == 1
        assert envelope["pages"] == [f"# Chunk {i} Page 1", f"# Chunk {i} Page 2"]
        assert envelope["page_count"] == 2
        assert "error" not in envelope


def test_batched_mode_one_chunk_fails_others_succeed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A per-chunk RuntimeError writes an error envelope but does not abort the batch."""

    from docline._tools import docling_worker

    chunks: list[tuple[Path, Path]] = []
    for i in range(3):
        inp = tmp_path / f"chunk-{i}.pdf"
        inp.write_bytes(b"%PDF-1.4\n")
        out = tmp_path / f"chunk-{i}.md"
        chunks.append((inp, out))

    manifest_path = _write_manifest(tmp_path / "manifest.json", chunks)

    def fake_read(path: Path, *, picture_sink: Any | None = None) -> list[str]:
        idx = int(path.stem.split("-")[1])
        if idx == 1:
            raise RuntimeError(f"docling exploded on chunk {idx}")
        return [f"chunk {idx} content"]

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", fake_read)

    exit_code = docling_worker.main(["--batch", str(manifest_path)])

    assert exit_code == 0  # at least one chunk succeeded
    # Chunks 0 and 2 succeeded with content envelopes.
    env0 = json.loads(chunks[0][1].read_text(encoding="utf-8"))
    env2 = json.loads(chunks[2][1].read_text(encoding="utf-8"))
    assert env0["pages"] == ["chunk 0 content"]
    assert env2["pages"] == ["chunk 2 content"]
    assert "error" not in env0
    assert "error" not in env2
    # Chunk 1 got an error envelope.
    env1 = json.loads(chunks[1][1].read_text(encoding="utf-8"))
    assert env1["pages"] == []
    assert env1["page_count"] == 0
    assert "error" in env1
    assert "docling exploded" in env1["error"]


def test_batched_mode_missing_input_writes_error_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A chunk whose input PDF is missing gets an error envelope, not a process-level abort."""

    from docline._tools import docling_worker

    real_inp = tmp_path / "real.pdf"
    real_inp.write_bytes(b"%PDF-1.4\n")
    ghost_inp = tmp_path / "ghost.pdf"  # never created
    chunks = [
        (real_inp, tmp_path / "real.md"),
        (ghost_inp, tmp_path / "ghost.md"),
    ]
    manifest_path = _write_manifest(tmp_path / "manifest.json", chunks)

    monkeypatch.setattr(
        "docline.readers.pdf._read_pdf_docling_pages",
        lambda path, picture_sink=None: ["real content"],
    )

    exit_code = docling_worker.main(["--batch", str(manifest_path)])

    assert exit_code == 0
    # Real chunk got content; ghost chunk got error envelope.
    real_env = json.loads(chunks[0][1].read_text(encoding="utf-8"))
    ghost_env = json.loads(chunks[1][1].read_text(encoding="utf-8"))
    assert real_env["pages"] == ["real content"]
    assert ghost_env["error"]
    assert "ghost.pdf" in ghost_env["error"]


def test_batched_mode_all_chunks_fail_returns_exit_6(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """If every chunk fails, the process exits non-zero so the parent can re-route."""

    from docline._tools import docling_worker

    chunks: list[tuple[Path, Path]] = []
    for i in range(2):
        inp = tmp_path / f"chunk-{i}.pdf"
        inp.write_bytes(b"%PDF-1.4\n")
        out = tmp_path / f"chunk-{i}.md"
        chunks.append((inp, out))

    manifest_path = _write_manifest(tmp_path / "manifest.json", chunks)

    def always_fails(path: Path, *, picture_sink: Any | None = None) -> list[str]:
        raise RuntimeError("docling-runtime: catastrophic")

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", always_fails)

    exit_code = docling_worker.main(["--batch", str(manifest_path)])

    captured = capsys.readouterr()
    diag = json.loads(captured.err.strip().splitlines()[-1])
    assert exit_code == 6
    assert diag["stage"] == "batch-runtime"
    # Both chunks still got error envelopes for diagnostic surfacing.
    for _inp, out in chunks:
        assert out.exists()
        env = json.loads(out.read_text(encoding="utf-8"))
        assert "error" in env


def test_batched_mode_docling_extras_missing_returns_exit_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """If docling extras are not installed, abort the whole batch."""

    from docline import dependencies
    from docline._tools import docling_worker

    inp = tmp_path / "chunk-0.pdf"
    inp.write_bytes(b"%PDF-1.4\n")
    manifest_path = _write_manifest(tmp_path / "manifest.json", [(inp, tmp_path / "chunk-0.md")])

    def no_extras(path: Path, *, picture_sink: Any | None = None) -> list[str]:
        raise dependencies.DependencyUnavailableError("docling not installed")

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", no_extras)

    exit_code = docling_worker.main(["--batch", str(manifest_path)])

    captured = capsys.readouterr()
    diag = json.loads(captured.err.strip().splitlines()[-1])
    assert exit_code == 4
    assert diag["stage"] == "docling-extras"


def test_batched_mode_missing_manifest_returns_exit_2(tmp_path: Path, capsys) -> None:
    """A nonexistent manifest path triggers an exit 2 CLI error."""

    from docline._tools import docling_worker

    exit_code = docling_worker.main(["--batch", str(tmp_path / "nope.json")])

    captured = capsys.readouterr()
    diag = json.loads(captured.err.strip().splitlines()[-1])
    assert exit_code == 2
    assert diag["stage"] == "batch-manifest"


def test_batched_mode_malformed_manifest_returns_exit_2(tmp_path: Path, capsys) -> None:
    """A manifest that is valid JSON but the wrong shape exits 2."""

    from docline._tools import docling_worker

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"not_chunks": []}), encoding="utf-8")

    exit_code = docling_worker.main(["--batch", str(bad)])

    captured = capsys.readouterr()
    diag = json.loads(captured.err.strip().splitlines()[-1])
    assert exit_code == 2
    assert diag["stage"] == "batch-manifest"


def test_batched_mode_chunk_entry_missing_fields_returns_exit_2(tmp_path: Path, capsys) -> None:
    """A chunk entry missing 'input' or 'output' string fields exits 2."""

    from docline._tools import docling_worker

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"chunks": [{"input": "x.pdf"}]}), encoding="utf-8")

    exit_code = docling_worker.main(["--batch", str(bad)])

    captured = capsys.readouterr()
    diag = json.loads(captured.err.strip().splitlines()[-1])
    assert exit_code == 2
    assert diag["stage"] == "batch-manifest"


# ---------------------------------------------------------------------------
# 034.005-T: do_ocr plumbing (single-chunk --no-ocr flag + batched manifest field)
# ---------------------------------------------------------------------------


def test_single_chunk_no_ocr_flag_disables_ocr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--no-ocr`` in single-chunk mode forwards ``do_ocr=False`` to the reader."""

    from docline._tools import docling_worker

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    output = tmp_path / "out.md"

    seen: dict[str, bool] = {}

    def fake_read(path: Path, *, picture_sink: Any | None = None, do_ocr: bool = True) -> list[str]:
        seen["do_ocr"] = do_ocr
        return ["x"]

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", fake_read)

    exit_code = docling_worker.main([str(pdf), str(output), "--no-ocr"])

    assert exit_code == 0
    assert seen["do_ocr"] is False
    assert output.exists()


def test_single_chunk_defaults_to_ocr_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Single-chunk mode without ``--no-ocr`` leaves OCR enabled (default behavior)."""

    from docline._tools import docling_worker

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    output = tmp_path / "out.md"

    seen: dict[str, bool] = {"do_ocr": True}

    def fake_read(path: Path, *, picture_sink: Any | None = None, do_ocr: bool = True) -> list[str]:
        seen["do_ocr"] = do_ocr
        return ["x"]

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", fake_read)

    exit_code = docling_worker.main([str(pdf), str(output)])

    assert exit_code == 0
    assert seen["do_ocr"] is True


def test_batched_manifest_do_ocr_field_routes_per_chunk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A per-chunk ``do_ocr`` manifest field forwards to the reader; absent defaults to True."""

    from docline._tools import docling_worker

    inp0 = tmp_path / "chunk-0.pdf"
    inp0.write_bytes(b"%PDF-1.4\n")
    inp1 = tmp_path / "chunk-1.pdf"
    inp1.write_bytes(b"%PDF-1.4\n")
    out0 = tmp_path / "chunk-0.md"
    out1 = tmp_path / "chunk-1.md"

    manifest = {
        "chunks": [
            {"input": str(inp0), "output": str(out0), "do_ocr": False},
            {"input": str(inp1), "output": str(out1)},  # no do_ocr -> default True
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    seen: dict[str, bool] = {}

    def fake_read(path: Path, *, picture_sink: Any | None = None, do_ocr: bool = True) -> list[str]:
        seen[path.stem] = do_ocr
        return ["content"]

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", fake_read)

    exit_code = docling_worker.main(["--batch", str(manifest_path)])

    assert exit_code == 0
    assert seen["chunk-0"] is False
    assert seen["chunk-1"] is True


# ---------------------------------------------------------------------------
# 040.001-T: ocr_scale plumbing (single-chunk --ocr-scale flag + manifest field)
# ---------------------------------------------------------------------------


def test_single_chunk_ocr_scale_flag_forwards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--ocr-scale=<float>`` in single-chunk mode forwards ``ocr_scale`` to the reader."""

    from docline._tools import docling_worker

    inp = tmp_path / "in.pdf"
    inp.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "out.md"

    seen: dict[str, float | None] = {}

    def fake_read(
        path: Path,
        *,
        picture_sink: Any | None = None,
        do_ocr: bool = True,
        ocr_scale: float | None = None,
    ) -> list[str]:
        seen["ocr_scale"] = ocr_scale
        return ["content"]

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", fake_read)

    exit_code = docling_worker.main([str(inp), str(out), "--ocr-scale=0.5"])

    assert exit_code == 0
    assert seen["ocr_scale"] == 0.5


def test_single_chunk_defaults_ocr_scale_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ``--ocr-scale`` the reader is called with the default (``None``)."""

    from docline._tools import docling_worker

    inp = tmp_path / "in.pdf"
    inp.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "out.md"

    seen: dict[str, float | None] = {"ocr_scale": 1.234}

    def fake_read(
        path: Path,
        *,
        picture_sink: Any | None = None,
        do_ocr: bool = True,
        ocr_scale: float | None = None,
    ) -> list[str]:
        seen["ocr_scale"] = ocr_scale
        return ["content"]

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", fake_read)

    exit_code = docling_worker.main([str(inp), str(out)])

    assert exit_code == 0
    assert seen["ocr_scale"] is None


def test_batched_manifest_ocr_scale_field_routes_per_chunk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A per-chunk ``ocr_scale`` manifest field forwards to the reader; absent -> None."""

    from docline._tools import docling_worker

    inp0 = tmp_path / "chunk-0.pdf"
    inp0.write_bytes(b"%PDF-1.4\n")
    inp1 = tmp_path / "chunk-1.pdf"
    inp1.write_bytes(b"%PDF-1.4\n")
    out0 = tmp_path / "chunk-0.md"
    out1 = tmp_path / "chunk-1.md"

    manifest = {
        "chunks": [
            {"input": str(inp0), "output": str(out0), "ocr_scale": 0.25},
            {"input": str(inp1), "output": str(out1)},  # no ocr_scale -> None
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    seen: dict[str, float | None] = {}

    def fake_read(
        path: Path,
        *,
        picture_sink: Any | None = None,
        do_ocr: bool = True,
        ocr_scale: float | None = None,
    ) -> list[str]:
        seen[path.stem] = ocr_scale
        return ["content"]

    monkeypatch.setattr("docline.readers.pdf._read_pdf_docling_pages", fake_read)

    exit_code = docling_worker.main(["--batch", str(manifest_path)])

    assert exit_code == 0
    assert seen["chunk-0"] == 0.25
    assert seen["chunk-1"] is None


def test_single_chunk_invalid_ocr_scale_returns_2(tmp_path: Path, capsys: Any) -> None:
    """A non-numeric ``--ocr-scale`` value is a CLI error (exit 2)."""

    from docline._tools import docling_worker

    inp = tmp_path / "in.pdf"
    inp.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "out.md"

    exit_code = docling_worker.main([str(inp), str(out), "--ocr-scale=abc"])

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["stage"] == "cli"
