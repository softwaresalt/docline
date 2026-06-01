"""Tests for CLI fetch and process adapters."""

import json

from docline.cli import main


def test_cli_fetch_valid_source_succeeds(capsys) -> None:
    """CLI fetch succeeds for a valid source."""
    exit_code = main(["fetch", "http://example.com"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)["success"] is True


def test_cli_fetch_result_json_has_source(capsys) -> None:
    """CLI fetch JSON output preserves the source field."""
    main(["fetch", "http://example.com"])
    captured = capsys.readouterr()

    assert json.loads(captured.out)["source"] == "http://example.com"


def test_cli_fetch_result_json_has_staged_path(capsys) -> None:
    """CLI fetch JSON output includes a staged path."""
    main(["fetch", "http://example.com"])
    captured = capsys.readouterr()

    assert json.loads(captured.out)["staged_path"]


def test_cli_fetch_no_source_returns_2(capsys) -> None:
    """CLI fetch returns exit code 2 when source is missing."""
    assert main(["fetch"]) == 2
    capsys.readouterr()


def test_cli_process_with_existing_staging_dir(capsys, monkeypatch, tmp_path) -> None:
    """CLI process succeeds when the staging directory exists."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()

    exit_code = main(["process", "--staging-dir", "staging"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)["success"] is True


def test_cli_process_missing_staging_dir_returns_1(capsys) -> None:
    """CLI process fails when the staging directory does not exist."""
    exit_code = main(["process", "--staging-dir", "missing-staging"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out)["success"] is False


def test_cli_fetch_custom_depth(capsys) -> None:
    """CLI fetch accepts a custom crawl depth."""
    exit_code = main(["fetch", "http://example.com", "--depth", "2"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)["success"] is True


def test_cli_fetch_invalid_output_dir_returns_2(capsys) -> None:
    """CLI fetch rejects unsafe output directories."""
    assert main(["fetch", "http://example.com", "--output-dir", "../out"]) == 2
    capsys.readouterr()


def test_cli_process_result_json_has_output_path(capsys, monkeypatch, tmp_path) -> None:
    """CLI process JSON output includes the output path on success."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()

    main(["process", "--staging-dir", "staging", "--output-dir", "outdir"])
    captured = capsys.readouterr()

    assert json.loads(captured.out)["output_path"] == "outdir"


def test_cli_manifest_with_invalid_extra_token_returns_2(capsys) -> None:
    """CLI rejects extra unrecognized tokens after --manifest via argparse."""
    exit_code = main(["--manifest", "--bogus-flag"])
    capsys.readouterr()
    assert exit_code == 2


def test_cli_unknown_command_returns_2(capsys) -> None:
    """CLI keeps returning exit code 2 for unknown commands."""
    assert main(["--unknown"]) == 2
    capsys.readouterr()

