"""Tests for the config-driven CLI fetch command."""

import json
from pathlib import Path

from docline.cli import main


def _write_config(config_dir: Path, name: str, content: str) -> None:
    """Write a YAML config fixture for CLI tests.

    Args:
        config_dir: Directory to write into.
        name: File name to create.
        content: YAML content.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / name).write_text(content, encoding="utf-8")


def test_cli_fetch_reads_default_elt_config_dir(monkeypatch, tmp_path: Path, capsys) -> None:
    """CLI fetch reads source configs from .elt/config by default."""
    monkeypatch.chdir(tmp_path)
    _write_config(
        tmp_path / ".elt" / "config",
        "source.yaml",
        "type: web_crawl\nurl: https://example.com\n",
    )

    exit_code = main(["fetch"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert len(payload) == 1
    assert payload[0]["metadata"]["source"] == "web_crawl:https://example.com"


def test_cli_fetch_missing_default_config_dir_returns_1(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """CLI fetch fails when the default ELT config directory is missing."""
    monkeypatch.chdir(tmp_path)

    exit_code = main(["fetch"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "ELT config directory not found" in captured.err


def test_cli_fetch_custom_config_dir_flag(monkeypatch, tmp_path: Path, capsys) -> None:
    """CLI fetch accepts a custom config directory."""
    monkeypatch.chdir(tmp_path)
    custom_config_dir = tmp_path / "configs"
    _write_config(
        custom_config_dir,
        "source.yaml",
        "type: github_repo\nrepo_url: https://github.com/org/repo\n",
    )

    exit_code = main(["fetch", "--config-dir", "configs"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert (
        payload[0]["metadata"]["source"] == "github_repo:https://github.com/org/repo@main:**/*.md"
    )


def test_manifest_flag_still_works(capsys) -> None:
    """CLI manifest output remains unchanged."""
    exit_code = main(["--manifest"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "tools" in json.loads(captured.out)


def test_process_command_still_works(monkeypatch, tmp_path: Path, capsys) -> None:
    """CLI process behavior remains unchanged."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()

    exit_code = main(["process", "--staging-dir", "staging"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out)["error"] == "Process execution is not implemented."
