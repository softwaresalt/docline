"""CLI verbosity + progress-wiring tests (056.007-T).

Covers ``-q/--quiet`` + ``-v/--verbose`` flag parsing and mutual exclusion, the
mapping to :class:`~docline.progress.Verbosity`, and the dispatch contract:
progress is written to stderr while the terminal JSON result stays on stdout,
unchanged across verbosity modes.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from docline.cli import _resolve_verbosity, main
from docline.fetch.models import SourceMetadata, StagingJob
from docline.fetch.staging import build_cache_path, make_job_id, sanitize_source
from docline.progress import Verbosity


def _stage_one_file(tmp_path: Path) -> tuple[str, str]:
    staging_root = tmp_path / "staging"
    source_key = "web_crawl:https://example.com/docs"
    job_id = make_job_id(source_key)
    cache_rel = build_cache_path(staging_root.name, job_id)
    cache_abs = staging_root.parent / cache_rel
    files_dir = cache_abs / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    (files_dir / "page.html").write_bytes(b"<html><body><h1>Docs</h1></body></html>")
    job = StagingJob(
        job_id=job_id,
        metadata=SourceMetadata(
            source=sanitize_source(source_key), fetch_timestamp=datetime.now(UTC)
        ),
        cache_path=cache_rel,
        complete=True,
    )
    (cache_abs / "metadata.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return str(staging_root.relative_to(tmp_path)), "output"


def test_resolve_verbosity_default_is_normal() -> None:
    assert _resolve_verbosity(argparse.Namespace()) is Verbosity.NORMAL


def test_resolve_verbosity_quiet_is_silent() -> None:
    assert _resolve_verbosity(argparse.Namespace(quiet=True)) is Verbosity.SILENT


def test_resolve_verbosity_verbose_is_verbose() -> None:
    assert _resolve_verbosity(argparse.Namespace(verbose=True)) is Verbosity.VERBOSE


@pytest.mark.parametrize("command", ["fetch", "process"])
def test_quiet_and_verbose_are_mutually_exclusive(command: str) -> None:
    # argparse rejects -q -v together; main() maps the SystemExit to exit code 2.
    assert main([command, "-q", "-v"]) == 2


def _run_process(tmp_path: Path, *flags: str) -> int:
    staging_rel, output_rel = _stage_one_file(tmp_path)
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        return main(["process", "--staging-dir", staging_rel, "--output-dir", output_rel, *flags])
    finally:
        os.chdir(original_cwd)


def test_process_prints_json_on_stdout_quiet_silences_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run_process(tmp_path, "-q")
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out.strip())
    assert payload["success"] is True
    # quiet: no progress on stderr; stdout carries no carriage-return control chars
    assert captured.err == ""
    assert "\r" not in captured.out


def test_process_verbose_emits_stderr_progress_with_same_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run_process(tmp_path, "-v")
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out.strip())
    assert payload["success"] is True
    # verbose: per-file progress line on stderr, carrying the job identity
    assert "job 1/1" in captured.err
    # the JSON result contract is unchanged — no progress leaks onto stdout
    assert "job 1/1" not in captured.out


def test_quiet_passes_none_progress_to_execute_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake(request, progress=None):
        from docline.app_models import ProcessResult

        captured["progress"] = progress
        return ProcessResult(
            input_path=request.staging_dir, output_path=request.output_dir, success=True
        )

    monkeypatch.setattr("docline.cli.execute_process", fake)
    monkeypatch.chdir(tmp_path)
    code = main(["process", "--staging-dir", "staging", "--output-dir", "output", "-q"])
    assert code == 0
    # quiet skips all progress work (no pre-scan, no per-file callbacks)
    assert captured["progress"] is None


def test_verbose_passes_reporter_to_execute_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake(request, progress=None):
        from docline.app_models import ProcessResult

        captured["progress"] = progress
        return ProcessResult(
            input_path=request.staging_dir, output_path=request.output_dir, success=True
        )

    monkeypatch.setattr("docline.cli.execute_process", fake)
    monkeypatch.chdir(tmp_path)
    code = main(["process", "--staging-dir", "staging", "--output-dir", "output", "-v"])
    assert code == 0
    assert captured["progress"] is not None


def _run_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *flags: str) -> tuple[int, dict]:
    captured: dict[str, object] = {}

    def fake_exec(config_dir, staging_dir, workspace_root=None, progress=None):
        captured["progress"] = progress
        return [
            StagingJob(
                job_id="j",
                cache_path="c",
                complete=True,
                metadata=SourceMetadata(source="s", fetch_timestamp=datetime.now(UTC)),
            )
        ]

    monkeypatch.setattr("docline.elt.execute.execute_elt_fetch", fake_exec)
    (tmp_path / ".elt" / "config").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "fetch",
            "--execute",
            "--config-dir",
            ".elt/config",
            "--staging-dir",
            ".elt/staging",
            *flags,
        ]
    )
    return code, captured


def test_fetch_quiet_passes_none_progress_and_silences_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, captured = _run_fetch(tmp_path, monkeypatch, "-q")
    out = capsys.readouterr()
    assert code == 0
    assert captured["progress"] is None  # quiet skips progress work
    json.loads(out.out.strip())  # jobs JSON still on stdout
    assert out.err == ""  # no progress on stderr


def test_fetch_verbose_passes_reporter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, captured = _run_fetch(tmp_path, monkeypatch, "-v")
    assert code == 0
    assert captured["progress"] is not None


def test_fetch_json_on_stdout_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = _run_fetch(tmp_path, monkeypatch)
    out = capsys.readouterr()
    assert code == 0
    payload = json.loads(out.out.strip())
    assert isinstance(payload, list)
