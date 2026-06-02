"""Tests for CLI fetch and process adapters."""

import json

from docline.cli import main


def test_cli_fetch_valid_config_reports_staging_jobs(capsys, monkeypatch, tmp_path) -> None:
    """CLI fetch reports staged jobs for discovered ELT configs."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".elt" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "source.yaml").write_text(
        "type: web_crawl\nurl: https://example.com\n",
        encoding="utf-8",
    )

    exit_code = main(["fetch"])
    captured = capsys.readouterr()

    payload = json.loads(captured.out)

    assert exit_code == 0
    assert len(payload) == 1
    assert payload[0]["metadata"]["source"] == "web_crawl:https://example.com"


def test_cli_fetch_result_json_is_a_job_list(capsys, monkeypatch, tmp_path) -> None:
    """CLI fetch outputs a JSON list of staging jobs."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".elt" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "source.yaml").write_text(
        "type: web_crawl\nurl: https://example.com\n",
        encoding="utf-8",
    )

    main(["fetch"])
    captured = capsys.readouterr()

    assert isinstance(json.loads(captured.out), list)


def test_cli_fetch_missing_config_dir_returns_1(capsys, monkeypatch, tmp_path) -> None:
    """CLI fetch returns exit code 1 when the default config dir is missing."""
    monkeypatch.chdir(tmp_path)

    exit_code = main(["fetch"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "ELT config directory not found" in captured.err


def test_cli_fetch_empty_config_dir_returns_1(capsys, monkeypatch, tmp_path) -> None:
    """CLI fetch returns exit code 1 when the config dir is empty."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".elt" / "config").mkdir(parents=True)

    assert main(["fetch"]) == 1
    captured = capsys.readouterr()

    assert "contains no source configs" in captured.err


def test_cli_process_with_existing_staging_dir_succeeds_when_empty(
    capsys, monkeypatch, tmp_path
) -> None:
    """CLI process succeeds with an empty staging directory."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()

    exit_code = main(["process", "--staging-dir", "staging"])
    captured = capsys.readouterr()

    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["error"] is None


def test_cli_process_missing_staging_dir_returns_1(capsys) -> None:
    """CLI process fails when the staging directory does not exist."""
    exit_code = main(["process", "--staging-dir", "missing-staging"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out)["success"] is False


def test_cli_fetch_custom_config_dir_reports_staging_jobs(capsys, monkeypatch, tmp_path) -> None:
    """CLI fetch can read configs from a custom directory."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "source.yaml").write_text(
        "type: github_repo\nrepo_url: https://github.com/org/repo\n",
        encoding="utf-8",
    )

    exit_code = main(["fetch", "--config-dir", "configs"])
    captured = capsys.readouterr()

    payload = json.loads(captured.out)

    assert exit_code == 0
    assert (
        payload[0]["metadata"]["source"] == "github_repo:https://github.com/org/repo@main:**/*.md"
    )


def test_cli_fetch_invalid_staging_dir_returns_1(capsys) -> None:
    """CLI fetch rejects unsafe staging directories."""
    assert main(["fetch", "--staging-dir", "../out"]) == 1
    captured = capsys.readouterr()

    assert "must not contain parent-directory traversal" in captured.err


def test_cli_process_result_json_has_output_path_when_staging_is_empty(
    capsys, monkeypatch, tmp_path
) -> None:
    """CLI process JSON output includes output_path when staging succeeds."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()

    main(["process", "--staging-dir", "staging", "--output-dir", "outdir"])
    captured = capsys.readouterr()

    payload = json.loads(captured.out)

    assert payload["output_path"] == "outdir"
    assert payload["error"] is None


def test_cli_manifest_with_invalid_extra_token_returns_2(capsys) -> None:
    """CLI rejects extra unrecognized tokens after --manifest via argparse."""
    exit_code = main(["--manifest", "--bogus-flag"])
    capsys.readouterr()
    assert exit_code == 2


def test_cli_manifest_with_fetch_subcommand_returns_2(capsys) -> None:
    """CLI rejects mixing --manifest with a subcommand invocation."""
    exit_code = main(["--manifest", "fetch"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "--manifest" in captured.err


def test_cli_manifest_with_process_subcommand_returns_2(capsys) -> None:
    """CLI rejects mixing --manifest with process subcommand usage."""
    exit_code = main(["--manifest", "process"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "--manifest" in captured.err


def test_cli_unknown_command_returns_2(capsys) -> None:
    """CLI keeps returning exit code 2 for unknown commands."""
    assert main(["--unknown"]) == 2
    capsys.readouterr()
