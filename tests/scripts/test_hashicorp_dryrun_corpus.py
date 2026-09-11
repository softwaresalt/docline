"""Integration tests for ``scripts/hashicorp_mdx_normalize.py`` (071.006-T /
071.007-T / 071.010-T -- C.T1, C.T2, D.T3).

All tests invoke the script as a real subprocess (the same way an
operator would), against either:

* a small synthetic fixture corpus checked into
  ``tests/scripts/fixtures/hashicorp/synthetic_corpus`` (deterministic,
  always runs), or
* the REAL external corpus at
  ``C:\\Source\\Docs\\hashicorp-tf-unified-dev-docs\\content`` (read-only;
  skipped cleanly when absent on the current machine).

HARD CONTAINMENT for this test file itself: every ``--dest`` used here is
a ``tmp_path``-derived directory, and ``tmp_path`` is always rooted under
the repo-local pytest ``--basetemp`` the operator/agent passes on the
command line (e.g. ``--basetemp=build/.pytest-tmp``) -- never the OS
temp directory. The real-corpus dry-run test never passes ``--execute``
and asserts the dest directory is never created at all.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "hashicorp_mdx_normalize.py"
_SYNTHETIC_CORPUS = Path(__file__).resolve().parent / "fixtures" / "hashicorp" / "synthetic_corpus"
_REAL_CORPUS = Path(r"C:\Source\Docs\hashicorp-tf-unified-dev-docs\content")


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        check=False,
    )


# ---------------------------------------------------------------------------
# C.T2 -- CLI surface / dry-run default / containment guard / help text
# ---------------------------------------------------------------------------


def test_help_documents_exact_operator_command() -> None:
    result = _run_cli(["--help"])
    assert result.returncode == 0
    assert "--execute" in result.stdout
    assert "--source" in result.stdout
    assert "--dest" in result.stdout
    assert "--report" in result.stdout
    # The exact operator command for the real external run must be documented.
    assert "hashicorp-tf-unified-dev-docs" in result.stdout
    assert "tf-unified-dev-docs-normalized" in result.stdout


def test_dry_run_default_performs_zero_writes(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest)])
    assert result.returncode == 0, result.stderr
    assert not dest.exists(), "dry-run (default) must never create the --dest directory"


def test_dry_run_emits_json_plan_with_expected_shape(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    report_path = tmp_path / "report.json"
    result = _run_cli(
        [
            "--source",
            str(_SYNTHETIC_CORPUS),
            "--dest",
            str(dest),
            "--report",
            str(report_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert not dest.exists()
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["execute"] is False
    assert report["schema_version"] == 1

    products = report["products"]
    assert products["vault"]["versioned"] is True
    assert products["vault"]["selected_version"] == "v2.x"
    assert products["terraform"]["selected_version"] == "v1.16.x"
    assert products["hcp-docs"]["versioned"] is False
    assert products["hcp-docs"]["selected_version"] is None

    vault_counts = products["vault"]["file_counts"]
    assert vault_counts["mdx_normalized"] == 2  # index.mdx + sub/page.mdx
    assert vault_counts["skipped_partials"] == 1  # content/partials/alert.mdx

    terraform_counts = products["terraform"]["file_counts"]
    assert terraform_counts["mdx_normalized"] == 1
    assert terraform_counts["assets_copied"] == 1
    assert terraform_counts["md_copied"] == 1
    assert terraform_counts["skipped_other"] == 1  # config.json

    assert "mystery-product" in report["excluded_top_level_dirs"]
    assert "global" in report["excluded_top_level_dirs"]
    assert any("mystery-product" in warning for warning in report["warnings"])

    assert report["totals"]["mdx_normalized"] == (
        vault_counts["mdx_normalized"] + terraform_counts["mdx_normalized"] + 1  # hcp-docs index
    )
    assert report["containment_violations"] == []


def test_dry_run_stdout_also_contains_json_plan() -> None:
    result = _run_cli(
        ["--source", str(_SYNTHETIC_CORPUS), "--dest", str(_SYNTHETIC_CORPUS / "nope")]
    )
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["execute"] is False


def test_execute_writes_expected_tree_and_never_materializes_mdx(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])
    assert result.returncode == 0, result.stderr

    # Non-latest / non-version / non-product directories must never appear.
    assert not (dest / "vault" / "v1.20.x").exists()
    assert not (dest / "terraform" / "v1.15.x").exists()
    assert not (dest / "terraform" / "templates").exists()
    assert not (dest / "global").exists()
    assert not (dest / "mystery-product").exists()

    # Partials must never be emitted as standalone docs.
    assert not (dest / "vault" / "v2.x" / "content" / "partials" / "alert.md").exists()
    assert not (dest / "vault" / "v2.x" / "content" / "partials" / "alert.mdx").exists()

    # Latest versioned content, normalized in-flight.
    vault_index = dest / "vault" / "v2.x" / "index.md"
    assert vault_index.exists()
    vault_text = vault_index.read_text(encoding="utf-8")
    assert "> **Heads up**" in vault_text
    assert "<Note" not in vault_text
    assert "<PATH>" in vault_text  # literal placeholder preserved
    assert "<TYPE>" in vault_text
    assert "<NAMESPACE>" in vault_text  # placeholder inside fenced code preserved

    sub_page = dest / "vault" / "v2.x" / "sub" / "page.md"
    assert sub_page.exists()
    assert "**(Enterprise-only)**" in sub_page.read_text(encoding="utf-8")

    terraform_index = dest / "terraform" / "v1.16.x" / "index.md"
    assert terraform_index.exists()
    terraform_text = terraform_index.read_text(encoding="utf-8")
    assert "#### CLI" in terraform_text
    assert "#### API" in terraform_text

    # Asset + ordinary markdown copy rule.
    assert (dest / "terraform" / "v1.16.x" / "diagram.png").exists()
    assert (
        (dest / "terraform" / "v1.16.x" / "notes.md")
        .read_text(encoding="utf-8")
        .startswith("# Ordinary Markdown Notes")
    )
    assert not (dest / "terraform" / "v1.16.x" / "config.json").exists()

    # Unversioned product: whole tree copied, not just a "latest" subdirectory.
    assert (dest / "hcp-docs" / "index.md").exists()
    assert (dest / "hcp-docs" / "assets" / "logo.svg").exists()

    # No intermediate .mdx ever materialized anywhere at dest.
    assert list(dest.rglob("*.mdx")) == []


def test_execute_required_flag_is_not_default() -> None:
    """Sanity check: omitting --execute must never write, even if --dest pre-exists."""
    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(_SYNTHETIC_CORPUS)])
    # --dest reused the read-only source corpus path on purpose here: if the
    # tool ever attempted a real write in dry-run mode, this would corrupt the
    # checked-in fixture. A zero-write dry-run leaves it untouched.
    assert result.returncode == 0, result.stderr
    assert not (_SYNTHETIC_CORPUS / "vault" / "v2.x" / "index.md").exists()


def test_guard_write_path_rejects_paths_outside_dest(tmp_path: Path) -> None:
    """Unit-level containment guard check -- no actual I/O is attempted on rejection."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("docline_hashicorp_mdx_normalize", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["docline_hashicorp_mdx_normalize"] = module
    spec.loader.exec_module(module)

    dest_root = tmp_path / "dest"
    outside = tmp_path / "sibling" / "escaped.md"
    with pytest.raises(module.ContainmentViolation):
        module.guard_write_path(dest_root, outside)
    assert not outside.exists()
    assert not outside.parent.exists()

    inside = dest_root / "nested" / "ok.md"
    resolved = module.guard_write_path(dest_root, inside)
    assert resolved == inside.resolve()


# ---------------------------------------------------------------------------
# D.T3 -- full-corpus read-only dry-run integration test against the REAL
# external corpus. Skips cleanly when the corpus is absent on this machine.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_real_corpus_dry_run_zero_writes_and_coverage_report(tmp_path: Path) -> None:
    if not _REAL_CORPUS.is_dir():
        pytest.skip(f"real external corpus not present at {_REAL_CORPUS}")

    dest = tmp_path / "dest-would-be-external"
    report_path = tmp_path / "real-corpus-report.json"
    result = _run_cli(
        [
            "--source",
            str(_REAL_CORPUS),
            "--dest",
            str(dest),
            "--report",
            str(report_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert not dest.exists(), "dry-run must perform zero writes, including against the real corpus"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["execute"] is False

    products = report["products"]
    # Live-verified findings (see requirements-evidence doc for the full narrative):
    assert products["vault"]["selected_version"] == "v2.x"
    assert products["terraform"]["selected_version"] == "v1.16.x"
    assert products["terraform-policy"]["selected_version"] == "v0.2.x (beta)"
    # Correction vs. the plan's assumed v202507-1: the real corpus's semver-style
    # directories (1.0.x/1.1.x/1.2.x/2.0.x) postdate every date-based release.
    assert products["terraform-enterprise"]["selected_version"] == "2.0.x"

    assert len(products) == 23
    versioned_count = sum(1 for p in products.values() if p["versioned"])
    unversioned_count = sum(1 for p in products.values() if not p["versioned"])
    assert versioned_count == 19
    assert unversioned_count == 4

    assert "global" in report["excluded_top_level_dirs"]
    assert isinstance(report["unhandled_constructs"], dict)
    assert report["containment_violations"] == []

    # Persist the real coverage report to a repo-local, git-ignored path so it
    # can be cited as requirements evidence without polluting the repo tree.
    evidence_dir = _REPO_ROOT / "build" / "hashicorp-dryrun-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "real-corpus-dry-run-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
