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
    # P1 regression (review-fix cycle 1): dry-run must NEVER write the
    # report file, even when --report is supplied. The plan is only ever
    # available on stdout in dry-run mode.
    assert not report_path.exists()
    assert "ignored in dry-run mode" in result.stderr
    report = json.loads(result.stdout)

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
    # P2 regression (review-fix cycle 1): config.json is no longer silently
    # dropped -- it is copied byte-for-byte and reported as such.
    assert terraform_counts["generic_copied"] == 1

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
    # P2 regression (review-fix cycle 1): generic non-md/image files (JSON
    # data, PDFs, videos, etc.) are copied byte-for-byte, not dropped.
    dest_config = dest / "terraform" / "v1.16.x" / "config.json"
    assert dest_config.exists()
    source_config = _SYNTHETIC_CORPUS / "terraform" / "v1.16.x" / "config.json"
    assert dest_config.read_bytes() == source_config.read_bytes()

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


# ---------------------------------------------------------------------------
# P1/P2 regressions (review-fix cycle 1): report containment + non-empty
# --dest rejection under --execute
# ---------------------------------------------------------------------------


def test_execute_rejects_non_empty_existing_dest(tmp_path: Path) -> None:
    """P1 regression: execute must fail closed against a pre-existing,
    non-empty --dest rather than overlaying it (which would leave stale
    versions/files behind). No deletion/replacement logic is implemented --
    the run simply refuses to proceed."""
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "stale-leftover.txt").write_text("stale", encoding="utf-8")

    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])
    assert result.returncode != 0
    assert "not empty" in result.stderr
    # Nothing new was written; the stale file is untouched and no product
    # trees were created.
    assert list(dest.iterdir()) == [dest / "stale-leftover.txt"]
    assert not (dest / "vault").exists()


def test_execute_succeeds_against_existing_empty_dest(tmp_path: Path) -> None:
    """An existing but EMPTY --dest is a valid execute target (not just an
    absent one)."""
    dest = tmp_path / "dest"
    dest.mkdir()

    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])
    assert result.returncode == 0, result.stderr
    assert (dest / "vault" / "v2.x" / "index.md").exists()


def test_dry_run_may_point_dest_at_a_non_empty_directory_without_creating_it(
    tmp_path: Path,
) -> None:
    """Dry-run is exempt from the non-empty --dest check entirely: it may
    point anywhere, including a pre-existing non-empty directory, without
    ever creating or touching it."""
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "pre-existing.txt").write_text("pre-existing", encoding="utf-8")

    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest)])
    assert result.returncode == 0, result.stderr
    assert list(dest.iterdir()) == [dest / "pre-existing.txt"]


def test_execute_report_guarded_under_dest_succeeds(tmp_path: Path) -> None:
    """P1: in --execute mode, a --report path resolving INSIDE --dest is
    written normally, guarded by the same containment check as every other
    write."""
    dest = tmp_path / "dest"
    report_path = dest / "_normalize-report.json"

    result = _run_cli(
        [
            "--source",
            str(_SYNTHETIC_CORPUS),
            "--dest",
            str(dest),
            "--execute",
            "--report",
            str(report_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["execute"] is True


def test_execute_report_outside_dest_fails_closed_before_any_corpus_write(
    tmp_path: Path,
) -> None:
    """P1 regression: a --report path resolving OUTSIDE --dest in --execute
    mode must fail closed with a containment violation BEFORE any corpus
    write begins -- --dest must never even be created."""
    dest = tmp_path / "dest"
    outside_report = tmp_path / "sibling" / "report.json"

    result = _run_cli(
        [
            "--source",
            str(_SYNTHETIC_CORPUS),
            "--dest",
            str(dest),
            "--execute",
            "--report",
            str(outside_report),
        ]
    )
    assert result.returncode != 0
    assert "containment violation" in result.stderr
    assert not outside_report.exists()
    assert not dest.exists(), "no corpus write may occur when the report path is rejected"


# ---------------------------------------------------------------------------
# P2 regression (review-fix cycle 1, finding 5): execute fails closed on
# genuine unresolved MDX components unless explicitly overridden
# ---------------------------------------------------------------------------


def _write_unresolved_construct_source(root: Path) -> Path:
    """Build a tiny unversioned-product source tree with one genuinely
    unresolved (bare, non-self-closing, non-paired, non-registry) MDX-shaped
    tag, using a recognized unversioned product name (``hcp-docs``)."""
    product_dir = root / "hcp-docs"
    product_dir.mkdir(parents=True)
    (product_dir / "index.mdx").write_text(
        "---\npage_title: Unresolved Example\n---\n"
        "This mentions <BrandNewWidget> which nothing understands.\n",
        encoding="utf-8",
    )
    return root


def test_execute_fails_closed_when_unresolved_mdx_constructs_remain(tmp_path: Path) -> None:
    source = _write_unresolved_construct_source(tmp_path / "source")
    dest = tmp_path / "dest"

    result = _run_cli(["--source", str(source), "--dest", str(dest), "--execute"])
    assert result.returncode != 0
    assert "unresolved" in result.stderr.lower()
    assert "BrandNewWidget" in result.stderr


def test_execute_succeeds_with_explicit_allow_unresolved_mdx_override(tmp_path: Path) -> None:
    source = _write_unresolved_construct_source(tmp_path / "source")
    dest = tmp_path / "dest"

    result = _run_cli(
        ["--source", str(source), "--dest", str(dest), "--execute", "--allow-unresolved-mdx"]
    )
    assert result.returncode == 0, result.stderr
    assert (dest / "hcp-docs" / "index.md").exists()
    assert "<BrandNewWidget>" in (dest / "hcp-docs" / "index.md").read_text(encoding="utf-8")


def test_dry_run_never_fails_on_unresolved_mdx_constructs(tmp_path: Path) -> None:
    source = _write_unresolved_construct_source(tmp_path / "source")
    dest = tmp_path / "dest"

    result = _run_cli(["--source", str(source), "--dest", str(dest)])
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["unresolved_constructs"]["BrandNewWidget"] == 1


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
    # P1 regression (review-fix cycle 1): dry-run never writes the --report
    # file either -- the JSON plan is only ever available on stdout.
    assert not report_path.exists()

    report = json.loads(result.stdout)
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
    assert isinstance(report["fallback_constructs"], dict)
    assert isinstance(report["ambiguous_tokens"], dict)
    assert isinstance(report["unresolved_constructs"], dict)
    assert report["containment_violations"] == []

    # Persist the real coverage report to a repo-local, git-ignored path so it
    # can be cited as requirements evidence without polluting the repo tree.
    evidence_dir = _REPO_ROOT / "build" / "hashicorp-dryrun-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "real-corpus-dry-run-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
